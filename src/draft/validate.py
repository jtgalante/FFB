"""Build-time assertions.

Every check here corresponds to a bug that shipped in this repo and produced
plausible output with no error. The point is to fail loudly at the moment the
data is written, not to be discovered later by eye.
"""

from __future__ import annotations

import pandas as pd

from .ids import _TEAM_ALIASES

VALID_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
}


class ValidationError(RuntimeError):
    """A build produced data that is structurally wrong."""


def check_min_rows(df: pd.DataFrame, minimum: int, label: str) -> None:
    """Reject a gated or truncated payload masquerading as a full pull."""
    if len(df) < minimum:
        raise ValidationError(
            f"{label}: only {len(df)} rows, expected at least {minimum}. "
            f"This is the signature of a paywalled or filtered response, not "
            f"of real data.")


def check_team_codes(df: pd.DataFrame, col: str, label: str) -> None:
    """Every team code must be canonical; nulls are allowed (free agents)."""
    seen = {t for t in df[col].dropna().unique()}
    bad = sorted(seen - VALID_TEAMS)
    if bad:
        hint = {b: _TEAM_ALIASES.get(b) for b in bad if b in _TEAM_ALIASES}
        raise ValidationError(
            f"{label}: non-canonical team codes {bad}. Run them through "
            f"ids.normalize_team first. Known mappings: {hint}")


def check_seasons_balanced(df: pd.DataFrame, seasons: list[int], label: str,
                           min_share: float = 0.5) -> None:
    """Each season must carry a plausible share of the rows.

    A schema difference between years can make a filter delete whole seasons
    while leaving a healthy-looking total.
    """
    counts = df.groupby("season").size()
    expected = len(df) / len(seasons)
    thin = [int(s) for s in seasons
            if counts.get(s, 0) < expected * min_share]
    if thin:
        raise ValidationError(
            f"{label}: seasons {thin} are missing or far too thin "
            f"({dict(counts)}). Check for a schema difference between years.")


def check_draft_complete(df: pd.DataFrame, teams: int, rounds: int) -> None:
    """Per season: picks are unique, contiguous, one per manager per round."""
    for season, g in df.groupby("season"):
        picks = sorted(g["pick"].tolist())
        if len(picks) != len(set(picks)):
            raise ValidationError(
                f"draft {season}: duplicate pick numbers")
        expected = list(range(1, len(g) + 1))
        if picks != expected:
            raise ValidationError(
                f"draft {season}: picks are not contiguous 1..{len(g)}")
        per_round = g.groupby("round")["manager"].nunique()
        bad = per_round[per_round != min(teams, len(g))].to_dict()
        if bad and len(g) >= teams:
            raise ValidationError(
                f"draft {season}: rounds without one pick per manager: {bad}")
