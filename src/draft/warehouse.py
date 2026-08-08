"""Read the canonical tables.

Analyses read from here, never from the raw JSON caches. The joins — manager
canonicalization, draft-slot arithmetic, player keys, weekly opponents — are
resolved once by `scripts/build_warehouse.py`. Re-deriving them per script is
what produced the JAC/LAR bye loss, the four silently-deleted injury seasons,
and the scrambled draft slots.

    from src.draft import warehouse as wh

    picks = wh.picks()          # season x round x slot, 2010-2025
    tw    = wh.team_weeks()     # season x week x manager, WITH opponent
    pw    = wh.player_weeks()   # season x week x player, our scoring
    ro    = wh.rosters()        # started lineups, 2019+
    pl    = wh.players()        # name, position, age

`team_weeks` is the one worth knowing about: the platform exports record your
score and your opponent's SCORE but never their NAME, so `opponent` is
reconstructed by score-matching within the week. It resolves for 99.9% of rows;
genuine ties are NULL rather than guessed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

WAREHOUSE = Path("data/warehouse")
TABLES = ("picks", "team_weeks", "player_weeks", "rosters", "players")


def load(table: str) -> pd.DataFrame:
    """Read one canonical table."""
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}; have {TABLES}")
    path = WAREHOUSE / f"{table}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Build it first:\n"
            f"    python -m scripts.build_warehouse")
    return pd.read_parquet(path)


def picks() -> pd.DataFrame:
    """One row per draft pick: season, round, pick, slot, manager, player."""
    return load("picks")


def team_weeks() -> pd.DataFrame:
    """One row per manager per week, with the opponent resolved."""
    return load("team_weeks")


def player_weeks() -> pd.DataFrame:
    """One row per NFL player per week, scored under this league's rules."""
    return load("player_weeks")


def rosters() -> pd.DataFrame:
    """One row per started lineup slot per week. Starters only, 2019+."""
    return load("rosters")


def players() -> pd.DataFrame:
    """One row per NFL player: name, position, age."""
    return load("players")


def weekly_by_season() -> dict[int, list[dict]]:
    """team_weeks in the shape the older standings code expects.

    `scripts/rebuild_standings.py` grew up reading the raw caches and hands
    around `dict[season] -> list of row dicts` keyed on `mgr`. This adapter
    lets that code move onto the warehouse without rewriting its internals.
    """
    tw = team_weeks().rename(columns={"manager": "mgr"})
    return {int(s): g.to_dict("records") for s, g in tw.groupby("season")}
