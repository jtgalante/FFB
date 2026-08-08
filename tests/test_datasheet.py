"""The exported datasheet must stand on its own."""
import sqlite3
from pathlib import Path

import pytest

DB = Path("data/export/ffb.sqlite")
pytestmark = pytest.mark.skipif(
    not DB.exists(),
    reason="run `python3 -m scripts.export_datasheet` first")


def _tables():
    with sqlite3.connect(DB) as con:
        return {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}


def test_every_warehouse_table_is_present():
    assert _tables() >= {"picks", "team_weeks", "player_weeks", "rosters",
                         "players", "champions"}


def test_picks_are_queryable_and_complete():
    with sqlite3.connect(DB) as con:
        n = con.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    assert n == 2420


def test_champions_cover_every_season():
    with sqlite3.connect(DB) as con:
        n = con.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
    assert n == 18


def test_a_join_across_grains_works():
    """The point of the handoff: picks join to champions without extra work."""
    with sqlite3.connect(DB) as con:
        rows = con.execute("""
            SELECT p.manager, COUNT(*) FROM picks p
            JOIN champions c ON c.season = p.season AND c.champion = p.manager
            WHERE p.round = 1 GROUP BY p.manager
        """).fetchall()
    assert rows


def test_dictionary_exists_and_documents_every_table():
    doc = Path("data/export/DATA_DICTIONARY.md").read_text()
    for t in ("picks", "team_weeks", "player_weeks", "rosters", "players",
              "champions"):
        assert f"### `{t}`" in doc
