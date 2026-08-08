# The Room: 16 Years of Draft Tendencies (2010–2025)

**Data:** all 2,420 draft picks, 2010–2025, same 10 managers every season.
Champions come from `config/history.yaml`, verified against league email — **not**
from the platform caches, which name the wrong champion in at least three
seasons (see §0). Regular-season strength is recomputed under the league's real
dual-points system. Generated tables live in `room_study_tables.md`
(`python -m scripts.room_study`); opponent-model parameters are exported to
`room_tendencies.json`.

Rules changed across eras (16 rounds + K/DST in 2010–12, DST-only 2013–23,
neither since 2024), so tendency comparisons are within-year: position rank at
pick and round-relative-to-room, never raw pick numbers. Recent-era numbers
(2021–25) are what matter for 2026; the long history tells us which tendencies
are stable traits rather than noise.

---

## 0. Why the platform data was wrong, and what replaced it

This league never played the format ESPN recorded. The regular season awards
**two points a week**: one for winning your matchup, one for finishing in the
week's **top five scorers**. ESPN could only store head-to-head W/L, so its
standings describe a different competition — and its playoff bracket, which
also can't express "the regular-season winner picks its opponent," named the
wrong champion in **2012, 2017, and 2020**.

Both halves are now reconstructed:

- **Regular season** is recomputed from weekly scores in
  `scripts/rebuild_standings.py`. It reproduces the commissioner's own
  spreadsheets *exactly* for 2019 and 2023 (all ten managers), and is one point
  off for two managers in 2018 — no ties exist in that data, so the likely
  cause is an ESPN stat correction applied after the sheet was written.
  Check it any time with `--validate`.
- **Champions** live in `config/history.yaml` with a source per season. Twelve
  are quoted directly from league email. **2018 and 2020 are derived**, not
  stated: the commissioner published cumulative title counts in January 2018
  and January 2022, and only one assignment of the intervening titles fits
  (2018 → McCauley, 2020 → Wallach). **2024 and 2025 come from the Sleeper
  bracket**, since league communication moved to GroupMe. Those four want a
  memory check from James before anything leans hard on them.

One more trap: a separate **Gaetz Dynasty** league also runs on Sleeper from
2024 (winners: Lettieri 2024, Dzuris 2025). It is a different competition and
is excluded everywhere here.

## 1. Room-level findings

**The QB market here is late, and nobody is fighting over it.** No QB has gone
in the first 19 picks in any of the last five drafts. The first QB goes at pick
25–34, the third at 36–55 — though the window is tightening (QB1 at picks 28,
26, 25 in 2023–25 versus 29, 34 in 2021–22). Ten starting QB jobs for ten
teams, and most managers roster only one or two, so the position never squeezes.

**Round 1 is still an RB round in this room: 74% RB / 26% WR over the last five
drafts.** By pick 19, on average ~12 RBs and ~6–7 WRs are gone. National
half-PPR consensus has drifted hard toward WRs early; this room has not
followed. If 2026 consensus again ranks WRs at the top, the structural discount
in this room sits at WR in rounds 2–3 — exactly where the pick 20/21 wrap-around
lands.

**The TE market is erratic, not efficient.** TE1 has gone anywhere from pick 13
to pick 41 in five years. There is no stable room price for elite TEs, so TE
value at a given pick depends on *who has already drafted*, not on a market
curve.

**The room does not herd much.** The measured "join a position run" rate (44%)
is roughly the unconditional rate of taking those positions, so runs are barely
a real phenomenon on average. Individuals differ: Clark (1.27x) and Gamble
(1.22x) chase them; Lettieri and Wiggins (0.85x) fade them.

**Player loyalty is real but mild.** Chance alone would have a manager re-drafting
his own last-year player 10% of the time. Lettieri (15%), Wiggins (14%), Dzuris
and McCauley (13%) run above that with documented favorites; Cannon (7%) and
Clark (8%) are actively disloyal.

## 2. What champions actually did

With the corrected champion list, the pattern is *stronger* than the platform
data suggested, not weaker:

- **13 of 16 champions took their first QB in round 5 or later; the median
  champion's first QB came in round 8.** The three exceptions are 2011 (rd 3),
  2012 (rd 2), and 2016 (rd 4) — all more than nine years ago. In the last nine
  seasons, no champion has taken a QB before round 5.
- **Champions spend early capital almost entirely on RB and WR.** Across their
  first four picks (64 picks total): **31 RB, 27 WR, 3 TE, 3 QB.**
- **Openings are RB-first**: 12 of 16 champions opened with an RB, and the modal
  start is RB→WR.
- **Slots 5–7 hold 11 of 16 titles**; slot 1 has 2 (Rogers 2021, Cannon 2025)
  and the second-best average regular-season seed (5.25). Slot 1 has produced a
  champion in two of the last five seasons — including last year. Treat all of
  this as narrative, not signal: 16 seasons over 10 slots is ~1.6 titles per
  slot expected, and these differences are well inside noise.

