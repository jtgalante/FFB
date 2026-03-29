"""ESPN Fantasy Football API client.

Uses the espn_api library to fetch league history, weekly matchups,
lineups, and drafts from private ESPN leagues.
"""

from espn_api.football import League

from .config import ESPNConfig, WeeklyScore, SlotScore, SeasonSummary, DraftPick

# Slots to skip (bench, IR, etc.)
SKIP_SLOTS = {"BE", "BN", "IR", "Bench"}


def _get_league(cfg: ESPNConfig, year: int) -> League:
    return League(
        league_id=cfg.league_id,
        year=year,
        espn_s2=cfg.espn_s2,
        swid=cfg.swid,
    )


def _get_owner_name(team) -> str:
    """Extract a readable owner name from a Team object."""
    if hasattr(team, 'owners') and team.owners:
        owner = team.owners[0]
        first = owner.get("firstName", "")
        last = owner.get("lastName", "")
        if first and last:
            return f"{first} {last}"
        return owner.get("displayName", team.team_name)
    return team.team_name


def _slot_name(slot_str: str, pos_counts: dict[str, int]) -> str | None:
    """Normalize ESPN slot string, numbering duplicates like RB1, RB2."""
    if slot_str in SKIP_SLOTS:
        return None

    base = slot_str.replace("RB/WR/TE", "FLEX").replace("D/ST", "DST")

    if base in ("RB", "WR"):
        pos_counts[base] = pos_counts.get(base, 0) + 1
        return f"{base}{pos_counts[base]}"

    if base in ("FLEX",):
        pos_counts[base] = pos_counts.get(base, 0) + 1
        count = pos_counts[base]
        return f"FLEX{count}" if count > 1 else "FLEX"

    return base


