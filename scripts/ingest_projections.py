"""Turn FantasyPros CSV exports into projections scored for THIS league.

    python -m scripts.ingest_projections            # read, check, write
    python -m scripts.ingest_projections --check    # report only, write nothing

Why this exists rather than just reading the FPTS column:

**FantasyPros exports QB projections at 4-point passing TDs and -1
interceptions.** This league plays 6-point passing TDs and -2. Verified
2026-08-07 against the real export: the FPTS column reproduces 4pt/-1 scoring
to a mean error of 0.14 points, and the league's actual scoring to 15.98.

The effect is not a uniform inflation, so it cannot be corrected with a
constant. TD-dependent passers gain far more than rushing QBs: the adjustment
ran from +0 to +59.3 points, and it moved Matthew Stafford from QB15 to QB8.
Anything built on the raw FPTS column would misprice the entire position — in
exactly the direction that matters, since the ADP market is also priced at 4pt.

RB/WR/TE exports are already half-PPR and need no correction (verified to 0.15
mean error), but they are recomputed from components anyway so that every
projection in the engine comes from one scoring path.

The other trap this handles: **the column order differs per position.** RB is
ATT,YDS,TDS,REC,YDS,TDS while WR is REC,YDS,TDS,ATT,YDS,TDS — rushing and
receiving are swapped, under duplicate header names. Reading these positionally
without checking would silently give every WR a rushing line. Each schema below
is therefore asserted against the real header, and a mismatch is a hard error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.draft.ids import normalize_team, player_key  # noqa: E402
from src.draft.sources import INPUTS_DIR  # noqa: E402

SRC_DIR = INPUTS_DIR / "Projections"
OUT = INPUTS_DIR / "projections.csv"
CONFIG = Path("config/league.yaml")

# (header as FantasyPros ships it) -> (our column names)
# The header is asserted verbatim; if FantasyPros reorders a column the run
# fails loudly instead of mis-mapping rushing onto receiving.
SCHEMAS = {
    "QB": (["Player", "Team", "ATT", "CMP", "YDS", "TDS", "INTS",
            "ATT", "YDS", "TDS", "FL", "FPTS"],
           ["name", "team", "pass_att", "cmp", "pass_yd", "pass_td", "pass_int",
            "rush_att", "rush_yd", "rush_td", "fl", "fpts_fp"]),
    "RB": (["Player", "Team", "ATT", "YDS", "TDS", "REC", "YDS", "TDS",
            "FL", "FPTS"],
           ["name", "team", "rush_att", "rush_yd", "rush_td", "rec", "rec_yd",
            "rec_td", "fl", "fpts_fp"]),
    # NOTE the reversal: WR leads with receiving, RB leads with rushing.
    "WR": (["Player", "Team", "REC", "YDS", "TDS", "ATT", "YDS", "TDS",
            "FL", "FPTS"],
           ["name", "team", "rec", "rec_yd", "rec_td", "rush_att", "rush_yd",
            "rush_td", "fl", "fpts_fp"]),
    "TE": (["Player", "Team", "REC", "YDS", "TDS", "FL", "FPTS"],
           ["name", "team", "rec", "rec_yd", "rec_td", "fl", "fpts_fp"]),
}

# The combined FLEX export, used only as an independent cross-check on the
# per-position files. It carries every RB/WR/TE in ONE consistent column order
# (rushing then receiving, for all three), so agreement between it and the
# per-position parse is real evidence the swap above was handled correctly.
FLEX_SCHEMA = (["Player", "Team", "POS", "ATT", "YDS", "TDS", "REC", "YDS",
                "TDS", "FL", "FPTS"],
               ["name", "team", "pos_rank", "rush_att", "rush_yd", "rush_td",
                "rec", "rec_yd", "rec_td", "fl", "fpts_fp"])

STAT_TO_SCORING = {
    "pass_yd": "pass_yd", "pass_td": "pass_td", "pass_int": "pass_int",
    "rush_yd": "rush_yd", "rush_td": "rush_td",
    "rec": "rec", "rec_yd": "rec_yd", "rec_td": "rec_td", "fl": "fum_lost",
}


def _path(tag: str) -> Path:
    return SRC_DIR / f"FantasyPros_Fantasy_Football_Projections_{tag}.csv"


def _read(tag: str, schema) -> pd.DataFrame:
    expected, ours = schema
    path = _path(tag)
    if not path.exists():
        raise SystemExit(
            f"Missing {path}.\nExport it from FantasyPros (Draft Projections -> "
            f"Download CSV) and save the .csv (not .numbers) into {SRC_DIR}/.")
    # Row 2 of every export is a blank spacer row.
    header = pd.read_csv(path, nrows=0).columns.tolist()
    # pandas de-duplicates repeated headers as YDS.1 / TDS.1 — undo for compare.
    header = [h.split(".")[0] for h in header]
    if header != expected:
        raise SystemExit(
            f"{path.name}: unexpected column layout.\n"
            f"  expected: {expected}\n  got:      {header}\n"
            f"These files use duplicate column names, so the order IS the "
            f"schema. Update SCHEMAS in this script rather than guessing.")
    df = pd.read_csv(path, skiprows=[1])
    df.columns = ours
    # Everything except the text columns is a stat. `pos_rank` ("RB1") is text
    # and must be excluded — coercing it to numeric silently NaNs the whole
    # column and takes the FLEX cross-check down with it.
    for c in ours:
        if c in ("name", "team", "pos_rank"):
            continue
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""),
                              errors="coerce")
    return df.dropna(subset=["fpts_fp"]).reset_index(drop=True)


def score(df: pd.DataFrame, scoring: dict) -> pd.Series:
    """Fantasy points under config/league.yaml, from component stats."""
    total = pd.Series(0.0, index=df.index)
    for stat, key in STAT_TO_SCORING.items():
        if stat in df.columns:
            total = total + df[stat].fillna(0.0) * float(scoring.get(key, 0.0))
    return total.round(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report only; do not write projections.csv")
    a = ap.parse_args()

    scoring = (yaml.safe_load(CONFIG.read_text()) or {}).get("scoring", {})
    print(f"Scoring from {CONFIG}: pass_td={scoring.get('pass_td')}, "
          f"pass_int={scoring.get('pass_int')}, rec={scoring.get('rec')}\n")

    frames = []
    for pos, schema in SCHEMAS.items():
        df = _read(pos, schema)
        df["pos"] = pos
        df["proj"] = score(df, scoring)
        df["delta"] = (df["proj"] - df["fpts_fp"]).round(1)
        frames.append(df)
        worst = df.loc[df["delta"].abs().idxmax()] if len(df) else None
        print(f"  {pos}: {len(df):>3} players | "
              f"mean adj {df['delta'].mean():+6.1f} | "
              f"max {df['delta'].max():+6.1f} "
              f"({worst['name'] if worst is not None else '-'})")

    all_ = pd.concat(frames, ignore_index=True)

    # ---- cross-check against the combined FLEX export --------------------
    print("\nCross-check vs the combined FLX export:")
    try:
        flx = _read("FLX", FLEX_SCHEMA)
        flx["pos"] = flx["pos_rank"].astype(str).str.extract(r"^([A-Z]{2})")[0]
        flx = flx.dropna(subset=["pos"])
        flx = flx[flx["pos"].isin(["RB", "WR", "TE"])].reset_index(drop=True)
        flx["proj_flx"] = score(flx, scoring)
        flx["k"] = [player_key(n, p) for n, p in zip(flx["name"], flx["pos"])]
        sub = all_[all_.pos.isin(["RB", "WR", "TE"])].copy()
        sub["k"] = [player_key(n, p) for n, p in zip(sub["name"], sub["pos"])]
        m = sub.merge(flx[["k", "proj_flx"]], on="k", how="inner")
        d = (m["proj"] - m["proj_flx"]).abs()
        # A zero-row merge makes d.max() NaN, and `NaN > 0.5` is False — which
        # would print "agreement is exact" having compared nothing at all.
        if len(m) == 0:
            raise SystemExit(
                f"cross-check joined 0 of {len(sub)} players — the key or the "
                f"POS parse is broken, so this proves nothing. Not a pass.")
        print(f"  matched {len(m)} of {len(sub)} RB/WR/TE | "
              f"max disagreement {d.max():.1f} pts | mean {d.mean():.2f}")
        # Distinguish a parse bug from FantasyPros disagreeing with itself.
        # A mis-mapped column shifts nearly every row; the real exports differ
        # on a handful of fringe players because the position page and the
        # FLEX page are built from different expert sets. Verified 2026-08-07:
        # Connor Heyward is TE86 on one page (14 rec) and a different player
        # on the other (9 rec + a rushing line). Both parse correctly.
        off = m.loc[d > 0.5, ["name", "pos", "proj", "proj_flx"]]
        if len(off) > 0.02 * len(m):
            print(f"  PARSE ERROR LIKELY — {len(off)} of {len(m)} rows differ; "
                  f"a mis-mapped column shifts everything, not a few rows:")
            print(off.head(5).to_string(index=False))
        elif len(off):
            print(f"  {len(m) - len(off)}/{len(m)} agree exactly — the RB/WR "
                  f"column reversal is handled. FantasyPros' own two pages "
                  f"disagree on {len(off)} fringe player(s):")
            print("   " + off.to_string(index=False).replace("\n", "\n   "))
        else:
            print("  agreement is exact — the RB/WR column reversal was "
                  "handled correctly")
        only_flx = set(flx["k"]) - set(sub["k"])
        if only_flx:
            print(f"  note: {len(only_flx)} players in FLX but not in the "
                  f"per-position files (deeper FLX list)")
    except SystemExit as e:
        print(f"  skipped: {e}")

    # ---- what the rescoring actually changes -----------------------------
    print("\nBiggest rank moves caused by using the league's real scoring:")
    for pos in ("QB", "RB", "WR", "TE"):
        d = all_[all_.pos == pos].copy()
        d["rank_fp"] = d.fpts_fp.rank(ascending=False)
        d["rank_lg"] = d.proj.rank(ascending=False)
        d["move"] = (d.rank_fp - d.rank_lg).astype(int)
        top = d[d.rank_lg <= 24]
        mv = top.loc[top["move"].abs().nlargest(3).index]
        moved = [f"{r['name']} {int(r.rank_fp)}->{int(r.rank_lg)}"
                 for _, r in mv.iterrows() if r["move"] != 0]
        print(f"  {pos}: " + (", ".join(moved) if moved else "no reordering"))

    all_["team"] = all_["team"].map(normalize_team)
    out = all_[["name", "pos", "team", "proj"]].copy()
    out["fp_proj_4pt"] = all_["fpts_fp"]      # keep the original, auditable
    out["rescore_delta"] = all_["delta"]
    out = out.sort_values("proj", ascending=False).reset_index(drop=True)

    dupes = out[out.duplicated(["name", "pos"], keep=False)]
    if len(dupes):
        print(f"\nWARNING: {len(dupes)} duplicate name|pos rows")
        print(dupes.head(10).to_string(index=False))

    if a.check:
        print(f"\n--check: not writing. Would write {len(out)} players to {OUT}")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nWrote {len(out)} players -> {OUT}")
    print("data.py picks this up automatically as a projections override.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
