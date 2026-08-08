"""Reconstruct true league standings, and scaffold the hand-verified history file.

Why this exists: the ESPN-era caches (2010-2023) record standings under plain
head-to-head W/L, but this league did not play plain head-to-head. In the
earlier years a team earned a point for winning its matchup AND a point for
finishing in the week's top 5 scorers — a dual-points format ESPN could not
represent. Its recorded "champion" is therefore frequently not the real one.
Playoff seeding is also non-standard (the regular-season winner picks its
first-round opponent), which no automated bracket read can infer.

So: this script recomputes what the data *can* determine (weekly standings
under either scoring system, and the plausible title games), then writes
config/history.yaml for a human to correct. That file — not the caches —
becomes the authority for every outcome-linked analysis.

    python -m scripts.rebuild_standings          # show the comparison
    python -m scripts.rebuild_standings --write  # scaffold config/history.yaml

Never overwrites a season already marked `verified: true`.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_canonical_name  # noqa: E402
from src.draft import warehouse as wh  # noqa: E402

# Weekly scores come from the warehouse. The season summaries do not live there
# yet, so `espn_recorded_champion` still reads the ESPN cache directly.
ESPN_CACHE = Path("data/espn_cache.json")
HISTORY_PATH = Path("config/history.yaml")

TOP_N_BONUS = 5  # a point for finishing in the week's top 5 scorers

# The dual-points system (matchup win + weekly top-5 finish) was proposed by
# Anthony Lettieri on 2013-11-18 and first played in 2014 week 1. Seasons
# before that were plain head-to-head, so applying the bonus to them would
# invent a competition the league never played.
DUAL_POINTS_FROM = 2014


def scoring_system(season: int) -> str:
    return "dual_points" if season >= DUAL_POINTS_FROM else "h2h"


def load_weekly() -> dict[int, list[dict]]:
    """season -> weekly rows, keyed on `mgr`. Read from the warehouse.

    `team_weeks` already carries the canonical manager name and the resolved
    opponent; the adapter renames `manager` to `mgr` for this module's callers
    (`scripts.room_study`, `scripts.variance_study`).
    """
    return wh.weekly_by_season()


def standings(rows: list[dict], dual_points: bool) -> list[dict]:
    """Regular-season table. Under dual_points, each week awards 1 point for
    winning the matchup and 1 for placing in the week's top 5 scorers."""
    reg = [r for r in rows if not r.get("is_playoff")]
    weeks = sorted({r["week"] for r in reg})
    tally: dict[str, dict] = defaultdict(
        lambda: {"h2h": 0, "top5": 0, "pf": 0.0, "games": 0})

    for wk in weeks:
        games = [r for r in reg if r["week"] == wk]
        ranked = sorted(games, key=lambda r: -r["points"])
        top5 = {r["mgr"] for r in ranked[:TOP_N_BONUS]}
        for r in games:
            t = tally[r["mgr"]]
            t["h2h"] += int(r["win"])
            t["top5"] += int(r["mgr"] in top5)
            t["pf"] += r["points"]
            t["games"] += 1

    out = []
    for mgr, t in tally.items():
        pts = t["h2h"] + t["top5"] if dual_points else t["h2h"]
        out.append({"mgr": mgr, "points": pts, "h2h": t["h2h"],
                    "top5": t["top5"], "pf": round(t["pf"], 1),
                    "games": t["games"]})
    out.sort(key=lambda r: (-r["points"], -r["pf"]))
    for i, r in enumerate(out, 1):
        r["seed"] = i
    return out


