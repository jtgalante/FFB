"""Fantasy football analytics computations.

All functions take the normalized DataFrames from normalize.py and return
analysis-ready DataFrames or dicts for the dashboard.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def manager_weekly_stats(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Per-manager aggregate stats across all seasons.

    Returns DataFrame with columns:
        manager, games, wins, losses, win_pct,
        avg_pts, median_pts, std_pts, min_pts, max_pts,
        cv (coefficient of variation / boom-bust index),
        avg_pts_against, total_pts, total_pts_against,
        lucky_wins, unlucky_losses
    """
    if weekly_df.empty:
        return pd.DataFrame()

    # Compute league-wide weekly median for lucky/unlucky calc
    week_medians = weekly_df.groupby(["season", "week"])["points"].median()
    weekly_df = weekly_df.copy()
    weekly_df["week_median"] = weekly_df.set_index(["season", "week"]).index.map(
        lambda idx: week_medians.get(idx, 0)
    )
    weekly_df["lucky_win"] = weekly_df["win"] & (weekly_df["points"] < weekly_df["week_median"])
    weekly_df["unlucky_loss"] = (~weekly_df["win"]) & (weekly_df["points"] > weekly_df["week_median"])

    stats = weekly_df.groupby("manager").agg(
        games=("points", "count"),
        wins=("win", "sum"),
        avg_pts=("points", "mean"),
        median_pts=("points", "median"),
        std_pts=("points", "std"),
        min_pts=("points", "min"),
        max_pts=("points", "max"),
        total_pts=("points", "sum"),
        avg_pts_against=("opponent_points", "mean"),
        total_pts_against=("opponent_points", "sum"),
        lucky_wins=("lucky_win", "sum"),
        unlucky_losses=("unlucky_loss", "sum"),
    ).reset_index()

    stats["losses"] = stats["games"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats["cv"] = (stats["std_pts"] / stats["avg_pts"] * 100).round(1)

    # Round numeric columns
    for col in ["avg_pts", "median_pts", "std_pts", "min_pts", "max_pts",
                "avg_pts_against", "total_pts", "total_pts_against"]:
        stats[col] = stats[col].round(2)

    col_order = [
        "manager", "games", "wins", "losses", "win_pct",
        "avg_pts", "median_pts", "std_pts", "min_pts", "max_pts", "cv",
        "avg_pts_against", "total_pts", "total_pts_against",
        "lucky_wins", "unlucky_losses",
    ]
    return stats[col_order].sort_values("avg_pts", ascending=False)


def manager_season_stats(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Per-manager, per-season stats for trend analysis."""
    if weekly_df.empty:
        return pd.DataFrame()

    stats = weekly_df.groupby(["manager", "season"]).agg(
        games=("points", "count"),
        wins=("win", "sum"),
        avg_pts=("points", "mean"),
        std_pts=("points", "std"),
        total_pts=("points", "sum"),
    ).reset_index()

    stats["losses"] = stats["games"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["games"] * 100).round(1)
    stats["cv"] = (stats["std_pts"] / stats["avg_pts"] * 100).round(1)

    for col in ["avg_pts", "std_pts", "total_pts"]:
        stats[col] = stats[col].round(2)

    return stats.sort_values(["manager", "season"])


def positional_averages(slots_df: pd.DataFrame) -> pd.DataFrame:
    """Average points per roster slot per manager.

    Returns pivot-ready DataFrame: manager x slot -> avg points.
    """
    if slots_df.empty:
        return pd.DataFrame()

    # Only include standard starter slots
    starter_slots = {"QB", "RB1", "RB2", "WR1", "WR2", "FLEX", "FLEX2", "TE", "K", "DST"}
    df = slots_df[slots_df["slot"].isin(starter_slots)].copy()

    avg = df.groupby(["manager", "slot"])["points"].mean().reset_index()
    avg["points"] = avg["points"].round(2)
    return avg


def positional_heatmap_data(slots_df: pd.DataFrame) -> pd.DataFrame:
    """Positional averages as a manager x slot matrix, expressed as
    difference from league average (positive = above avg, negative = below).
    """
    avg = positional_averages(slots_df)
    if avg.empty:
        return pd.DataFrame()

    pivot = avg.pivot(index="manager", columns="slot", values="points")

    # Compute league average per slot
    league_avg = pivot.mean()
    diff = pivot.subtract(league_avg).round(2)

    # Order columns sensibly
    col_order = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "FLEX", "FLEX2", "TE", "K", "DST"]
                 if c in diff.columns]
    return diff[col_order]


def boom_bust_data(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Mean vs std dev per manager — for scatter plot."""
    stats = manager_weekly_stats(weekly_df)
    if stats.empty:
        return pd.DataFrame()
    return stats[["manager", "avg_pts", "std_pts", "cv", "win_pct"]].copy()


def lucky_unlucky(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Expected wins (based on scoring rank each week) vs actual wins."""
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    # For each week, rank all managers by points — expected win% = rank / n_teams
    df["week_rank"] = df.groupby(["season", "week"])["points"].rank(ascending=True)
    n_teams = df.groupby(["season", "week"])["points"].transform("count")
    df["expected_win"] = (df["week_rank"] - 1) / (n_teams - 1)

    result = df.groupby("manager").agg(
        actual_wins=("win", "sum"),
        expected_wins=("expected_win", "sum"),
        games=("win", "count"),
    ).reset_index()

    result["actual_win_pct"] = (result["actual_wins"] / result["games"] * 100).round(1)
    result["expected_win_pct"] = (result["expected_wins"] / result["games"] * 100).round(1)
    result["luck_factor"] = (result["actual_win_pct"] - result["expected_win_pct"]).round(1)
    result["expected_wins"] = result["expected_wins"].round(1)

    return result.sort_values("luck_factor", ascending=False)


def head_to_head(weekly_df: pd.DataFrame, manager_a: str, manager_b: str) -> dict:
    """Compare two managers across all shared weeks."""
    if weekly_df.empty:
        return {}

    a = weekly_df[weekly_df["manager"] == manager_a][["season", "week", "points"]].rename(
        columns={"points": "pts_a"})
    b = weekly_df[weekly_df["manager"] == manager_b][["season", "week", "points"]].rename(
        columns={"points": "pts_b"})

    merged = a.merge(b, on=["season", "week"])

    return {
        "manager_a": manager_a,
        "manager_b": manager_b,
        "weeks_compared": len(merged),
        "a_higher": int((merged["pts_a"] > merged["pts_b"]).sum()),
        "b_higher": int((merged["pts_b"] > merged["pts_a"]).sum()),
        "a_avg": round(merged["pts_a"].mean(), 2),
        "b_avg": round(merged["pts_b"].mean(), 2),
        "a_std": round(merged["pts_a"].std(), 2),
        "b_std": round(merged["pts_b"].std(), 2),
        "avg_diff": round((merged["pts_a"] - merged["pts_b"]).mean(), 2),
    }


def weekly_scoring_timeline(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Weekly points for all managers — for line chart."""
    if weekly_df.empty:
        return pd.DataFrame()
    df = weekly_df.copy()
    df["week_label"] = df["season"].astype(str) + " W" + df["week"].astype(str)
    return df[["manager", "season", "week", "week_label", "points"]].sort_values(
        ["season", "week", "manager"])


def cumulative_points(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative total points over time for each manager.

    Returns a DataFrame with manager, season, week, week_label,
    weekly_points, and cumulative_points columns.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.sort_values(["season", "week"]).copy()
    df["week_label"] = df["season"].astype(str) + " W" + df["week"].astype(str)

    # Create a global ordering for cumulative sum
    df["global_order"] = df["season"] * 100 + df["week"]
    df = df.sort_values(["manager", "global_order"])
    df["cumulative_points"] = df.groupby("manager")["points"].cumsum()

    return df[["manager", "season", "week", "week_label", "points", "cumulative_points"]].copy()


def championships_and_sackos(summaries_df: pd.DataFrame) -> pd.DataFrame:
    """Count championships (#1 finish) and sackos (last place) per manager.

    Returns DataFrame: manager, championships, sackos, seasons_played,
    best_finish, worst_finish, avg_finish.
    """
    if summaries_df.empty:
        return pd.DataFrame()

    df = summaries_df.copy()

    # Filter out finish=0 (missing data from ESPN for recent seasons)
    valid = df[df["finish"] > 0].copy()

    if valid.empty:
        return pd.DataFrame()

    n_teams_per_season = valid.groupby("season")["manager"].transform("count")

    valid["is_champ"] = valid["finish"] == 1
    # Sacko = last place (finish equals number of teams in that season)
    valid["is_sacko"] = valid["finish"] == n_teams_per_season

    result = valid.groupby("manager").agg(
        championships=("is_champ", "sum"),
        sackos=("is_sacko", "sum"),
        seasons_played=("season", "count"),
        best_finish=("finish", "min"),
        worst_finish=("finish", "max"),
        avg_finish=("finish", "mean"),
    ).reset_index()

    result["avg_finish"] = result["avg_finish"].round(1)

    return result.sort_values(["championships", "avg_finish"],
                               ascending=[False, True])


# =========================================================================
# ADVANCED METRICS
# =========================================================================


def schedule_adjusted_win_rate(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """For each week, simulate each manager playing every other manager.

    Returns DataFrame: manager, simulated_wins, simulated_games,
    simulated_win_pct, actual_win_pct, schedule_effect.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    rows = []
    for (season, week), group in df.groupby(["season", "week"]):
        scores = group[["manager", "points"]].values.tolist()
        n = len(scores)
        for mgr_name, mgr_pts in scores:
            sim_wins = sum(1 for _, opp_pts in scores if mgr_pts > opp_pts and _ != mgr_name)
            sim_games = n - 1
            rows.append({"manager": mgr_name, "sim_wins": sim_wins, "sim_games": sim_games})

    sim_df = pd.DataFrame(rows)
    result = sim_df.groupby("manager").agg(
        simulated_wins=("sim_wins", "sum"),
        simulated_games=("sim_games", "sum"),
    ).reset_index()

    result["simulated_win_pct"] = (result["simulated_wins"] / result["simulated_games"] * 100).round(1)

    # Get actual win pct
    actual = df.groupby("manager").agg(
        actual_wins=("win", "sum"), games=("win", "count")
    ).reset_index()
    actual["actual_win_pct"] = (actual["actual_wins"] / actual["games"] * 100).round(1)

    result = result.merge(actual[["manager", "actual_win_pct"]], on="manager")
    result["schedule_effect"] = (result["actual_win_pct"] - result["simulated_win_pct"]).round(1)

    return result.sort_values("simulated_win_pct", ascending=False)


def dominance_score(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Margin of victory / defeat analysis per manager.

    Returns: manager, avg_mov (margin of victory in wins), avg_mod (margin in losses),
    blowout_wins (>30 pts), close_wins (<10 pts), close_losses (<10 pts), blowout_losses.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    df["margin"] = df["points"] - df["opponent_points"]

    wins = df[df["win"]]
    losses = df[~df["win"]]

    win_stats = wins.groupby("manager")["margin"].agg(
        avg_mov="mean", blowout_wins=lambda x: (x > 30).sum(),
        close_wins=lambda x: (x < 10).sum(),
    ).reset_index()

    loss_stats = losses.groupby("manager")["margin"].agg(
        avg_mod="mean", blowout_losses=lambda x: (x < -30).sum(),
        close_losses=lambda x: (x > -10).sum(),
    ).reset_index()

    result = win_stats.merge(loss_stats, on="manager", how="outer").fillna(0)
    result["avg_mov"] = result["avg_mov"].round(1)
    result["avg_mod"] = result["avg_mod"].abs().round(1)
    result["dominance"] = (result["avg_mov"] - result["avg_mod"]).round(1)

    for col in ["blowout_wins", "close_wins", "close_losses", "blowout_losses"]:
        result[col] = result[col].astype(int)

    return result.sort_values("dominance", ascending=False)


def second_half_surge(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Compare first-half vs second-half season performance per manager per season.

    Returns: manager, season, first_half_avg, second_half_avg, surge (positive = improved).
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    results = []
    for (manager, season), group in df.groupby(["manager", "season"]):
        group = group.sort_values("week")
        n = len(group)
        mid = n // 2
        first_half = group.iloc[:mid]["points"].mean()
        second_half = group.iloc[mid:]["points"].mean()
        results.append({
            "manager": manager, "season": season,
            "first_half_avg": round(first_half, 1),
            "second_half_avg": round(second_half, 1),
            "surge": round(second_half - first_half, 1),
        })

    result = pd.DataFrame(results)

    # Also compute career averages
    career = result.groupby("manager").agg(
        avg_first_half=("first_half_avg", "mean"),
        avg_second_half=("second_half_avg", "mean"),
        avg_surge=("surge", "mean"),
        surge_seasons=("surge", lambda x: (x > 0).sum()),
        fade_seasons=("surge", lambda x: (x < 0).sum()),
    ).reset_index()
    for col in ["avg_first_half", "avg_second_half", "avg_surge"]:
        career[col] = career[col].round(1)

    return career.sort_values("avg_surge", ascending=False)


def close_game_record(weekly_df: pd.DataFrame, threshold: float = 10.0) -> pd.DataFrame:
    """Win/loss record in games decided by fewer than `threshold` points.

    Returns: manager, close_games, close_wins, close_losses, close_win_pct.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.copy()
    df["margin"] = (df["points"] - df["opponent_points"]).abs()
    close = df[df["margin"] < threshold]

    result = close.groupby("manager").agg(
        close_games=("win", "count"),
        close_wins=("win", "sum"),
    ).reset_index()
    result["close_losses"] = result["close_games"] - result["close_wins"]
    result["close_win_pct"] = (result["close_wins"] / result["close_games"] * 100).round(1)

    # Also add total games for context
    total = df.groupby("manager")["win"].count().reset_index(name="total_games")
    result = result.merge(total, on="manager")
    result["close_game_pct"] = (result["close_games"] / result["total_games"] * 100).round(1)

    return result.sort_values("close_win_pct", ascending=False)


def elo_ratings(weekly_df: pd.DataFrame, k: float = 32.0, start_elo: float = 1500.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chess-style Elo rating system applied to weekly matchups.

    Returns:
        (final_ratings_df, elo_history_df)
        - final_ratings_df: manager, elo, peak_elo, low_elo, games
        - elo_history_df: manager, season, week, elo (for charting)
    """
    if weekly_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = weekly_df.sort_values(["season", "week"]).copy()

    # Initialize ratings
    managers = sorted(df["manager"].unique())
    ratings = {m: start_elo for m in managers}
    peak = {m: start_elo for m in managers}
    low = {m: start_elo for m in managers}

    history = []

    # Process each week's matchups
    for (season, week), group in df.groupby(["season", "week"], sort=True):
        # Find actual matchups (opponents)
        matchups_seen = set()
        for _, row in group.iterrows():
            mgr = row["manager"]
            pts = row["points"]
            opp_pts = row["opponent_points"]
            win = row["win"]

            # Find the opponent
            opp_rows = group[
                (group["points"] == opp_pts) & (group["opponent_points"] == pts) & (group["manager"] != mgr)
            ]
            if opp_rows.empty:
                continue
            opp = opp_rows.iloc[0]["manager"]

            pair = tuple(sorted([mgr, opp]))
            if pair in matchups_seen:
                continue
            matchups_seen.add(pair)

            # Elo calculation
            ra, rb = ratings[mgr], ratings[opp]
            ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400))
            eb = 1.0 - ea

            if win:
                sa, sb = 1.0, 0.0
            elif pts == opp_pts:
                sa, sb = 0.5, 0.5
            else:
                sa, sb = 0.0, 1.0

            ratings[mgr] = ra + k * (sa - ea)
            ratings[opp] = rb + k * (sb - eb)

            peak[mgr] = max(peak[mgr], ratings[mgr])
            peak[opp] = max(peak[opp], ratings[opp])
            low[mgr] = min(low[mgr], ratings[mgr])
            low[opp] = min(low[opp], ratings[opp])

        # Record post-week ratings for all managers
        for m in managers:
            history.append({"manager": m, "season": season, "week": week, "elo": round(ratings[m], 1)})

    final = pd.DataFrame([
        {"manager": m, "elo": round(ratings[m], 1), "peak_elo": round(peak[m], 1),
         "low_elo": round(low[m], 1)}
        for m in managers
    ]).sort_values("elo", ascending=False)

    history_df = pd.DataFrame(history)
    history_df["week_label"] = history_df["season"].astype(str) + " W" + history_df["week"].astype(str)

    return final, history_df


def rolling_power_rating(weekly_df: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """Rolling average of points scored (last N weeks) for each manager.

    Returns DataFrame with manager, season, week, week_label, rolling_avg.
    """
    if weekly_df.empty:
        return pd.DataFrame()

    df = weekly_df.sort_values(["season", "week"]).copy()
    df["global_order"] = df["season"] * 100 + df["week"]
    df = df.sort_values(["manager", "global_order"])
    df["week_label"] = df["season"].astype(str) + " W" + df["week"].astype(str)

    df["rolling_avg"] = df.groupby("manager")["points"].transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    ).round(1)

    return df[["manager", "season", "week", "week_label", "rolling_avg"]].copy()


# =========================================================================
# DRAFT ANALYTICS
# =========================================================================


def draft_overview(drafts_df: pd.DataFrame, weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Per-manager draft performance summary.

    Returns: manager, total_picks, avg_round, positions_drafted (dict counts),
    avg_season_pts (avg points their picks scored).
    """
    if drafts_df.empty:
        return pd.DataFrame()

    df = drafts_df.copy()

    # Fill in season_points from weekly data if available
    if not weekly_df.empty and "season_points" in df.columns:
        # Compute total season points per manager per season from weekly data
        season_totals = weekly_df.groupby(["manager", "season"])["points"].sum().reset_index(
            name="manager_season_pts")
        # We don't have player-level season points from weekly, so use what drafts has
        pass

    result = df.groupby("manager").agg(
        total_picks=("pick", "count"),
        seasons_drafted=("season", "nunique"),
        avg_round=("round", "mean"),
    ).reset_index()

    result["avg_round"] = result["avg_round"].round(1)

    # Position breakdown per manager
    pos_counts = df.groupby(["manager", "position"]).size().unstack(fill_value=0)
    result = result.merge(pos_counts, left_on="manager", right_index=True, how="left")

    return result.sort_values("total_picks", ascending=False)


def draft_position_tendencies(drafts_df: pd.DataFrame) -> pd.DataFrame:
    """How each manager allocates draft capital by position and round.

    Returns: manager, position, avg_pick, count, pct_of_picks.
    """
    if drafts_df.empty:
        return pd.DataFrame()

    df = drafts_df.copy()

    result = df.groupby(["manager", "position"]).agg(
        count=("pick", "count"),
        avg_pick=("pick", "mean"),
        avg_round=("round", "mean"),
    ).reset_index()

    # Percentage of each manager's picks
    total_picks = df.groupby("manager")["pick"].count().reset_index(name="total")
    result = result.merge(total_picks, on="manager")
    result["pct_of_picks"] = (result["count"] / result["total"] * 100).round(1)

    result["avg_pick"] = result["avg_pick"].round(1)
    result["avg_round"] = result["avg_round"].round(1)

    return result.sort_values(["manager", "count"], ascending=[True, False])


def draft_round_analysis(drafts_df: pd.DataFrame) -> pd.DataFrame:
    """What positions each manager drafts in each round.

    Returns pivot table: manager x round -> most-drafted position.
    """
    if drafts_df.empty:
        return pd.DataFrame()

    df = drafts_df.copy()

    # Limit to first 10 rounds for clean display
    df = df[df["round"] <= 10]

    # Most common position per manager per round
    mode_pos = df.groupby(["manager", "round"])["position"].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else ""
    ).reset_index()

    pivot = mode_pos.pivot(index="manager", columns="round", values="position")
    pivot.columns = [f"R{c}" for c in pivot.columns]

    return pivot


def draft_capital_by_position(drafts_df: pd.DataFrame) -> pd.DataFrame:
    """Average draft pick spent on each position by each manager.

    Lower = spending higher picks on that position.
    Returns a manager x position pivot of average pick numbers.
    """
    if drafts_df.empty:
        return pd.DataFrame()

    df = drafts_df.copy()
    main_positions = ["QB", "RB", "WR", "TE", "K", "DST"]
    df = df[df["position"].isin(main_positions)]

    pivot = df.groupby(["manager", "position"])["pick"].mean().unstack(fill_value=0).round(1)

    col_order = [c for c in main_positions if c in pivot.columns]
    return pivot[col_order]
