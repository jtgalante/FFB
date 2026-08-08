"""Build the canonical tables every analysis reads.

Eleven analysis scripts each re-derive the same joins from the raw JSON
caches: manager canonicalization, slot arithmetic, player keys, opponent
resolution. That duplication is where a series of silent data bugs bred. This
script does each join once, validates the result, and writes tidy parquet to
data/warehouse/. Nothing reads these tables yet — migrating those scripts onto
them is the point, and is still to come.

Tables:
    picks         season x round x slot   who drafted whom, where
    team_weeks    season x week x manager scores, WITH the opponent resolved
    player_weeks  season x week x player  NFL scoring under our rules
    rosters       season x week x slot    started lineups (2019+)
    players       player                  name, position, team, age

Opponent resolution deserves a note: the platform exports record your score and
your opponent's score but never the opponent's NAME. Matching a manager's
opponent_points against the other scores in the same week recovers it uniquely
for 99.5% of manager-weeks. A second pass closes the gap to 99.9% without
guessing: where a tie makes my row ambiguous, my opponent's row often names me
unambiguously, and that pairing is deduced rather than assumed. The 2 rows that
remain null are mutually ambiguous on score alone — they are determinable by
elimination, but that needs bipartite matching, which is deliberately not
implemented for two rows of 2498.

KNOWN SOURCE DEFECT, carried into `team_weeks` on purpose: in 18 rows (9 games,
2015/2016/2018, all ESPN) the `win` flag contradicts the two scores — the ESPN
export credits the lower scorer with the win. The contradiction is symmetric,
so both sides of each game are wrong together. It is a defect in the archive,
not in these joins, and silently "fixing" it would rewrite league history, so
the build warns and writes it through unchanged. Anything computing records
from `team_weeks` should decide explicitly whether to trust `win` or to
recompute it from the scores.
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
from src.draft.validate import (check_draft_complete,  # noqa: E402
                                check_seasons_balanced, check_team_codes,
                                check_win_consistency)

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


def resolve_opponents(g: pd.DataFrame) -> dict:
    """Name each row's opponent within one week. Row index -> manager or None.

    Pass 1 matches a row's opponent_points against the other scores in the
    week and accepts the match only when exactly one manager scored it.

    Pass 2 closes the loop by symmetry. A score tie leaves my own row
    ambiguous, but my opponent's row may name me unambiguously; if exactly one
    such row claims me AND its own score is the one I recorded as my
    opponent's, the pairing follows from that row alone. This deduces, it does
    not guess: with no unique claimant the row stays None.
    """
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
    return res


def build_team_weeks() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["weekly"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    opponents = {}
    for _, g in df.groupby(["season", "week", "is_playoff"]):
        opponents.update(resolve_opponents(g))
    df["opponent"] = pd.Series(opponents, dtype=object).reindex(df.index)
    return df[["season", "week", "manager", "opponent", "points",
               "opponent_points", "win", "is_playoff", "platform"]]


def build_rosters() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["slots"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
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

    bad_wins = check_win_consistency(tw, "team_weeks")
    if len(bad_wins):
        seasons = ", ".join(str(s) for s in sorted(bad_wins["season"].unique()))
        print(f"  WARNING: team_weeks has {len(bad_wins)} rows where `win` "
              f"contradicts the scores (seasons {seasons}).\n"
              f"           Source defect in the ESPN export, written through "
              f"unchanged. Recompute from points if you need true records.")

    pw = build_player_weeks()
    check_team_codes(pw, "team", "player_weeks")
    check_seasons_balanced(pw, [2021, 2022, 2023, 2024, 2025], "player_weeks")
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
