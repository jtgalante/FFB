"""Does anything in the injury data actually predict next season?

    python -m scripts.injury_signal

Writes research/injury_signal.md and data/draft/durability.parquet.

Two questions, answered honestly:

1. **Which injury features carry signal?** Every candidate is tested one at a
   time against next season's availability, with the sample size shown, so a
   correlation built on eleven players is visibly a correlation built on eleven
   players.

2. **Does the model survive out of sample?** In-sample R² rises automatically
   as features are added; it is not evidence. Everything here is scored by
   **leave-one-season-out cross-validation** — fit on four seasons, predict the
   fifth, repeat. Out-of-sample R² can go NEGATIVE, meaning the model is worse
   than predicting the mean, and if it does that is the finding.

The output is a per-player `durability` score on 0-100, which is a percentile
within position, plus the expected-games estimate behind it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.games_model import (CAPS, SOFT_TISSUE, injury_features,  # noqa: E402
                                 season_shapes)
from src.draft.ids import player_key  # noqa: E402

WEEKLY = Path("data/draft/weekly_points.parquet")
BYES = Path("data/draft/byes_by_season.parquet")
INJ = Path("data/draft/injuries.parquet")
PLAYERS = Path("data/draft/players.parquet")
PROJ = Path("data/inputs/projections.csv")
OUT_MD = Path("research/injury_signal.md")
OUT_PQ = Path("data/draft/durability.parquet")

PARTS = ["Knee", "Ankle", "Hamstring", "Concussion", "Shoulder", "Groin",
         "Foot", "Calf", "Back", "Hip", "Quadricep", "Achilles"]


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


def main() -> int:
    w = pd.read_parquet(WEEKLY)
    byes = pd.read_parquet(BYES)
    bye_of = {(int(r.season), r.team): r.bye for r in byes.itertuples()}
    inj = pd.read_parquet(INJ)
    players = pd.read_parquet(PLAYERS)
    ages = players.dropna(subset=["age"]).set_index("key_name").age.to_dict()

    ps = season_shapes(w, bye_of).merge(part_features(inj),
                                        on=["key_name", "season"], how="left")
    feat_cols = ["n_listed", "n_out", "n_dnp", "n_parts", "wk_soft"] + \
                [f"wk_{p.lower()}" for p in PARTS]
    for c in feat_cols:
        ps[c] = ps[c].fillna(0.0)

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
            y = float(n.games)
        except KeyError:
            y = 0.0
        rec = {"season": int(r.season), "pos": r.pos, "y": y,
               "inj_rate": r.inj_rate, "games": r.games,
               "age_then": a - (2026 - r.season)}
        rec.update({c: float(r[c]) for c in feat_cols})
        rows.append(rec)
    d = pd.DataFrame(rows)

    L = [f"# Does the injury data predict anything?\n",
         "*Generated by `python -m scripts.injury_signal`. Scored by "
         "**leave-one-season-out cross-validation** — fit on four seasons, "
         "predict the fifth. Out-of-sample R² can be negative, which means the "
         "model is worse than guessing the average.*\n",
         f"Sample: **{len(d)} startable player-seasons**, 2021–25.\n",
         "## One feature at a time\n",
         "| feature | players with it | corr with next-season games | "
         "out-of-sample R² |", "|---|---|---|---|"]

    single = []
    for c in ["inj_rate", "games", "age_then"] + feat_cols:
        nz = int((d[c] != 0).sum())
        if nz < 20:
            continue
        corr = float(np.corrcoef(d[c], d.y)[0, 1])
        r2 = loso_r2(d, [c], "y")
        single.append((c, nz, corr, r2))
    for c, nz, corr, r2 in sorted(single, key=lambda t: -t[3]):
        flag = " ✅" if r2 > 0 else ""
        L.append(f"| `{c}` | {nz} | {corr:+.3f} | **{r2:+.4f}**{flag} |")
    L.append("")
    good = [c for c, _, _, r2 in single if r2 > 0]
    L.append(f"**{len(good)} of {len(single)} features beat guessing the mean "
             f"out of sample.**" + (f" They are: "
             + ", ".join(f"`{c}`" for c in good) + "." if good else "") + "\n")

    L.append("## Combinations\n")
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
        X = np.column_stack([d[c].to_numpy(float) for c in cols]
                            + [np.ones(len(d))])
        beta, *_ = np.linalg.lstsq(X, d.y.to_numpy(float), rcond=None)
        ins = 1 - ((d.y - X @ beta) ** 2).sum() / ((d.y - d.y.mean()) ** 2).sum()
        oos = loso_r2(d, cols, "y")
        L.append(f"| {lab} | {ins:.4f} | **{oos:+.4f}** |")
        if oos > best_r2:
            best_combo, best_r2 = cols, oos
    L.append("")
    L.append("Note how in-sample R² climbs with every feature added while "
             "out-of-sample does not. That gap is the overfitting this "
             "cross-validation exists to expose.\n")

    # ---- per-player durability score -------------------------------------
    pr = pd.read_csv(PROJ)
    pr["key_name"] = [player_key(n, p) for n, p in zip(pr.name, pr.pos)]
    career = ps.groupby("key_name").agg(
        n_seasons=("games", "size"), inj_rate=("inj_rate", "mean"),
        games=("games", "mean"),
        **{c: (c, "mean") for c in feat_cols})
    out = pr.merge(career, on="key_name", how="left")
    out["age_then"] = out.key_name.map(ages)

    cols = best_combo
    X = np.column_stack([d[c].to_numpy(float) for c in cols] + [np.ones(len(d))])
    beta, *_ = np.linalg.lstsq(X, d.y.to_numpy(float), rcond=None)
    have = out[cols].notna().all(axis=1)
    pred = np.full(len(out), float(d.y.mean()))
    if have.any():
        Xa = np.column_stack([out.loc[have, c].to_numpy(float) for c in cols]
                             + [np.ones(int(have.sum()))])
        pred[have.to_numpy()] = Xa @ beta
    out["exp_games"] = np.clip(pred, 6.0, 17.0)
    out["durability"] = (out.groupby("pos").exp_games
                         .rank(pct=True) * 100).round(0)
    out.loc[out.n_seasons.isna(), "durability"] = np.nan

    L.append("## Per-player durability\n")
    L.append("`durability` is a percentile **within position** of predicted "
             "games played — 100 is the most durable at that position. It is "
             f"built from the best cross-validated model above (out-of-sample "
             f"R² = {best_r2:+.3f}).\n")
    L.append("Players with no NFL history are left blank rather than assumed "
             "average, because a blank is honest and a 50 is not.\n")
    board = out[out.n_seasons.notna()].nlargest(40, "proj")
    for label, sub in (("Most durable, of the top 40 by projection",
                        board.nlargest(10, "durability")),
                       ("Least durable", board.nsmallest(10, "durability"))):
        L.append(f"**{label}**\n")
        L.append("| player | pos | age | seasons | injured share | "
                 "exp games | durability |")
        L.append("|---|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            L.append(f"| {r['name']} | {r.pos} | {r.age_then:.0f} | "
                     f"{r.n_seasons:.0f} | {r.inj_rate*100:.0f}% | "
                     f"{r.exp_games:.1f} | **{r.durability:.0f}** |")
        L.append("")

    OUT_PQ.parent.mkdir(parents=True, exist_ok=True)
    out[["key_name", "name", "pos", "n_seasons", "inj_rate", "exp_games",
         "durability"]].to_parquet(OUT_PQ, index=False)
    OUT_MD.write_text("\n".join(L))
    print(f"single features with positive OOS R2: {good}")
    print(f"best combo {best_combo} -> OOS R2 {best_r2:+.4f}")
    print(f"Wrote {OUT_MD} and {OUT_PQ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