def fetch_season_data(cfg: ESPNConfig, year: int) -> tuple[
    list[WeeklyScore], list[SlotScore], list[SeasonSummary]
]:
    """Fetch all data for a single ESPN season."""
    try:
        league = _get_league(cfg, year)
    except Exception as e:
        print(f"  Could not load ESPN {year}: {e}")
        return [], [], []

    weekly_scores: list[WeeklyScore] = []
    slot_scores: list[SlotScore] = []

    # Determine number of regular season weeks and total weeks (including playoffs)
    reg_season_weeks = league.settings.reg_season_count if hasattr(league.settings, 'reg_season_count') else 14
    # Fetch up to 3 extra weeks for playoffs
    total_weeks = reg_season_weeks + 3

    # Build owner map: team_id -> manager name
    owner_map = {team.team_id: _get_owner_name(team) for team in league.teams}

    # Per-manager season accumulators
    manager_stats: dict[str, dict] = {
        name: {"wins": 0, "losses": 0, "pf": 0.0, "pa": 0.0}
        for name in owner_map.values()
    }

    # Try box_scores (2019+) for detailed lineup data
    use_box_scores = year >= 2019
    if use_box_scores:
        for week in range(1, total_weeks + 1):
            try:
                box_scores = league.box_scores(week)
            except Exception:
                continue

            # Skip empty weeks (past end of season)
            if not any(box.home_score or box.away_score for box in box_scores):
                break

            is_playoff = week > reg_season_weeks

            for box in box_scores:
                for side, score, opp_score, lineup in [
                    ("home", box.home_score, box.away_score, box.home_lineup),
                    ("away", box.away_score, box.home_score, box.away_lineup),
                ]:
                    team = box.home_team if side == "home" else box.away_team
                    if team is None:
                        continue

                    manager = owner_map.get(team.team_id, team.team_name)
                    pts = score or 0
                    opp_pts = opp_score or 0
                    win = pts > opp_pts

                    weekly_scores.append(WeeklyScore(
                        manager=manager, season=year, week=week,
                        points=pts, opponent_points=opp_pts, win=win,
                        platform="espn", is_playoff=is_playoff,
                    ))

                    if not is_playoff and manager in manager_stats:
                        manager_stats[manager]["wins"] += int(win)
                        manager_stats[manager]["losses"] += int(not win)
                        manager_stats[manager]["pf"] += pts
                        manager_stats[manager]["pa"] += opp_pts

                    # Lineup slot breakdown
                    if lineup:
                        pos_counts: dict[str, int] = {}
                        for player in lineup:
                            slot = _slot_name(player.slot_position, pos_counts)
                            if slot is None:
                                continue
                            player_pts = player.points if hasattr(player, 'points') else 0
                            slot_scores.append(SlotScore(
                                manager=manager, season=year, week=week,
                                slot=slot, player_name=player.name,
                                points=player_pts, platform="espn",
                                is_playoff=is_playoff,
                            ))
    else:
        # Pre-2019: use team.scores/schedule/outcomes for weekly totals (no lineup detail)
        for team in league.teams:
            manager = owner_map.get(team.team_id, team.team_name)
            scores = team.scores if hasattr(team, 'scores') else []
            schedule = team.schedule if hasattr(team, 'schedule') else []
            outcomes = team.outcomes if hasattr(team, 'outcomes') else []

            for week_idx, pts in enumerate(scores):
                week = week_idx + 1
                is_playoff = week > reg_season_weeks
                opp_team = schedule[week_idx] if week_idx < len(schedule) else None
                opp_pts = opp_team.scores[week_idx] if opp_team and hasattr(opp_team, 'scores') and week_idx < len(opp_team.scores) else 0
                outcome = outcomes[week_idx] if week_idx < len(outcomes) else "U"
                win = outcome == "W"

                weekly_scores.append(WeeklyScore(
                    manager=manager, season=year, week=week,
                    points=pts, opponent_points=opp_pts, win=win,
                    platform="espn", is_playoff=is_playoff,
                ))

                if not is_playoff and manager in manager_stats:
                    manager_stats[manager]["wins"] += int(win)
                    manager_stats[manager]["losses"] += int(not win)
                    manager_stats[manager]["pf"] += pts
                    manager_stats[manager]["pa"] += opp_pts

    # Season summaries — use final_standing (includes playoff results)
    season_summaries = []
    for team in league.teams:
        manager = owner_map.get(team.team_id, team.team_name)
        stats = manager_stats.get(manager, {"wins": 0, "losses": 0, "pf": 0, "pa": 0})
        finish = team.final_standing if hasattr(team, 'final_standing') and team.final_standing else 0
        season_summaries.append(SeasonSummary(
            manager=manager, season=year, platform="espn",
            wins=stats["wins"], losses=stats["losses"],
            total_points=stats["pf"], total_points_against=stats["pa"],
            finish=finish,
        ))

    return weekly_scores, slot_scores, season_summaries


def discover_seasons(cfg: ESPNConfig, start_year: int = 2010, end_year: int = 2025) -> list[int]:
    """Try to access each year and return the ones that work."""
    valid = []
    for year in range(end_year, start_year - 1, -1):
        try:
            league = _get_league(cfg, year)
            if league.teams:
                valid.append(year)
                print(f"  Found ESPN season: {year} ({len(league.teams)} teams)")
        except Exception:
            continue
    return sorted(valid)


