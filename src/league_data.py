"""The dashboard's bridge to the verified league record.

Everything outcome-linked that the dashboard shows — who won, who came last,
where a team really finished in the regular season — comes from here, and from
here only. It exists because the platform exports disagree with what actually
happened, and the disagreement is structural rather than a handful of bad rows:

* **Champions.** ESPN's `finish` field describes a competition this league never
  played. From 2014 the regular season awarded TWO points a week — one for
  winning your matchup and one for placing in the week's top 5 scorers — which
  ESPN cannot represent, so its seeding is not the league's seeding. Since 2023
  the #1 seed also *picks* its own semifinal opponent, which no automated
  bracket read can infer. Measured against the record James verified with the
  league owner, counting `finish == 1` is wrong for 7 of the 10 managers: it
  credits Bryan Cannon with 1 title (he has 3), Matt McCauley with 3 (4), and
  James Galante with 2 (1). The authority is `config/history.yaml`, where every
  one of the 18 seasons (2008-2025) is `verified: true`.

* **Standings.** The true regular-season table is recomputed from weekly scores
  by `scripts.rebuild_standings.standings`, which reproduces the commissioner's
  own spreadsheets EXACTLY for 2019 and 2023.

* **Matchups.** The platform exports record your score and your opponent's
  *score* but never their *name*, so the old "head to head" compared two
  managers' scores in the same week whether or not they played each other.
  `data/warehouse/team_weeks.parquet` now carries a reconstructed `opponent`
  (99.9% of rows; genuine score ties are NULL rather than guessed), so real
  head-to-head is computable — see `analytics.head_to_head`.

    from src import league_data as ld

    ld.champions()               # season, champion, runner_up, sacko, ...
    ld.title_counts()            # manager, championships, runner_ups, sackos
    ld.dual_points_standings()   # season, manager, seed, points, ...
    ld.team_weeks()              # warehouse pass-through, WITH opponent
    ld.picks()                   # warehouse pass-through

Two coverage limits worth knowing, both of which callers should surface rather
than paper over:

1. **Weekly data starts in 2010, the title record starts in 2008.** Anything
   derived from weekly scores (standings, seeds, real matchups) cannot cover
   2008-2009. `champions()` and `title_counts()` do.
2. **`sacko` is only recorded for the seasons where a source names one** (7 of
   18). Sacko counts are therefore a floor, not a total. The last dual-points
   seed is deliberately NOT substituted: the sacko is a toilet-bowl outcome,
   not the bottom of the regular-season table.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from scripts import rebuild_standings as rs
from src.draft import warehouse as wh

# The seasons in config/history.yaml that predate any weekly export. Kept
# explicit so callers can tell "no title that year" from "no data that year".
PRE_PLATFORM_SEASONS = (2008, 2009)


def _roster() -> list[str]:
    """Every canonical manager name, from the warehouse plus the title record.

    Taking the union means a manager who only ever appears in `history.yaml`
    still gets a row (with zeros) instead of silently vanishing from a count.
    """
    names = set(wh.team_weeks()["manager"].dropna().unique())
    for row in rs.load_history().values():
        for key in ("champion", "runner_up", "sacko"):
            if row.get(key):
                names.add(row[key])
    return sorted(names)


def champions() -> pd.DataFrame:
    """The verified outcome of every season, one row per season.

    Columns: season, champion, runner_up, sacko, scoring, source, verified.

    Straight from `config/history.yaml` — NOT from any platform `finish`
    field, for the reasons in this module's docstring. `runner_up` and `sacko`
    are NULL where no source names one; they are not inferred.
    """
    rows = []
    for season, rec in sorted(rs.load_history().items()):
        rows.append({
            "season": int(season),
            "champion": rec.get("champion"),
            "runner_up": rec.get("runner_up"),
            "sacko": rec.get("sacko"),
            "scoring": rec.get("scoring"),
            "source": rec.get("source"),
            "verified": bool(rec.get("verified", False)),
        })
    return pd.DataFrame(rows, columns=[
        "season", "champion", "runner_up", "sacko",
        "scoring", "source", "verified"])


def title_counts(seasons: Iterable[int] | None = None) -> pd.DataFrame:
    """Championships, runner-up finishes and sackos per manager.

    Columns: manager, championships, runner_ups, sackos. Every manager in the
    league gets a row, including those with none of the three.

    `seasons` restricts the window; the default counts the whole verified
    record, so `championships` sums to 18 (2008-2025). Note that sackos are
    only recorded for the seasons where a source names one — see the module
    docstring.
    """
    champs = champions()
    if seasons is not None:
        champs = champs[champs["season"].isin(set(int(s) for s in seasons))]

    counts = {m: {"championships": 0, "runner_ups": 0, "sackos": 0}
              for m in _roster()}
    for _, row in champs.iterrows():
        for col, key in (("champion", "championships"),
                         ("runner_up", "runner_ups"),
                         ("sacko", "sackos")):
            name = row[col]
            if pd.notna(name) and name:
                counts.setdefault(
                    name, {"championships": 0, "runner_ups": 0, "sackos": 0})
                counts[name][key] += 1

    out = pd.DataFrame([{"manager": m, **c} for m, c in counts.items()])
    return out.sort_values(
        ["championships", "runner_ups", "manager"],
        ascending=[False, False, True]).reset_index(drop=True)


def dual_points_standings(season: int | None = None) -> pd.DataFrame:
    """The real regular-season table, recomputed from weekly scores.

    Columns: season, manager, seed, points, h2h_wins, top5_weeks, points_for,
    games, scoring.

    `points` is the league's actual currency: from 2014 a week awards 1 point
    for winning the matchup and 1 for a top-5 weekly score, so `points` is
    `h2h_wins + top5_weeks`. Before 2014 the league played plain head-to-head
    and no bonus is applied — applying it would invent a competition that was
    never played. `seed` is the rank within the season (ties broken by points
    for), 1 = best.

    This is `scripts.rebuild_standings.standings`, which reproduces the
    commissioner's own spreadsheets exactly for 2019 and 2023. Weekly data
    begins in 2010, so 2008-2009 have no standings even though they have a
    verified champion.
    """
    weekly = rs.load_weekly()
    wanted = sorted(weekly) if season is None else [int(season)]

    rows = []
    for yr in wanted:
        if yr not in weekly:
            raise KeyError(
                f"no weekly data for {yr}; have {min(weekly)}-{max(weekly)}")
        system = rs.scoring_system(yr)
        for r in rs.standings(weekly[yr], dual_points=(system == "dual_points")):
            rows.append({
                "season": yr,
                "manager": r["mgr"],
                "seed": r["seed"],
                "points": r["points"],
                "h2h_wins": r["h2h"],
                "top5_weeks": r["top5"],
                "points_for": r["pf"],
                "games": r["games"],
                "scoring": system,
            })
    return pd.DataFrame(rows, columns=[
        "season", "manager", "seed", "points", "h2h_wins", "top5_weeks",
        "points_for", "games", "scoring"]).sort_values(
            ["season", "seed"]).reset_index(drop=True)


def team_weeks() -> pd.DataFrame:
    """Warehouse pass-through: one row per manager per week, WITH `opponent`.

    `opponent` is reconstructed by score-matching inside the week because the
    exports never recorded opponent names. It resolves for 99.9% of rows;
    genuine score ties are NULL and should be excluded, not guessed.
    """
    return wh.team_weeks()


def picks() -> pd.DataFrame:
    """Warehouse pass-through: one row per draft pick, slots already resolved.

    Draft slots must never be re-derived from the platform caches — ESPN and
    Sleeper shuffle slot assignments on import. See `docs/DATA.md`.
    """
    return wh.picks()
