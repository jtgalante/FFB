"""Local data store for the draft engine.

The engine reads only from data/draft/ (parquet) — populated either by the
network fetchers in sources.py (`cli fetch`, run on a laptop) or by
`build_fixtures()`, which derives a fully offline development dataset from
the real league caches committed in this repo (data/sleeper_cache.json,
data/draft_cache.json: 2024-25 starter weekly points and the 2025 draft
board). Fixture data is clearly marked in meta.json and in the board output.

Manual overrides in data/inputs/ always win:
  projections.csv  name, pos, proj [, team, games]
  adp.csv          name, pos, adp
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .ids import player_key
from .sources import DRAFT_DATA_DIR, INPUTS_DIR

SLEEPER_CACHE = Path("data/sleeper_cache.json")
DRAFT_CACHE = Path("data/draft_cache.json")

# Expected games played per season by position (historical league-wide rates,
# used for fixture projections and as the availability prior in the risk model).
EXPECTED_GAMES = {"QB": 15.5, "RB": 14.0, "WR": 14.8, "TE": 14.6}

_SLOT_POS = {"QB": "QB", "TE": "TE"}
_SLOT_RE = re.compile(r"^(QB|RB|WR|TE)\d*$")


@dataclass
class DataStore:
    projections: pd.DataFrame   # key_name, name, pos, team, proj, games
    adp: pd.DataFrame           # key_name, adp
    weekly: pd.DataFrame        # key_name, name, pos, season, week, pts
    byes: pd.DataFrame | None   # team, bye
    source: str                 # "live" or "fixture"

    @classmethod
    def load(cls, data_dir: Path | str = DRAFT_DATA_DIR) -> "DataStore":
        data_dir = Path(data_dir)
        meta_path = data_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                "No draft data found. Run `python -m src.draft.cli fetch` "
                "(laptop, live data) or `python -m src.draft.cli bootstrap` "
                "(offline fixture from the committed league caches).")
        meta = json.loads(meta_path.read_text())

        proj = pd.read_parquet(data_dir / "projections.parquet")
        adp = pd.read_parquet(data_dir / "adp.parquet")
        weekly = pd.read_parquet(data_dir / "weekly_points.parquet")
        byes_path = data_dir / "byes.parquet"
        byes = pd.read_parquet(byes_path) if byes_path.exists() else None

        proj, adp = _apply_input_overrides(proj, adp)
        if "games" not in proj.columns:
            proj["games"] = proj["pos"].map(EXPECTED_GAMES).fillna(14.5)
        if "team" not in proj.columns:
            proj["team"] = None
        return cls(projections=proj, adp=adp, weekly=weekly, byes=byes,
                   source=meta.get("source", "live"))

    def universe(self) -> pd.DataFrame:
        """Master player table: projections joined with ADP and byes.

        Players with projections but no ADP get adp = undrafted sentinel
        (total pool size + their projection rank) so they sort last.
        """
        df = self.projections.merge(self.adp[["key_name", "adp"]],
                                    on="key_name", how="left")
        n = len(df)
        missing = df["adp"].isna()
        if missing.any():
            rank = df["proj"].rank(ascending=False)
            df.loc[missing, "adp"] = n + rank[missing]
        if self.byes is not None and "team" in df.columns:
            df = df.merge(self.byes, on="team", how="left")
        if "bye" not in df.columns:
            df["bye"] = np.nan
        df = df.sort_values("adp").reset_index(drop=True)
        df["adp_rank"] = np.arange(1, len(df) + 1)
        return df


def _apply_input_overrides(proj: pd.DataFrame, adp: pd.DataFrame):
    """CSVs in data/inputs/ replace fetched projections/ADP wholesale."""
    proj_csv = INPUTS_DIR / "projections.csv"
    adp_csv = INPUTS_DIR / "adp.csv"
    if proj_csv.exists():
        p = pd.read_csv(proj_csv)
        p["key_name"] = [player_key(n, x) for n, x in zip(p["name"], p["pos"])]
        print(f"Using projections override: {proj_csv} ({len(p)} players)")
        proj = p
    if adp_csv.exists():
        a = pd.read_csv(adp_csv)
        a["key_name"] = [player_key(n, x) for n, x in zip(a["name"], a["pos"])]
        print(f"Using ADP override: {adp_csv} ({len(a)} players)")
        adp = a
    return proj, adp


# ---------------------------------------------------------------------------
# Offline fixture bootstrap from the committed league caches
# ---------------------------------------------------------------------------

def _cache_weekly_points() -> pd.DataFrame:
    """Starter player-weeks from the Sleeper cache, positions resolved from
    lineup slots (QB/RB1/WR2/TE) or, for FLEX slots, the draft cache."""
    slots = json.loads(SLEEPER_CACHE.read_text())["slots"]
    drafts = json.loads(DRAFT_CACHE.read_text())["drafts"]
    pos_by_name = {}
    for d in drafts:
        if d["position"] in ("QB", "RB", "WR", "TE"):
            pos_by_name.setdefault(player_key(d["player_name"], "")[:-1], d["position"])

    rows = []
    for s in slots:
        if s["player_name"] in ("Empty", "") or s["points"] is None:
            continue
        m = _SLOT_RE.match(s["slot"])
        if m:
            pos = m.group(1)
        else:  # FLEX / FLEX2
            pos = pos_by_name.get(player_key(s["player_name"], "")[:-1])
            if pos is None:
                continue
        rows.append({"name": s["player_name"], "pos": pos,
                     "season": s["season"], "week": s["week"],
                     "pts": s["points"]})
    df = pd.DataFrame(rows)
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    df["team"] = None
    # A started player scoring exactly 0 is nearly always a DNP (injury after
    # lineups locked); drop so fixture per-game averages aren't dragged down.
    df = df[df["pts"] != 0.0]
    return df.drop_duplicates(["key_name", "season", "week"]).reset_index(drop=True)


def build_fixtures(data_dir: Path | str = DRAFT_DATA_DIR) -> None:
    """Build an offline dev dataset in data/draft/ from the league caches.

    Projections: 2025 per-game scoring (last-drafted-season points for bench
    players never started) scaled to expected games. ADP: blend of 2025 draft
    slot and projection rank — the realistic "market reprices on last season"
    approximation. This is a DEVELOPMENT fixture: run `cli fetch` for real
    2026 projections/ADP before draft day.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    weekly = _cache_weekly_points()
    weekly.to_parquet(data_dir / "weekly_points.parquet", index=False)

    drafts = json.loads(DRAFT_CACHE.read_text())["drafts"]
    d25 = pd.DataFrame([d for d in drafts if d["season"] == 2025
                        and d["position"] in ("QB", "RB", "WR", "TE")])
    d25["key_name"] = [player_key(n, p) for n, p in zip(d25["player_name"], d25["position"])]

    w25 = weekly[weekly["season"] == 2025]
    pg = (w25.groupby("key_name")
             .agg(name=("name", "first"), pos=("pos", "first"),
                  pg_mean=("pts", "mean"), n_weeks=("pts", "size"))
             .reset_index())

    # Bench-only players: infer per-game scoring from draft slot via the
    # points-vs-pick curve fitted on players we do have data for.
    merged = d25.merge(pg, on="key_name", how="left")
    have = merged.dropna(subset=["pg_mean"])
    slope, intercept = np.polyfit(have["pick"], np.log(have["pg_mean"].clip(lower=1.0)), 1)
    est = np.exp(intercept + slope * merged["pick"])
    merged["pg_mean"] = merged["pg_mean"].fillna(pd.Series(est, index=merged.index))
    merged["pos"] = merged["pos"].fillna(merged["position"])
    merged["name"] = merged["name"].fillna(merged["player_name"])

    # Undrafted-in-2025 players who produced (waiver adds) — keep them too.
    extra = pg[~pg["key_name"].isin(set(merged["key_name"]))].copy()
    extra = extra[extra["n_weeks"] >= 4]
    extra["pick"] = np.nan
    proj = pd.concat([merged[["key_name", "name", "pos", "pg_mean", "pick"]],
                      extra[["key_name", "name", "pos", "pg_mean", "pick"]]],
                     ignore_index=True).drop_duplicates("key_name")

    proj["games"] = proj["pos"].map(EXPECTED_GAMES).fillna(14.5)
    proj["proj"] = (proj["pg_mean"] * proj["games"]).round(1)
    proj["team"] = None

    # Fixture ADP: market reprices on production but anchors on last draft.
    proj_rank = proj["proj"].rank(ascending=False)
    pick_rank = proj["pick"].rank().fillna(proj_rank + 30)
    blend = 0.6 * proj_rank + 0.4 * pick_rank
    proj["adp"] = blend.rank(method="first")
    adp = proj[["key_name", "adp"]].copy()

    proj = proj[["key_name", "name", "pos", "team", "proj", "games"]]
    proj.to_parquet(data_dir / "projections.parquet", index=False)
    adp.to_parquet(data_dir / "adp.parquet", index=False)

    (data_dir / "meta.json").write_text(json.dumps({
        "source": "fixture",
        "note": "Derived from 2024-25 league caches. Run `cli fetch` for real data.",
    }, indent=2))
    print(f"Fixture built: {len(proj)} players with projections, "
          f"{len(weekly)} historical player-weeks -> {data_dir}")
