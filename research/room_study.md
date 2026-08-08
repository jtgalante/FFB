# The Room: 16 Years of Draft Tendencies (2010–2025)

**Data:** all 2,420 draft picks, 2010–2025, same 10 managers every season; final
standings for all 16 seasons; weekly lineup data 2019–2025. Generated tables and
the exact methodology live in `room_study_tables.md` (regenerate with
`python -m scripts.room_study`). Per-manager parameters for the draft simulator's
opponent model are exported to `room_tendencies.json`.

Rules changed across eras (16 rounds + K/DST in 2010–12, DST-only 2013–23, neither
since 2024), so all tendency comparisons are within-year: position rank at pick and
round-relative-to-room, not raw pick numbers. Recent-era numbers (2021–25) are what
matter for 2026; the long history mainly tells us which tendencies are stable traits
versus noise.

---

## 1. Room-level findings

**The QB market here is late and getting later is over.** No QB has gone in the
first 19 picks in any of the last five drafts. The first QB goes at pick 25–34, and
the third QB at pick 36–55 — but the window is tightening: QB1 went at picks 28, 26,
25 in 2023–25 after 29, 34 in 2021–22. Ten starting QB jobs for ten teams, and six
of ten managers roster only 1–2 QBs, so there is never a positional squeeze. Nobody
in this room pays a premium at the position anymore: zero QBs drafted in rounds 1–3
in the last five years except one apiece by Cannon, Darco, Wiggins, McCauley, and
Clark spread across five drafts.

**Round 1 is still an RB round in this room: 74% RB / 26% WR over the last five
drafts.** By pick 19, on average ~12 RBs and ~6–7 WRs are gone. National half-PPR
consensus has drifted heavily toward WRs early; this room has not followed. If 2026
consensus boards again rank WRs at the top, the structural discount in this room is
at WR in rounds 2–3 — the wrap-around at picks 20/21 should reliably offer WRs
ranked well above their cost.