def final_week_games(rows: list[dict]) -> list[tuple[str, str, float, float]]:
    """Matchups in the last playoff week, as (winner, loser, wpts, lpts)."""
    playoff = [r for r in rows if r.get("is_playoff")]
    if not playoff:
        return []
    last = max(r["week"] for r in playoff)
    games, seen = [], set()
    for r in (x for x in playoff if x["week"] == last):
        if r["mgr"] in seen:
            continue
        opp = next((x for x in playoff
                    if x["week"] == last and x["mgr"] != r["mgr"]
                    and abs(x["points"] - r["opponent_points"]) < 0.01
                    and abs(x["opponent_points"] - r["points"]) < 0.01
                    and x["mgr"] not in seen), None)
        if opp is None:
            continue
        seen.update({r["mgr"], opp["mgr"]})
        hi, lo = (r, opp) if r["points"] >= opp["points"] else (opp, r)
        games.append((hi["mgr"], lo["mgr"], hi["points"], lo["points"]))
    return games


def espn_recorded_champion(season: int) -> str | None:
    if not ESPN_CACHE.exists():
        return None
    for s in json.loads(ESPN_CACHE.read_text())["summaries"]:
        if s["season"] == season and s["finish"] == 1:
            return get_canonical_name("espn", s["manager"])
    return None


def analyze() -> dict[int, dict]:
    weekly = load_weekly()
    report = {}
    for season, rows in weekly.items():
        dual = scoring_system(season) == "dual_points"
        h2h_table = standings(rows, dual_points=False)
        dual_table = standings(rows, dual_points=dual)
        finals = final_week_games(rows)
        seed_of = {r["mgr"]: r["seed"] for r in dual_table}
        # The title game is most plausibly the final-week matchup whose two
        # teams have the best combined corrected seeding.
        ranked_finals = sorted(
            finals, key=lambda g: seed_of.get(g[0], 99) + seed_of.get(g[1], 99))
        report[season] = {
            "platform": rows[0]["platform"],
            "h2h": h2h_table,
            "dual": dual_table,
            "finals": ranked_finals,
            "espn_champion": espn_recorded_champion(season),
        }
    return report


def print_report(report: dict[int, dict]) -> None:
    for season, r in report.items():
        print(f"\n=== {season} ({r['platform']}) " + "=" * 40)
        h2h_win = r["h2h"][0]["mgr"]
        dual_win = r["dual"][0]["mgr"]
        flag = "" if h2h_win == dual_win else "   <-- SCORING SYSTEM CHANGES THE #1 SEED"
        print(f"  Regular season #1 by H2H only : {h2h_win}")
        print(f"  Regular season #1 by dual pts : {dual_win}{flag}")
        print(f"  ESPN-recorded champion        : {r['espn_champion'] or '(sleeper era)'}")
        print("  Top 4 by dual points:")
        for row in r["dual"][:4]:
            print(f"    {row['seed']}. {row['mgr']:<20} {row['points']:>3} pts "
                  f"({row['h2h']} h2h + {row['top5']} top-5), {row['pf']} PF")
        if r["finals"]:
            print("  Final-week games (best-seeded first — likely title game on top):")
            for w, l, wp, lp in r["finals"][:3]:
                print(f"    {w} def. {l}  {wp:.1f}-{lp:.1f}")


def scaffold(report: dict[int, dict]) -> None:
    existing = {}
    if HISTORY_PATH.exists():
        existing = (yaml.safe_load(HISTORY_PATH.read_text()) or {}).get("seasons", {})

    seasons = {}
    for season, r in report.items():
        prior = existing.get(season, {})
        if prior.get("verified"):
            seasons[season] = prior
            continue
        guess_champ = r["finals"][0][0] if r["finals"] else None
        guess_runner = r["finals"][0][1] if r["finals"] else None
        seasons[season] = {
            "verified": False,
            "champion": prior.get("champion", guess_champ),
            "runner_up": prior.get("runner_up", guess_runner),
            "regular_season_winner": prior.get(
                "regular_season_winner", r["dual"][0]["mgr"]),
            "scoring": prior.get("scoring", scoring_system(season)),
            "notes": prior.get("notes", ""),
        }

    HISTORY_PATH.parent.mkdir(exist_ok=True)
    header = (
        "# Verified league history — the authority for all outcome-linked analysis.\n"
        "#\n"
        "# The platform caches cannot be trusted for champions: the ESPN years used a\n"
        "# dual-points regular season (1 pt for the matchup win + 1 pt for a weekly\n"
        "# top-5 score) that ESPN could not represent, and the playoff format lets the\n"
        "# regular-season winner choose its opponent. Values below are DATA GUESSES\n"
        "# until a human checks them.\n"
        "#\n"
        "# For each season: correct the names, then set `verified: true`. Verified\n"
        "# seasons are never overwritten by `python -m scripts.rebuild_standings --write`.\n"
        "#\n"
        "# scoring: dual_points | h2h    (which regular-season system was in force)\n"
        "# notes:   anything unusual — opponent choice, tiebreaks, co-champions\n\n"
    )
    HISTORY_PATH.write_text(header + yaml.safe_dump(
        {"seasons": seasons}, sort_keys=True, default_flow_style=False))
    n_unverified = sum(1 for s in seasons.values() if not s["verified"])
    print(f"\nWrote {HISTORY_PATH}: {len(seasons)} seasons, "
          f"{n_unverified} awaiting verification.")


