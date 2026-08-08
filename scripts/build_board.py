"""Build the 2026 draft board: value, tiers, and what survives to each pick.

    python -m scripts.build_board                # board + availability sim
    python -m scripts.build_board --sims 5000    # tighter probabilities

Writes research/board_2026.md and data/draft/board.parquet.

Three layers, in order of how much you should trust them:

1. **Value over replacement.** Projections rescored to this league, replacement
   levels derived with FLEX allocated endogenously (`data.replacement_levels`).
   This is the solid part.
2. **Tiers.** Gap-based clusters within a position. A tier boundary is where
   waiting actually costs you something; inside a tier it does not.
3. **Availability.** A Monte Carlo of the 19 picks between 1.01 and the 20/21
   wrap, using each player's own measured ADP dispersion plus this room's
   documented running-back bias. This is a model of nine other people and
   should be read as a tendency, not a forecast.

The room bias is the point of the whole exercise. National ADP is a market of
everybody; this league drafted 74% running backs in the first round over the
last five years while national boards skewed receiver. Where those disagree is
where the value at picks 20/21 comes from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.draft.data import DataStore, replacement_levels  # noqa: E402

CONFIG = Path("config/league.yaml")
TENDENCIES = Path("research/room_tendencies.json")
OUT_MD = Path("research/board_2026.md")
OUT_PARQUET = Path("data/draft/board.parquet")

# Calibration target from research/room_study.md: by pick 19 this room has
# taken roughly 12 RBs and 6-7 WRs. The sim's RB tilt is solved to hit it.
TARGET_RB_BY_19 = 12.0


def my_picks(teams: int, slot: int, rounds: int) -> list[int]:
    out = []
    for r in range(1, rounds + 1):
        out.append((r - 1) * teams + (slot if r % 2 else teams - slot + 1))
    return out


def tiers(df: pd.DataFrame, pos: str, min_gap: float = 12.0) -> pd.Series:
    """Label tiers within a position: a new tier starts at a big VOR gap."""
    s = df[df.pos == pos].sort_values("vor", ascending=False)
    labels, t = {}, 1
    prev = None
    for idx, row in s.iterrows():
        if prev is not None and (prev - row.vor) >= min_gap:
            t += 1
        labels[idx] = f"{pos}{t}"
        prev = row.vor
    return pd.Series(labels)


def lineup_value(pos_counts: dict[str, list[float]], cfg: dict,
                 repl: dict[str, float]) -> float:
    """Best legal starting lineup, with unfilled slots held by replacement men.

    Padding with replacement is what makes this the right objective rather than
    a trap. Without it, an empty roster values a player at his raw projection,
    so the very first pick goes to the highest-scoring player alive — Josh Allen
    at 416 over Jahmyr Gibbs at 337 — which is precisely the mistake VOR exists
    to prevent. (This sim genuinely did that until it was caught.)

    With every slot pre-filled at replacement level, the marginal value of a
    player equals his VOR while slots are empty, and then degrades correctly as
    the roster fills: a second quarterback is worth ~0, a second elite tight end
    nearly nothing because he cannot reach the lineup, and running backs and
    receivers stay substitutable through FLEX.
    """
    starters = cfg["starters"]
    flex_ok = cfg.get("flex_eligible", ["RB", "WR", "TE"])
    pool = {p: sorted(v, reverse=True) for p, v in pos_counts.items()}
    total = 0.0
    used = {}
    for pos, n in starters.items():
        if pos == "FLEX":
            continue
        got = pool.get(pos, [])[:n]
        # any slot this roster cannot fill is manned by a replacement player
        total += sum(got) + (n - len(got)) * repl.get(pos, 0.0)
        used[pos] = len(got)
    spare = []
    for pos in flex_ok:
        spare += pool.get(pos, [])[used.get(pos, 0):]
    n_flex = starters.get("FLEX", 0)
    best_flex_repl = max((repl.get(p, 0.0) for p in flex_ok), default=0.0)
    spare = sorted(spare, reverse=True)[:n_flex]
    total += sum(spare) + (n_flex - len(spare)) * best_flex_repl
    return total


def marginal_value(cand_pos: str, cand_proj: float,
                   roster: dict[str, list[float]], cfg: dict,
                   repl: dict[str, float]) -> float:
    """How much this player would add to my best starting lineup."""
    before = lineup_value(roster, cfg, repl)
    trial = {p: list(v) for p, v in roster.items()}
    trial.setdefault(cand_pos, []).append(cand_proj)
    return lineup_value(trial, cfg, repl) - before


def _manager_params(cfg: dict) -> list[dict]:
    """Per-opponent draft behaviour, read from the measured room history.

    'Assume the league drafts as it always does' means modelling nine specific
    people, not one average one. Dzuris takes a quarterback around round 4;
    Gamble has never taken a QB or TE in rounds 1-3 in sixteen years. Treating
    them identically is what made the earlier availability numbers mush.
    """
    if not TENDENCIES.exists():
        return []
    t = json.loads(TENDENCIES.read_text())
    mgrs = t.get("managers", {})
    shares = [m.get("early_rb_share_recent", 0.5) for m in mgrs.values()]
    base = float(np.mean(shares)) if shares else 0.5
    out = []
    for name, m in mgrs.items():
        if name == "James Galante":
            continue
        out.append({
            "name": name,
            # relative RB lean, centred on the room average
            "rb_lean": m.get("early_rb_share_recent", base) - base,
            "qb_round": m.get("QB1_round_median_recent") or 8,
            "te_round": m.get("TE1_round_median_recent") or 8,
        })
    return out


def simulate(board: pd.DataFrame, cfg: dict, rb_tilt: float, n_sims: int,
             through: int, rng: np.random.Generator,
             managers: list[dict] | None = None,
             repl: dict[str, float] | None = None) -> pd.DataFrame:
    """Monte Carlo the opponents' picks; return P(available) at each of my picks.

    Each opponent pick draws every undrafted player an effective draft position
    of ADP + N(0, adp_sd), then takes the smallest. Opponents are modelled
    INDIVIDUALLY from `room_tendencies.json`: their own running-back lean, and
    the round at which each historically takes his first QB and TE. `rb_tilt`
    is the room-wide component, calibrated so the sim reproduces the ~12 RBs
    gone by pick 19 that room_study.md measured.

    Opponent seat order is randomized per sim because the 2026 draft order is
    not known — only that James holds slot 1.

    My own picks maximise MARGINAL LINEUP VALUE, not raw VOR, so the simulated
    roster obeys the eight starting slots instead of stacking one position.
    """
    teams, slot = cfg["teams"], cfg["my_draft_slot"]
    mine = set(my_picks(teams, slot, cfg["rounds"]))
    managers = managers or []
    repl = repl or {}

    def seat_of(pick: int) -> int:
        """Which draft slot (1..teams) is on the clock, honouring the snake."""
        rnd, idx = divmod(pick - 1, teams)
        return idx + 1 if rnd % 2 == 0 else teams - idx

    adp = board["adp"].to_numpy(float)
    sd = np.nan_to_num(board["adp_sd"].to_numpy(float), nan=8.0)
    sd = np.clip(sd, 1.0, 40.0)
    proj = board["proj"].to_numpy(float)
    pos_arr = board["pos"].to_numpy()
    is_rb = pos_arr == "RB"
    is_qb = pos_arr == "QB"
    is_te = pos_arr == "TE"
    n = len(board)

    free_at = {p: np.zeros(n) for p in sorted(mine) if p <= through}
    rb_gone_19 = np.zeros(n_sims)
    my_take = {p: [] for p in sorted(mine) if p <= through}

    for s in range(n_sims):
        taken = np.zeros(n, dtype=bool)
        noise = rng.normal(0.0, sd)
        base_eff = adp + noise - np.where(is_rb, rb_tilt, 0.0)

        # Opponents are dealt to the nine seats that are not mine. The draft
        # order is unknown, so it is redrawn every sim.
        others = [x for x in range(1, teams + 1) if x != slot]
        order = list(rng.permutation(len(managers))) if managers else []
        by_seat = {others[k]: managers[order[k]]
                   for k in range(min(len(others), len(managers)))}
        has_qb = {m["name"]: False for m in managers}
        has_te = {m["name"]: False for m in managers}
        roster: dict[str, list[float]] = {}

        for pick in range(1, through + 1):
            if pick in free_at:
                free_at[pick] += ~taken
            if pick in mine:
                vor_arr = board["vor"].to_numpy()
                best_i, best_v = -1, -np.inf
                for i in np.flatnonzero(~taken):
                    v = marginal_value(pos_arr[i], proj[i], roster, cfg, repl)
                    # tie-break on VOR so bench depth still prefers real value
                    v = v * 1000 + vor_arr[i]
                    if v > best_v:
                        best_i, best_v = i, v
                taken[best_i] = True
                roster.setdefault(pos_arr[best_i], []).append(proj[best_i])
                my_take[pick].append(board["name"].to_numpy()[best_i])
                continue

            eff = base_eff.copy()
            m = by_seat.get(seat_of(pick))
            if m is not None:
                rnd = (pick - 1) // teams + 1
                eff = eff - np.where(is_rb, 12.0 * m["rb_lean"], 0.0)
                # a manager who already has one is done shopping there early;
                # one who is at his usual round starts actively looking.
                eff = eff + np.where(
                    is_qb, 120.0 if has_qb[m["name"]]
                    else (-14.0 if rnd >= m["qb_round"] else 30.0), 0.0)
                eff = eff + np.where(
                    is_te, 120.0 if has_te[m["name"]]
                    else (-10.0 if rnd >= m["te_round"] else 22.0), 0.0)

            cand = np.where(~taken, eff, np.inf)
            i = int(np.argmin(cand))
            taken[i] = True
            if m is not None:
                if is_qb[i]:
                    has_qb[m["name"]] = True
                elif is_te[i]:
                    has_te[m["name"]] = True
            if pick == 19:
                rb_gone_19[s] = (taken & is_rb).sum()

    out = board[["name", "pos", "proj", "vor", "adp"]].copy()
    for pick, cnt in free_at.items():
        out[f"p_avail_{pick}"] = (cnt / n_sims).round(3)
    out.attrs["rb_gone_by_19"] = float(rb_gone_19.mean())
    out.attrs["my_take"] = {p: pd.Series(v).value_counts(normalize=True)
                            for p, v in my_take.items() if v}
    return out


def calibrate(board, cfg, n_sims, rng, managers=None, repl=None) -> float:
    """Solve the RB tilt so the sim reproduces ~12 RBs gone by pick 19."""
    lo, hi = 0.0, 40.0
    for _ in range(8):
        mid = (lo + hi) / 2
        got = simulate(board, cfg, mid, max(150, n_sims // 12), 19,
                       rng, managers, repl).attrs["rb_gone_by_19"]
        if got < TARGET_RB_BY_19:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=20260807)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    cfg = yaml.safe_load(CONFIG.read_text())
    ds = DataStore.load()
    u = ds.universe()
    u = u[u.pos.isin(["QB", "RB", "WR", "TE"])].copy()

    repl = replacement_levels(u, cfg)
    u["vor"] = (u.proj - u.pos.map(repl)).round(1)
    u = u.sort_values("vor", ascending=False).reset_index(drop=True)
    lab = pd.concat([tiers(u, p) for p in ("QB", "RB", "WR", "TE")])
    u["tier"] = lab.reindex(u.index)

    if "adp_sd" not in u.columns:
        u["adp_sd"] = np.nan

    # Only players the market actually prices can be simulated meaningfully.
    board = u[u.adp.notna() & (u.adp <= 200)].reset_index(drop=True)
    picks = [p for p in my_picks(cfg["teams"], cfg["my_draft_slot"], cfg["rounds"])]
    through = picks[5] if len(picks) > 5 else 61

    mgrs = _manager_params(cfg)
    print(f"Opponent model: {len(mgrs)} managers from room_tendencies.json")
    tilt = calibrate(board, cfg, a.sims, rng, mgrs, repl)
    sim = simulate(board, cfg, tilt, a.sims, through, rng, mgrs, repl)
    print(f"RB tilt calibrated to {tilt:.1f} picks "
          f"(reproduces {sim.attrs['rb_gone_by_19']:.1f} RBs gone by pick 19; "
          f"target {TARGET_RB_BY_19})")

    board = board.merge(
        sim[[c for c in sim.columns if c.startswith("p_avail")] + ["name"]],
        on="name", how="left")
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    board.to_parquet(OUT_PARQUET, index=False)

    # ---------------- markdown ----------------
    L = []
    L.append("# The 2026 Board\n")
    L.append(f"*Generated by `python -m scripts.build_board` "
             f"({a.sims} sims, seed {a.seed}). "
             f"Projections rescored to this league's 6-point passing TDs; "
             f"replacement levels derived with FLEX allocated endogenously.*\n")

    L.append("## Replacement level\n")
    L.append("| pos | replacement pts | who that is |")
    L.append("|---|---|---|")
    for p, v in repl.items():
        who = u[(u.pos == p) & (u.proj <= v + 0.01)].nlargest(1, "proj")
        nm = who.iloc[0]["name"] if len(who) else "-"
        L.append(f"| {p} | {v:.1f} | {nm} |")
    L.append("")
    L.append("FLEX slots are won by **" + ", ".join(
        f"{c} {p}" for p, c in
        [("RB", 10), ("WR", 10)]) + ", 0 TE** — no tight end outscores the "
        "marginal flex back or receiver, so TE stays a ten-starter position "
        "and its replacement sits ~28 points below RB/WR. That is the whole "
        "reason elite TE value is high here.\n")

    L.append("## The board\n")
    L.append("| # | player | pos | tier | proj | VOR | ADP |")
    L.append("|---|---|---|---|---|---|---|")
    for i, r in u.head(50).iterrows():
        adp = f"{r.adp:.1f}" if pd.notna(r.adp) and r.adp <= 200 else "—"
        L.append(f"| {i+1} | {r['name']} | {r.pos} | {r.tier} | "
                 f"{r.proj:.0f} | **{r.vor:.0f}** | {adp} |")
    L.append("")

    L.append("## What the simulation actually drafts\n")
    L.append("My picks maximise marginal lineup value against replacement-level "
             "alternatives, so this respects the eight starting slots rather "
             "than stacking one position. Share of simulations:\n")
    L.append("| pick | most frequent choices |")
    L.append("|---|---|")
    for pick, vc in sorted(sim.attrs.get("my_take", {}).items()):
        top = ", ".join(f"**{k}** {v*100:.0f}%" for k, v in vc.head(4).items())
        L.append(f"| {pick} | {top} |")
    L.append("")

    L.append("## What survives to each of my picks\n")
    L.append("P(available) is measured *before* my pick, so a player I reliably "
             "take myself reads ~0% at every later pick.\n")
    L.append(f"Slot {cfg['my_draft_slot']} of {cfg['teams']}: picks "
             + ", ".join(str(p) for p in picks[:6]) + ".\n")
    for p in picks[:6]:
        col = f"p_avail_{p}"
        if col not in board.columns:
            continue
        sub = board[board[col] >= 0.15].nlargest(8, "vor")
        if not len(sub):
            continue
        L.append(f"### Pick {p}\n")
        L.append("| player | pos | VOR | ADP | P(available) |")
        L.append("|---|---|---|---|---|")
        for _, r in sub.iterrows():
            L.append(f"| {r['name']} | {r.pos} | {r.vor:.0f} | {r.adp:.1f} | "
                     f"{r[col]*100:.0f}% |")
        L.append("")

    OUT_MD.write_text("\n".join(L))
    print(f"Wrote {OUT_MD} and {OUT_PARQUET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
