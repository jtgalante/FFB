# Known deficiencies in the data

Everything here is a **known** gap, deliberately recorded. The point of the
build-time validators and the ClickyDraft verification is that unknown gaps
become known ones; this file is the list they produced.

Ordered by how much they could distort a conclusion.

---

## 1. Six draft boards are still unverified

`scripts/verify_clickydraft.py` checks the archive against the original
ClickyDraft boards. Where it has run, ESPN was found to scramble the draft
**slot** in most seasons — 8 or 9 of 10 managers — while getting
manager-to-player and manager-to-round right every time.

| status | seasons |
|---|---|
| verified against a board | 2014, 2015, 2017, 2019, 2020, 2021, 2022, 2023 |
| native (Sleeper, no import step) | 2024, 2025 |
| **UNVERIFIED** | **2010, 2011, 2012, 2013, 2016, 2018** |

**What this affects:** anything measured in pick NUMBERS for those six seasons —
"QB1 goes at pick 25", "12 RBs are gone by pick 19", who held 1.01. Anything
measured in ROUNDS was always safe, because rounds survive the import intact.

**What it does not affect:** the 2026 draft plan. The opponent model reads
2021–25, all of which are now verified.

**To close it:** get the boards from Bryan, transcribe to
`data/inputs/clickydraft/<season>.tsv`, run `python -m scripts.verify_clickydraft --write`.

## 2. The 2009 draft is recovered but not attributable

`data/inputs/clickydraft/2009.tsv` holds a complete 16-round board that predates
the archive (`draft_cache.json` starts at 2010). It is deliberately held OUT of
the cache: only 6 of 10 slots have a manager.

Unknown: **Bourbon St Drunks, Team Koopa Troopa Beach, Banshee Boardwalk,
Toad's Turnpike**. Unassigned: **Bryan Cannon, Stephen Rogers, Brendan Gamble,
Jonathan Wiggins**. See `data/inputs/clickydraft/2009_slots.json`, which also
records a failed statistical approach so nobody retries it.

Merging it partially would introduce phantom managers into every per-manager
analysis, so it stays out until someone remembers the four team names.

## 3. Eighteen rows where `win` contradicts its own scores

In `team_weeks`, 9 games across 2015, 2016 and 2018 record a winner who scored
fewer points. A defect in the ESPN export, written through unchanged rather
than silently "corrected" — rewriting it would be inventing league history.
`scripts/build_warehouse.py` prints a warning; `check_win_consistency` in
`src/draft/validate.py` finds them.

Head-to-head records for those three seasons are off by a game or two.

## 4. Opponents are reconstructed, not recorded

The platforms recorded your score and your opponent's SCORE, never their NAME.
`team_weeks.opponent` is recovered by matching scores within a week: 99.9% of
2,498 manager-weeks resolve uniquely. **Two rows do not** — 2010 week 6, Bryan
Cannon and Brian Dzuris, a mutual score tie. They are NULL rather than guessed;
resolving them needs elimination/bipartite matching, deliberately not built.

## 5. Lineups start in 2019, and benches never existed

`rosters` covers 2019–2025 only. Before that we have team scores and draft
picks but not who was started.

And for **every** season, only the 8 starting slots were exported. Bench players
were never captured, so **"points left on your bench" is not answerable** and
never will be from this data.

## 6. No transactions, ever

Zero waiver claims, adds, drops or trades, for any season. In-season roster
management is completely invisible. Anything attributing an outcome to "he
worked the waiver wire" is unfalsifiable here.

## 7. 2008 and 2009 have champions but almost nothing else

`config/history.yaml` covers 18 seasons; the weekly and summary data start at
2010. So all-time scoring, seeds and head-to-head cover 16 seasons while the
title count covers 18. **The dashboard shows 16 seasons and therefore reports
Matt McCauley with 3 titles and Bryan Cannon with 2**, against a verified 4 and
3.

## 8. Sacko records are a floor, not a count

Only 7 of 18 seasons record a last-place finisher in `history.yaml`. A manager
with 0 sackos may simply be missing from the recorded seasons.

## 9. Projections are a single-source point estimate

FantasyPros CSV export only, because both their API and their public pages are
gated to 10 players (see `docs/DATA.md`). **No ECR**, so no consensus rank and
no dispersion — every projection is one number with no uncertainty around it.
Nothing downstream can express a confidence interval on player value.

## 10. ADP is pooled, not 10-team

FantasyFootballCalculator echoes the `teams` parameter in its response metadata
but ignores it: `teams=10` and `teams=12` return byte-identical ADP for all 209
players. Positional runs in a real 10-team room are more compressed than this
implies. Sleeper's own ADP endpoint 404s, so the only genuine 10-team source
would be your own mock drafts.

## 11. 2020's board disagrees with ESPN on real players

After slot repair, 2020 matches its ClickyDraft board on 122 of 150 cells — the
worst of any verified season. The residue is genuine player-level disagreement
between the two sources, including a known anomaly where Donnie Darco's roster
lists "BAL DEF" twice (rounds 12 and 14); one is probably Jerry Jeudy.

## 12. Player-level NFL data covers 2021–2025 only

`player_weeks` (29,340 rows) is the nflverse fetch window. Any per-player
durability, variance or games-played analysis is five seasons deep, which is why
`research/availability.md` keeps insisting its findings are tiebreaks rather
than facts.

## 13. Injury reports miss the worst injuries

Once a player goes on IR he drops off the weekly injury report entirely, so a
season-ending injury often produces FEWER report rows than a nagging one.
Absence from `injuries.parquet` is not absence of injury. This is why the games
model pairs report features with appearance-shape features and never uses the
reports alone.
