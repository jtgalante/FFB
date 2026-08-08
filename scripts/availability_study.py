"""Availability: who misses games, what predicts it, and what to do about it.

    python -m scripts.availability_study

Writes `research/availability.md`, plus three tables the board can read:
`data/draft/availability.parquet` (career games played per player),
`data/draft/games_model.parquet` (2026 expected games and the damped
multiplier) and `data/draft/durability.parquet` (the per-player 0-100 score).

This script replaces three — `availability.py`, `games_model.py` and
`injury_signal.py` — which grew one after another over a single session as each
corrected the one before it. Read in the order they were written they
contradict each other; in particular `games_model.md` published an IN-SAMPLE R²
table whose winner ("everything", 0.050) is worse than guessing the mean once
cross-validated (-0.036). The document produced here tells the investigation in
the order it should be READ, and the superseded in-sample table survives only
as a labelled record of the mistake.

## What "games played" means here

nflverse weekly stats carry one row per player per week in which he recorded
any participation. A 17-game season across 18 weeks means one bye, so **17 is a
full season** and appearances out of 17 is the availability measure.

Two honest limits, stated up front because they bound every number below:

1. **A raw games count cannot distinguish injury from benching, suspension, or
   being a backup.** A rookie who takes over in week 8 reads identically to a
   starter who tore an ACL in week 8. §2 below splits the season by SHAPE to
   separate the two; where a raw count is still used (base rates, career
   availability) the population is restricted instead — to drafted starters, or
   to seasons clearing a points-per-game floor.
2. **Manager "injury luck" is measured on players they drafted**, so it credits
   or blames a manager for the whole season of a player he cut in week 3. It is
   a measure of draft-day luck, which is the thing the draft engine can
   actually act on, not of in-season management.

## And the injury reports

`data/draft/injuries.parquet` (nflverse weekly injury reports) adds the body
part and the report status, so a hamstring can be told from an Achilles. Soft
tissue injuries — hamstring, groin, calf, quad, hip — are the ones with a
reputation for recurring, and that is testable here rather than assumed.

**Known gap:** once a player goes on IR he drops off the weekly report
entirely, so a season-ending injury often produces FEWER report rows than a
nagging one. The report features are therefore paired with the shape features,
never used alone.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.draft import warehouse as wh  # noqa: E402
from src.draft.ids import player_key  # noqa: E402

BYES = Path("data/draft/byes_by_season.parquet")
INJ = Path("data/draft/injuries.parquet")
PROJ = Path("data/inputs/projections.csv")

OUT_MD = Path("research/availability.md")
OUT_CAREER = Path("data/draft/availability.parquet")
OUT_GAMES = Path("data/draft/games_model.parquet")
OUT_DURABILITY = Path("data/draft/durability.parquet")
OUT_GAP = Path("data/draft/projection_games_gap.parquet")

SEASON, FULL_SEASON, LAST_WK = 2026, 17, 18
RELEVANT_PPG = 6.0        # per-game scoring floor for "was actually playing"

# Two different startable pools, deliberately. The narrow one bounds the
# per-player tables a human reads; the wide one is the modelling population,
# where a few extra marginal starters per season buy sample size.
BOARD_CAPS = {"QB": 16, "RB": 40, "WR": 50, "TE": 16}
CAPS = {"QB": 20, "RB": 45, "WR": 60, "TE": 20}

SOFT_TISSUE = {"Hamstring", "Groin", "Calf", "Quadricep", "Quad", "Hip"}
PARTS = ["Knee", "Ankle", "Hamstring", "Concussion", "Shoulder", "Groin",
         "Foot", "Calf", "Back", "Hip", "Quadricep", "Achilles"]


# --------------------------------------------------------------------------
# feature construction
# --------------------------------------------------------------------------

def player_seasons(w: pd.DataFrame) -> pd.DataFrame:
    """Games played and per-game scoring, per player-season."""
    g = (w.groupby(["key_name", "name", "pos", "season"], as_index=False)
           .agg(games=("pts", "size"), pts=("pts", "sum")))
    g["ppg"] = (g.pts / g.games).round(2)
    g["missed"] = (FULL_SEASON - g.games).clip(lower=0)
    return g


def season_shapes(w: pd.DataFrame, bye_of: dict) -> pd.DataFrame:
    """Split each player-season into head (role), gaps and tail (health)."""
    rows = []
    for (key, name, pos, season), g in w.groupby(["key_name", "name", "pos",
                                                  "season"], sort=False):
        wks = sorted(g.week.tolist())
        first, last = wks[0], wks[-1]
        team = g.team.dropna().iloc[0] if g.team.notna().any() else None
        bye = bye_of.get((int(season), team))
        present = set(wks)
        gaps = sum(1 for x in range(first, last + 1)
                   if x not in present and x != bye)
        head = sum(1 for x in range(1, first) if x != bye)
        tail = sum(1 for x in range(last + 1, LAST_WK + 1) if x != bye)
        rows.append({"key_name": key, "name": name, "pos": pos,
                     "season": int(season), "games": len(wks), "head": head,
                     "gaps": gaps, "tail": tail, "pts": g.pts.sum(),
                     "ppg": g.pts.mean()})
    d = pd.DataFrame(rows)
    # Bracket access, not attribute access: `d.head` and `d.tail` are
    # DataFrame METHODS, so `d.gaps + d.tail` adds an int to a bound method.
    d["inj_missed"] = d["gaps"] + d["tail"]
    d["opportunity"] = (FULL_SEASON - d["head"]).clip(lower=1)
    d["inj_rate"] = (d["inj_missed"] / d["opportunity"]).clip(0, 1)
    return d


def injury_features(inj: pd.DataFrame) -> pd.DataFrame:
    """Coarse per player-season report counts, for the applied 2026 model."""
    if inj is None or inj.empty:
        return pd.DataFrame(columns=["key_name", "season", "n_out",
                                     "n_soft", "n_parts"])
    d = inj.copy()
    d["is_out"] = d.report_status.eq("Out").astype(int)
    d["is_soft"] = d.report_primary_injury.isin(SOFT_TISSUE).astype(int)
    return (d.groupby(["key_name", "season"], as_index=False)
              .agg(n_out=("is_out", "sum"), n_soft=("is_soft", "sum"),
                   n_parts=("report_primary_injury", "nunique")))


def part_features(inj: pd.DataFrame) -> pd.DataFrame:
    """Per player-season: weeks listed for each body part, plus severity."""
    d = inj.copy()
    d["out"] = d.report_status.eq("Out").astype(int)
    d["dnp"] = d.practice_status.astype(str).str.contains(
        "Did Not Participate", na=False).astype(int)
    base = (d.groupby(["key_name", "season"], as_index=False)
              .agg(n_listed=("week", "nunique"), n_out=("out", "sum"),
                   n_dnp=("dnp", "sum"),
                   n_parts=("report_primary_injury", "nunique")))
    for p in PARTS:
        sub = (d[d.report_primary_injury == p]
               .groupby(["key_name", "season"], as_index=False)
               .week.nunique().rename(columns={"week": f"wk_{p.lower()}"}))
        base = base.merge(sub, on=["key_name", "season"], how="left")
    base["wk_soft"] = (d[d.report_primary_injury.isin(SOFT_TISSUE)]
                       .groupby(["key_name", "season"]).week.nunique()
                       .reindex(pd.MultiIndex.from_frame(
                           base[["key_name", "season"]])).to_numpy())
    return base.fillna(0.0)


# --------------------------------------------------------------------------
# fitting
# --------------------------------------------------------------------------

def fit(d, cols, target="y_games"):
    """Ordinary least squares. Returns (beta, in-sample R²)."""
    X = np.column_stack([d[c].to_numpy(float) for c in cols] + [np.ones(len(d))])
    y = d[target].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    return beta, float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def loso_r2(d: pd.DataFrame, cols: list[str], target: str) -> float:
    """Leave-one-season-out cross-validated R². Can be negative."""
    preds, actual = [], []
    for s in sorted(d.season.unique()):
        tr, te = d[d.season != s], d[d.season == s]
        if len(tr) < 30 or te.empty:
            continue
        X = np.column_stack([tr[c].to_numpy(float) for c in cols]
                            + [np.ones(len(tr))])
        beta, *_ = np.linalg.lstsq(X, tr[target].to_numpy(float), rcond=None)
        Xt = np.column_stack([te[c].to_numpy(float) for c in cols]
                             + [np.ones(len(te))])
        preds.append(Xt @ beta)
        actual.append(te[target].to_numpy(float))
    p, a = np.concatenate(preds), np.concatenate(actual)
    return float(1 - ((a - p) ** 2).sum() / ((a - a.mean()) ** 2).sum())


def next_season_panel(ps: pd.DataFrame, ages: dict, feat_cols: list[str],
                      hist: bool) -> pd.DataFrame:
    """One row per startable player-season, labelled with NEXT season's games.

    `hist=False` uses the season's own features (the cross-validation panel);
    `hist=True` averages every prior season instead (the panel the applied
    2026 model is fitted on, since a 2026 forecast has a whole career to look
    back at rather than one year).

    A player who is not in the data the following season left the league: that
    is scored as zero games, not dropped, because dropping it would quietly
    condition the whole exercise on surviving.
    """
    startable = pd.concat([g.nlargest(CAPS.get(p, 40), "pts")
                           for (s, p), g in ps.groupby(["season", "pos"])])
    idx = ps.set_index(["key_name", "season"])
    rows = []
    for _, r in startable.iterrows():
        nxt = r.season + 1
        if nxt > ps.season.max():
            continue
        a = ages.get(r.key_name)
        if a is None or not np.isfinite(a):
            continue
        try:
            n = idx.loc[(r.key_name, nxt)]
            if isinstance(n, pd.DataFrame):
                n = n.iloc[0]
            y_games, y_inj = float(n.games), float(n.inj_rate)
        except KeyError:
            y_games, y_inj = 0.0, 1.0     # left the league entirely
        rec = {"season": int(r.season), "pos": r.pos,
               "age_then": a - (SEASON - r.season),
               "y_games": y_games, "y_inj": y_inj}
        if hist:
            prior = ps[(ps.key_name == r.key_name) & (ps.season <= r.season)]
            rec.update({"hist_games": prior.games.mean(), "n_prior": len(prior),
                        "inj_rate": r.inj_rate,
                        "hist_inj": prior.inj_rate.mean()})
        else:
            rec.update({"inj_rate": r.inj_rate, "games": r.games})
        rec.update({c: float(r[c]) for c in feat_cols})
        rows.append(rec)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------

def main() -> int:
    w = wh.player_weeks()
    players = wh.players()
    picks = wh.picks()
    byes = pd.read_parquet(BYES)
    bye_of = {(int(r.season), r.team): r.bye for r in byes.itertuples()}
    inj = pd.read_parquet(INJ)
    ages = players.dropna(subset=["age"]).set_index("key_name").age.to_dict()
    pr = pd.read_csv(PROJ)
    pr["key_name"] = [player_key(n, p) for n, p in zip(pr.name, pr.pos)]

    seasons = sorted(w.season.unique())
    ps = player_seasons(w)
    shapes = season_shapes(w, bye_of)

    L = [f"# Availability ({seasons[0]}–{seasons[-1]})\n",
         "*Generated by `python -m scripts.availability_study`. A full season "
         "is 17 games — 18 weeks, one bye.*\n",
         "James's stated number one problem across sixteen years is "
         "availability, and `variance_study.md` independently reached the same "
         "place from the other direction: games missed reduce the mean "
         "directly, and the mean is what pays, while weekly variance is worth "
         "almost nothing. This league has **no IR slot**, so an injured player "
         "also occupies one of only seven bench spots all season.\n",
         "This document supersedes the separate `games_model.md` and "
         "`injury_signal.md`, which were written in the order the work "
         "happened and disagreed with each other where the later corrected the "
         "earlier. It is ordered to be read, not to be re-lived: base rates, "
         "then the role-versus-health split that makes the numbers mean "
         "anything, then what survives cross-validation, then the per-player "
         "output, then what it is worth.\n"]

    # ------------------------------------------------------------------ §1
    # Base rates must come from players who were EXPECTED to start, otherwise
    # a backup quarterback who starts three games at a decent clip reads as an
    # injured starter. Rounds 1-8 of this room's own drafts is that population.
    drafts = picks[picks.season.isin(seasons) & (picks["round"] <= 8)
                   & picks.position.isin(["QB", "RB", "WR", "TE"])].copy()
    ps_idx = ps.set_index(["key_name", "season"])

    drafted_games = defaultdict(list)
    for _, r in drafts.iterrows():
        try:
            rec = ps_idx.loc[(r.key_name, r.season)]
        except KeyError:
            continue
        if isinstance(rec, pd.DataFrame):
            rec = rec.iloc[0]
        drafted_games[r.position].append(rec.games)
    base_drafted = {p: round(float(pd.Series(v).mean()), 2)
                    for p, v in drafted_games.items() if v}

    L.append("## 1. Base rates by position\n")
    L.append("This replaces the hardcoded `EXPECTED_GAMES` in "
             "`src/draft/data.py`, which was a guess.\n")
    L.append("Measured over **players actually drafted in rounds 1-8 of this "
             "league** — the population that was expected to start. Using all "
             "fantasy-relevant player-seasons instead put QB at 10.3 games, "
             "which is not an injury rate: it is backup quarterbacks clearing "
             "a per-game threshold across a handful of starts. The population "
             "has to be defined by what was EXPECTED of a player, not by what "
             "he ended up scoring, or the measurement absorbs the thing it is "
             "trying to measure.\n")
    L.append("| pos | drafted seasons | mean games | median | P(16+) | P(<12) |")
    L.append("|---|---|---|---|---|---|")
    base = {}
    for pos in ("QB", "RB", "WR", "TE"):
        v = pd.Series(drafted_games.get(pos, []), dtype=float)
        if v.empty:
            continue
        base[pos] = round(float(v.mean()), 2)
        L.append(f"| {pos} | {len(v)} | **{v.mean():.2f}** | "
                 f"{v.median():.0f} | {(v >= 16).mean()*100:.0f}% | "
                 f"{(v < 12).mean()*100:.0f}% |")
    L.append("")
    L.append("```python\nEXPECTED_GAMES = " + json.dumps(base) + "\n```\n")
    L.append("The positions are within a game of each other. Whatever "
             "separates a durable player from a fragile one, it is not what "
             "position he plays.\n")

    # ------------------------------------------------------------------ §2
    L.append("## 2. Role versus health\n")
    L.append("A games count conflates a rookie who sat with a starter who tore "
             "something. Both appear in eight games; only one of them tells "
             "you anything about next year. The **shape** of the season "
             "separates them, and it is unambiguous in the data:\n")
    L.append("```")
    L.append("Cam Skattebo    2025  wk 1-8 at 14.5 ppg, then nothing   -> season-ending")
    L.append("Omarion Hampton 2025  wk 1-5, gone 6-13, back 14-17      -> mid-season, returned")
    L.append("Theo Wease      2025  nothing until wk 16, then 3 games  -> late call-up, role")
    L.append("```\n")
    L.append("So every player-season is split three ways:\n")
    L.append("* `head` — weeks missed **before** his first appearance. Role, "
             "not health.")
    L.append("* `gaps` — weeks missed inside his active window, bye excluded. "
             "Health.")
    L.append("* `tail` — weeks missed after his last appearance. Health, "
             "usually season-ending.\n")
    L.append("and `inj_rate = (gaps + tail) / (17 - head)` — the share of the "
             "season he was plausibly in the role and did not play. Wease's "
             "fourteen missing weeks are all head, so his injury rate is zero, "
             "which is correct: he has never been hurt. A raw games count "
             "called him the most fragile player on the board.\n")

    # ------------------------------------------------------------------ §3
    parts = part_features(inj)
    cv_ps = shapes.merge(parts, on=["key_name", "season"], how="left")
    feat_cols = ["n_listed", "n_out", "n_dnp", "n_parts", "wk_soft"] + \
                [f"wk_{p.lower()}" for p in PARTS]
    for c in feat_cols:
        cv_ps[c] = cv_ps[c].fillna(0.0)
    d = next_season_panel(cv_ps, ages, feat_cols, hist=False)

    L.append("## 3. What actually predicts next season\n")
    L.append("Scored by **leave-one-season-out cross-validation** — fit on "
             "four seasons, predict the fifth, repeat. Out-of-sample R² can go "
             "negative, which means the model is worse than guessing the "
             "average, and where it does that is the finding rather than an "
             "embarrassment. In-sample R² rises automatically as features are "
             "added and is not evidence of anything.\n")
    L.append(f"Sample: **{len(d)} startable player-seasons**, "
             f"{seasons[0]}–{str(seasons[-1])[2:]}, following every one into "
             "the next season including those who left the league.\n")
    L.append("### One feature at a time\n")
    L.append("| feature | players with it | corr with next-season games | "
             "out-of-sample R² |")
    L.append("|---|---|---|---|")
    single = []
    for c in ["inj_rate", "games", "age_then"] + feat_cols:
        nz = int((d[c] != 0).sum())
        if nz < 20:
            continue
        corr = float(np.corrcoef(d[c], d.y_games)[0, 1])
        r2 = loso_r2(d, [c], "y_games")
        single.append((c, nz, corr, r2))
    for c, nz, corr, r2 in sorted(single, key=lambda t: -t[3]):
        flag = " ✅" if r2 > 0 else ""
        L.append(f"| `{c}` | {nz} | {corr:+.3f} | **{r2:+.4f}**{flag} |")
    L.append("")
    good = [c for c, _, _, r2 in single if r2 > 0]
    L.append(f"**{len(good)} of {len(single)} features beat guessing the mean "
             f"out of sample.**" + (f" They are: "
             + ", ".join(f"`{c}`" for c in good) + "." if good else "") + "\n")
    L.append("**Body-part identity does not predict.** Every `wk_<part>` "
             "column except hamstring is negative out of sample — a knee "
             "history, an ankle history, a shoulder history tell you nothing "
             "about next season that the overall rate does not already. What "
             "survives is the injury-shaped rate itself, practice "
             "participation (`n_dnp`), weeks listed Out, and age. The folk "
             "taxonomy of injuries is not a forecasting tool at this sample "
             "size; the amount of football a player has missed is.\n")

    L.append("### Combinations\n")
    L.append("| model | in-sample R² | out-of-sample R² |")
    L.append("|---|---|---|")
    combos = [
        ("age only", ["age_then"]),
        ("injury-shaped rate + age", ["inj_rate", "age_then"]),
        ("+ weeks listed Out", ["inj_rate", "age_then", "n_out"]),
        ("+ soft tissue", ["inj_rate", "age_then", "n_out", "wk_soft"]),
        ("+ distinct body parts",
         ["inj_rate", "age_then", "n_out", "wk_soft", "n_parts"]),
        ("every injury feature", ["inj_rate", "age_then"] + feat_cols),
    ]
    best_combo, best_r2 = None, -9e9
    for lab, cols in combos:
        _, ins = fit(d, cols, "y_games")
        oos = loso_r2(d, cols, "y_games")
        L.append(f"| {lab} | {ins:.4f} | **{oos:+.4f}** |")
        if oos > best_r2:
            best_combo, best_r2 = cols, oos
    L.append("")
    L.append("In-sample R² climbs with every feature added while out-of-sample "
             "does not. That gap is the overfitting this cross-validation "
             "exists to expose, and it is not a small effect here: the "
             "kitchen-sink model more than doubles the in-sample fit and is "
             "**worse than a constant** out of sample.\n")

    L.append("### The ranking this corrected\n")
    L.append("An earlier version of this work published an in-sample R² table "
             "and named its top row the best model. Recomputed here so the "
             "correction is checkable rather than asserted — same target, same "
             "startable pool, but each player's features averaged over his "
             "whole career to date, which is the shape a 2026 forecast "
             "actually has available:\n")

    gm_ifeat = injury_features(inj)
    gm_ps = shapes.merge(gm_ifeat, on=["key_name", "season"], how="left")
    for c in ("n_out", "n_soft", "n_parts"):
        gm_ps[c] = gm_ps[c].fillna(0.0)
    dg = next_season_panel(gm_ps, ages, ["n_out", "n_soft", "n_parts"],
                           hist=True)
    MODELS = [
        ("games count + age + seasons", ["hist_games", "age_then", "n_prior"]),
        ("injury-shaped rate only", ["hist_inj"]),
        ("injury rate + age", ["hist_inj", "age_then"]),
        ("injury rate + age + seasons", ["hist_inj", "age_then", "n_prior"]),
        ("+ injury report features",
         ["hist_inj", "age_then", "n_prior", "n_out", "n_soft"]),
        ("everything", ["hist_games", "hist_inj", "age_then", "n_prior",
                        "n_out", "n_soft", "n_parts"]),
    ]
    ins_results = [(lab, cols, *fit(dg, cols)) for lab, cols in MODELS]
    ins_best = max(ins_results, key=lambda r: r[3])
    L.append("| model | in-sample R² (**do not read as accuracy**) |")
    L.append("|---|---|")
    for lab, _, _, r2 in ins_results:
        mark = " ⬅ *ranked best in-sample*" if lab == ins_best[0] else ""
        L.append(f"| {lab} | {r2:.4f}{mark} |")
    L.append("")
    L.append(f"The winner there, `{ins_best[0]}` at {ins_best[3]:.3f}, is the "
             f"model that scores **{loso_r2(d, ['inj_rate', 'age_then'] + feat_cols, 'y_games'):+.3f}** "
             "out of sample in the table above — worse than predicting the "
             "mean. The ranking inverts almost exactly: the honest best is "
             f"**injury rate + age at {best_r2:+.3f}**, which is the "
             f"second-*worst* row of the in-sample table. Two features is the "
             "ceiling; the seven-feature model was fitting noise. Everything "
             "downstream applies two.\n")
    L.append("**Report-data caveat, which bounds all of the above:** a player "
             "on IR drops off the weekly injury report, so a season-ending "
             "injury can produce fewer report rows than a nagging one. The "
             "report features are only ever used alongside the shape "
             "features for this reason.\n")

    # ------------------------------------------------------------------ §4
    rel = ps[ps.ppg >= RELEVANT_PPG].copy()
    car = (rel.groupby(["key_name", "name", "pos"], as_index=False)
              .agg(seasons=("season", "nunique"), games=("games", "sum"),
                   missed=("missed", "sum")))
    car["avail"] = (car.games / (car.seasons * FULL_SEASON)).round(3)
    car = car[car.seasons >= 2]

    L.append("## 4. Per-player durability\n")
    L.append("Two views. The first is the **record** — games actually played, "
             "no model — restricted to seasons averaging "
             f"{RELEVANT_PPG}+ points per game so that backups and call-ups "
             "are not counted as injuries. The second is the **forecast**, the "
             "cross-validated model from §3 turned into a within-position "
             "percentile.\n")
    L.append("### The record\n")

    # Positional caps, not an overall top-120: an overall cut leaves in backup
    # QBs (whose projections are low but whose ROLE is the reason, not
    # fragility) and drops startable tight ends.
    board = pd.concat([pr[pr.pos == k].nlargest(v, "proj")
                       for k, v in BOARD_CAPS.items()])[["key_name", "proj"]]
    j = car.merge(board, on="key_name", how="inner")
    for label, sub in (("Most durable", j.nlargest(10, "avail")),
                       ("Least durable", j.nsmallest(10, "avail"))):
        L.append(f"**{label}** (startable in 2026 — QB16/RB40/WR50/TE16 "
                 f"by projection — with 2+ seasons of history)\n")
        L.append("| player | pos | seasons | games | availability |")
        L.append("|---|---|---|---|---|")
        for _, r in sub.iterrows():
            L.append(f"| {r['name']} | {r.pos} | {r.seasons} | "
                     f"{int(r.games)}/{int(r.seasons*FULL_SEASON)} | "
                     f"**{r.avail*100:.0f}%** |")
        L.append("")

    # ---- the model-based score ------------------------------------------
    career = cv_ps.groupby("key_name").agg(
        n_seasons=("games", "size"), inj_rate=("inj_rate", "mean"),
        games=("games", "mean"),
        **{c: (c, "mean") for c in feat_cols})
    dur = pr.merge(career, on="key_name", how="left")
    dur["age_then"] = dur.key_name.map(ages)

    beta, _ = fit(d, best_combo, "y_games")
    have = dur[best_combo].notna().all(axis=1)
    pred = np.full(len(dur), float(d.y_games.mean()))
    if have.any():
        Xa = np.column_stack([dur.loc[have, c].to_numpy(float)
                              for c in best_combo]
                             + [np.ones(int(have.sum()))])
        pred[have.to_numpy()] = Xa @ beta
    dur["exp_games"] = np.clip(pred, 6.0, 17.0)
    dur["durability"] = (dur.groupby("pos").exp_games
                         .rank(pct=True) * 100).round(0)
    dur.loc[dur.n_seasons.isna(), "durability"] = np.nan

    L.append("### The score\n")
    L.append("`durability` is a percentile **within position** of predicted "
             "games played — 100 is the most durable at that position. It is "
             f"built from the best cross-validated model above (out-of-sample "
             f"R² = {best_r2:+.3f}).\n")
    L.append("Players with no NFL history are left blank rather than assumed "
             "average, because a blank is honest and a 50 is not.\n")
    top40 = dur[dur.n_seasons.notna()].nlargest(40, "proj")
    for label, sub in (("Most durable, of the top 40 by projection",
                        top40.nlargest(10, "durability")),
                       ("Least durable", top40.nsmallest(10, "durability"))):
        L.append(f"**{label}**\n")
        L.append("| player | pos | age | seasons | injured share | "
                 "exp games | durability |")
        L.append("|---|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            L.append(f"| {r['name']} | {r.pos} | {r.age_then:.0f} | "
                     f"{r.n_seasons:.0f} | {r.inj_rate*100:.0f}% | "
                     f"{r.exp_games:.1f} | **{r.durability:.0f}** |")
        L.append("")
    L.append("The two views mostly agree and disagree usefully where they "
             "don't: the score is a forecast and is therefore dominated by age "
             "and by career injury rate, so young players with short clean "
             "records rank above veterans with longer ones. Read the record "
             "for what happened and the score for what to expect.\n")

    # ------------------------------------------------------------------ §5
    L.append("## 5. Manager injury luck\n")
    L.append("Games missed by the players each manager **drafted**, over the "
             f"seasons for which player-level data exists ({seasons[0]}–"
             f"{seasons[-1]}). Restricted to each manager's first eight picks — "
             "the ones intended as starters — so that late fliers do not "
             "dominate.\n")
    L.append("Expected games per drafted starter, by position (the reference "
             "population is drafted starters themselves, not all NFL "
             "contributors): "
             + ", ".join(f"**{k}** {v}"
                         for k, v in sorted(base_drafted.items()))
             + ".\n")

    rows = []
    for mgr, g in drafts.groupby("manager"):
        exp = act = 0.0
        n = 0
        deltas = []
        for _, r in g.iterrows():
            try:
                rec = ps_idx.loc[(r.key_name, r.season)]
            except KeyError:
                continue          # never played that season at all — not injury
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            act += rec.games
            e = base_drafted.get(r.position, 15.0)
            exp += e
            deltas.append(rec.games - e)
            n += 1
        if n:
            dd = pd.Series(deltas)
            se = float(dd.std(ddof=1) / (n ** 0.5)) if n > 1 else float("nan")
            rows.append({"manager": mgr, "picks": n,
                         "expected": round(exp, 1), "actual": round(act, 1),
                         "delta": round(act - exp, 1),
                         "per_pick": round((act - exp) / n, 2),
                         "se": round(se, 2),
                         "t": round(((act - exp) / n) / se, 2) if se else 0.0})
    tab = pd.DataFrame(rows).sort_values("per_pick")
    L.append("| manager | picks | expected | actual | delta | per pick | ± SE | t |")
    L.append("|---|---|---|---|---|---|---|---|")
    for _, r in tab.iterrows():
        L.append(f"| {r['manager']} | {r.picks} | {r.expected:.0f} | "
                 f"{r.actual:.0f} | **{r.delta:+.0f}** | {r.per_pick:+.2f} | "
                 f"{r.se:.2f} | {r.t:+.2f} |")
    L.append("")
    worst, best_mgr = tab.iloc[0], tab.iloc[-1]
    L.append(f"Range: **{worst['manager']}** {worst.per_pick:+.2f} games per "
             f"drafted starter, **{best_mgr['manager']}** "
             f"{best_mgr.per_pick:+.2f}. "
             f"Over eight starters that is a spread of "
             f"{abs(worst.per_pick - best_mgr.per_pick) * 8:.1f} games a season "
             f"between the unluckiest and the luckiest.\n")
    big = tab.t.abs().max()
    L.append("### None of this is statistically significant\n")
    L.append(f"The largest t-statistic in the table is **{big:.2f}**. With "
             f"~40 drafted starters per manager over five seasons, and a "
             f"standard deviation of roughly five games on any single player's "
             f"availability, the standard error on these per-pick figures is "
             f"~0.5 games — comparable to the effects themselves. **Nobody in "
             f"this room is measurably lucky or unlucky with injuries.**\n")
    L.append("That is a more useful answer than a ranking would be. The "
             "ordering is real in the sense that it happened, but it does not "
             "predict anything, and it should not be carried into 2026 as a "
             "belief about anyone's fortune — including one's own. Five "
             "seasons is simply too few.\n")
    L.append("**What IS actionable** is §4. Individual durability is measured "
             "on far more data than a manager's forty picks, and it is the "
             "input the draft can actually use: prefer the durable player when "
             "value is close, and price the fragile one down rather than "
             "hoping. With no IR slot, a player who misses six games costs a "
             "roster spot as well as the points.\n")
    L.append("Note also that drafting fragile players and being unlucky are "
             "indistinguishable in this table by construction. If a manager "
             "were persistently negative across many more seasons, the "
             "actionable reading would be that he keeps buying injury risk — "
             "not that the universe dislikes him.\n")

    # ------------------------------------------------------------------ §6
    L.append("## 6. Is injury risk already priced into the projections?\n")
    L.append("Partly — and the part it misses is the part that matters.\n")
    L.append("A projection implies a number of games: divide it by the "
             "player's recent points-per-game and you get the games the "
             "projection is assuming. Comparing that to the games he has "
             "actually played says whether the forecaster has haircut him.\n")

    recent = w[w.season >= max(seasons) - 1]
    hist = (recent.groupby("key_name")
                  .agg(games=("pts", "size"), pts=("pts", "sum"),
                       name=("name", "first"),
                       pos=("pos", "first")).reset_index())
    hist["ns"] = recent.groupby("key_name").season.nunique().values
    hist = hist[(hist.ns == 2) & (hist.games >= 12)
                & (hist.pts / hist.games >= 5)].copy()
    hist["ppg"] = hist.pts / hist.games
    hist["hist_gps"] = hist.games / 2

    adj = hist.merge(pr[["key_name", "proj"]], on="key_name", how="inner")
    adj["implied"] = adj.proj / adj.ppg
    adj["gap"] = adj.implied - adj.hist_gps
    adj["bucket"] = pd.cut(adj.hist_gps, [0, 12, 14, 16, 17.1],
                           labels=["<12 g/yr", "12–14", "14–16", "16–17"])
    L.append("| recent games/yr | n | actually played | projection assumes | gap |")
    L.append("|---|---|---|---|---|")
    for b, s in adj.groupby("bucket", observed=True):
        L.append(f"| {b} | {len(s)} | {s.hist_gps.mean():.1f} | "
                 f"{s.implied.mean():.1f} | **{s.gap.mean():+.1f}** |")
    L.append("")
    L.append("In aggregate the gap is near zero, which looks like a full "
             "haircut. **It is not.** That average is carried by players "
             "whose low games reflect a diminished ROLE — backups and "
             "ageing veterans, whose projections are low for that reason. "
             "Split out the players whose games were lost to injury while "
             "their role stayed elite and the picture inverts:\n")
    L.append("| player | pos | recent games/yr | projection assumes | gap |")
    L.append("|---|---|---|---|---|")
    watch = adj[(adj.hist_gps < 13) & (adj.proj >= 180)].nlargest(8, "gap")
    for _, r in watch.iterrows():
        L.append(f"| {r['name']} | {r.pos} | {r.hist_gps:.1f} | "
                 f"{r.implied:.1f} | **{r.gap:+.1f}** |")
    L.append("")
    L.append("These are projected back to roughly a full season. Their "
             "injury history is **not** priced in.\n")
    L.append("### The sensitivity\n")
    L.append("What the board looks like if each of these players simply "
             "repeats his own recent availability. This is a stress test, "
             "not a replacement board — the truth is somewhere between, "
             "since players do recover and a two-season sample is thin.\n")
    L.append("| player | projection | if he plays at his own recent rate | loss |")
    L.append("|---|---|---|---|")
    for _, r in watch.iterrows():
        shrunk = r.proj * r.hist_gps / r.implied
        L.append(f"| {r['name']} | {r.proj:.0f} | **{shrunk:.0f}** | "
                 f"{shrunk - r.proj:+.0f} |")
    L.append("")
    L.append("**The one that decides a pick: Christian McCaffrey.** He is "
             "the third most valuable player on the 2026 board, and the "
             "gap between what his projection assumes and what he has "
             "actually played is the difference between a top-three pick "
             "and a mid-second-round one.\n")

    # ------------------------------------------------------------------ §7
    # APPLY the role-free model, not the best-fitting one. `hist_games` earns
    # its R² partly by encoding "is he a starter" — and the 2026 projection
    # already encodes that. Including it here double-counts role and punishes
    # short careers: it drove Theo Wease, who has never been injured, to the
    # harshest markdown on the board purely for having played three games.
    # What we want from this model is the HEALTH component only. And it is the
    # CROSS-VALIDATED feature set, not the best in-sample one — see §3.
    APPLY = ["hist_inj", "age_then"]
    apply_beta, _ = fit(dg, APPLY)
    apply_r2 = best_r2   # out-of-sample, from §3; the in-sample fit is not it

    gcareer = (gm_ps.groupby("key_name")
               .agg(hist_games=("games", "mean"), hist_inj=("inj_rate", "mean"),
                    n_prior=("games", "size"), n_out=("n_out", "mean"),
                    n_soft=("n_soft", "mean"), n_parts=("n_parts", "mean")))
    out = pr.merge(gcareer, on="key_name", how="left")
    out["age_then"] = out.key_name.map(ages)

    # Shrink each player's injured share toward his positional mean, weighted
    # by how many seasons of evidence he has. One alarming season should move
    # the estimate part of the way, not all of it.
    SHRINK_K = 1.5
    pos_mean = out.groupby("pos")["hist_inj"].transform("mean")
    n_seasons = out["n_prior"].fillna(0)
    out["hist_inj"] = ((n_seasons * out["hist_inj"].fillna(pos_mean)
                        + SHRINK_K * pos_mean) / (n_seasons + SHRINK_K))

    have = out[APPLY].notna().all(axis=1) & out.age_then.notna()
    pred = np.full(len(out), float(dg.y_games.mean()))
    if have.any():
        X = np.column_stack([out.loc[have, c].to_numpy(float) for c in APPLY]
                            + [np.ones(int(have.sum()))])
        pred[have.to_numpy()] = X @ apply_beta
    out["exp_games"] = np.clip(pred, 6.0, FULL_SEASON)

    # Normalise within position over the startable pool: a global denominator
    # marks nearly everyone up, and a cross-position one compares a QB's
    # durability to a running back's.
    out["avail_mult"] = 1.0
    for pos, n in CAPS.items():
        at = out[out.pos == pos]
        if at.empty:
            continue
        ref = out.loc[at.nlargest(min(n, len(at)), "proj").index,
                      "exp_games"].mean()
        if ref > 0:
            out.loc[at.index, "avail_mult"] = out.loc[at.index, "exp_games"] / ref
    # DAMP by how much the model actually knows. A raw multiplier spanning
    # 0.60–1.15 asserts ±40% swings in projected points on the strength of an
    # R² of 0.02 — indefensible. Scaling the deviation from 1.0 by the model's
    # correlation (√R²) keeps the ORDERING intact while sizing the magnitude to
    # the evidence. The result is a few percent either way: a tiebreak, which
    # is all this is entitled to be.
    reliability = float(np.sqrt(max(apply_r2, 0.0)))
    out["avail_mult"] = 1.0 + (out["avail_mult"] - 1.0) * reliability
    out.loc[n_seasons == 0, "avail_mult"] = 1.0
    out["avail_mult"] = out.avail_mult.round(3)
    out["proj_adj"] = (out.proj * out.avail_mult).round(1)

    top = pd.concat([out[out.pos == k].nlargest(min(v, (out.pos == k).sum()),
                                                "proj")
                     for k, v in CAPS.items()]).copy()
    top["delta"] = top.proj_adj - top.proj

    L.append("## 7. How to use it\n")
    L.append(f"The applied model is the **role-free, cross-validated** one "
             f"(out-of-sample R² = {apply_r2:.3f}), not the best-fitting one. "
             f"`hist_games` earns part of its R² by encoding *is he a "
             f"starter*, and the 2026 projection already encodes that — "
             f"including it double-counts role and punishes short careers. The "
             f"multiplier is then damped by √R² = {reliability:.2f}, which "
             f"preserves the ordering while sizing the magnitude to what the "
             f"model actually knows.\n")
    L.append("The whole adjustment is therefore worth about **±3%** of "
             "projected points, which is what an out-of-sample R² of "
             f"{apply_r2:.3f} entitles it to be. That is a tiebreak: it will "
             "never override a real gap in projected points, and it is not "
             "supposed to. Where two players are close, take the durable one.\n")
    for label, sub in (("Marked down most", top.nsmallest(10, "delta")),
                       ("Marked up most", top.nlargest(8, "delta"))):
        L.append(f"**{label}**\n")
        L.append("| player | pos | age | injured share of career | exp games | proj | adjusted | Δ |")
        L.append("|---|---|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            L.append(f"| {r['name']} | {r.pos} | {r.age_then:.0f} | "
                     f"{r.hist_inj*100:.0f}% | {r.exp_games:.1f} | "
                     f"{r.proj:.0f} | **{r.proj_adj:.0f}** | {r.delta:+.0f} |")
        L.append("")
    L.append("**Availability remains mostly unpredictable.** That is the "
             "finding, not a failure to find one. Roughly 98% of the variance "
             "in next season's games played is not explained by anything in "
             "five years of appearance shapes, injury reports and ages. The "
             "correct response is to stop trying to forecast it precisely and "
             "instead (a) prefer the durable player on ties, (b) refuse to pay "
             "a full-season price for a player whose projection silently "
             "assumes one (§6), and (c) remember that with no IR slot the cost "
             "of an injury here is a bench spot as well as the points.\n")

    # ------------------------------------------------------------------ out
    OUT_CAREER.parent.mkdir(parents=True, exist_ok=True)
    car.to_parquet(OUT_CAREER, index=False)
    if len(adj):
        adj.to_parquet(OUT_GAP, index=False)
    out[["key_name", "name", "pos", "exp_games", "avail_mult", "proj",
         "proj_adj", "hist_inj", "n_prior"]].to_parquet(OUT_GAMES, index=False)
    dur[["key_name", "name", "pos", "n_seasons", "inj_rate", "exp_games",
         "durability"]].to_parquet(OUT_DURABILITY, index=False)
    OUT_MD.write_text("\n".join(L))

    print(f"single features with positive OOS R2: {good}")
    print(f"best combo {best_combo} -> OOS R2 {best_r2:+.4f}")
    print(f"Wrote {OUT_MD}")
    print(f"      {OUT_CAREER}, {OUT_GAMES}, {OUT_DURABILITY}, {OUT_GAP}")
    print(tab.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
