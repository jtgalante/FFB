"""Canonical player identity handling.

Name matching across sources (FantasyPros, Sleeper, nflverse) is the classic
failure mode of fantasy data pipelines. Everything joins on `key_name`:
normalized "name|position". When real ID crosswalks are available (nflverse
ff_playerids), `build_crosswalk` maps source IDs onto the canonical key.
"""

from __future__ import annotations

import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Names that differ across sources beyond mechanical normalization.
_ALIASES = {
    "hollywood brown": "marquise brown",
    "tank dell": "nathaniel dell",
    "gabe davis": "gabriel davis",
    "josh palmer": "joshua palmer",
    "cam ward": "cameron ward",
    "chig okonkwo": "chigoziem okonkwo",
    "scotty miller": "scott miller",
    "mitch trubisky": "mitchell trubisky",
}


def normalize_name(name: str) -> str:
    """Normalize a player name for cross-source matching.

    Lowercase, strip accents/punctuation/suffixes, collapse whitespace.
    """
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = re.sub(r"[.'\"]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    parts = [p for p in s.split() if p not in _SUFFIXES]
    s = " ".join(parts)
    return _ALIASES.get(s, s)


def player_key(name: str, position: str) -> str:
    """Canonical join key: normalized name + position."""
    pos = (position or "").upper().replace("DEF", "DST")
    return f"{normalize_name(name)}|{pos}"


def build_crosswalk(ff_playerids_df):
    """From a dynastyprocess/nflverse ff_playerids table, return a DataFrame
    keyed by `key_name` with sleeper_id / fantasypros_id / gsis_id columns.

    Optional: the engine joins on player_key alone when this is absent.
    """
    df = ff_playerids_df.copy()
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["position"])]
    keep = [c for c in ("key_name", "sleeper_id", "fantasypros_id",
                        "gsis_id", "team", "birthdate") if c in df.columns]
    return df[keep].drop_duplicates("key_name").set_index("key_name")
