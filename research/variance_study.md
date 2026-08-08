# Does variance help? Testing the spec's central assumption

**Answer: no. In this league, expected points dominate and weekly variance is
worth almost nothing.** The spec's design decision #1 — that a top-heavy payoff
justifies building a high-variance roster — does not survive contact with this
format's actual rules.

Reproduce with `python -m scripts.variance_study`.

## Method

A full 10-team league simulation on real data (40,000 seasons per cell). Each
simulated season samples one real season 2018–2025 and uses nine of its teams'
**actual week-by-week scores** as the opposition — which preserves both the
week-to-week scoring environment and the fact that good teams stay good — then
inserts a focal team drawn from N(μ, σ) and plays the league's real rules:
14-week dual-points regular season, top 4 qualify, #1 seed picks its opponent,
one-week semifinal, **two-week aggregate final**.

The focal team's mean is held at the league average (101.8 points/week) while σ
is swept across the full realistic range. For reference, real per-team weekly
standard deviations in this league run from 11.6 to 33.3, median 20.0 — so the
sweep from 12 to 32 spans essentially every roster the league has ever fielded.

## Results

| σ | Dual points | Avg seed | P(playoffs) | P(final) | P(title) |
|---|---|---|---|---|---|
| 12 | 14.25 | 5.35 | 37.6% | 15.6% | 6.2% ± 0.1% |
| 16 | 14.21 | 5.37 | 37.1% | 15.9% | 6.5% ± 0.1% |
| 20 | 14.18 | 5.39 | 37.2% | 16.0% | 6.4% ± 0.1% |
| 24 | 14.16 | 5.41 | 36.8% | 15.7% | 6.1% ± 0.1% |
| 28 | 14.13 | 5.43 | 36.6% | 16.1% | 6.7% ± 0.1% |
| 32 | 14.13 | 5.44 | 37.0% | 16.3% | 6.8% ± 0.1% |

Raising the **mean** instead, at σ = 22:

| Extra pts/week | Dual points | P(playoffs) | P(title) |
|---|---|---|---|
| +0 | 14.20 | 37.3% | 6.6% |
| +2 | 15.02 | 46.5% | 9.5% |
| +4 | 15.87 | 55.8% | 12.5% |
| +6 | 16.64 | 64.6% | 16.3% |
| +8 | 17.42 | 72.6% | 20.4% |

## The exchange rate

**One extra point per week of expected scoring is worth +1.72 percentage points
of championship probability.**

Going from σ = 12 to σ = 32 — a twenty-point swing in weekly standard deviation,
wider than the gap between the steadiest and streakiest teams in league history
— moves P(title) by just **+0.59 ± 0.17 percentage points**. That entire swing
is worth about **0.34 points per week of mean**, or **0.017 points per week per
unit of σ**.

Put plainly: **trading away even one point per week of projection to gain
ceiling is a losing trade by roughly a factor of five**, and you would need to
add twenty points of weekly standard deviation to make back a third of a point
of mean. The best-ball literature's rule of thumb — volatility worth about half
a unit of expected points — is off by more than an order of magnitude here.

## Why this format punishes variance

The small positive effect that does exist hides two opposing forces:

- **Variance hurts the regular season.** Dual points fall from 14.25 to 14.13
  and average seed drifts from 5.35 to 5.44. The top-5 bonus is a *threshold* —
  scoring 190 earns exactly what scoring 125 earns — so ceiling weeks are capped
  while floor weeks still cost the point. With only 4 of 10 teams qualifying,
  seeding is where seasons are won.
- **Variance helps slightly once you are in.** P(reaching the final) rises from
  15.6% to 16.3%, the familiar underdog-wants-a-coin-flip effect.

These nearly cancel. The format is deliberately hostile to the second effect:
the title is decided over **two weeks**, not one, which averages out exactly the
luck a weaker team needs.

A counterfactual confirms the format is doing the work. Under a conventional
setup — plain head-to-head, 6 playoff teams, one-week final — the same σ sweep
moves P(title) from 5.5% to 6.5%, an effect roughly **twice as large** as in the
real format. Variance is worth more in normal leagues. It is close to worthless
in this one.

## What this means for the draft engine

1. **Optimize expected points, not P(championship).** The two objectives rank
   candidates nearly identically here, and expected points is far cheaper to
   compute — which matters directly for the sub-30-second live re-solve.
   The spec's three-layer architecture survives; the expensive correlated
   season Monte Carlo at its center does not earn its keep.
2. **Set `lambda_risk` to roughly zero, and `ceiling_weight` likewise.** A mild
   *preference for floor* is defensible for starters; a ceiling tilt is not
   supported by anything measured here.
3. **Spend the effort on the alpha model instead.** If a point per week of
   projection is worth 1.72 points of championship probability, then projection
   accuracy and paying the right price relative to ADP are where the entire edge
   lives. Every hour spent on correlation structure is an hour not spent there.
4. **Availability matters more than upside.** Games missed reduce the mean
   directly, and the mean is what pays. The risk model should prioritize the
   games-played model over the weekly-variance model — the reverse of the
   spec's emphasis.

## What this does *not* test

The simulation varies **weekly** variance at a fixed season mean. It says
nothing about **season-long outcome uncertainty** — the breakout-or-bust
question on a late-round pick whose true talent is unknown.

That is a genuinely different thing, and there the usual upside logic may still
hold: the waiver wire is a free option, so you can discard the bust and keep the
breakout. A late-round swing is cheap because its downside is truncated, not
because variance is inherently valuable. Any "draft upside late" rule should be
justified by *that* argument, and tested separately, rather than by the
top-heavy-payoff reasoning this study rejects.
