"""Network data fetchers for the draft engine.

These hit external services (FantasyPros, Sleeper, nflverse GitHub releases)
and therefore need normal internet access — run `python -m src.draft.cli fetch`
on your laptop. Everything lands in data/draft/ as parquet/CSV; the rest of
the engine only reads those local files, so draft day has zero live
dependencies.

Manual override: drop CSVs in data/inputs/ and they win over anything fetched:
  projections.csv  columns: name, pos, proj  (optional: team, bye, games)
  adp.csv          columns: name, pos, adp
Both FantasyPros pages have CSV export buttons if scraping ever breaks.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

from .ids import player_key

DRAFT_DATA_DIR = Path("data/draft")
INPUTS_DIR = Path("data/inputs")

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ffb-draft-engine/1.0"}

FP_PROJECTION_URL = "https://www.fantasypros.com/nfl/projections/{pos}.php?week=draft&scoring=HALF"
FP_ADP_URL = "https://www.fantasypros.com/nfl/adp/half-point-ppr-overall.php"

NFLVERSE_WEEKLY_PATTERNS = [
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_{year}.parquet",
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_{year}.parquet",
]
NFLVERSE_SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/schedules.csv"
FF_PLAYERIDS_URL = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"


def _get(url: str, **kw) -> requests.Response:
    resp = requests.get(url, headers=_UA, timeout=60, **kw)
    resp.raise_for_status()
    return resp


def fetch_fantasypros_projections() -> pd.DataFrame:
    """Season (draft) projections, half-PPR, positions QB/RB/WR/TE.

    Parses the projection tables; returns columns name, pos, proj.
    """
    frames = []
    for pos in ("qb", "rb", "wr", "te"):
        html = _get(FP_PROJECTION_URL.format(pos=pos)).text
        tables = pd.read_html(io.StringIO(html), attrs={"id": "data"})
        if not tables:
            raise RuntimeError(f"FantasyPros projections table not found for {pos}")
        df = tables[0]
        # Multi-level headers: last row group has ('Unnamed', 'Player') and ('MISC','FPTS')
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ["_".join(str(c) for c in tup if "Unnamed" not in str(c)).strip("_")
                          for tup in df.columns]
        player_col = next(c for c in df.columns if "Player" in c)
        fpts_col = next(c for c in df.columns if "FPTS" in c)
        out = pd.DataFrame({
            "name": df[player_col].astype(str).str.replace(r"\s+[A-Z]{2,3}$", "", regex=True),
            "team": df[player_col].astype(str).str.extract(r"\s+([A-Z]{2,3})$")[0],
            "pos": pos.upper(),
            "proj": pd.to_numeric(df[fpts_col], errors="coerce"),
        }).dropna(subset=["proj"])
        frames.append(out)
        time.sleep(1)
    result = pd.concat(frames, ignore_index=True)
    result["key_name"] = [player_key(n, p) for n, p in zip(result["name"], result["pos"])]
    return result


def fetch_fantasypros_adp() -> pd.DataFrame:
    """Current half-PPR overall ADP. Returns columns name, pos, adp."""
    html = _get(FP_ADP_URL).text
    tables = pd.read_html(io.StringIO(html), attrs={"id": "data"})
    if not tables:
        raise RuntimeError("FantasyPros ADP table not found")
    df = tables[0]
    df.columns = [str(c) for c in df.columns]
    player_col = next(c for c in df.columns if "Player" in c)
    pos_col = next(c for c in df.columns if c.strip().upper() == "POS")
    adp_col = df.columns[-1]  # AVG column is last
    out = pd.DataFrame({
        "name": df[player_col].astype(str)
                 .str.replace(r"\s+\([A-Za-z ]*\)$", "", regex=True)          # strip "(Team Bye)"
                 .str.replace(r"\s+[A-Z]{2,3}(\s+O)?$", "", regex=True),      # strip team suffix
        "pos": df[pos_col].astype(str).str.replace(r"\d+$", "", regex=True),
        "adp": pd.to_numeric(df[adp_col], errors="coerce"),
    }).dropna(subset=["adp"])
    out = out[out["pos"].isin(["QB", "RB", "WR", "TE"])]
    out["key_name"] = [player_key(n, p) for n, p in zip(out["name"], out["pos"])]
    return out


def fetch_sleeper_players() -> pd.DataFrame:
    """Sleeper player DB → name, pos, team, sleeper_id (for live-draft matching)."""
    data = _get("https://api.sleeper.app/v1/players/nfl").json()
    rows = []
    for pid, p in data.items():
        pos = (p.get("position") or "")
        if pos not in ("QB", "RB", "WR", "TE") or not p.get("active", True):
            continue
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        rows.append({"sleeper_id": pid, "name": name, "pos": pos,
                     "team": p.get("team"), "age": p.get("age"),
                     "years_exp": p.get("years_exp")})
    df = pd.DataFrame(rows)
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    return df


def fetch_nflverse_weekly(years: list[int]) -> pd.DataFrame:
    """Weekly player stats from nflverse-data GitHub releases.

    Tries known asset-name patterns per year (nflverse renames occasionally).
    """
    frames = []
    for year in years:
        last_err = None
        for pattern in NFLVERSE_WEEKLY_PATTERNS:
            url = pattern.format(year=year)
            try:
                resp = _get(url)
                frames.append(pd.read_parquet(io.BytesIO(resp.content)))
                last_err = None
                break
            except Exception as e:  # noqa: BLE001 - try next pattern
                last_err = e
        if last_err is not None:
            raise RuntimeError(f"Could not fetch nflverse weekly stats for {year}: {last_err}")
    return pd.concat(frames, ignore_index=True)


def fetch_byes(season: int) -> pd.DataFrame:
    """Team bye weeks for a season from the nflverse schedule file."""
    df = pd.read_csv(io.BytesIO(_get(NFLVERSE_SCHEDULE_URL).content))
    df = df[(df["season"] == season) & (df["game_type"] == "REG")]
    weeks = sorted(df["week"].unique())
    teams = sorted(set(df["home_team"]) | set(df["away_team"]))
    rows = []
    for team in teams:
        played = set(df[(df["home_team"] == team) | (df["away_team"] == team)]["week"])
        bye = [w for w in weeks if w not in played]
        rows.append({"team": team, "bye": bye[0] if bye else None})
    return pd.DataFrame(rows)


def weekly_fantasy_points(weekly: pd.DataFrame, scoring: dict[str, float]) -> pd.DataFrame:
    """Compute per-player-week fantasy points from nflverse stats under the
    league's scoring settings. Returns key_name, season, week, pos, team, pts.
    """
    df = weekly.copy()
    pos_col = "position" if "position" in df.columns else "position_group"
    df = df[df[pos_col].isin(["QB", "RB", "WR", "TE"])]

    def col(name: str) -> pd.Series:
        return pd.to_numeric(df.get(name), errors="coerce").fillna(0.0) if name in df.columns \
            else pd.Series(0.0, index=df.index)

    pts = (
        col("passing_yards") * scoring.get("pass_yd", 0.04)
        + col("passing_tds") * scoring.get("pass_td", 4)
        + (col("interceptions") + col("passing_interceptions")) * scoring.get("pass_int", -1)
        + col("rushing_yards") * scoring.get("rush_yd", 0.1)
        + col("rushing_tds") * scoring.get("rush_td", 6)
        + col("receptions") * scoring.get("rec", 0.5)
        + col("receiving_yards") * scoring.get("rec_yd", 0.1)
        + col("receiving_tds") * scoring.get("rec_td", 6)
        + (col("sack_fumbles_lost") + col("rushing_fumbles_lost")
           + col("receiving_fumbles_lost")) * scoring.get("fum_lost", -2)
        + (col("passing_2pt_conversions") + col("rushing_2pt_conversions")
           + col("receiving_2pt_conversions")) * scoring.get("two_pt", 2)
    )
    name_col = "player_display_name" if "player_display_name" in df.columns else "player_name"
    out = pd.DataFrame({
        "name": df[name_col],
        "pos": df[pos_col],
        "team": df["recent_team"] if "recent_team" in df.columns else df.get("team"),
        "season": df["season"],
        "week": df["week"],
        "pts": pts.round(2),
    })
    out["key_name"] = [player_key(n, p) for n, p in zip(out["name"], out["pos"])]
    return out


def fetch_all(league_years: list[int] | None = None) -> dict[str, Path]:
    """Fetch everything and write to data/draft/. Returns written paths."""
    import yaml as _yaml
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    scoring = _yaml.safe_load(Path("config/league.yaml").read_text()).get("scoring", {})
    years = league_years or [2021, 2022, 2023, 2024, 2025]

    print("Fetching nflverse weekly stats", years, "...")
    weekly = fetch_nflverse_weekly(years)
    pts = weekly_fantasy_points(weekly, scoring)
    p = DRAFT_DATA_DIR / "weekly_points.parquet"
    pts.to_parquet(p, index=False)
    written["weekly_points"] = p
    print(f"  {len(pts)} player-weeks -> {p}")

    print("Fetching FantasyPros projections ...")
    proj = fetch_fantasypros_projections()
    p = DRAFT_DATA_DIR / "projections.parquet"
    proj.to_parquet(p, index=False)
    written["projections"] = p
    print(f"  {len(proj)} players -> {p}")

    print("Fetching FantasyPros ADP ...")
    adp = fetch_fantasypros_adp()
    p = DRAFT_DATA_DIR / "adp.parquet"
    adp.to_parquet(p, index=False)
    written["adp"] = p
    print(f"  {len(adp)} players -> {p}")

    print("Fetching Sleeper players ...")
    players = fetch_sleeper_players()
    p = DRAFT_DATA_DIR / "players.parquet"
    players.to_parquet(p, index=False)
    written["players"] = p
    print(f"  {len(players)} players -> {p}")

    try:
        print("Fetching bye weeks ...")
        byes = fetch_byes(max(years) + 1)
        p = DRAFT_DATA_DIR / "byes.parquet"
        byes.to_parquet(p, index=False)
        written["byes"] = p
    except Exception as e:  # noqa: BLE001 - byes are optional
        print(f"  bye fetch failed ({e}); season sim will randomize byes")

    meta = DRAFT_DATA_DIR / "meta.json"
    meta.write_text(json.dumps({"fetched_at": time.time(), "years": years,
                                "source": "live"}, indent=2))
    return written
