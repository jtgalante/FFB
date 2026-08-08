"""The verified record, and the analytics that now depend on it.

These guard the correction described in `src/league_data.py`: championships
come from `config/history.yaml`, not from ESPN's `finish` field, and
head-to-head means games actually played, not scores in the same week.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from src import analytics
from src import league_data as ld

HISTORY_PATH = Path("config/history.yaml")


@pytest.fixture(scope="module")
def history() -> dict:
    return yaml.safe_load(HISTORY_PATH.read_text())["seasons"]


@pytest.fixture(scope="module")
def counts() -> pd.DataFrame:
    return ld.title_counts()


# ---------------------------------------------------------------- champions


def test_every_season_is_verified(history):
    unverified = [s for s, r in history.items() if not r.get("verified")]
    assert unverified == [], f"unverified seasons: {unverified}"


def test_champions_covers_2008_to_2025():
    champs = ld.champions()
    assert list(champs["season"]) == list(range(2008, 2026))
    assert champs["champion"].notna().all()


def test_title_counts_match_history_exactly(history, counts):
    """Recount the YAML by hand and demand the same answer."""
    expected: dict[str, int] = {}
    for rec in history.values():
        expected[rec["champion"]] = expected.get(rec["champion"], 0) + 1

    got = dict(zip(counts["manager"], counts["championships"]))
    for manager, n in expected.items():
        assert got[manager] == n, f"{manager}: {got[manager]} != {n}"
    # Managers with no title are present with a zero, not missing.
    for manager, n in got.items():
        assert n == expected.get(manager, 0)


def test_the_two_counts_the_dashboard_used_to_get_wrong(counts):
    """ESPN's `finish` credited Matt with 3 and Bryan with 1."""
    got = dict(zip(counts["manager"], counts["championships"]))
    assert got["Matt McCauley"] == 4
    assert got["Bryan Cannon"] == 3


def test_total_championships_is_eighteen(counts):
    assert int(counts["championships"].sum()) == 18


def test_all_ten_managers_have_a_row(counts):
    assert len(counts) == 10
    assert counts["manager"].is_unique


def test_seasons_filter_restricts_the_window():
    """2008-2009 predate the weekly exports, so a 2010+ window drops two."""
    modern = ld.title_counts(range(2010, 2026))
    assert int(modern["championships"].sum()) == 16
    got = dict(zip(modern["manager"], modern["championships"]))
    assert got["Matt McCauley"] == 3
    assert got["Bryan Cannon"] == 2


# ------------------------------------------------------- standings & seeds


@pytest.mark.parametrize("season", [2014, 2019, 2023])
def test_standings_give_ten_distinct_seeds(season):
    table = ld.dual_points_standings(season)
    assert len(table) == 10
    assert sorted(table["seed"]) == list(range(1, 11))
    assert table["manager"].is_unique


def test_dual_points_is_the_sum_of_its_parts():
    table = ld.dual_points_standings(2019)
    assert (table["points"] == table["h2h_wins"] + table["top5_weeks"]).all()


def test_pre_2014_seasons_get_no_top_five_bonus():
    """The bonus was first played in 2014 week 1; applying it earlier would
    invent a competition the league never ran."""
    table = ld.dual_points_standings(2012)
    assert (table["points"] == table["h2h_wins"]).all()
    assert table["scoring"].eq("h2h").all()


def test_standings_reproduce_the_commissioners_sheet():
    """2019 is one of the two seasons validated against the real spreadsheet."""
    official = {"Tyler Clark": 18, "Brian Dzuris": 18, "Anthony Lettieri": 16,
                "Bryan Cannon": 15, "Brendan Gamble": 13, "Matt McCauley": 12,
                "Donnie Darco": 12, "James Galante": 12, "Jonathan Wiggins": 10,
                "Stephen Rogers": 4}
    table = ld.dual_points_standings(2019)
    assert dict(zip(table["manager"], table["points"])) == official


def test_all_seasons_have_ten_seeds():
    table = ld.dual_points_standings()
    for season, group in table.groupby("season"):
        assert sorted(group["seed"]) == list(range(1, 11)), season


# ------------------------------------------------------------ head to head


@pytest.fixture(scope="module")
def weekly() -> pd.DataFrame:
    """The warehouse in the shape the dashboard hands to analytics."""
    return ld.team_weeks()[
        ["season", "week", "manager", "points", "opponent_points",
         "win", "is_playoff"]]


def test_head_to_head_is_symmetric(weekly):
    a, b = "Matt McCauley", "James Galante"
    fwd = analytics.head_to_head(weekly, a, b)
    rev = analytics.head_to_head(weekly, b, a)

    assert fwd["a_wins"] == rev["b_wins"]
    assert fwd["b_wins"] == rev["a_wins"]
    assert fwd["meetings"] == rev["meetings"]
    assert fwd["ties"] == rev["ties"]
    assert fwd["a_avg"] == rev["b_avg"]
    assert fwd["avg_diff"] == pytest.approx(-rev["avg_diff"])
    assert fwd["biggest_blowout"] == rev["biggest_blowout"]