def fetch_draft_data(cfg: ESPNConfig, year: int) -> list[DraftPick]:
    """Fetch draft picks for a single ESPN season.

    Uses league.draft which returns a list of pick objects with attributes like
    playerName, team, round_num, round_pick, bid_amount.
    Handles both snake drafts and auction drafts gracefully.
    """
    try:
        league = _get_league(cfg, year)
    except Exception as e:
        print(f"  Could not load ESPN {year} for draft: {e}")
        return []

    try:
        draft = league.draft
    except Exception as e:
        print(f"  No draft data for ESPN {year}: {e}")
        return []

    if not draft:
        return []

    # Build owner map: team_id -> manager name
    owner_map = {team.team_id: _get_owner_name(team) for team in league.teams}

    # Build position map from rosters (covers all drafted players cheaply)
    pos_map: dict[int, str] = {}
    for team in league.teams:
        for player in team.roster:
            if hasattr(player, 'playerId') and hasattr(player, 'position'):
                pos_map[player.playerId] = player.position or ""

    draft_picks: list[DraftPick] = []

    for overall_pick, pick in enumerate(draft, start=1):
        try:
            # Get player name
            player_name = getattr(pick, "playerName", "") or ""

            # Get team/manager
            team = getattr(pick, "team", None)
            if team:
                manager = owner_map.get(team.team_id, getattr(team, "team_name", "Unknown"))
            else:
                manager = "Unknown"

            # Get round info
            round_num = getattr(pick, "round_num", 0) or 0
            round_pick = getattr(pick, "round_pick", 0) or 0

            # For auction drafts, round_num may be 0; use overall pick order
            if round_num == 0:
                round_num = 1  # auction drafts are effectively 1 round

            # Calculate overall pick number
            if round_num > 0 and round_pick > 0:
                n_teams = len(league.teams)
                pick_no = (round_num - 1) * n_teams + round_pick
            else:
                pick_no = overall_pick

            # Get player ID
            player_id = ""
            pid_int = 0
            if hasattr(pick, "playerId"):
                player_id = str(pick.playerId)
                pid_int = pick.playerId
            elif hasattr(pick, "player_id"):
                player_id = str(pick.player_id)
                pid_int = pick.player_id

            # Get position — try roster map first, then player_info as fallback
            position = pos_map.get(pid_int, "")
            if not position:
                try:
                    info = league.player_info(playerId=pid_int)
                    if info and hasattr(info, 'position'):
                        position = info.position or ""
                except Exception:
                    pass
            # Normalize position
            position = position.replace("D/ST", "DST").replace("DEF", "DST")

            draft_picks.append(DraftPick(
                manager=manager,
                season=year,
                platform="espn",
                round=round_num,
                pick=pick_no,
                player_name=player_name,
                player_id=player_id,
                position=position,
            ))
        except Exception as e:
            print(f"  Error processing ESPN draft pick in {year}: {e}")
            continue

    return draft_picks


def fetch_all_espn_drafts(cfg: ESPNConfig) -> list[DraftPick]:
    """Fetch draft data across all available ESPN seasons."""
    if not cfg.is_configured:
        return []

    seasons = discover_seasons(cfg)
    all_drafts: list[DraftPick] = []

    for year in seasons:
        print(f"  Fetching ESPN {year} draft...")
        picks = fetch_draft_data(cfg, year)
        all_drafts.extend(picks)

    print(f"  Total ESPN draft picks: {len(all_drafts)}")
    return all_drafts


def fetch_all_espn_data(cfg: ESPNConfig) -> tuple[
    list[WeeklyScore], list[SlotScore], list[SeasonSummary], list[DraftPick]
]:
    """Fetch data across all available ESPN seasons.

    Returns (weekly_scores, slot_scores, season_summaries, draft_picks).
    """
    if not cfg.is_configured:
        print("ESPN not configured — skipping. Set ESPN_LEAGUE_ID, ESPN_S2, ESPN_SWID in .env")
        return [], [], [], []

    print("Discovering ESPN seasons...")
    seasons = discover_seasons(cfg)
    print(f"Found {len(seasons)} ESPN season(s)")

    all_weekly: list[WeeklyScore] = []
    all_slots: list[SlotScore] = []
    all_summaries: list[SeasonSummary] = []
    all_drafts: list[DraftPick] = []

    for year in seasons:
        print(f"  Fetching ESPN {year}...")
        weekly, slots, summaries = fetch_season_data(cfg, year)
        all_weekly.extend(weekly)
        all_slots.extend(slots)
        all_summaries.extend(summaries)

        # Fetch draft data for this season
        picks = fetch_draft_data(cfg, year)
        all_drafts.extend(picks)

    return all_weekly, all_slots, all_summaries, all_drafts


if __name__ == "__main__":
    cfg = ESPNConfig()
    if cfg.is_configured:
        weekly, slots, summaries, drafts = fetch_all_espn_data(cfg)
        print(f"\nTotal: {len(weekly)} weekly scores, {len(slots)} slot scores, "
              f"{len(summaries)} season summaries, {len(drafts)} draft picks")
    else:
        print("Set ESPN_LEAGUE_ID, ESPN_S2, and ESPN_SWID in .env")
