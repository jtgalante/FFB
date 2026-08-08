"""The warehouse tables must be internally consistent.

These run against the real committed data, so they double as a regression
check on the archive itself.
"""
from pathlib import Path

import pandas as pd
import pytest

WAREHOUSE = Path("data/warehouse")
pytestmark = pytest.mark.skipif(
    not (WAREHOUSE / "picks.parquet").exists(),
    reason="run `python3 -m scripts.build_warehouse` first")


def test_picks_has_one_row_per_manager_per_round():
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    counts = p.groupby(["season", "round"])["manager"].nunique()
    assert set(counts.unique()) == {10}


def test_picks_slots_agree_with_pick_numbers():
    from src.draft.draftmath import slot_of
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    assert (p["slot"] == [slot_of(x, 10) for x in p["pick"]]).all()


def test_team_weeks_resolve_an_opponent_for_almost_every_row():
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet")
    assert t["opponent"].notna().mean() > 0.99


def test_team_weeks_opponents_are_symmetric():
    """If A played B in a week, B played A."""
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet").dropna(
        subset=["opponent"])
    pairs = {(r.season, r.week, r.manager, r.opponent) for r in t.itertuples()}
    missing = [p for p in pairs
               if (p[0], p[1], p[3], p[2]) not in pairs]
    assert not missing[:5]


def test_player_weeks_cover_every_history_season():
    w = pd.read_parquet(WAREHOUSE / "player_weeks.parquet")
    assert set(w["season"].unique()) >= {2021, 2022, 2023, 2024, 2025}
