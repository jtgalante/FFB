"""Export the warehouse as one self-contained SQLite file plus a dictionary.

This is the hand-off artefact: give someone `data/export/` and they have the
whole league, queryable, with the caveats written down. SQLite because it is in
the standard library, opens in every tool, and carries its schema with it.

Deliberately NOT one flat table. Three grains live here — pick, team-week,
player-week — and flattening them would either repeat a manager's season across
2,420 pick rows or lose information.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WAREHOUSE = Path("data/warehouse")
OUT = Path("data/export")
DB = OUT / "ffb.sqlite"
DOC = OUT / "DATA_DICTIONARY.md"
HISTORY = Path("config/history.yaml")

TABLES = {
    "picks": ("One row per draft pick, 2010-2025.",
              "Draft slot and pick number are corrected against the original "
              "ClickyDraft boards where those exist; ESPN scrambled the slot in "
              "5 of 7 verified seasons. Manager and round were always correct."),
    "team_weeks": ("One row per manager per week, 2010-2025.",
                   "`opponent` is RECONSTRUCTED by matching each manager's "
                   "opponent_points to another manager's points in the same "
                   "week. It resolves for 99.9% of rows; genuine score "
                   "ties are left NULL rather than guessed. NOTE: 18 rows "
                   "carry a `win` flag that contradicts the scores - a defect "
                   "in the ESPN export, written through unchanged."),
    "player_weeks": ("One row per NFL player per week, 2021-2025.",
                     "`pts` is recomputed under THIS league's scoring "
                     "(6-point passing TDs, half PPR, -2 INT), not the "
                     "source's default. Regular season only."),
    "rosters": ("One row per started lineup slot per week, 2019-2025.",
                "Starters only - bench players were never exported, so "
                "'points left on the bench' is not answerable from this."),
    "players": ("One row per NFL player.", "From the Sleeper player index; "
                "covers currently-active players only."),
    "champions": ("One row per season, 2008-2025.",
                  "Confirmed by the league owner. Do NOT use platform data for "
                  "this - ESPN records the wrong champion in at least three "
                  "seasons because it cannot represent the dual-points format."),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    frames = {}
    for name in ("picks", "team_weeks", "player_weeks", "rosters", "players"):
        path = WAREHOUSE / f"{name}.parquet"
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts.build_warehouse first")
        frames[name] = pd.read_parquet(path)

    hist = yaml.safe_load(HISTORY.read_text())["seasons"]
    frames["champions"] = pd.DataFrame(
        [{"season": int(s), "champion": v.get("champion"),
          "runner_up": v.get("runner_up"), "scoring": v.get("scoring"),
          "source": v.get("source"), "verified": bool(v.get("verified"))}
         for s, v in sorted(hist.items())])

    con = sqlite3.connect(DB)
    for name, df in frames.items():
        df.to_sql(name, con, index=False)
    con.commit()

    L = ["# FFB League Data - Dictionary\n",
         "One SQLite file, `ffb.sqlite`, containing the tables below. Every "
         "figure is derived from league exports and public NFL data; nothing is "
         "hand-entered except the champion list.\n",
         "```bash",
         "sqlite3 ffb.sqlite 'SELECT * FROM picks LIMIT 5;'",
         "```\n",
         "```python",
         "import sqlite3, pandas as pd",
         "con = sqlite3.connect('ffb.sqlite')",
         "picks = pd.read_sql('SELECT * FROM picks', con)",
         "```\n",
         "**There is deliberately no single flat table.** Three grains live "
         "here - pick, team-week, player-week. Joining them into one sheet "
         "would repeat a manager's season across thousands of rows.\n",
         "## The league\n",
         "10 managers, the same ten since 2010. Half-PPR, **6-point passing "
         "TDs**, no kickers or defences since 2024. The regular season is NOT "
         "plain head-to-head: each week awards two points, one for winning your "
         "matchup and one for finishing in the week's top five scorers.\n",
         "## Tables\n"]
    for name, (grain, caveat) in TABLES.items():
        df = frames[name]
        L.append(f"### `{name}`\n")
        L.append(f"{grain} **{len(df):,} rows.**\n")
        L.append(f"> {caveat}\n")
        L.append("| column | type |")
        L.append("|---|---|")
        for c, t in df.dtypes.items():
            L.append(f"| `{c}` | {t} |")
        L.append("")
    DOC.write_text("\n".join(L))

    print(f"Wrote {DB} ({DB.stat().st_size/1e6:.1f} MB)")
    for name, df in frames.items():
        print(f"   {name:<14} {len(df):>6} rows")
    print(f"Wrote {DOC}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
