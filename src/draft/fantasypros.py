"""FantasyPros data client.

Three ways in, tried in this order — the first that works wins:

1. **Official API** (`FANTASYPROS_API_KEY` in .env). Partner/public API v2 at
   api.fantasypros.com. Cleanest and most stable. A premium fantasypros.com
   account is not automatically an API key — request one at
   https://www.fantasypros.com/apis/ if the key-based path 401s.

2. **CSV export** (data/inputs/*.csv). Every FantasyPros projections/ADP/ECR
   page has a "Download CSV" button for premium accounts. This path needs no
   key and never breaks; see `docs/DATA.md`. Handled in data.py.

3. **Public page scrape** (sources.py). Fallback when neither above is set up;
   brittle by nature since it depends on page markup.

Endpoint shapes for (1) are documented sparsely and have changed before, so
every call here reports the URL and raw response on failure rather than
silently falling through.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests

from .ids import player_key

API_BASE = "https://api.fantasypros.com/public/v2/json/nfl"
SCORING = "HALF"  # half-PPR


class FantasyProsError(RuntimeError):
    pass


def api_key() -> str | None:
    return os.getenv("FANTASYPROS_API_KEY") or None


def _api_get(path: str, params: dict[str, Any], key: str) -> dict:
    url = f"{API_BASE}{path}"
    resp = requests.get(url, params=params, timeout=45,
                        headers={"x-api-key": key, "Accept": "application/json"})
    if resp.status_code != 200:
        raise FantasyProsError(
            f"{resp.status_code} from {resp.url}\n{resp.text[:400]}")
    return resp.json()


def fetch_consensus_rankings(season: int, key: str,
                             position: str = "ALL") -> pd.DataFrame:
    """Expert Consensus Rankings (ECR) for a draft.

    ECR is the experts' fair-value ordering — distinct from ADP, which is what
    the market actually charges. The engine wants both: ECR feeds the alpha
    model, ADP feeds the price/option-value model.
    """
    data = _api_get(f"/{season}/consensus-rankings",
                    {"type": "draft", "scoring": SCORING,
                     "position": position, "week": 0}, key)
    players = data.get("players") or data.get("rankings") or []
    if not players:
        raise FantasyProsError(f"No players in ECR response; keys={list(data)}")
    rows = []
    for p in players:
        pos = (p.get("player_position_id") or p.get("position_id") or "").upper()
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        rows.append({
            "name": p.get("player_name") or p.get("name"),
            "pos": pos,
            "team": p.get("player_team_id") or p.get("team_id"),
            "ecr": _num(p.get("rank_ecr") or p.get("rank")),
            "ecr_sd": _num(p.get("rank_std") or p.get("stdev")),
            "ecr_best": _num(p.get("rank_min")),
            "ecr_worst": _num(p.get("rank_max")),
            "bye": _num(p.get("player_bye_week")),
            "fantasypros_id": p.get("player_id") or p.get("fpid"),
        })
    df = pd.DataFrame(rows).dropna(subset=["name", "ecr"])
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    return df


def fetch_projections(season: int, key: str) -> pd.DataFrame:
    """Season-long projected fantasy points under half-PPR."""
    frames = []
    for pos in ("QB", "RB", "WR", "TE"):
        data = _api_get(f"/{season}/projections",
                        {"position": pos, "week": "draft", "scoring": SCORING}, key)
        players = data.get("players") or []
        rows = []
        for p in players:
            stats = p.get("stats") or p
            pts = _num(stats.get("points") or stats.get("fpts") or p.get("points"))
            if pts is None:
                continue
            rows.append({
                "name": p.get("name") or p.get("player_name"),
                "pos": pos,
                "team": p.get("team_id") or p.get("player_team_id"),
                "proj": pts,
                "games": _num(stats.get("games")) or None,
            })
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        raise FantasyProsError("No projection rows returned for any position")
    df = pd.concat(frames, ignore_index=True)
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    return df


def fetch_adp(season: int, key: str) -> pd.DataFrame:
    """FantasyPros consensus ADP (their blend across host sites)."""
    data = _api_get(f"/{season}/adp", {"scoring": SCORING, "position": "ALL"}, key)
    players = data.get("players") or data.get("adp") or []
    rows = []
    for p in players:
        pos = (p.get("player_position_id") or p.get("position_id") or "").upper()
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        rows.append({
            "name": p.get("player_name") or p.get("name"),
            "pos": pos,
            "adp": _num(p.get("adp") or p.get("rank_ave")),
        })
    df = pd.DataFrame(rows).dropna(subset=["name", "adp"])
    if df.empty:
        raise FantasyProsError(f"No ADP rows; response keys={list(data)}")
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    return df


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Sleeper ADP — the market price that actually matters for a Sleeper league
# ---------------------------------------------------------------------------

def fetch_sleeper_adp(season: int, teams: int = 10,
                      scoring: str = "half_ppr") -> pd.DataFrame:
    """Real ADP from completed Sleeper drafts of the matching format.

    Sleeper has no documented public ADP endpoint, so this reads their
    published mock/real draft aggregates. If it fails, FantasyPros ADP or a
    CSV export covers the same need — ADP sources agree closely at the top.
    """
    url = f"https://api.sleeper.app/v1/players/nfl/adp/{scoring}/{season}"
    resp = requests.get(url, timeout=45,
                        headers={"User-Agent": "ffb-draft-engine/1.0"})
    if resp.status_code != 200:
        raise FantasyProsError(f"Sleeper ADP unavailable ({resp.status_code} {url})")
    data = resp.json()
    rows = []
    for entry in (data if isinstance(data, list) else data.get("adp", [])):
        pos = (entry.get("position") or "").upper()
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        rows.append({
            "name": entry.get("full_name") or entry.get("name"),
            "pos": pos,
            "adp": _num(entry.get("adp") or entry.get("adp_half_ppr")),
            "sleeper_id": entry.get("player_id"),
        })
    df = pd.DataFrame(rows).dropna(subset=["name", "adp"])
    if df.empty:
        raise FantasyProsError("Sleeper ADP returned no usable rows")
    df["key_name"] = [player_key(n, p) for n, p in zip(df["name"], df["pos"])]
    return df
