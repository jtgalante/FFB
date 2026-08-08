# The 2026 Draft: Analysis and Plan

**Status: analysis phase complete.** This is the synthesis of `league_rules.md`,
`room_study.md`, `variance_study.md` and the 2026 data, and it supersedes the
per-finding notes where they disagree. Generated inputs live in
`board_2026.md` (`python -m scripts.build_board`).

---

## 1. The bottom line

Optimise **expected points**. Ignore variance. The draft reduces to seven
consecutive pairs of picks, and three of the first four pairs have a specific
target that this room reliably leaves on the table.

| pick | take | why |
|---|---|---|
| **1** | Jahmyr Gibbs | 170 VOR, the largest gap on the board |
| **20 / 21** | the two best RB/WR — *unless* the best is worth <~70 VOR, then Josh Allen | Allen is ~100% available but only the right call ~22% of the time; the rivals there are worth 71–74 |
| **40 / 41** | **Trey McBride or Brock Bowers**, plus the best RB/WR | a top-two TE lands here in **94%** of sims and nothing else in the window is close |
| **60 / 61** | a quarterback if you skipped one (53% of sims), else best available | Daniels / Burrow / Hurts / Jackson are the fallback, and it is a good one |

Everything below is why, and where it could be wrong.

## 2. The structural fact nobody in this room can copy

James drafts from slot 1. His picks are:

> 1 · **20, 21** · **40, 41** · **60, 61** · 80, 81 · …

The gaps alternate **19, 1, 19, 1**. After the opener, *every pick is half of a
back-to-back pair with no opponent in between.*

This matters more than it sounds:

- **There is never a sequencing decision inside a pair.** At 20/21 he does not
  have to guess whether a player survives one more pick — he simply takes the
  best two available. The classic "reach for the guy who won't last" problem
  does not exist at this slot.
- **All the risk is concentrated in the 19-pick gaps.** The only question that
  matters is what survives *nineteen* opposing picks, which is exactly what the
  availability simulation in `board_2026.md` estimates.
- **It rewards targeting scarce positions.** A pair of picks can solve two
  positions at once, so the cost of spending one on QB or TE is much lower than
  it would be for a manager picking once per round.

## 3. What is settled

Verified against the live league on 2026-08-07 (`data/draft/league_settings.json`):

- 10 teams, half-PPR, **6-point passing TDs**, **−2 interceptions**
- Starters: QB / RB / RB / WR / WR / TE / FLEX / FLEX. No K, no DST
- **No IR slot.** 7 bench spots; an injury costs a real roster spot all season
- 14-week dual-points regular season, 4 playoff teams, two-week aggregate final

## 4. The value model

**Value over replacement, on projections rescored to this league.** Not raw
projections, and not championship probability.

Rescoring is not cosmetic. FantasyPros exports QBs at 4-point passing TDs; this
league plays 6. The correction runs from +0 to +59 points and **reorders the
position** (Stafford QB15 → QB8, Burrow QB7 → QB4).

Replacement levels are derived with FLEX allocated endogenously, not hand-picked:

| pos | replacement | who |
|---|---|---|
| QB | 345.4 | Jaxson Dart |
| RB | 167.1 | Rhamondre Stevenson |
| WR | 163.6 | Marvin Harrison Jr. |
| TE | 138.5 | George Kittle |

Two consequences do real work in what follows:

1. **FLEX arbitrages RB against WR.** The 20 flex slots go 10 RB / 10 WR, and
   the two replacement levels converge to within 3.5 points. Practically: you
   need *four good RB/WR*, not two of each.
2. **FLEX does nothing for TE.** No tight end outscores the marginal flex back
   or receiver, so TE stays a ten-starter position with replacement 28 points
   below. This is the entire reason elite TE is worth buying — and the reason a
   *second* elite TE is worth almost nothing, since he cannot reach the lineup.

**Why not optimise championship probability?** `variance_study.md` settles it:
one point per week of expected scoring is worth +1.72pp of title probability,
while the entire realistic range of weekly volatility is worth +0.59pp. Expected
points and championship probability rank candidates almost identically here, and
the first is far cheaper. `lambda_risk` is set to **-0.017** (the exchange rate
the study actually implies — variance is very faintly helpful, and far too
faintly to act on) and `ceiling_weight` to **0**.

## 5. Findings

### 5.1 The room's running-back bias is the edge — but it is priced into RB, not WR

