"""Does roster variance help or hurt in THIS league's format?

The draft spec assumed a top-heavy payoff rewards high-variance rosters (the
best-ball finding that volatility is worth roughly half a unit of expected
points). This league's actual rules point the other way, and this script
settles it empirically rather than by argument.

Three format features work against variance:

1. The regular season awards a point for a weekly TOP-5 finish. That is a
   THRESHOLD: scoring 190 earns exactly what scoring 125 earns. Ceiling weeks
   are capped, while floor weeks still cost the point.
2. Only 4 of 10 teams reach the playoffs, a high bar that rewards consistency.
3. The title is decided by a TWO-WEEK aggregate, averaging out luck in the one
   round where a coin flip would most help a weaker team.

Method: a full 10-team league simulation on real data. Each sim samples one
real season and uses nine of its teams' actual week-by-week scores as rivals —
which preserves both the week-level scoring environment and the fact that good
teams stay good — then inserts a focal team drawn from N(mu, sigma) and plays
the real rules: 14-week dual-points regular season, top 4 qualify, #1 seed
picks its opponent, 1-week semifinal, 2-week aggregate final.

    python -m scripts.variance_study
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.rebuild_standings import load_weekly  # noqa: E402

N_SIMS = 40000
REG_WEEKS = 14
TOP_N = 5
PLAYOFF_TEAMS = 4
TEAMS = 10
RNG = np.random.default_rng(20260807)


def season_matrices(min_season: int = 2018) -> list[np.ndarray]:
    """One (10 teams x weeks) array per season, team identity preserved."""
    weekly = load_weekly()
    out = []
    for season, rows in weekly.items():
        if season < min_season:
            continue
        managers = sorted({r["mgr"] for r in rows})
        weeks = sorted({r["week"] for r in rows if not r.get("is_playoff")})
        by = {(r["mgr"], r["week"]): r["points"] for r in rows
              if not r.get("is_playoff")}
        mat = np.array([[by.get((m, w), np.nan) for w in weeks] for m in managers])
        if mat.shape[0] == TEAMS and not np.isnan(mat).any() and (mat > 0).all():
            out.append(mat)
    return out


def _dual_points(scores: np.ndarray) -> np.ndarray:
    """scores: (sims, teams, weeks) -> (sims, teams) points under real rules.

    Each week: 1 point for winning a randomly paired matchup, 1 point for a
    top-5 finish among the ten teams.
    """
    n, t, w = scores.shape
    # random pairing each week: permute team order, pair (0,1) (2,3) ...
    order = np.argsort(RNG.random((n, w, t)), axis=2)
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(t)[None, None, :], axis=2)
    partner_rank = ranks ^ 1                      # 0<->1, 2<->3, ...
    partner = np.take_along_axis(order, partner_rank, axis=2)
    sc = np.transpose(scores, (0, 2, 1))          # (n, w, t)
    opp = np.take_along_axis(sc, partner, axis=2)
    h2h = (sc > opp).sum(axis=1)                  # (n, t)

    cutoff = np.sort(sc, axis=2)[:, :, -TOP_N][:, :, None]
    top5 = (sc >= cutoff).sum(axis=1)
    return h2h + top5


def _h2h_only(scores: np.ndarray) -> np.ndarray:
    n, t, w = scores.shape
    order = np.argsort(RNG.random((n, w, t)), axis=2)
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(t)[None, None, :], axis=2)
    partner = np.take_along_axis(order, ranks ^ 1, axis=2)
    sc = np.transpose(scores, (0, 2, 1))
    opp = np.take_along_axis(sc, partner, axis=2)
    return (sc > opp).sum(axis=1)


def simulate(mu: float, sigma: float, seasons: list[np.ndarray],
             n: int = N_SIMS, dual_points: bool = True,
             playoff_teams: int = PLAYOFF_TEAMS, final_weeks: int = 2) -> dict:
    """P(playoffs), P(final), P(title) for a focal team of (mu, sigma).

    The focal team is team index 0; the other nine are real teams.
    """
    # sample a season and 9 of its teams per sim
    pick = RNG.integers(0, len(seasons), size=n)
    rivals = np.empty((n, TEAMS - 1, REG_WEEKS + 1 + final_weeks))
    for si, mat in enumerate(seasons):
        sel = pick == si
        k = int(sel.sum())
        if not k:
            continue
        teams = np.argsort(RNG.random((k, TEAMS)), axis=1)[:, :TEAMS - 1]
        wk = RNG.integers(0, mat.shape[1], size=(k, REG_WEEKS + 1 + final_weeks))
        # (k, 9, weeks): each rival's own scores, resampled by week
        rivals[sel] = mat[teams[:, :, None], wk[:, None, :]]

    focal = RNG.normal(mu, sigma, size=(n, 1, REG_WEEKS + 1 + final_weeks))
    allsc = np.concatenate([focal, rivals], axis=1)     # (n, 10, weeks)

    reg = allsc[:, :, :REG_WEEKS]
    points = _dual_points(reg) if dual_points else _h2h_only(reg)
    pf = reg.sum(axis=2)
    key = points + pf / 1e6                            # points, then total PF
    seed = 1 + (key > key[:, :1]).sum(axis=1)          # focal's seed
    made = seed <= playoff_teams

    # --- playoffs: recover the actual qualifying field -------------------
    order = np.argsort(-key, axis=1)                   # seeds 1..10
    field = order[:, :playoff_teams]
    semi_week = allsc[:, :, REG_WEEKS]
    fin = allsc[:, :, REG_WEEKS + 1:REG_WEEKS + 1 + final_weeks].sum(axis=2)

    rows = np.arange(n)
    if playoff_teams == 4:
        # #1 picks its opponent; assume it picks the weakest qualifier (seed 4)
        pairs = [(0, 3), (1, 2)]
    else:
        # 6 teams: seeds 1-2 bye, 3v6 and 4v5, then 1 v lowest survivor
        pairs = [(2, 5), (3, 4)]

    semi_scores = np.take_along_axis(semi_week, field, axis=1)
    winners = []
    for a, b in pairs:
        wa = semi_scores[:, a] >= semi_scores[:, b]
        winners.append(np.where(wa, field[:, a], field[:, b]))
    if playoff_teams == 6:
        # byes advance; final four -> pick the two strongest remaining
        winners = [field[:, 0], field[:, 1]]

    fin_a = fin[rows, winners[0]]
    fin_b = fin[rows, winners[1]]
    champ = np.where(fin_a >= fin_b, winners[0], winners[1])

    in_final = (winners[0] == 0) | (winners[1] == 0)
    title = champ == 0
    p = title.mean()
    return {"playoffs": made.mean(), "final": in_final.mean(),
            "title": p, "title_se": float(np.sqrt(p * (1 - p) / n)),
            "avg_points": points[:, 0].mean(), "avg_seed": seed.mean()}


def main() -> int:
    seasons = season_matrices()
    pool = np.concatenate([m.ravel() for m in seasons])
    league_mu, league_sd = pool.mean(), pool.std()
    team_sds = np.concatenate([m.std(axis=1) for m in seasons])
    print(f"Bootstrap pool: {len(seasons)} complete seasons (2018-2025)")
    print(f"League mean team-week {league_mu:.1f}, overall sd {league_sd:.1f}")
    print(f"Real per-team weekly sd: min {team_sds.min():.1f}, "
          f"median {np.median(team_sds):.1f}, max {team_sds.max():.1f}\n")

    print("Focal team held at league-average scoring; only weekly VARIANCE changes.")
    print(f"{'sigma':>6} {'dual pts':>9} {'avg seed':>9} {'P(playoff)':>11} "
          f"{'P(final)':>9} {'P(title)':>16}")
    sigmas = [12, 16, 20, 24, 28, 32]
    results = {}
    for s in sigmas:
        r = simulate(league_mu, s, seasons)
        results[s] = r
        print(f"{s:>6} {r['avg_points']:>9.2f} {r['avg_seed']:>9.2f} "
              f"{r['playoffs']:>10.1%} {r['final']:>8.1%} "
              f"{r['title']:>10.1%} +/-{r['title_se']:.1%}")

    lo, hi = results[sigmas[0]], results[sigmas[-1]]
    d_title = hi["title"] - lo["title"]
    se = float(np.sqrt(lo["title_se"] ** 2 + hi["title_se"] ** 2))
    print(f"\nsigma {sigmas[0]} -> {sigmas[-1]} at identical mean: "
          f"dual points {lo['avg_points']:.2f} -> {hi['avg_points']:.2f} "
          f"({hi['avg_points'] - lo['avg_points']:+.2f}), "
          f"P(title) {d_title:+.2%} +/- {se:.2%}")

    print("\nFor scale — raising the weekly MEAN instead, at sigma 22:")
    mean_res = {}
    for dmu in (0, 2, 4, 6, 8):
        r = simulate(league_mu + dmu, 22, seasons)
        mean_res[dmu] = r
        print(f"  +{dmu:>2} pts/wk: dual pts {r['avg_points']:.2f}, "
              f"P(playoff) {r['playoffs']:>5.1%}, P(title) {r['title']:>5.1%}")

    # exchange rate: how much weekly mean is the whole sigma range worth?
    slope = ((mean_res[8]["title"] - mean_res[0]["title"]) / 8)   # per pt/week
    if slope > 0:
        equiv = d_title / slope
        print(f"\nEXCHANGE RATE: raising the mean is worth {slope:+.2%} P(title) "
              f"per point/week.\n  The entire sigma {sigmas[0]}->{sigmas[-1]} "
              f"swing ({d_title:+.2%}) is worth {equiv:+.2f} points/week of mean "
              f"-- i.e. {equiv / (sigmas[-1] - sigmas[0]):+.3f} pts/week per unit "
              f"of sigma.")

    print("\nCounterfactual — plain H2H, 6 playoff teams, 1-week final:")
    for s in (12, 22, 32):
        r = simulate(league_mu, s, seasons, dual_points=False,
                     playoff_teams=6, final_weeks=1)
        print(f"  sigma {s:>2}: P(playoff) {r['playoffs']:>5.1%}, "
              f"P(title) {r['title']:>5.1%}")

    out = Path("research/variance_study.json")
    out.write_text(json.dumps({
        "league_mean": float(league_mu),
        "n_seasons": len(seasons),
        "by_sigma": {str(k): {kk: float(vv) for kk, vv in v.items()}
                     for k, v in results.items()},
        "by_mean_delta": {str(k): {kk: float(vv) for kk, vv in v.items()}
                          for k, v in mean_res.items()},
    }, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