## 3. Scouting reports (2026 opponents)

"QB rd" / "TE rd" are recent-era (2021–25) medians. "Seed" is average
dual-points regular-season seed, 2021–25.

- **Matt McCauley** — 3 titles (2016, 2018, 2023), seed 5.6. Waits on QB (rd 8
  recent; rd 13 in his 2023 title year). Balanced RB/WR early. The most
  consistently dangerous drafter in the room.
- **Peter Wallach** *(exported as "Donnie Darco")* — 3 titles (2010, 2014,
  2020), but the worst recent seed in the room (7.2). Waits longest on QB
  (rd 10) and recently grabs an early TE (rd 5 median). Declining.
- **Anthony Lettieri** — 3 titles, none since 2019, and a 7.4 recent seed.
  QB rd 6, TE rd 8, RB-heavy early, fades runs, rebuys his guys (Chubb, Sanders).
- **Bryan Cannon** — reigning champion (2025, from slot 1) plus 2012; best
  recent seed after Wiggins (4.4). Latest QB in the room (rd 9, ~QB7) and now
  pays up for TE (rd 4 median; his title run opened RB→WR→WR→TE). Least loyal
  (7%), doesn't chase runs. The most market-efficient drafter here.
- **Jonathan Wiggins** — 1 title (2011) but the **best recent seed in the room
  (3.6)** and the best 16-year average seed (4.38). Early-ish QB (rd 5) and TE
  (rd 6); most loyal drafter (Brees 5x, Godwin/Ekeler 4x). Consistently strong,
  chronically unlucky in the bracket.
- **Stephen Rogers** — 2021 champion, tied for best recent seed (3.6). QB rd 5,
  WR-heavy early (8 of his last 15 early picks — most in the room).
- **Tyler Clark** — 2022 champion, seed 6.8. Biggest run-chaser (1.27x): if two
  RBs go back-to-back before his pick, expect a third. QB rd 6, TE rd 9.
- **Brendan Gamble** — 2017 champion, seed 6.4. Very late QB (rd 7, ~QB7),
  latest TE (rd 10), joins runs (1.22x), and has taken **zero** QBs or TEs in
  rounds 1–3 across 16 years. The purest RB/WR-early drafter in the room.
- **Brian Dzuris** — 0 titles in 16 years, though a respectable 5.4 recent seed.
  **Earliest QB in the room recently (rd 4)** — the one manager likely to take a
  QB before pick 40. Joins runs (1.15x).

## 4. James's own profile (know thyself)

- **One QB per draft, 15 of 16 years** — the most extreme single tendency in the
  dataset. Historically paid for elite QBs (average QB3 taken; Rodgers 6x), but
  drifting later (rd 9 Mahomes in 2025).
- **Earliest TE-taker in the room by rank** (average TE4), median round 7 recently.
- Middle of the room on runs (0.95x) and loyalty (11%).
- One title (2024), recent seed 4.6 — fourth-best in the room.

Treat these as priors to challenge, not to flatter. The one-QB habit is
defensible in a 10-team league where streaming is easy. The early-TE habit is
the one to interrogate: it spends capital in exactly the rounds where this
room's champions loaded up on RB and WR.

## 5. Hypotheses for 2026 from slot 1

Testable once real 2026 projections and ADP are fetched:

1. **Picks 20/21 should offer WR value.** The room takes ~12 RBs in the first 19
   picks while national boards are WR-heavy; expect WRs ranked top-12 nationally
   to survive to the wrap. The engine should price this gap explicitly.
2. **QB can wait until pick 40/41 at the earliest, probably 60/61.** QB1 goes
   ~pick 25, QB3 ~pick 37–55, and only Dzuris threatens before pick 40.
3. **TE timing hinges on Cannon and Darco**, the two recent early-TE buyers — a
   solver tracking who has already taken a TE will out-time any static rule.
4. **At 1.1, take the best RB or WR.** No champion in 16 years started QB or TE,
   and 12 of 16 opened RB. The pick's real cost is what disappears during the
   18-pick wait, which the 20/21 scenario cache should quantify.
5. **Exploitable quirks for the opponent model:** Clark's run-chasing, the
   loyalty lists, Dzuris's early QB, Cannon's early TE, Rogers's WR lean — all
   parameterized in `room_tendencies.json`.

## 6. Caveats

- Tendency findings rest on 2,420 picks and are solid. **Outcome-linked findings
  rest on 16 championships** — strong narrative, weak statistics. Nothing in §2
  should be treated as significant on its own; it earns its place by agreeing
  with the structural argument in §1.
- 2018, 2020, 2024, and 2025 champions are derived rather than quoted. If any
  proves wrong, §2's counts shift by one.
- No historical ADP is attached yet, so "reaching" is measured only against this
  room's own revealed order, not against the market. The laptop data pass adds
  realized points and true ADP, enabling hit-rate and reach-vs-market analysis.