**The TE market is erratic, not efficient.** TE1 has gone anywhere from pick 13 to
pick 41 in five years. There's no stable room price for elite TEs — meaning TE value
at any given pick depends almost entirely on *who* has already drafted, not on a
market curve. (The simulator's opponent model matters most here.)

**The room does not herd much.** The measured "join a position run" rate (44%) is
roughly the unconditional rate of taking those positions; position runs are barely a
real phenomenon here on average. But individuals differ: Clark (1.27x) and Gamble
(1.22x) chase runs; Lettieri and Wiggins (0.85x) fade them.

**Player loyalty is real but mild.** If a manager drafted a player last year and he's
drafted again this year, random chance says the same manager takes him 10% of the
time. Wiggins (14%), Lettieri (15%), Dzuris, and McCauley (13%) run above that and
have documented "their guys" (Wiggins: Godwin, Ekeler; Lettieri: Chubb, Sanders;
McCauley: M. Thomas, Julio). Cannon (7%) and Clark (8%) are actively disloyal.
Mild, but usable at the margin: a "his guy" is slightly likelier to be reached for
a few picks before your turn.

## 2. What champions did

Sixteen champions' draft constructions (full table in `room_study_tables.md`):

- **14 of 16 champions took no QB before round 5.** Median champion first-QB round:
  7.5. The two exceptions are from 2011 and 2016. No round-1 or round-2 QB has ever
  won this league.
- **Champions' first four picks are overwhelmingly RB/WR** — across 64 such picks,
  only 4 TEs and 2 QBs appear. The modal opening is RB→WR or RB→RB, then WRs.
- **Slot 1 has won 3 of the last 6 titles** (Gamble 2020, Rogers 2021, Cannon 2025)
  and 3 of 16 overall with the second-best average finish (5.06). The middle slots
  (5–7) have historically done best (avg finish 3.8–4.8, 8 titles combined), but with
  ~16 seasons per slot this is suggestive, not significant. The wrap-around slot is
  not a disadvantage in this room's history — 2025's champion drafted exactly the
  seat James drafts from in 2026.

## 3. Scouting reports (2026 opponents)

Ordered by titles. "QB rd" / "TE rd" are recent-era (2021–25) medians.

- **Anthony Lettieri** — 4 titles (none since 2019, avg finish 6.4 recently). QB rd 6,
  TE rd 8. RB-heavy early (8 of last 15 early picks RB). Fades runs, rebuys his guys
  (Chubb 4x, Sanders 4x). The most decorated drafter, but drifting mid-pack.
- **Matt McCauley** — 3 titles incl. 2023. Waits on QB (rd 8 recent; rd 13 in his
  2023 title year). Balanced RB/WR early, mild loyalty (Thomas/Julio era). Steady:
  avg finish 5.4 recently.
- **Jonathan Wiggins** — 2 titles, best 16-year win rate, avg finish 4.6 recently.
  Early-ish QB (rd 5) and TE (rd 6) for this room; fades runs; most loyal drafter in
  the room (Brees 5x, Godwin/Ekeler 4x).
- **Donnie Darco** — 2 titles (2010, 2014), struggling lately (avg finish 8.6
  recently). Waits longest on QB (rd 10 recent) but grabbed an early TE recently
  (rd 5 median). Unpredictable at TE.
- **Bryan Cannon** — reigning champ (2025, from slot 1). Latest QB in the room
  (rd 9 median, rank ~QB7). Recently pays up for TE (rd 4 median 2021–25 — took
  TE early in his title run: RB→WR→WR→TE start). Least loyal (7%), doesn't chase
  runs. Arguably the most market-efficient drafter here.
- **Stephen Rogers** — 2021 champ (also from slot 1), avg finish 4.6 recently.
  QB rd 5, WR-heavy early recently (8 of 15 early picks WR — most in room).
- **Tyler Clark** — 2022 champ. Biggest run-chaser (1.27x) — if two RBs go in a row
  before his pick, expect a third. QB rd 6, waits on TE (rd 9). Low loyalty.
- **Brendan Gamble** — 2020 champ (slot 1 again). Very late QB (rd 7 recent, rank
  ~QB7), latest TE (rd 10), joins runs (1.22x), zero early-round QBs/TEs in 16
  years of rounds 1–3. The purest RB/WR-early drafter in the room.
- **Brian Dzuris** — 0 titles in 16 years (avg finish 6.5, best-ever 21-25 stretch
  5.8). Earliest QB in the room recently (rd 4 median) — the one manager who might
  take a QB before pick 40. Joins runs (1.15x).

## 4. James's own profile (know thyself)

- **One QB per draft, 15 of 16 years.** The single most extreme tendency in the
  entire dataset. Historically paid up for elite QBs (avg rank taken: QB3; Rodgers
  6x), but has drifted later — rd 9 Mahomes in 2025.
- **Earliest TE-taker in the room by rank taken** (avg TE4), median rd 7 recently.
- Middle-of-room on runs (0.95x) and loyalty (11%).
- One title (2024), from slot 7. Avg finish 5.4 over the last five years.

The engine should treat these as *priors to challenge*, not to flatter: the
1-QB strategy is defensible in a 10-team league (streaming is easy), but the
early-TE habit costs RB/WR capital in exactly the rounds where this room's
champions loaded up on RB/WR.

## 5. Implications for 2026 from slot 1 (hypotheses to validate with live data)

These become the testable inputs to the strategy engine once real 2026
projections/ADP are fetched:

1. **Picks 20/21 will offer WR value.** The room takes ~12 RBs in the first 19
   picks while national boards are WR-heavy — expect WRs ranked top-12 nationally
   to be available at the wrap. The engine should price this exact gap.
2. **QB can wait until pick 40/41 minimum, probably 60/61.** QB1 goes ~pick 25;
   QB3 ~pick 37–55; only Dzuris is a threat before pick 40. With 2 FLEX and only
   10 starting QBs, replacement level at QB is high.
3. **TE strategy hinges on Cannon and Darco** (the two recent early-TE buyers) —
   a solver that tracks who has already taken a TE will out-time a static rule.
4. **At 1.1 itself,** history says take the consensus #1 RB/WR and ignore
   everything else; no champion path here has ever started with a QB or TE, and the
   1.1 pick's real cost is what disappears during the 18-pick wait — which the
   pick-20/21 scenario cache should quantify explicitly.
5. **Exploitable opponent quirks for the simulator:** Clark's run-chasing, the
   loyalty lists (Wiggins/Lettieri/McCauley/Dzuris), Dzuris's early QB, Cannon's
   early TE, Rogers's WR lean. All parameterized in `room_tendencies.json`.

## 6. Caveats

- 16 seasons × 10 managers is a real panel for *tendencies*, but outcome-linked
  claims (champion constructions, slot effects) are 16 data points — treat as
  weak evidence, strong narrative.
- No historical ADP is attached yet, so "reach" behavior (vs. market) is measured
  only against this room's own revealed order. The laptop data pass (nflverse +
  FantasyPros API) adds realized points and market ADP, enabling hit-rate and
  reach-vs-market analysis.
- 2024–25 champions were resolved from playoff-bracket week-17 matchups (the raw
  cache double-codes finish=1 those years); 2010–23 finishes are as recorded by ESPN.