def test_head_to_head_is_symmetric_for_every_pair(weekly):
    managers = sorted(weekly["manager"].unique())
    for i, a in enumerate(managers):
        for b in managers[i + 1:]:
            fwd = analytics.head_to_head(weekly, a, b)
            rev = analytics.head_to_head(weekly, b, a)
            assert fwd["a_wins"] == rev["b_wins"], (a, b)
            assert fwd["b_wins"] == rev["a_wins"], (a, b)
            assert fwd["meetings"] == rev["meetings"], (a, b)


def test_head_to_head_counts_only_real_meetings(weekly):
    """Every meeting must be a row where the resolved opponent is the other
    manager — far fewer than the shared weeks the old version compared."""
    a, b = "Matt McCauley", "James Galante"
    h2h = analytics.head_to_head(weekly, a, b)

    shared_weeks = len(
        weekly[weekly["manager"] == a][["season", "week"]].merge(
            weekly[weekly["manager"] == b][["season", "week"]],
            on=["season", "week"]))

    assert 0 < h2h["meetings"] < shared_weeks
    assert h2h["a_wins"] + h2h["b_wins"] + h2h["ties"] == h2h["meetings"]
    assert h2h["weeks_compared"] == h2h["meetings"]  # dashboard's key


def test_head_to_head_respects_the_season_filter(weekly):
    a, b = "Matt McCauley", "James Galante"
    recent = weekly[weekly["season"] >= 2020]
    assert (analytics.head_to_head(recent, a, b)["meetings"]
            < analytics.head_to_head(weekly, a, b)["meetings"])


def test_head_to_head_blowout_is_the_largest_margin(weekly):
    a, b = "Matt McCauley", "James Galante"
    h2h = analytics.head_to_head(weekly, a, b)
    blowout = h2h["biggest_blowout"]
    assert blowout["margin"] == pytest.approx(
        blowout["winner_points"] - blowout["loser_points"], abs=0.01)

    met = ld.team_weeks()
    met = met[(met["manager"] == a) & (met["opponent"] == b)]
    biggest = (met["points"] - met["opponent_points"]).abs().max()
    assert blowout["margin"] == pytest.approx(biggest, abs=0.01)


def test_head_to_head_empty_input_returns_empty_dict():
    assert analytics.head_to_head(pd.DataFrame(), "a", "b") == {}


def test_head_to_head_for_managers_who_never_met(weekly):
    h2h = analytics.head_to_head(weekly, "Matt McCauley", "Nobody At All")
    assert h2h["meetings"] == 0
    assert h2h["weeks_compared"] == 0
    assert h2h["biggest_blowout"] is None


# ----------------------------------------- championships_and_sackos bridge


@pytest.fixture(scope="module")
def summaries(weekly) -> pd.DataFrame:
    """A stand-in for normalize.py's season summaries — only `season` and
    `manager` are read now, and `finish` deliberately is not."""
    return weekly[["season", "manager"]].drop_duplicates().assign(finish=0)


def test_championships_ignores_the_finish_field(summaries):
    result = analytics.championships_and_sackos(summaries)
    # Every `finish` above is 0; the old implementation returned nothing here.
    assert not result.empty
    assert int(result["championships"].sum()) == 16  # 2010-2025 window


def test_championships_keeps_the_dashboards_columns(summaries):
    result = analytics.championships_and_sackos(summaries)
    assert list(result.columns) == [
        "manager", "championships", "sackos", "seasons_played",
        "best_finish", "worst_finish", "avg_finish"]
    assert len(result) == 10


def test_championships_agree_with_title_counts(summaries):
    result = analytics.championships_and_sackos(summaries)
    expected = ld.title_counts(sorted(summaries["season"].unique()))
    merged = result.merge(expected, on="manager", suffixes=("", "_exp"))
    assert (merged["championships"] == merged["championships_exp"]).all()
    assert (merged["sackos"] == merged["sackos_exp"]).all()


def test_seed_derived_finishes_are_in_range(summaries):
    result = analytics.championships_and_sackos(summaries)
    assert result["best_finish"].between(1, 10).all()
    assert result["worst_finish"].between(1, 10).all()
    assert (result["best_finish"] <= result["worst_finish"]).all()
    assert result["avg_finish"].between(1, 10).all()


def test_championships_honours_the_season_filter(summaries):
    recent = summaries[summaries["season"] >= 2024]
    result = analytics.championships_and_sackos(recent)
    got = dict(zip(result["manager"], result["championships"]))
    assert got["James Galante"] == 1   # 2024
    assert got["Bryan Cannon"] == 1    # 2025
    assert got["Matt McCauley"] == 0
    assert (result["seasons_played"] <= 2).all()


def test_championships_empty_input_returns_empty_frame():
    assert analytics.championships_and_sackos(pd.DataFrame()).empty