This room took 74% RB in round one over five years; by pick 19 roughly **12 RBs**
are gone. Calibrating the simulator to reproduce that requires shifting RBs
**8.5 picks earlier** than national ADP.

The original hypothesis (`room_study.md` §5.1) was that this leaves *WR* value at
20/21. **That is only half right.** WR value does survive, but the WR tier
flattens hard after Amon-Ra St. Brown — Lamb and Jefferson come in at 54 and 51
VOR, good but not exceptional. The bigger beneficiaries of an RB-drained board
are **the positions nobody is bidding on at all**: QB and TE.

### 5.2 The QB edge is one player, not a position

The room takes QB1 at ~pick 25. National ADP has Josh Allen at 25.7. **The room
is exactly at market on QB** — so "this room is late on QB" confers no discount
by itself. `room_study.md` finding #2 overstates this.

The real mispricing is the scoring system. At 6-point passing TDs, Allen is the
**18th most valuable player on the board** and ~**100% available** at 20/21.
The cliff behind him is enormous:

| | VOR |
|---|---|
| Josh Allen | **70** |
| Drake Maye | 28 |
| Lamar Jackson | 26 |
| Joe Burrow | 21 |

**Take Allen at 20/21, or take no quarterback until round 6+.** Maye at his ADP
of 49 is a ~34-point mistake against the tight end sitting at 44 — the gap
between QB1 and QB2 means there is no middle path.

But Allen is a *conditional* buy, not a lock: the simulation takes him only
~22% of the time, because Jacobs (72 VOR), London (74) and Hampton (71) are
genuine rivals at those picks and Allen is 70. **The rule is the threshold, not
the name** — take him only if the best RB/WR available is worth less than ~70.
The fallback is sound: a QB arrives at pick 60 in 53% of sims.

**This contradicts the champion pattern, deliberately.** "13 of 16 champions
took their first QB in round 5+" is drawn mostly from the **4-point era** —
6-point passing TDs only passed in **2022**. Four drafts under the current rule,
and the room's QB1 has moved earlier in each of the last three (28, 26, 25).
That looks like a market repricing slowly. Weight the scoring math over the
historical pattern.

### 5.3 The tight end pocket at 40/41 is the cleanest edge on the board

| player | VOR | ADP | P(available at 40) |
|---|---|---|---|
| Trey McBride | **62** | 44.1 | **70%** |
| Brock Bowers | 57 | 45.1 | 70% |
| Travis Etienne Jr. | 43 | 38.6 | 25% |
| D'Andre Swift | 38 | 43.3 | 41% |

McBride leads that window by ~19 points of VOR, and **one of the two elite
tight ends is there 94% of the time** — which is the number that matters, since
either solves the slot.
Note also: Cannon won 2025 taking McBride at pick 40.

**Do not take both tight ends.** A second TE cannot start (§4.2). Take one, and
spend 41 on the best RB/WR.

### 5.4 Availability, not variance, is the risk that matters

`variance_study.md` already argued games-played beats weekly ceiling. **No IR
slot** sharpens it: an injured player occupies one of seven bench spots all
season. This also weakens that study's own "draft upside late" caveat — the
waiver-wire option is real, but the carrying cost is higher here than assumed.

### 5.5 `opponent_adp_noise: 4.0` is wrong and should be per-player

Measured dispersion from 1,808 drafts:

| | rds 1–2 | rds 3–4 | rds 5–6 | rds 7–12 | rd 13+ |
|---|---|---|---|---|---|
| mean ADP sd | **2.0** | 4.3 | 7.2 | 10.2 | **15.7** |

