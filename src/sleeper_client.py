"""Sleeper Fantasy Football API client.

Fetches league history, weekly matchups, lineups, and drafts from the
Sleeper REST API (no authentication required).
"""

import json
import time
from pathlib import Path

import requests

from .config import WeeklyScore, SlotScore, SeasonSummary, DraftPick

BASE_URL = "https://api.sleeper.app/v1"
PLAYERS_CACHE = Path("data/players_cache.json")


def _get(endpoint: str) -> dict | list | None:
    """Make a GET request to the Sleeper API with basic rate limiting."""
    resp = requests.get(f"{BASE_URL}{endpoint}")
    if resp.status_code == 429:
        time.sleep(2)
        resp = requests.get(f"{BASE_URL}{endpoint}")
    resp.raise_for_status()
    return resp.json()


def get_players() -> dict:
    """Get the full player database, cached locally."""
    if PLAYERS_CACHE.exists():
        with open(PLAYERS_CACHE) as f:
            return json.load(f)

    players = _get("/players/nfl")
    PLAYERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(PLAYERS_CACHE, "w") as f:
        json.dump(players, f)
    return players


def get_league(league_id: str) -> dict:
    return _get(f"/league/{league_id}")


def get_users(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/users")


def get_rosters(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/rosters")


def get_matchups(league_id: str, week: int) -> list[dict]:
    return _get(f"/league/{league_id}/matchups/{week}")


def get_drafts(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/drafts")


def get_draft_picks(draft_id: str) -> list[dict]:
    return _get(f"/draft/{draft_id}/picks")


def get_transactions(league_id: str, week: int) -> list[dict]:
    return _get(f"/league/{league_id}/transactions/{week}")


def _build_roster_to_manager(league_id: str) -> dict[int, str]:
    """Map roster_id -> manager display_name for a league."""
    users = get_users(league_id)
    rosters = get_rosters(league_id)

    user_map = {u["user_id"]: u.get("display_name", u.get("username", "Unknown"))
                for u in users}

    return {
        r["roster_id"]: user_map.get(r.get("owner_id", ""), f"Roster {r['roster_id']}")
        for r in rosters
    }


def _map_starters_to_slots(starters: list[str], roster_positions: list[str],
                           players_db: dict) -> list[tuple[str, str, str]]:
    """Map the starters array to (slot_name, player_id, player_name) tuples.

    Sleeper's starters array is ordered to match the league's roster_positions
    setting (excluding BN/bench slots).
    """
    active_positions = [p for p in roster_positions if p != "BN"]
    results = []

    # Track how many of each position we've seen for numbering (RB1, RB2, etc.)
    pos_counts: dict[str, int] = {}

    for i, player_id in enumerate(starters):
        if i >= len(active_positions):
            break

        slot_raw = active_positions[i]

        # Number duplicate positions: RB -> RB1, RB2; WR -> WR1, WR2
        if slot_raw in ("RB", "WR", "FLEX", "SUPER_FLEX", "REC_FLEX"):
            pos_counts[slot_raw] = pos_counts.get(slot_raw, 0) + 1
            count = pos_counts[slot_raw]
            slot_name = f"{slot_raw}{count}" if slot_raw in ("RB", "WR") or count > 1 else slot_raw
        else:
            slot_name = slot_raw

        # Normalize slot names
        slot_name = slot_name.replace("SUPER_FLEX", "SFLEX").replace("REC_FLEX", "RFLEX").replace("DEF", "DST")

        if player_id == "0" or player_id is None:
            player_name = "Empty"
        elif player_id in players_db:
            p = players_db[player_id]
            player_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        else:
            player_name = player_id  # defense IDs are team abbreviations like "DET"

        results.append((slot_name, player_id, player_name))

    return results


def fetch_league_history(starting_league_id: str) -> list[str]:
    """Walk the previous_league_id chain to get all historical league IDs.
    Returns list from oldest to newest.
    """
    league_ids = []
    current_id = starting_league_id

    while current_id:
        league_ids.append(current_id)
        league = get_league(current_id)
        current_id = league.get("previous_league_id")

    return list(reversed(league_ids))


def fetch_season_data(league_id: str) -> tuple[
    list[WeeklyScore], list[SlotScore], list[SeasonSummary]
]:
    """Fetch all data for a single Sleeper season.

    Returns (weekly_scores, slot_scores, season_summaries).
    """
    league = get_league(league_id)
    season = int(league["season"])
    playoff_week_start = league.get("settings", {}).get("playoff_week_start", 15)
    total_weeks = league.get("settings", {}).get("last_scored_leg", playoff_week_start + 2)
    roster_positions = league.get("roster_positions", [])

    roster_to_manager = _build_roster_to_manager(league_id)
    players_db = get_players()

    weekly_scores: list[WeeklyScore] = []
    slot_scores: list[SlotScore] = []

    # Per-manager season accumulators
    manager_stats: dict[str, dict] = {
        name: {"wins": 0, "losses": 0, "pf": 0.0, "pa": 0.0}
        for name in roster_to_manager.values()
    }

    for week in range(1, total_weeks + 1):
        matchups = get_matchups(league_id, week)
        if not matchups:
            break

        # Group by matchup_id to pair opponents
        by_matchup: dict[int, list[dict]] = {}
        for m in matchups:
            mid = m.get("matchup_id")
            if mid is not None:
                by_matchup.setdefault(mid, []).append(m)

        for mid, teams in by_matchup.items():
            if len(teams) != 2:
                continue

            for team, opponent in [(teams[0], teams[1]), (teams[1], teams[0])]:
                rid = team["roster_id"]
                manager = roster_to_manager.get(rid, f"Roster {rid}")
                pts = team.get("points", 0) or 0
                opp_pts = opponent.get("points", 0) or 0
                win = pts > opp_pts

                weekly_scores.append(WeeklyScore(
                    manager=manager, season=season, week=week,
                    points=pts, opponent_points=opp_pts, win=win,
                    platform="sleeper",
                    is_playoff=week >= playoff_week_start,
                ))

                if manager in manager_stats:
                    manager_stats[manager]["wins"] += int(win)
                    manager_stats[manager]["losses"] += int(not win)
                    manager_stats[manager]["pf"] += pts
                    manager_stats[manager]["pa"] += opp_pts

                # Lineup slot breakdown
                starters = team.get("starters", [])
                players_points = team.get("players_points", {})

                if starters and roster_positions:
                    mapped = _map_starters_to_slots(starters, roster_positions, players_db)
                    for slot_name, player_id, player_name in mapped:
                        player_pts = players_points.get(player_id, 0) or 0
                        slot_scores.append(SlotScore(
                            manager=manager, season=season, week=week,
                            slot=slot_name, player_name=player_name,
                            points=player_pts, platform="sleeper",
                            is_playoff=week >= playoff_week_start,
                        ))

    # Build season summaries with playoff bracket results
    rosters = get_rosters(league_id)

    # Resolve playoff brackets for final standings
    roster_finish: dict[int, int] = {}
    try:
        winners = _get(f"/league/{league_id}/winners_bracket") or []
        losers = _get(f"/league/{league_id}/losers_bracket") or []

        if winners:
            # Championship: winner of final round in winners bracket = #1
            final = max(winners, key=lambda m: m.get("r", 0))
            if final.get("w"):
                roster_finish[final["w"]] = 1
            if final.get("l"):
                roster_finish[final["l"]] = 2

        if losers:
            # Sacko: loser of final round in losers bracket = last place
            n_teams = len(rosters)
            sacko_final = max(losers, key=lambda m: m.get("r", 0))
            if sacko_final.get("l"):
                roster_finish[sacko_final["l"]] = n_teams
            if sacko_final.get("w"):
                roster_finish[sacko_final["w"]] = n_teams - 1
    except Exception:
        pass

    roster_standings = sorted(rosters, key=lambda r: (
        -(r.get("settings", {}).get("wins", 0)),
        r.get("settings", {}).get("losses", 0),
    ))

    season_summaries = []
    for rank, roster in enumerate(roster_standings, 1):
        rid = roster["roster_id"]
        manager = roster_to_manager.get(rid, f"Roster {rid}")
        stats = manager_stats.get(manager, {"wins": 0, "losses": 0, "pf": 0, "pa": 0})
        # Use bracket-derived finish if available, otherwise reg season rank
        finish = roster_finish.get(rid, rank)
        season_summaries.append(SeasonSummary(
            manager=manager, season=season, platform="sleeper",
            wins=stats["wins"], losses=stats["losses"],
            total_points=stats["pf"], total_points_against=stats["pa"],
            finish=finish,
        ))

    return weekly_scores, slot_scores, season_summaries


def fetch_draft_data(league_id: str, season: int) -> list[DraftPick]:
    """Fetch draft picks for a single Sleeper season.

    Uses the drafts endpoint to find draft IDs, then fetches picks for each.
    Maps roster_id to manager name and resolves player info from the players DB.
    """
    try:
        drafts = get_drafts(league_id)
    except Exception as e:
        print(f"  Could not load Sleeper drafts for {season}: {e}")
        return []

    if not drafts:
        return []

    roster_to_manager = _build_roster_to_manager(league_id)
    players_db = get_players()
    draft_picks: list[DraftPick] = []

    for draft in drafts:
        draft_id = draft.get("draft_id")
        if not draft_id:
            continue

        try:
            picks = get_draft_picks(draft_id)
        except Exception as e:
            print(f"  Could not load Sleeper draft picks for draft {draft_id}: {e}")
            continue

        if not picks:
            continue

        for pick in picks:
            roster_id = pick.get("roster_id")
            manager = roster_to_manager.get(roster_id, f"Roster {roster_id}")

            player_id = pick.get("player_id", "")
            metadata = pick.get("metadata", {}) or {}

            # Resolve player name from metadata first, then players DB
            first_name = metadata.get("first_name", "")
            last_name = metadata.get("last_name", "")
            if first_name or last_name:
                player_name = f"{first_name} {last_name}".strip()
            elif player_id and player_id in players_db:
                p = players_db[player_id]
                player_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            else:
                player_name = player_id or "Unknown"

            # Resolve position from metadata first, then players DB
            position = metadata.get("position", "")
            if not position and player_id and player_id in players_db:
                position = players_db[player_id].get("position", "")
            # Normalize DST-like positions
            position = position.replace("DEF", "DST") if position else ""

            round_num = pick.get("round", 0)
            pick_no = pick.get("pick_no", 0)

            draft_picks.append(DraftPick(
                manager=manager,
                season=season,
                platform="sleeper",
                round=round_num,
                pick=pick_no,
                player_name=player_name,
                player_id=str(player_id),
                position=position,
            ))

    return draft_picks


def fetch_all_sleeper_drafts(starting_league_id: str) -> list[DraftPick]:
    """Fetch draft data across all Sleeper seasons.

    Walks the previous_league_id chain and aggregates all draft picks.
    """
    league_ids = fetch_league_history(starting_league_id)
    all_drafts: list[DraftPick] = []

    for lid in league_ids:
        league = get_league(lid)
        season = int(league["season"])
        print(f"  Fetching Sleeper {season} draft (league {lid})...")
        picks = fetch_draft_data(lid, season)
        all_drafts.extend(picks)

    print(f"  Total Sleeper draft picks: {len(all_drafts)}")
    return all_drafts


def fetch_all_sleeper_data(starting_league_id: str) -> tuple[
    list[WeeklyScore], list[SlotScore], list[SeasonSummary], list[DraftPick]
]:
    """Fetch data across all Sleeper seasons.

    Walks the previous_league_id chain and aggregates all data.
    Returns (weekly_scores, slot_scores, season_summaries, draft_picks).
    """
    league_ids = fetch_league_history(starting_league_id)
    print(f"Found {len(league_ids)} Sleeper season(s)")

    all_weekly: list[WeeklyScore] = []
    all_slots: list[SlotScore] = []
    all_summaries: list[SeasonSummary] = []
    all_drafts: list[DraftPick] = []

    for lid in league_ids:
        league = get_league(lid)
        season = int(league["season"])
        print(f"  Fetching {league['season']} (league {lid})...")
        weekly, slots, summaries = fetch_season_data(lid)
        all_weekly.extend(weekly)
        all_slots.extend(slots)
        all_summaries.extend(summaries)

        # Fetch draft data for this season
        picks = fetch_draft_data(lid, season)
        all_drafts.extend(picks)

    return all_weekly, all_slots, all_summaries, all_drafts


if __name__ == "__main__":
    from .config import SleeperConfig
    cfg = SleeperConfig()
    if cfg.league_id:
        weekly, slots, summaries, drafts = fetch_all_sleeper_data(cfg.league_id)
        print(f"\nTotal: {len(weekly)} weekly scores, {len(slots)} slot scores, "
              f"{len(summaries)} season summaries, {len(drafts)} draft picks")
        if weekly:
            managers = sorted(set(w.manager for w in weekly))
            print(f"Managers: {', '.join(managers)}")
    else:
        print("Set SLEEPER_LEAGUE_ID in .env")
