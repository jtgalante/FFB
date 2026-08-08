"""How many games will each player actually play in 2026?

    python -m scripts.games_model

Writes research/games_model.md and data/draft/games_model.parquet, the latter
carrying `exp_games` and an `avail_mult` per player for the board to apply.

## Why a games count is the wrong input

Counting a player's games conflates two unrelated things. A rookie who appears
in eight games because he sat behind a starter, and a starter who appears in
eight games because he tore something in November, are the same number and
completely different facts. The first predicts nothing about 2026; the second
might.

The **shape** of the season separates them, and it is unambiguous in the data:

    Cam Skattebo 2025     wk 1-8 at 14.5 ppg, then nothing   -> season-ending
    Omarion Hampton 2025  wk 1-5, gone 6-13, back 14-17      -> mid-season, returned
    Theo Wease 2025       nothing until wk 16, then 3 games  -> late call-up, role

So each player-season is split three ways:

* `head`  — weeks missed BEFORE his first appearance. Role, not health.
* `gaps`  — weeks missed inside his active window (bye excluded). Injury.
* `tail`  — weeks missed after his last appearance. Injury, usually ending.

and `inj_rate = (gaps + tail) / (17 - head)` — the share of the season he was
plausibly in the role and did not play.

## And the injury reports

`data/draft/injuries.parquet` (nflverse weekly injury reports) adds the body
part and the report status, so a hamstring can be told from an Achilles. Soft
tissue injuries — hamstring, groin, calf, quad — are the ones with a
reputation for recurring, and that is testable here rather than assumed.

**Known gap:** once a player goes on IR he drops off the weekly report
entirely, so a season-ending injury often produces FEWER report rows than a
nagging one. The report features are therefore paired with the shape features,
never used alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.draft.ids import player_key  # noqa: E402

WEEKLY = Path("data/draft/weekly_points.parquet")
BYES = Path("data/draft/byes_by_season.parquet")
INJ = Path("data/draft/injuries.parquet")
PLAYERS = Path("data/draft/players.parquet")
PROJ = Path("data/inputs/projections.csv")
OUT_MD = Path("research/games_model.md")
OUT_PQ = Path("data/draft/games_model.parquet")

SEASON, FULL, LAST_WK = 2026, 17, 18
CAPS = {"QB": 20, "RB": 45, "WR": 60, "TE": 20}
SOFT_TISSUE = {"Hamstring", "Groin", "Calf", "Quadricep", "Quad", "Hip"}


def season_shapes(w: pd.DataFrame, bye_of: dict) -> pd.DataFrame:
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
    d["opportunity"] = (FULL - d["head"]).clip(lower=1)
    d["inj_rate"] = (d["inj_missed"] / d["opportunity"]).clip(0, 1)
    return d


def injury_features(inj: pd.DataFrame) -> pd.DataFrame:
    if inj is None or inj.empty:
        return pd.DataFrame(columns=["key_name", "season", "n_out",
                                     "n_soft", "n_parts"])
    d = inj.copy()
    d["is_out"] = d.report_status.eq("Out").astype(int)
    d["is_soft"] = d.report_primary_injury.isin(SOFT_TISSUE).astype(int)
    return (d.groupby(["key_name", "season"], as_index=False)
              .agg(n_out=("is_out", "sum"), n_soft=("is_soft", "sum"),
                   n_parts=("report_primary_injury", "nunique")))


def fit(d, cols, target="y_games"):
    X = np.column_stack([d[c].to_numpy(float) for c in cols] + [np.ones(len(d))])
    y = d[target].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    return beta, float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def main() -> int:
    w = pd.read_parquet(WEEKLY)
    byes = pd.read_parquet(BYES)
    bye_of = {(int(r.season), r.team): r.bye for r in byes.itertuples()}
    inj = pd.read_parquet(INJ) if INJ.exists() else None
    players = pd.read_parquet(PLAYERS)
    ages = players.dropna(subset=["age"]).set_index("key_name").age.to_dict()

    ps = season_shapes(w, bye_of)
    ifeat = injury_features(inj)
    ps = ps.merge(ifeat, on=["key_name", "season"], how="left")
    for c in ("n_out", "n_soft", "n_parts"):
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
        prior = ps[(ps.key_name == r.key_name) & (ps.season <= r.season)]
        try:
            n = idx.loc[(r.key_name, nxt)]
            if isinstance(n, pd.DataFrame):
                n = n.iloc[0]
            y_games, y_inj = float(n.games), float(n.inj_rate)
        except KeyError:
            y_games, y_inj = 0.0, 1.0     # left the league entirely
        rows.append({
            "hist_games": prior.games.mean(), "n_prior": len(prior),
            "age_then": a - (SEASON - r.season),
            "inj_rate": r.inj_rate, "hist_inj": prior.inj_rate.mean(),
            "n_out": r.n_out, "n_soft": r.n_soft, "n_parts": r.n_parts,
            "y_games": y_games, "y_inj": y_inj})
    d = pd.DataFrame(rows)

    MODELS = [
        ("games count + age + seasons (previous model)",
         ["hist_games", "age_then", "n_prior"]),
        ("injury-shaped rate only", ["hist_inj"]),
        ("injury rate + age", ["hist_inj", "age_then"]),
        ("injury rate + age + seasons", ["hist_inj", "age_then", "n_prior"]),
        ("+ injury report features",
         ["hist_inj", "age_then", "n_prior", "n_out", "n_soft"]),
        ("everything", ["hist_games", "hist_inj", "age_then", "n_prior",
                        "n_out", "n_soft", "n_parts"]),
    ]
    results = [(lab, cols, *fit(d, cols)) for lab, cols in MODELS]
    best = max(results, key=lambda r: r[3])

    L = [f"# Expected games played, {SEASON}\n",
         "*Generated by `python -m scripts.games_model`.*\n",
         "## Separating role from health\n",
         "A games count conflates a rookie who sat with a starter who tore "
         "something. The **shape** of a season separates them — weeks missed "
         "before a player's first appearance are role, weeks missed inside his "
         "active window or after his last appearance are health.\n",
         "```",
         "Cam Skattebo    2025  wk 1-8 at 14.5 ppg, then nothing   -> season-ending",
         "Omarion Hampton 2025  wk 1-5, gone 6-13, back 14-17      -> mid-season, returned",
         "Theo Wease      2025  nothing until wk 16, then 3 games  -> late call-up, role",
         "```\n",
         f"Fitted on **{len(d)} startable player-seasons** (2021–25), following "
         "every one into the next season including those who left the league.\n",
         "| model | R² |", "|---|---|"]
    for lab, _, _, r2 in results:
        mark = " ⬅" if lab == best[0] else ""
        L.append(f"| {lab} | **{r2:.4f}**{mark} |")
    L.append("")
    L.append("**These are IN-SAMPLE and should not be read as accuracy.** "
             "In-sample R² climbs whenever a feature is added. Scored by "
             "leave-one-season-out cross-validation in "
             "`research/injury_signal.md`, the ranking inverts: injury rate + "
             "age is the best model at **+0.017**, and the 'everything' model "
             "below scores **-0.036** — worse than guessing the average. This "
             "script therefore APPLIES two features, not seven.\n")
    L.append(f"**Best in-sample: {best[3]:.3f}.** Replacing the raw games count with the "
             f"injury-shaped rate moves R² from "
             f"{results[0][3]:.3f} to {results[3][3]:.3f} — a real improvement, "
             f"and still small in absolute terms. **Availability remains mostly "
             f"unpredictable**, and any adjustment built on it must stay a "
             f"tiebreak.\n")

    coefs = dict(zip(best[1], best[2]))
    L.append("```\n" + " ".join(f"{v:+.4f}·{k}" for k, v in coefs.items())
             + f" {best[2][-1]:+.3f}\n```\n")
    if "n_soft" in coefs:
        L.append(f"Soft-tissue weeks (hamstring, groin, calf, quad, hip) carry "
                 f"a coefficient of **{coefs['n_soft']:+.3f}** games. "
                 + ("They do predict future absence, which is the folk wisdom "
                    "holding up." if coefs["n_soft"] < 0 else
                    "The sign is the wrong way round for the folk wisdom about "
                    "soft-tissue recurrence — treat it as noise at this sample "
                    "size.") + "\n")
    L.append("**Report-data caveat:** a player on IR drops off the weekly "
             "injury report, so a season-ending injury can produce fewer report "
             "rows than a nagging one. The report features are only ever used "
             "alongside the shape features for this reason.\n")

    # ---- apply to 2026 ---------------------------------------------------
    pr = pd.read_csv(PROJ)
    pr["key_name"] = [player_key(n, p) for n, p in zip(pr.name, pr.pos)]
    career = (ps.groupby("key_name")
                .agg(hist_games=("games", "mean"), hist_inj=("inj_rate", "mean"),
                     n_prior=("games", "size"), n_out=("n_out", "mean"),
                     n_soft=("n_soft", "mean"), n_parts=("n_parts", "mean")))
    out = pr.merge(career, on="key_name", how="left")
    out["age_then"] = out.key_name.map(ages)

    # APPLY the role-free model, not the best-fitting one. `hist_games` earns
    # its R² partly by encoding "is he a starter" — and the 2026 projection
    # already encodes that. Including it here double-counts role and punishes
    # short careers: it drove Theo Wease, who has never been injured, to the
    # harshest markdown on the board purely for having played three games.
    # What we want from this model is the HEALTH component only.
    # CROSS-VALIDATED feature set, not the best in-sample one. The R2 table
    # above is in-sample and rises automatically as features are added; it is
    # not evidence. `scripts.injury_signal` scores the same candidates by
    # leave-one-season-out CV and the verdict is blunt:
    #
    #     injury-shaped rate + age        out-of-sample R2 = +0.017  <- best
    #     + weeks listed Out                                 +0.014
    #     + soft tissue                                      +0.011
    #     every injury feature                               -0.036  <- WORSE
    #                                                                   than
    #                                                                   guessing
    #
    # The "everything" model that scored 0.050 in-sample is worse than
    # predicting the mean out of sample. Two features is the honest ceiling.
    APPLY = ["hist_inj", "age_then"]
    apply_beta, apply_r2_insample = fit(d, APPLY)
    apply_r2 = 0.0174   # measured out-of-sample; see research/injury_signal.md

    # Shrink each player's injured share toward his positional mean, weighted
    # by how many seasons of evidence he has. One alarming season should move
    # the estimate part of the way, not all of it.
    SHRINK_K = 1.5
    pos_mean = out.groupby("pos")["hist_inj"].transform("mean")
    n_seasons = out["n_prior"].fillna(0)
    out["hist_inj"] = ((n_seasons * out["hist_inj"].fillna(pos_mean)
                        + SHRINK_K * pos_mean) / (n_seasons + SHRINK_K))

    have = out[APPLY].notna().all(axis=1) & out.age_then.notna()
    pred = np.full(len(out), float(d.y_games.mean()))
    if have.any():
        X = np.column_stack([out.loc[have, c].to_numpy(float) for c in APPLY]
                            + [np.ones(int(have.sum()))])
        pred[have.to_numpy()] = X @ apply_beta
    out["exp_games"] = np.clip(pred, 6.0, FULL)

    # Normalise within position over the startable pool (see the note in the
    # previous revision: a global denominator marks nearly everyone up, and a
    # cross-position one compares a QB's durability to a running back's).
    MIN_SEASONS = 2
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
    # R² of 0.03 — indefensible. Scaling the deviation from 1.0 by the model's
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
    L.append("## What it changes on the 2026 board\n")
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
    L.append("### How to use this\n")
    L.append(f"The applied model is the **role-free, cross-validated** one "
             f"(out-of-sample R² = {apply_r2:.3f}), not the best-fitting one. "
             f"`hist_games` earns part of its R² by "
             f"encoding *is he a starter*, and the 2026 projection already "
             f"encodes that — including it double-counts role and punishes "
             f"short careers. The multiplier is then damped by √R² = "
             f"{reliability:.2f}, which preserves the ordering while sizing the "
             f"magnitude to what the model actually knows.\n")
    L.append(f"**As a tiebreak.** At R² = {best[3]:.2f} the model is a little "
             "better than assuming everyone is average and nowhere near good "
             "enough to override a real gap in projected points. Where two "
             "players are close, prefer the durable one.\n")

    OUT_PQ.parent.mkdir(parents=True, exist_ok=True)
    out[["key_name", "name", "pos", "exp_games", "avail_mult", "proj",
         "proj_adj", "hist_inj", "n_prior"]].to_parquet(OUT_PQ, index=False)
    OUT_MD.write_text("\n".join(L))
    for lab, _, _, r2 in results:
        print(f"  R2={r2:.4f}  {lab}")
    print(f"\nWrote {OUT_MD} and {OUT_PQ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
