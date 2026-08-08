"""FLEX-aware replacement levels.

Hand-picking replacement ranks (RB27/WR30/TE13) is really a guess at how the
two FLEX slots split. Derived properly, the 20 flex slots go 10 RB / 10 WR and
zero TE, so RB and WR replacement converge and TE stays far below.
"""
import pandas as pd

from src.draft.data import replacement_levels

CFG = {
    "teams": 10,
    "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
    "flex_eligible": ["RB", "WR", "TE"],
}


def _pool(pos: str, n: int, top: float, step: float) -> pd.DataFrame:
    return pd.DataFrame({"pos": [pos] * n,
                         "proj": [top - i * step for i in range(n)]})


def test_replacement_is_the_best_player_who_never_starts():
    # 10 QBs needed; give it 12 descending from 300 by 10 -> 11th is 200.
    proj = _pool("QB", 12, 300.0, 10.0)
    proj = pd.concat([proj, _pool("RB", 40, 300.0, 5.0),
                      _pool("WR", 40, 300.0, 5.0),
                      _pool("TE", 20, 150.0, 5.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["QB"] == 200.0


def test_flex_pulls_rb_and_wr_replacement_together():
    """Identical RB and WR pools must land at the same replacement level."""
    proj = pd.concat([_pool("QB", 20, 300.0, 5.0),
                      _pool("RB", 60, 300.0, 4.0),
                      _pool("WR", 60, 300.0, 4.0),
                      _pool("TE", 20, 120.0, 4.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["RB"] == levels["WR"]


def test_a_weak_tight_end_pool_wins_no_flex_slots():
    """With TEs far below RB/WR, TE replacement is the 11th TE, not deeper."""
    proj = pd.concat([_pool("QB", 20, 300.0, 5.0),
                      _pool("RB", 60, 300.0, 2.0),
                      _pool("WR", 60, 300.0, 2.0),
                      _pool("TE", 20, 100.0, 2.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["TE"] == 100.0 - 10 * 2.0   # the 11th TE
    assert levels["TE"] < levels["RB"]
