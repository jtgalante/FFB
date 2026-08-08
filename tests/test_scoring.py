"""Projection rescoring under this league's rules.

FantasyPros exports QB projections at 4-point passing TDs and -1 INT; this
league plays 6 and -2. Reading its FPTS column directly understates Josh Allen
by 43.5 points and moves Matthew Stafford from QB15 to QB8.
"""
import pandas as pd

from scripts.ingest_projections import score


def test_scores_a_quarterback_at_six_point_passing_tds(league_cfg):
    # Josh Allen's 2026 FantasyPros component line.
    df = pd.DataFrame([{
        "pass_yd": 3814.0, "pass_td": 27.4, "pass_int": 11.2,
        "rush_yd": 585.2, "rush_td": 11.8, "fl": 4.1,
    }])
    got = float(score(df, league_cfg["scoring"]).iloc[0])
    # 152.56 + 164.4 - 22.4 + 58.52 + 70.8 - 8.2
    assert got == 415.7


def test_the_same_line_at_four_point_tds_is_the_published_number(league_cfg):
    df = pd.DataFrame([{
        "pass_yd": 3814.0, "pass_td": 27.4, "pass_int": 11.2,
        "rush_yd": 585.2, "rush_td": 11.8, "fl": 4.1,
    }])
    four_pt = dict(league_cfg["scoring"], pass_td=4.0, pass_int=-1.0)
    got = float(score(df, four_pt).iloc[0])
    assert abs(got - 372.2) < 0.2   # FantasyPros' own FPTS column


def test_half_ppr_receptions_are_worth_half_a_point(league_cfg):
    df = pd.DataFrame([{"rec": 100.0}])
    assert float(score(df, league_cfg["scoring"]).iloc[0]) == 50.0


def test_missing_stat_columns_contribute_nothing(league_cfg):
    """A tight end export has no rushing columns; that must not error."""
    df = pd.DataFrame([{"rec": 10.0, "rec_yd": 100.0, "rec_td": 1.0}])
    assert float(score(df, league_cfg["scoring"]).iloc[0]) == 21.0
