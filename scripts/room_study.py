"""16-year draft tendency study of the league room (2010-2025).

Reads the committed league caches (data/draft_cache.json, data/espn_cache.json,
data/sleeper_cache.json), canonicalizes manager names across platforms, and
produces:

  research/room_study_tables.md   generated tables (this script's output)
  research/room_tendencies.json   per-manager parameters for the draft
                                  simulator's opponent model

Eras (rules changed over the years):
  2010-2012: 16 rounds, K + DST drafted
  2013-2023: 15 rounds, DST no K
  2024-2025: Sleeper, no K/DST (14 rounds in 2024, 15 in 2025)

All cross-era comparisons are made within-year (position rank at pick,
round-relative-to-room-median) so rule changes don't pollute tendencies.

Usage: python -m scripts.room_study
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median, mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_canonical_name  # noqa: E402

DRAFT_CACHE = Path("data/draft_cache.json")
ESPN_CACHE = Path("data/espn_cache.json")
SLEEPER_CACHE = Path("data/sleeper_cache.json")
OUT_TABLES = Path("research/room_study_tables.md")
OUT_JSON = Path("research/room_tendencies.json")

CORE_POS = ("QB", "RB", "WR", "TE")
RECENT = range(2021, 2026)          # last 5 drafts
ALL_YEARS = range(2010, 2026)

FIRST = "James Galante"             # the user; everyone else is an opponent


def load_picks() -> list[dict]:
    picks = json.loads(DRAFT_CACHE.read_text())["drafts"]
    for p in picks:
        p["mgr"] = get_canonical_name(p["platform"], p["manager"])
    picks.sort(key=lambda p: (p["season"], p["pick"]))
    # Position rank at pick: nth player of that position off the board.
    counters: dict[tuple, int] = defaultdict(int)
    for p in picks:
        key = (p["season"], p["position"])
        counters[key] += 1
        p["pos_rank"] = counters[key]
    return picks


def espn_recorded_champion_for(outcomes: list[dict], season: int) -> str | None:
    """What the platform cache claims — kept only to show where it is wrong."""
    for r in outcomes:
        if r["season"] == season and r["finish"] == 1:
            return r["mgr"]
    return None


def load_verified_history() -> dict[int, dict]:
    """Champions from config/history.yaml — the only trustworthy source.

    See that file for why the platform caches cannot be used.
    """
    import yaml
    path = Path("config/history.yaml")
    if not path.exists():
        raise FileNotFoundError(
            "config/history.yaml missing. Run: python -m scripts.rebuild_standings --write")
    return (yaml.safe_load(path.read_text()) or {}).get("seasons", {})


def load_true_standings() -> dict[int, list[dict]]:
    """Regular-season standings recomputed under the league's real
    dual-points system (1 pt per matchup win + 1 pt per weekly top-5 score)."""
    from scripts.rebuild_standings import load_weekly, standings, scoring_system
    weekly = load_weekly()
    return {season: standings(rows, dual_points=scoring_system(season) == "dual_points")
            for season, rows in weekly.items()}


def load_outcomes() -> list[dict]:
    """Season summaries with 2024-25 champion resolved from the week-17
    playoff matchup (the cached finish field double-codes '1' those years)."""
    es = json.loads(ESPN_CACHE.read_text())["summaries"]
    sl = json.loads(SLEEPER_CACHE.read_text())
    rows = []
    for r in es:
        if r["finish"] > 0:  # espn cache holds placeholder rows for 2024-25
            rows.append({**r, "mgr": get_canonical_name("espn", r["manager"])})
    # Resolve Sleeper-era champions: winner of the week-17 game involving the
    # bracket runner-up (the unique finish=2 team).
    runner_up = {r["season"]: r["manager"] for r in sl["summaries"] if r["finish"] == 2}
    champs = {}
    for w in sl["weekly"]:
        yr = w["season"]
        if w["week"] == 17 and w.get("is_playoff") and yr in runner_up:
            if w["manager"] == runner_up[yr] and not w["win"]:
                pass  # runner-up losing the final; champion is the opponent row
            if w["win"] and w["manager"] != runner_up[yr]:
                # did this winner play the runner-up?
                pass
    # Simpler: find runner-up's week-17 opponent via matching scores.
    by_year_week = defaultdict(list)
    for w in sl["weekly"]:
        if w["week"] == 17:
            by_year_week[w["season"]].append(w)
    for yr, games in by_year_week.items():
        ru = runner_up.get(yr)
        ru_row = next((g for g in games if g["manager"] == ru), None)
        if ru_row is None:
            continue
        opp = next((g for g in games if g["manager"] != ru
                    and abs(g["points"] - ru_row["opponent_points"]) < 0.01
                    and abs(g["opponent_points"] - ru_row["points"]) < 0.01), None)
        if opp is not None:
            champs[yr] = opp["manager"]
    for r in sl["summaries"]:
        mgr = get_canonical_name("sleeper", r["manager"])
        finish = r["finish"]
        if r["season"] in champs:
            is_champ = r["manager"] == champs[r["season"]]
            if finish == 1 and not is_champ:
                finish = 3  # was seed-1 fallback, not the title winner
            elif is_champ:
                finish = 1
        rows.append({**r, "mgr": mgr, "finish": finish})
    return rows


def draft_slots(picks) -> dict[tuple, int]:
    """(season, mgr) -> draft slot, from round-1 pick order."""
    slots = {}
    for p in picks:
        if p["round"] == 1:
            slots[(p["season"], p["mgr"])] = p["pick"]
    return slots


def first_pos_round(picks, mgr, season, pos, nth=1):
    taken = [p for p in picks
             if p["mgr"] == mgr and p["season"] == season and p["position"] == pos]
    return (taken[nth - 1]["round"], taken[nth - 1]["pos_rank"]) if len(taken) >= nth else (None, None)


def run_analysis(picks) -> dict:
    """Position-run behavior: how often a pick continues a live run
    (previous 2+ picks same position), overall and per manager."""
    stats = {m: {"opps": 0, "joins": 0} for m in {p["mgr"] for p in picks}}
    room = {"opps": 0, "joins": 0}
    for season in ALL_YEARS:
        seq = [p for p in picks if p["season"] == season]
        for i in range(2, len(seq)):
            a, b, cur = seq[i - 2], seq[i - 1], seq[i]
            if a["position"] == b["position"] and a["position"] in CORE_POS:
                pos = a["position"]
                # only count as an opportunity where joining is plausible (early-mid draft)
                if cur["round"] > 10:
                    continue
                stats[cur["mgr"]]["opps"] += 1
                room["opps"] += 1
                if cur["position"] == pos:
                    stats[cur["mgr"]]["joins"] += 1
                    room["joins"] += 1
    return {"room": room, "managers": stats}


def loyalty(picks) -> dict:
    """Year-over-year rebuy: if a manager drafted player X last year and X is
    drafted again this year, how often is it the same manager who takes him?"""
    by_year_player = defaultdict(dict)   # season -> key -> mgr
    for p in picks:
        by_year_player[p["season"]][p["player_name"].lower()] = p["mgr"]
    retained = defaultdict(int)
    chances = defaultdict(int)
    repeats = defaultdict(lambda: defaultdict(int))
    for p in picks:
        prev = by_year_player.get(p["season"] - 1, {})
        key = p["player_name"].lower()
        if key in prev:
            chances[prev[key]] += 1
            if prev[key] == p["mgr"]:
                retained[p["mgr"]] += 1
        repeats[p["mgr"]][key] += 1
    top_repeats = {m: sorted(((n, k) for k, n in d.items() if n >= 4), reverse=True)[:5]
                   for m, d in repeats.items()}
    return {"retained": dict(retained), "chances": dict(chances),
            "top_repeats": top_repeats}


def fmt_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def main():
    picks = load_picks()
    outcomes = load_outcomes()
    slots = draft_slots(picks)
    managers = sorted({p["mgr"] for p in picks})
    md = ["# Room study tables (generated by scripts/room_study.py)", ""]

    # ---- champions & regular-season strength ------------------------------
    # Titles come from the verified history file; regular-season strength is
    # recomputed under the real dual-points system. Neither uses ESPN's
    # recorded standings, which describe a format this league never played.
    history = load_verified_history()
    true_standings = load_true_standings()

    titles = defaultdict(list)
    for season, rec in sorted(history.items()):
        champ = rec.get("champion")
        if champ:
            titles[champ].append(season)

    seeds = defaultdict(list)   # mgr -> [(season, seed, points, avail)]
    for season, table in true_standings.items():
        avail = table[0]["games"] * 2
        for r in table:
            seeds[r["mgr"]].append((season, r["seed"], r["points"], avail))

    rows = []
    for m in managers:
        s = seeds[m]
        recent = [x for x in s if x[0] in RECENT]
        rows.append([
            m, len(titles[m]),
            ", ".join(str(y) for y in titles[m]) or "—",
            round(mean(x[1] for x in s), 2),
            round(mean(x[1] for x in recent), 2) if recent else "—",
            f"{mean(x[2] for x in s):.1f}/{mean(x[3] for x in s):.0f}",
        ])
    rows.sort(key=lambda r: (-r[1], r[3]))
    md += ["## Titles and regular-season strength (2010-2025)", "",
           "Titles are from `config/history.yaml` (verified against league email). "
           "Seed and points are recomputed under the league's real dual-points "
           "regular season, not ESPN's head-to-head-only record.", "",
           fmt_table(["Manager", "Titles", "Years", "Avg seed",
                      "Avg seed 21-25", "Avg pts/available"], rows), ""]

    # Where the platform data disagrees with the verified record
    disagreements = []
    for season, rec in sorted(history.items()):
        cached = espn_recorded_champion_for(outcomes, season)
        if cached and rec.get("champion") and cached != rec["champion"]:
            disagreements.append([season, cached, rec["champion"],
                                  rec.get("source", "?")])
    if disagreements:
        md += ["### Seasons where the platform cache names the wrong champion", "",
               fmt_table(["Season", "Cache says", "Actually", "Evidence"],
                         disagreements), ""]

    # ---- QB / TE timing per manager -------------------------------------
    tend = {}
    for pos, nth_list in (("QB", [1, 2]), ("TE", [1])):
        for nth in nth_list:
            rows = []
            for m in managers:
                rds, ranks, recent_rds = [], [], []
                for yr in ALL_YEARS:
                    rd, rank = first_pos_round(picks, m, yr, pos, nth)
                    if rd is not None:
                        rds.append(rd)
                        ranks.append(rank)
                        if yr in RECENT:
                            recent_rds.append(rd)
                label = f"{pos}{nth}"
                tend.setdefault(m, {})[f"{label}_round_median"] = median(rds) if rds else None
                tend[m][f"{label}_round_median_recent"] = median(recent_rds) if recent_rds else None
                rows.append([m,
                             median(rds) if rds else "—",
                             f"{min(rds)}–{max(rds)}" if rds else "—",
                             median(recent_rds) if recent_rds else "—",
                             round(mean(ranks), 1) if ranks else "—"])
            rows.sort(key=lambda r: (r[1] if isinstance(r[1], (int, float)) else 99))
            md += [f"## {pos} #{nth} timing (round taken)", "",
                   fmt_table(["Manager", "Median rd (16y)", "Range", "Median rd (21-25)",
                              f"Avg {pos} rank taken"], rows), ""]

    # ---- Early-round positional capital ----------------------------------
    rows = []
    for m in managers:
        early = [p for p in picks if p["mgr"] == m and p["round"] <= 3]
        early_recent = [p for p in early if p["season"] in RECENT]
        n, nr = len(early), len(early_recent)
        counts = {pos: sum(1 for p in early if p["position"] == pos) for pos in CORE_POS}
        counts_r = {pos: sum(1 for p in early_recent if p["position"] == pos) for pos in CORE_POS}
        tend[m]["early_rb_share_recent"] = round(counts_r["RB"] / nr, 3) if nr else None
        tend[m]["early_qb_share_recent"] = round(counts_r["QB"] / nr, 3) if nr else None
        rows.append([m] + [f"{counts[pos]} ({counts_r[pos]})" for pos in CORE_POS])
    md += ["## Rounds 1-3 position counts — 16 years (last 5 in parens)", "",
           fmt_table(["Manager", "QB", "RB", "WR", "TE"], rows), ""]

    # ---- DST early habit (2013-2023 era) ---------------------------------
    rows = []
    for m in managers:
        rds = [p["round"] for p in picks
               if p["mgr"] == m and p["position"] == "DST" and 2013 <= p["season"] <= 2023]
        if rds:
            rows.append([m, median(rds), min(rds)])
    rows.sort(key=lambda r: r[1])
    md += ["## DST round (2013-2023, position existed)", "",
           fmt_table(["Manager", "Median rd", "Earliest"], rows), ""]

    # ---- Run joining ------------------------------------------------------
    runs = run_analysis(picks)
    base = runs["room"]["joins"] / max(runs["room"]["opps"], 1)
    rows = []
    for m in managers:
        s = runs["managers"][m]
        rate = s["joins"] / s["opps"] if s["opps"] else 0
        tend[m]["run_join_rate"] = round(rate, 3)
        rows.append([m, s["opps"], s["joins"], f"{rate:.0%}", f"{rate / base:.2f}x"])
    rows.sort(key=lambda r: -float(r[4][:-1]))
    md += [f"## Position-run joining (rounds 1-10; room base rate {base:.0%})", "",
           fmt_table(["Manager", "Opportunities", "Joined", "Rate", "vs room"], rows), ""]

    # ---- Loyalty ----------------------------------------------------------
    loy = loyalty(picks)
    rows = []
    for m in managers:
        ch = loy["chances"].get(m, 0)
        re = loy["retained"].get(m, 0)
        rate = re / ch if ch else 0
        tend[m]["rebuy_rate"] = round(rate, 3)
        reps = ", ".join(f"{k.title()} ({n}x)" for n, k in loy["top_repeats"].get(m, [])[:3]) or "—"
        rows.append([m, ch, re, f"{rate:.0%}", reps])
    rows.sort(key=lambda r: -int(r[2]))
    md += ["## Player loyalty (their last-year player drafted again by anyone; 10% = random)", "",
           fmt_table(["Manager", "Chances", "Re-bought", "Rate", "Most-drafted (4+ years)"], rows), ""]

    # ---- Room-level market curves (recent era) ---------------------------
    md += ["## Market curves, 2021-2025 drafts", ""]
    rows = []
    for yr in RECENT:
        yr_picks = [p for p in picks if p["season"] == yr]
        c19 = {pos: sum(1 for p in yr_picks if p["pick"] <= 19 and p["position"] == pos)
               for pos in CORE_POS}
        qb1 = next((p["pick"] for p in yr_picks if p["position"] == "QB"), None)
        qb3 = next((p["pick"] for p in yr_picks if p["position"] == "QB" and p["pos_rank"] == 3), None)
        te1 = next((p["pick"] for p in yr_picks if p["position"] == "TE"), None)
        rows.append([yr, c19["RB"], c19["WR"], c19["QB"], c19["TE"], qb1, qb3, te1])
    md += ["Positions taken in the first 19 picks (i.e. gone before pick 20/21 from slot 1), "
           "and where the QB/TE markets open:", "",
           fmt_table(["Year", "RB≤19", "WR≤19", "QB≤19", "TE≤19",
                      "QB1 pick", "QB3 pick", "TE1 pick"], rows), ""]

    # position taken by round, room aggregate, recent era
    rows = []
    for rnd in range(1, 16):
        rp = [p for p in picks if p["season"] in RECENT and p["round"] == rnd]
        if not rp:
            continue
        n = len(rp)
        rows.append([rnd] + [f"{sum(1 for p in rp if p['position'] == pos) / n:.0%}"
                             for pos in CORE_POS])
    md += ["Position share by round (2021-2025, QB/RB/WR/TE picks):", "",
           fmt_table(["Round", "QB", "RB", "WR", "TE"], rows), ""]

    # ---- Champion draft construction --------------------------------------
    rows = []
    qb_rounds, first4 = [], []
    for yr, rec in sorted(history.items()):
        m = rec.get("champion")
        if not m:
            continue
        picks6 = [p for p in picks if p["season"] == yr and p["mgr"] == m][:6]
        seq = " → ".join(p["position"] for p in picks6)
        qb_rd, _ = first_pos_round(picks, m, yr, "QB")
        if qb_rd:
            qb_rounds.append(qb_rd)
        first4 += [p["position"] for p in picks6[:4]]
        rows.append([yr, m, slots.get((yr, m), "?"), seq, qb_rd or "none",
                     "" if rec.get("source") in ("email", "email_list") else
                     rec.get("source", "")])
    md += ["## Champion draft construction (first 6 picks)", "",
           fmt_table(["Year", "Champion", "Slot", "Rounds 1-6 positions",
                      "First QB rd", "Caveat"], rows), ""]
    if qb_rounds:
        late = sum(1 for r in qb_rounds if r >= 5)
        share = {pos: first4.count(pos) for pos in CORE_POS}
        md += [f"Champions' first QB: median round {median(qb_rounds)}; "
               f"{late} of {len(qb_rounds)} waited until round 5 or later. "
               f"Their first four picks: {share['RB']} RB, {share['WR']} WR, "
               f"{share['TE']} TE, {share['QB']} QB.", ""]

    # ---- Draft slots recent ----------------------------------------------
    rows = []
    for m in managers:
        s = [slots.get((yr, m), "—") for yr in RECENT]
        rows.append([m] + s)
    md += ["## Draft slots by year (2021-2025)", "",
           fmt_table(["Manager"] + [str(y) for y in RECENT], rows), ""]

    # ---- Does draft slot matter? -----------------------------------------
    seed_by = {(yr, r["mgr"]): r["seed"]
               for yr, table in true_standings.items() for r in table}
    champ_by_year = {yr: rec.get("champion") for yr, rec in history.items()}
    slot_seeds, slot_titles = defaultdict(list), defaultdict(int)
    for (yr, m), slot in slots.items():
        if (yr, m) in seed_by:
            slot_seeds[slot].append(seed_by[(yr, m)])
        if champ_by_year.get(yr) == m:
            slot_titles[slot] += 1
    rows = [[s, len(slot_seeds[s]), round(mean(slot_seeds[s]), 2), slot_titles[s]]
            for s in sorted(slot_seeds)]
    md += ["## Outcomes by draft slot (16 seasons, dual-points seeding)", "",
           "With 16 seasons spread over 10 slots this is ~16 observations per "
           "slot — suggestive at best, and not evidence that any slot is better.", "",
           fmt_table(["Slot", "Seasons", "Avg reg-season seed", "Titles"], rows), ""]

    OUT_TABLES.parent.mkdir(exist_ok=True)
    OUT_TABLES.write_text("\n".join(md))

    # opponent-model parameters
    for m in managers:
        t = tend[m]
        t["titles"] = len(titles[m])
        t["avg_seed"] = round(mean(x[1] for x in seeds[m]), 2)
    OUT_JSON.write_text(json.dumps(
        {"generated_from": "2010-2025 league caches",
         "run_join_base_rate": round(base, 3),
         "managers": tend}, indent=2))
    print(f"Wrote {OUT_TABLES} and {OUT_JSON}")
    print("\n" + "\n".join(md[:60]))


if __name__ == "__main__":
    main()
