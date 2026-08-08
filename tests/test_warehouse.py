"""The warehouse tables must be internally consistent.

Most of these run against the real committed data, so they double as a
regression check on the archive itself.
"""
from pathlib import Path

import pandas as pd
import pytest

WAREHOUSE = Path("data/warehouse")
needs_warehouse = pytest.mark.skipif(
    not (WAREHOUSE / "picks.parquet").exists(),
    reason="run `python3 -m scripts.build_warehouse` first")


def test_pass_two_recovers_an_opponent_that_a_score_tie_hid():
    """The symmetry pass is what makes the table symmetric; delete it and this
    fails while the aggregate resolution rate barely moves.

    A and B played each other. Two managers scored 76, so A's own row cannot
    say which of them it faced — but B's row records a 110-point opponent and
    only A scored 110, so B names A unambiguously and A's opponent follows.
    """
    from scripts.build_warehouse import resolve_opponents
    week = pd.DataFrame([
        {"manager": "A", "points": 110.0, "opponent_points": 76.0},
        {"manager": "B", "points": 76.0, "opponent_points": 110.0},
        {"manager": "C", "points": 76.0, "opponent_points": 78.0},
        {"manager": "D", "points": 78.0, "opponent_points": 76.0},
    ])
    res = resolve_opponents(week)
    assert res[1] == "A" and res[2] == "D"          # unique on score alone
    assert res[0] == "B", "pass 2 failed to recover A's opponent"
    assert res[3] == "C", "pass 2 failed to recover D's opponent"


def test_resolution_leaves_a_mutually_ambiguous_pairing_null():
    """Two games, all four scores identical: nothing distinguishes the
    pairings, so every row must stay null rather than be guessed."""
    from scripts.build_warehouse import resolve_opponents
    week = pd.DataFrame([
        {"manager": m, "points": 90.0, "opponent_points": 90.0}
        for m in "ABCD"
    ])
    assert set(resolve_opponents(week).values()) == {None}


@needs_warehouse
def test_picks_has_one_row_per_manager_per_round(league_cfg):
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    counts = p.groupby(["season", "round"])["manager"].nunique()
    assert set(counts.unique()) == {league_cfg["teams"]}


@needs_warehouse
def test_picks_slots_agree_with_pick_numbers(league_cfg):
    from src.draft.draftmath import slot_of
    teams = league_cfg["teams"]
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    assert (p["slot"] == [slot_of(x, teams) for x in p["pick"]]).all()


@needs_warehouse
def test_team_weeks_resolve_an_opponent_for_almost_every_row():
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet")
    assert t["opponent"].notna().mean() > 0.99


@needs_warehouse
def test_team_weeks_opponents_are_symmetric():
    """If A played B in a week, B played A."""
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet").dropna(
        subset=["opponent"])
    pairs = {(r.season, r.week, r.manager, r.opponent) for r in t.itertuples()}
    missing = [p for p in pairs
               if (p[0], p[1], p[3], p[2]) not in pairs]
    assert not missing, f"{len(missing)} one-way pairings, e.g. {missing[:5]}"


@needs_warehouse
def test_player_weeks_cover_every_history_season():
    w = pd.read_parquet(WAREHOUSE / "player_weeks.parquet")
    assert set(w["season"].unique()) >= {2021, 2022, 2023, 2024, 2025}