# Official standings transcribed from the commissioner's Google Sheets, used to
# validate the reconstruction. Nicknames resolved: Biscuit = Stephen Rogers,
# Burke/Dizzy = Brian Dzuris, Peter = Peter Wallach (exported as "Donnie Darco").
OFFICIAL_STANDINGS = {
    2023: {"Matt McCauley": 18, "Stephen Rogers": 18, "Brendan Gamble": 18,
           "Brian Dzuris": 17, "Donnie Darco": 16, "Jonathan Wiggins": 12,
           "James Galante": 12, "Bryan Cannon": 11, "Anthony Lettieri": 9,
           "Tyler Clark": 9},
    2019: {"Tyler Clark": 18, "Brian Dzuris": 18, "Anthony Lettieri": 16,
           "Bryan Cannon": 15, "Brendan Gamble": 13, "Matt McCauley": 12,
           "Donnie Darco": 12, "James Galante": 12, "Jonathan Wiggins": 10,
           "Stephen Rogers": 4},
    2018: {"Matt McCauley": 19, "Donnie Darco": 18, "Jonathan Wiggins": 18,
           "Bryan Cannon": 14, "Brendan Gamble": 12, "James Galante": 12,
           "Brian Dzuris": 12, "Stephen Rogers": 11, "Tyler Clark": 8,
           "Anthony Lettieri": 6},
}


def validate() -> bool:
    """Check the dual-points reconstruction against the official sheets.

    2019 and 2023 reproduce exactly. 2018 differs by one point for two
    managers with no exact ties present in the data — most likely an ESPN
    stat correction applied after the commissioner's sheet was written.
    """
    weekly = load_weekly()
    all_ok = True
    for season, official in sorted(OFFICIAL_STANDINGS.items()):
        mine = {r["mgr"]: r["points"] for r in standings(weekly[season], True)}
        diffs = {m: (mine.get(m), pts) for m, pts in official.items()
                 if mine.get(m) != pts}
        if diffs:
            all_ok = False
            print(f"  {season}: {len(diffs)} manager(s) differ")
            for m, (got, want) in diffs.items():
                print(f"      {m}: reconstructed {got}, official {want}")
        else:
            print(f"  {season}: exact match (all 10 managers)")
    return all_ok


def load_history() -> dict[int, dict]:
    """Verified history for downstream analysis. Unverified seasons are
    returned too, flagged, so callers can decide whether to trust them."""
    if not HISTORY_PATH.exists():
        return {}
    raw = yaml.safe_load(HISTORY_PATH.read_text()) or {}
    return raw.get("seasons", {})


def main() -> int:
    if "--validate" in sys.argv:
        print("Validating dual-points reconstruction against official sheets:")
        validate()
        return 0
    report = analyze()
    print_report(report)
    if "--write" in sys.argv:
        scaffold(report)
    else:
        print("\n(Run with --write to scaffold config/history.yaml)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
