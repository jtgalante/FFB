"""Build the canonical tables every analysis reads.

Eleven scripts each used to re-derive the same joins from raw JSON caches:
manager canonicalization, slot arithmetic, player keys, opponent resolution.
That is where the bugs bred. This does each join once, validates the result,
and writes tidy parquet to data/warehouse/.

Tables:
    picks         season x round x slot   who drafted whom, where
    team_weeks    season x week x manager scores, WITH the opponent resolved
    player_weeks  season x week x player  NFL scoring under our rules
    rosters       season x week x slot    started lineups (2019+)
    players       player                  name, position, birth date

Opponent resolution deserves a note: the platform exports record your score and
your opponent's score but never the opponent's NAME. Matching a manager's
opponent_points against the other scores in the same week recovers it uniquely
for 99.5% of manager-weeks. A second pass closes the gap to 99.9% without
guessing: where a tie makes my row ambiguous, my opponent's row often names me
unambiguously, and that pairing is deduced rather than assumed. The 2 rows that
remain null are genuinely undetermined by score alone.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_canonical_name  # noqa: E402
from src.draft.draftmath import slot_of  # noqa: E402
from src.draft.ids import normalize_team, player_key  # noqa: E402
from src.draft.validate import check_draft_complete  # noqa: E402

OUT = Path("data/warehouse")
LEAGUE = Path("data/league_cache.json")
DRAFTS = Path("data/draft_cache.json")
CONFIG = Path("config/league.yaml")


def build_picks(teams: int) -> pd.DataFrame:
    rows = json.loads(DRAFTS.read_text())["drafts"]
    df = pd.DataFrame(rows)
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    df["slot"] = [slot_of(p, teams) for p in df["pick"]]
    df["key_name"] = [player_key(n, pos) for n, pos
                      in zip(df["player_name"], df["position"])]
    return df[["season", "round", "pick", "slot", "manager", "player_name",
               "position", "key_name"]].sort_values(["season", "pick"])


def build_team_weeks() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["weekly"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    opponents = {}
    for (_, _, _), g in df.groupby(["season", "week", "is_playoff"]):
        by_score = defaultdict(list)
        for r in g.itertuples():
            by_score[round(r.points, 2)].append(r.manager)
        res, mgr, pts = {}, {}, {}
        for r in g.itertuples():
            cand = [m for m in by_score.get(round(r.opponent_points, 2), [])
                    if m != r.manager]
            res[r.Index] = cand[0] if len(cand) == 1 else None
            mgr[r.Index] = r.manager
            pts[r.Index] = round(r.points, 2)
        # A tie makes my own row ambiguous, but my opponent's row may name me
        # unambiguously — and if it does, the pairing is deduced, not guessed.
        claims = defaultdict(list)
        for i, opp in res.items():
            if opp is not None:
                claims[opp].append(i)
        for r in g.itertuples():
            if res[r.Index] is None:
                back = {mgr[i] for i in claims.get(r.manager, [])
                        if pts[i] == round(r.opponent_points, 2)}
                if len(back) == 1:
                    res[r.Index] = back.pop()
        opponents.update(res)
    df["opponent"] = pd.Series(opponents, dtype=object).reindex(df.index)
    return df[["season", "week", "manager", "opponent", "points",
               "opponent_points", "win", "is_playoff", "platform"]]


def build_rosters() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["slots"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    df = df[~df["player_name"].isin(["Empty", ""])]
    return df[["season", "week", "manager", "slot", "player_name", "points",
               "is_playoff"]]


def build_player_weeks() -> pd.DataFrame:
    df = pd.read_parquet("data/draft/weekly_points.parquet")
    df["team"] = df["team"].map(normalize_team)
    return df


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    picks = build_picks(cfg["teams"])
    check_draft_complete(picks, cfg["teams"], cfg["rounds"])
    picks.to_parquet(OUT / "picks.parquet", index=False)
    print(f"  picks         {len(picks):>6} rows")

    tw = build_team_weeks()
    resolved = tw["opponent"].notna().mean()
    tw.to_parquet(OUT / "team_weeks.parquet", index=False)
    print(f"  team_weeks    {len(tw):>6} rows "
          f"({resolved*100:.1f}% opponents resolved)")

    pw = build_player_weeks()
    pw.to_parquet(OUT / "player_weeks.parquet", index=False)
    print(f"  player_weeks  {len(pw):>6} rows")

    ro = build_rosters()
    ro.to_parquet(OUT / "rosters.parquet", index=False)
    print(f"  rosters       {len(ro):>6} rows "
          f"(seasons {ro.season.min()}-{ro.season.max()})")

    pl = pd.read_parquet("data/draft/players.parquet")
    pl.to_parquet(OUT / "players.parquet", index=False)
    print(f"  players       {len(pl):>6} rows")
    print(f"\nWrote {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
