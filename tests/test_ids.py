"""Team and player key normalization.

The JAC/LAR case is not hypothetical: FantasyPros ships JAC and LAR while
nflverse ships JAX and LA, and the mismatch silently dropped bye weeks for
every Jaguar and Ram until it was caught by eye.
"""
import pytest

from src.draft.ids import normalize_name, normalize_team, player_key


@pytest.mark.parametrize("raw,expected", [
    ("LA", "LAR"), ("STL", "LAR"), ("LAR", "LAR"),
    ("JAC", "JAX"), ("JAX", "JAX"),
    ("SD", "LAC"), ("OAK", "LV"), ("WSH", "WAS"),
    ("sea", "SEA"), (" KC ", "KC"),
])
def test_normalize_team_maps_variants_to_one_code(raw, expected):
    assert normalize_team(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "FA", "nan", "None"])
def test_normalize_team_returns_none_for_no_team(raw):
    assert normalize_team(raw) is None


def test_player_key_strips_suffix_and_keeps_position():
    assert player_key("Patrick Mahomes II", "QB") == "patrick mahomes|QB"


def test_player_key_separates_same_name_different_position():
    assert player_key("Mike Williams", "WR") != player_key("Mike Williams", "RB")


def test_normalize_name_applies_known_aliases():
    assert normalize_name("Hollywood Brown") == "marquise brown"
