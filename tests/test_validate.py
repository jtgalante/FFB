"""Validators. Each one corresponds to a bug that actually shipped."""
import pandas as pd
import pytest

from src.draft.validate import (ValidationError, check_min_rows,
                                check_seasons_balanced, check_team_codes,
                                check_draft_complete)


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