A flat 4.0 tells the engine elite players might fall (they don't) and late
players will wait (they won't) — corrupting precisely the 19-pick-gap
calculation this slot depends on. Per-player `adp_sd` is already in
`data/draft/adp.parquet` and is what `build_board.py` uses.

## 6. The plan, with probabilities

From `board_2026.md`, 2,000 simulations, RB tilt calibrated to this room.

These are what the simulation *actually drafts*, choosing at each of my picks
the player who adds most to my best starting lineup against replacement-level
alternatives — not the highest VOR in isolation. Percentages are share of sims.

| pick | choice |
|---|---|
| **1** | **Jahmyr Gibbs, 100%** |
| **20** | best RB/WR: St. Brown 14%, Chase Brown 10%, Smith-Njigba 9%, Barkley 9% |
| **21** | **Josh Allen 22%**, Jacobs 19%, London 13%, Hampton 13% |
| **40** | **Trey McBride 67%**, Brock Bowers 27% — *a top-two TE 94% of the time* |
| **41** | best RB: Etienne 18%, Swift 17%, Javonte Williams 12% |
| **60** | **a quarterback 53%**: Daniels 32%, Burrow 8%, Hurts 7%, Jackson 6% |

**Order inside a pair is irrelevant.** Picks 20 and 21 are consecutive, so the
two players you end up with are the same whichever you name first. Allen
appearing at 21 rather than 20 is an artefact of greedy ordering, not strategy.

**Correcting my own earlier overconfidence: Allen is not a lock.** He is ~100%
*available* at 20/21, but taking him is only right about 22% of the time,
because Jacobs (72 VOR), London (74) and Hampton (71) are genuine rivals at the
same picks and Allen is 70. The rule that survives is the one about the cliff,
not about Allen specifically:

> **Take Allen at 20/21 only if the best RB/WR there is worth less than ~70.
> Otherwise take the skill player and let the QB come at 60.**

That works because the fallback is good: the sim takes a quarterback at pick 60
in 53% of runs — Daniels, Burrow, Hurts or Jackson — which is exactly the round
5–6 the room's champions historically used. The two branches are not far apart
in value, which is why this is a decision rule rather than a script.

**The tight end call is the firm one.** A top-two TE at pick 40 happens in 94%
of simulations, and nothing else in that window is close. If you remember one
thing from this document, it is pick 40.

## 7. What would change this

- **Allen gone before 20.** 9% of sims. Then take no QB until round 6+ and
  treat 20/21 as two RB/WR picks. Do not take Maye as consolation.
- **McBride *and* Bowers gone before 40.** ~11%. Then TE is unsolved; Loveland
  (32 VOR, ADP 68) is the fallback at 60/61, not a reach at 41.
- **The room drafts to national ADP instead of its own history.** The RB tilt is
  calibrated on 2021–25 behaviour by the same ten managers. If someone brings a
  national cheat sheet, RB value at 20/21 improves and QB/TE value falls.
- **The champions table.** 2018 and 2020 are inferred, not confirmed. They do
  not affect §5.2's conclusion — that rests on the scoring math — but they do
  affect how much weight the champion pattern deserves as counter-evidence.

## 8. Known limits — read before trusting any number here

1. **ADP is pooled, not 10-team.** FantasyPros' `teams` parameter is echoed but
   ignored; `teams=10` and `teams=12` return identical values. Positional runs
   in a 10-team room are more compressed than this implies, which affects
   exactly who survives to 20/21.
2. **No ECR, so no market uncertainty.** The CSV export gives projections but
   not consensus rank or its dispersion. Every projection here is a point
   estimate from one source with no confidence interval.
3. **The opponent model is nine individuals, but a thin model of each.** Every
   opponent now carries his own RB lean and his own historical first-QB and
   first-TE round from `room_tendencies.json`, and seat order is redrawn each
   sim because the 2026 draft order is unknown. Still unmodelled: run-chasing
   (Clark, 1.27x), player loyalty (rebuy rates), and any reaction to what I do.
4. **Projections are single-source.** No blending, no regression, no
   games-played model. §5.4 argues availability is the dominant risk, and it is
   currently unmodelled.
5. **Replacement level is static.** It is computed as if all 150 picks happen at
   once, so late-round VOR understates true scarcity.

## 9. Corrections made during this analysis

Recorded because several were repeated in conversation before being caught.

| claim | corrected to | cause |
|---|---|---|
| WR value is the main edge at 20/21 | QB and TE are; WR is real but flatter | ADP-only analysis before projections existed |
| Josh Allen is the 15th most valuable player | 18th | replacement ranks were hand-picked, not FLEX-derived |
| The TE pocket leads its window by ~32 VOR | ~19 | same |
| James is 1st in points per week | 2nd, by 0.3 | included playoff weeks |
| The room being "late on QB" is an edge | It is at market; the *scoring system* is the edge | conflated relative-to-other-leagues with relative-to-price |
| "Take Josh Allen at 20" | Take him only if the best RB/WR there is worth <~70 VOR; right ~22% of the time | greedy VOR ignored that RB/WR rivals at those picks are worth 71-74 |
| Opponents modelled as one average RB-biased drafter | Nine individuals, from `room_tendencies.json` | placeholder that survived longer than it should have |
