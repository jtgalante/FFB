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
| **20 / 21** | Josh Allen + best RB/WR | Allen is 91% available and the market prices him for a different scoring system |
| **40 / 41** | Trey McBride + best RB/WR | 85% available; TE replacement sits 28 points below RB/WR |
| **60 / 61** | best available | QB and TE are both already solved |

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
the first is far cheaper. Set `lambda_risk` and `ceiling_weight` to ~0.

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
**18th most valuable player on the board** and available at pick 20 **91% of the
time**. And the cliff behind him is enormous:

| | VOR |
|---|---|
| Josh Allen | **70** |
| Drake Maye | 28 |
| Lamar Jackson | 26 |
| Joe Burrow | 21 |

**Take Allen at 20, or take no quarterback until round 6+.** Maye at his ADP of
49 is a ~34-point mistake against the tight end sitting at 44.

**This contradicts the champion pattern, deliberately.** "13 of 16 champions
took their first QB in round 5+" is drawn mostly from the **4-point era** —
6-point passing TDs only passed in **2022**. Four drafts under the current rule,
and the room's QB1 has moved earlier in each of the last three (28, 26, 25).
That looks like a market repricing slowly. Weight the scoring math over the
historical pattern.

### 5.3 The tight end pocket at 40/41 is the cleanest edge on the board

| player | VOR | ADP | P(available at 40) |
|---|---|---|---|
| Trey McBride | **62** | 44.1 | **85%** |
| Brock Bowers | 57 | 45.1 | 89% |
| Travis Etienne Jr. | 43 | 38.6 | 24% |
| D'Andre Swift | 38 | 43.3 | 44% |

McBride leads that window by ~19 points of VOR and arrives 85% of the time.
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

**Pick 1 — Jahmyr Gibbs (170 VOR).** Bijan is 165 and equivalent; McCaffrey and
Taylor drop to 128/123. Take a back.

**Picks 20/21 — Josh Allen (91%) plus the best RB/WR.** Realistic partners:
Breece Hall (62 VOR, 61%), Hampton (71, 36%), Jacobs (72, 33%), London (74, 21%).
Take the best two available; there is no sequencing risk inside the pair.

**Picks 40/41 — Trey McBride (85%) plus the best RB/WR.** Likely partners:
Swift (38, 44%), Nabers (30, 47%).

**Picks 60/61 — best available.** With QB and TE solved, this is pure VOR.

Result after four pairs: an elite RB, an elite QB, an elite TE, and three or
four RB/WR — from a room that will have spent its early capital almost entirely
on running backs.

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
3. **The opponent model is nine people, calibrated on one aggregate statistic.**
   It reproduces "≈12 RBs gone by pick 19" and randomises seat order because the
   2026 draft order is unknown. Per-manager tendencies in
   `room_tendencies.json` are **not yet wired in** — Dzuris's early QB and
   Cannon's early TE are the two that would most change §5.2 and §5.3.
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
