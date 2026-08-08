"""Validators. Each one corresponds to a bug that actually shipped."""
import pandas as pd
import pytest

from src.draft.validate import (ValidationError, check_min_rows,
                                check_seasons_balanced, check_team_codes,
                                check_draft_complete, check_win_consistency)


def test_min_rows_rejects_a_paywalled_slice():
    """FantasyPros served 10 of 852 players and the board was written anyway."""
    with pytest.raises(ValidationError, match="10 rows"):
        check_min_rows(pd.DataFrame({"a": range(10)}), 120, "projections")


def test_min_rows_accepts_a_full_pull():
    check_min_rows(pd.DataFrame({"a": range(500)}), 120, "projections")


def test_team_codes_rejects_unknown_codes():
    """JAC/LAR vs JAX/LA silently dropped bye weeks for two teams."""
    df = pd.DataFrame({"team": ["KC", "JAC", "SEA"]})
    with pytest.raises(ValidationError, match="JAC"):
        check_team_codes(df, "team", "byes")


def test_team_codes_allows_nulls():
    check_team_codes(pd.DataFrame({"team": ["KC", None]}), "team", "byes")


def test_seasons_balanced_catches_a_silently_dropped_season():
    """2021 injuries had game_type but no season_type; the filter deleted
    four of five seasons and nothing raised."""
    df = pd.DataFrame({"season": [2025] * 100 + [2024] * 2})
    with pytest.raises(ValidationError, match="2024"):
        check_seasons_balanced(df, [2024, 2025], "injuries", min_share=0.25)


def test_seasons_balanced_passes_when_even():
    df = pd.DataFrame({"season": [2024] * 50 + [2025] * 50})
    check_seasons_balanced(df, [2024, 2025], "injuries", min_share=0.25)


def test_draft_complete_catches_a_duplicate_pick():
    df = pd.DataFrame({"season": [2025] * 4, "round": [1, 1, 2, 2],
                       "pick": [1, 1, 3, 4], "manager": list("abab")})
    with pytest.raises(ValidationError, match="duplicate"):
        check_draft_complete(df, teams=2, rounds=2)


def test_draft_complete_passes_on_a_clean_snake():
    df = pd.DataFrame({"season": [2025] * 4, "round": [1, 1, 2, 2],
                       "pick": [1, 2, 3, 4], "manager": list("abba")})
    check_draft_complete(df, teams=2, rounds=2)


def test_win_consistency_reports_a_loser_flagged_as_the_winner():
    """18 rows of the real ESPN archive credit the lower scorer with the win.
    This reports rather than raises: the defect is in the source, not the
    join, and it is written through unchanged."""
    df = pd.DataFrame({"season": [2016, 2016, 2025],
                       "points": [80.68, 78.96, 120.0],
                       "opponent_points": [78.96, 80.68, 90.0],
                       "win": [False, True, True]})
    bad = check_win_consistency(df, "team_weeks")
    assert len(bad) == 2
    assert sorted(bad["season"].unique()) == [2016]


def test_win_consistency_accepts_a_clean_table():
    """A tie is consistent with win=False."""
    df = pd.DataFrame({"season": [2025] * 3, "points": [120.0, 90.0, 100.0],
                       "opponent_points": [90.0, 120.0, 100.0],
                       "win": [True, False, False]})
    assert check_win_consistency(df, "team_weeks").empty
