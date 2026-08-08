"""Snake draft position arithmetic.

Odd rounds run slot 1..N, even rounds run N..1. Everything else in the engine
derives draft position from these two functions, so they live in one place.
"""

from __future__ import annotations


def slot_of(pick: int, teams: int) -> int:
    """Which draft slot (1..teams) made this overall pick."""
    rnd, idx = divmod(pick - 1, teams)
    return idx + 1 if rnd % 2 == 0 else teams - idx


def pick_of(rnd: int, slot: int, teams: int) -> int:
    """Overall pick number for a given round and slot."""
    return (rnd - 1) * teams + (slot if rnd % 2 else teams - slot + 1)
