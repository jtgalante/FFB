"""Snake draft arithmetic.

A wrong version of this shipped in scripts/harpers_index.py, which reported
James's back-to-back picks as 39 and 40 when they are 40 and 41.
"""
import pytest

from src.draft.draftmath import pick_of, slot_of

TEAMS = 10


def test_round_one_runs_left_to_right():
    assert [slot_of(p, TEAMS) for p in range(1, 11)] == list(range(1, 11))


def test_round_two_reverses():
    assert [slot_of(p, TEAMS) for p in range(11, 21)] == list(range(10, 0, -1))


def test_slot_one_holds_the_wrap_pair():
    assert pick_of(1, 1, TEAMS) == 1
    assert pick_of(2, 1, TEAMS) == 20
    assert pick_of(3, 1, TEAMS) == 21
    assert pick_of(4, 1, TEAMS) == 40
    assert pick_of(5, 1, TEAMS) == 41


def test_slot_ten_holds_the_mirror_pair():
    assert pick_of(1, 10, TEAMS) == 10
    assert pick_of(2, 10, TEAMS) == 11


@pytest.mark.parametrize("rnd", range(1, 16))
@pytest.mark.parametrize("slot", range(1, 11))
def test_pick_of_and_slot_of_are_inverses(rnd, slot):
    assert slot_of(pick_of(rnd, slot, TEAMS), TEAMS) == slot
