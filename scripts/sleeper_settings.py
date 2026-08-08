"""Read the live league settings from Sleeper and reconcile config/league.yaml.

Run this on your laptop (api.sleeper.app is unreachable from the cloud
sandbox). It answers, from the source of truth, everything the email archive
could not confirm: exact scoring values, whether an IR spot exists, the roster,
and the playoff field.

    python -m scripts.sleeper_settings              # show settings + diff
    python -m scripts.sleeper_settings --write      # apply to config/league.yaml

Finds this season's league automatically from your Sleeper username (each
season is a NEW league id on Sleeper, so the id in .env goes stale every year).
Falls back to SLEEPER_LEAGUE_ID from .env.

    python -m scripts.sleeper_settings --user jtgalante --season 2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

BASE = "https://api.sleeper.app/v1"
CONFIG = Path("config/league.yaml")

# Sleeper scoring key -> our config key
SCORING_MAP = {
    "rec": "rec", "pass_yd": "pass_yd", "pass_td": "pass_td",
    "pass_int": "pass_int", "rush_yd": "rush_yd", "rush_td": "rush_td",
    "rec_yd": "rec_yd", "rec_td": "rec_td", "fum_lost": "fum_lost",
    "pass_2pt": "two_pt", "rush_2pt": "two_pt_rush", "rec_2pt": "two_pt_rec",
    "bonus_rec_te": "bonus_rec_te",
}


def _get(path: str):
    r = requests.get(f"{BASE}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def find_league(user: str | None, season: int) -> dict:
    """Locate this season's league. Sleeper mints a new id each season."""
    if user:
        u = _get(f"/user/{user}")
        leagues = _get(f"/user/{u['user_id']}/leagues/nfl/{season}")
        if not leagues:
            raise SystemExit(
                f"No {season} leagues found for '{user}'. If the draft hasn't "
                f"been created yet, re-run once it exists, or pass --league-id.")
        if len(leagues) > 1:
            print(f"{user} is in {len(leagues)} leagues for {season}:")
            for i, lg in enumerate(leagues):
                print(f"  [{i}] {lg['name']}  ({lg['total_rosters']} teams, "
                      f"id {lg['league_id']})")
            print("Pick one with --league-id. NOTE: the redraft league is the "
                  "one to use — do not configure against Gaetz Dynasty.")
            raise SystemExit(1)
        return leagues[0]

    lid = os.getenv("SLEEPER_LEAGUE_ID", "")
    if not lid:
        raise SystemExit("Set SLEEPER_LEAGUE_ID in .env or pass --user/--league-id")
    return _get(f"/league/{lid}")


def summarize(league: dict) -> dict:
    """Pull the settings that matter into our config's shape."""
    s = league.get("settings", {}) or {}
    scoring = league.get("scoring_settings", {}) or {}
    positions = league.get("roster_positions", []) or []

    starters: dict[str, int] = {}
    bench = ir = taxi = 0
    for slot in positions:
        if slot == "BN":
            bench += 1
        elif slot == "IR":
            ir += 1
        elif slot == "TAXI":
            taxi += 1
        else:
            name = {"DEF": "DST", "SUPER_FLEX": "SFLEX",
                    "REC_FLEX": "RFLEX", "WRRB_FLEX": "FLEX"}.get(slot, slot)
            starters[name] = starters.get(name, 0) + 1

    playoff_start = s.get("playoff_week_start") or 15
    out_scoring = {}
    for their, ours in SCORING_MAP.items():
        if their in scoring:
            out_scoring[ours] = float(scoring[their])

    return {
        "name": league.get("name"),
        "season": league.get("season"),
        "league_id": league.get("league_id"),
        "status": league.get("status"),
        "teams": s.get("num_teams") or league.get("total_rosters"),
        "starters": starters,
        "bench_slots": bench,
        "ir_slots": ir,
        "taxi_slots": taxi,
        # IR and taxi slots are not drafted into, so they don't add rounds
        "rounds": bench + sum(starters.values()),
        "regular_season_weeks": playoff_start - 1,
        "playoff_weeks": list(range(playoff_start, playoff_start + 3)),
        "playoff_teams": s.get("playoff_teams"),
        "playoff_round_type": s.get("playoff_round_type"),
        "scoring": out_scoring,
        "raw_scoring": scoring,
    }


def show(info: dict) -> None:
    print(f"League : {info['name']}  ({info['season']}, "
          f"id {info['league_id']}, status {info['status']})")
    print(f"Teams  : {info['teams']}")
    print(f"Starters: " + ", ".join(f"{k}x{v}" for k, v in info["starters"].items()))
    print(f"Bench {info['bench_slots']}, IR {info['ir_slots']}, "
          f"taxi {info['taxi_slots']}  ->  {info['rounds']} draft rounds")
    print(f"Regular season {info['regular_season_weeks']} weeks; "
          f"playoffs {info['playoff_weeks']}, {info['playoff_teams']} teams, "
          f"round type {info['playoff_round_type']}")
    print("\nScoring (all non-zero values Sleeper reports):")
    for k, v in sorted(info["raw_scoring"].items()):
        if v:
            print(f"    {k:<22} {v}")


def diff_config(info: dict) -> list[str]:
    if not CONFIG.exists():
        return ["config/league.yaml missing"]
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    msgs = []

    def cmp(label, ours, theirs):
        if theirs is not None and ours != theirs:
            msgs.append(f"  {label}: config={ours!r}  sleeper={theirs!r}")

    cmp("teams", cfg.get("teams"), info["teams"])
    cmp("rounds", cfg.get("rounds"), info["rounds"])
    cmp("starters", cfg.get("starters"), info["starters"])
    cmp("regular_season_weeks", cfg.get("regular_season_weeks"),
        info["regular_season_weeks"])
    cmp("playoff_teams", cfg.get("playoff_teams"), info["playoff_teams"])
    for k, v in info["scoring"].items():
        cmp(f"scoring.{k}", (cfg.get("scoring") or {}).get(k), v)
    return msgs


def apply(info: dict) -> None:
    cfg = yaml.safe_load(CONFIG.read_text()) or {}
    cfg["teams"] = info["teams"]
    cfg["rounds"] = info["rounds"]
    cfg["starters"] = info["starters"]
    cfg["regular_season_weeks"] = info["regular_season_weeks"]
    cfg["playoff_weeks"] = info["playoff_weeks"]
    if info["playoff_teams"]:
        cfg["playoff_teams"] = info["playoff_teams"]
    cfg.setdefault("scoring", {}).update(info["scoring"])
    CONFIG.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"\nWrote {CONFIG}. Re-check the playoff comments by hand: Sleeper "
          f"cannot express the two-week final or the #1 seed's opponent pick.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="jtgalante",
                    help="Sleeper username (default jtgalante)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--league-id")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    league = _get(f"/league/{a.league_id}") if a.league_id \
        else find_league(a.user, a.season)
    info = summarize(league)
    show(info)

    print("\nDifferences vs config/league.yaml:")
    msgs = diff_config(info)
    print("\n".join(msgs) if msgs else "  none — config matches Sleeper")

    Path("data/draft").mkdir(parents=True, exist_ok=True)
    Path("data/draft/league_settings.json").write_text(json.dumps(info, indent=2))
    print("\nSaved raw settings to data/draft/league_settings.json")

    if a.write and msgs:
        apply(info)
    elif msgs:
        print("Re-run with --write to apply these to config/league.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
