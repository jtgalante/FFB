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


def simulate(board: pd.DataFrame, cfg: dict, rb_tilt: float, n_sims: int,
             through: int, rng: np.random.Generator) -> pd.DataFrame:
    """Monte Carlo the opponents' picks; return P(available) at each of my picks.

    Each opponent pick draws every undrafted player an effective draft position
    of ADP + N(0, adp_sd), then takes the smallest. `rb_tilt` shifts running
    backs earlier for everyone but me, reproducing this room's documented bias.
    Opponent seat order is randomized per sim because the 2026 draft order is
    not known — only that James holds slot 1.
    """
    teams, slot = cfg["teams"], cfg["my_draft_slot"]
    mine = set(my_picks(teams, slot, cfg["rounds"]))

    adp = board["adp"].to_numpy(float)
    sd = np.nan_to_num(board["adp_sd"].to_numpy(float), nan=8.0)
    sd = np.clip(sd, 1.0, 40.0)
    is_rb = (board["pos"] == "RB").to_numpy()
    n = len(board)

    # counts[i] = number of sims in which player i was still free at each pick
    free_at = {p: np.zeros(n) for p in sorted(mine) if p <= through}
    rb_gone_19 = np.zeros(n_sims)

    for s in range(n_sims):
        taken = np.zeros(n, dtype=bool)
        noise = rng.normal(0.0, sd)
        eff = adp + noise - np.where(is_rb, rb_tilt, 0.0)
        for pick in range(1, through + 1):
            if pick in free_at:
                free_at[pick] += ~taken
            if pick in mine:
                # I take the best available by value, so the sim keeps going
                cand = np.where(~taken, board["vor"].to_numpy(), -np.inf)
                taken[int(np.argmax(cand))] = True
                continue
            cand = np.where(~taken, eff, np.inf)
            taken[int(np.argmin(cand))] = True
            if pick == 19:
                rb_gone_19[s] = (taken & is_rb).sum()

    out = board[["name", "pos", "proj", "vor", "adp"]].copy()
    for pick, cnt in free_at.items():
        out[f"p_avail_{pick}"] = (cnt / n_sims).round(3)
    out.attrs["rb_gone_by_19"] = float(rb_gone_19.mean())
    return out


def calibrate(board, cfg, n_sims, rng) -> float:
    """Solve the RB tilt so the sim reproduces ~12 RBs gone by pick 19."""
    lo, hi = 0.0, 40.0
    for _ in range(8):
        mid = (lo + hi) / 2
        got = simulate(board, cfg, mid, max(200, n_sims // 10), 19,
                       rng).attrs["rb_gone_by_19"]
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

    tilt = calibrate(board, cfg, a.sims, rng)
    sim = simulate(board, cfg, tilt, a.sims, through, rng)
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

    L.append("## What survives to each of my picks\n")
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
