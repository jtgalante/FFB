# FFB — fantasy football draft engine

Two things live here: the original Streamlit analytics dashboard (`src/*.py`,
2010–2025 league history), and a **draft engine** being built for James's 2026
draft (`src/draft/`, `scripts/`, `research/`, `config/`).

James drafts from **slot 1** (picks 1, 20, 21, 40, 41, …) in a 10-team league.
The draft is imminent — August 2026.

## Read these first

| File | What it is |
|---|---|
| `research/draft_analysis_2026.md` | **The synthesis + the pick-by-pick plan. Start here.** |
| `research/board_2026.md` | Generated board: VOR, tiers, P(available) at each pick |
| `research/availability.md` | **The whole availability investigation**: base rates, role-vs-health, what survives cross-validation, per-player durability, manager luck, and what it is worth |
| `research/room_study.md` | 16 years of opponent draft tendencies + scouting reports |
| `research/variance_study.md` | **Rejects the original spec's core premise** — read before designing anything |
| `research/league_rules.md` | Dated rule timeline with quoted evidence |
| `config/league.yaml` | League settings + engine parameters |
| `config/history.yaml` | Verified champions per season (the platform data is wrong) |
| `data/clickydraft_cache.json` | Golden-source draft history: 2020–2022, correct slot order, team→manager map |
| `docs/DATA.md` | How to get projections/ADP onto the engine |

## The league (verified — see research/league_rules.md)

- 10 teams, half-PPR, **6-point passing TDs**, snake, 15 rounds
- Starters (8): QB, RB, RB, WR, WR, TE, FLEX, FLEX. **No K, no DST**
- **Regular season is NOT plain head-to-head.** 14 weeks, and each week awards
  two points: one for winning your matchup, one for a **top-5 weekly score**
- Playoffs: **4 teams**, week 15 semifinal, **weeks 16–17 two-week aggregate
  final**. The #1 seed picks its semifinal opponent

## Findings that should drive the build

1. **Variance is nearly worthless here.** One point/week of expected scoring is
   worth +1.72pp of championship probability; the entire σ 12→32 range is worth
   +0.59pp (~0.34 pts/week). Optimize **expected points**, set `lambda_risk` and
   `ceiling_weight` to ~0, and prioritize **availability** over weekly variance.
   The spec's correlated season Monte Carlo does not earn its cost.
2. **The room's QB market is late, but that is NOT an edge on its own.** QB1
   goes ~pick 25 here; national ADP has Josh Allen at 25.7 — the room is
   exactly at market. The edge is the **scoring system**: at 6-point passing
   TDs Allen is the 18th most valuable player and ~100% available at 20/21,
   with a 42-point VOR cliff behind him. But he is a **conditional** buy: the
   sim takes him only ~22% of the time, because the RB/WR rivals at those picks
   are worth 71-74 and Allen is 70. The rule is the threshold, not the name —
   take him only if the best RB/WR there is worth <~70, else let a QB come at
   pick 60 (53% of sims). The "13 of 16 champions waited" figure is mostly from
   the 4-point era, which ended in 2022. See `draft_analysis_2026.md` §5.2.
3. **Round 1 is 74% RB in this room.** The original inference — that this
   leaves *WR* value at 20/21 — is only half right; the WR tier flattens after
   St. Brown. The bigger beneficiaries of an RB-drained board are the positions
   nobody bids on: **QB at 20 and TE at 40**. A top-two tight end is there at
   pick 40 in **94%** of sims and leads that window by ~19 VOR — the firmest
   call on the board. See §5.1/§5.3.
4. **From slot 1 the pick gaps alternate 19, 1, 19, 1.** Every pick after the
   opener is half of a back-to-back pair, so there is no sequencing decision
   inside a pair — take the best two available. All risk is in the 19-pick
   gaps, and one pair can solve two scarce positions at once.
5. **Availability is measured, and nobody is cursed.** `availability.md`: the
   largest t-statistic on manager injury luck is 1.82 over five seasons, so no
   one in this room is measurably lucky or unlucky. The actionable signal is
   per-player — Christian McCaffrey has played 72% of games since 2021 and is
   the 3rd most valuable player on the board.
6. Per-opponent tendencies from `research/room_tendencies.json` **are** wired
   into the board simulation (per-manager RB lean, first-QB and first-TE
   round). Still unmodelled: run-chasing, loyalty, and reaction to my picks.

## Data

The engine reads only local files (`data/draft/`), so draft day needs no network.

```bash
python -m scripts.sleeper_settings          # live league settings -> config diff
python -m scripts.fetch_data                # ADP, weeklies, byes, player index
python -m scripts.ingest_projections        # FantasyPros CSV exports -> projections
python -m scripts.build_warehouse           # canonical joined tables -> data/warehouse/
python -m scripts.export_datasheet          # one SQLite file + dictionary -> data/export/
python -m scripts.verify_clickydraft        # check draft slots vs the golden boards
python -m pytest tests/ -q                  # 201 invariants
```

**Projections come from CSV export, not the network.** Save the FantasyPros
per-position exports (QB/RB/WR/TE, plus FLX as a cross-check) into
`data/inputs/Projections/` and run `scripts.ingest_projections`. It recomputes
fantasy points from the component stats under `config/league.yaml` — necessary
because **FantasyPros exports QB projections at 4-point passing TDs and −1
INT**, so its FPTS column understates this league's QBs by up to 59 points and
reorders the position (Stafford QB15 → QB8). It also handles the per-position
column-order reversal (RB is rush-then-rec, WR is rec-then-rush, under
duplicate header names) and cross-checks the parse against the FLX export.

`FANTASYPROS_API_KEY` goes in `.env` (gitignored). **The account allows 50 API
calls/day.** The client caches every response to `data/draft/fp_cache/` and
commits it, enforces a daily ledger, and supports `dry_run=True`.

**The FantasyPros API cannot serve bulk data on this key** (tested 2026-08-07,
3 calls): it answers 200 but returns `tier: free`, `public_api_limited: true`,
`limit: 10` — 10 players out of a `count` of 852, and an explicit `limit` param
does not lift it. The logged-out **web pages are gated identically** (10 `<tr>`
rows), so the scrape fallback is dead too. Premium *website* access and premium
*API* access are separate products. Both paths now raise rather than write a
10-row board. See `docs/DATA.md`. **Projections and ECR must come from the CSV
export into `data/inputs/`** — that is the only ungated path.

Working sources as of 2026-08-07: ADP from FantasyFootballCalculator (public,
no key, includes per-player ADP stdev), weekly history from the nflverse
`stats_player` release (the old `player_stats` tag is frozen at 2024), byes from
`nfldata/games.csv` (the `schedules` release asset 404s), player index from
Sleeper. Sleeper's `/players/nfl/adp/...` endpoint 404s — it does not exist.

**If you are running in a cloud container**, `api.sleeper.app`, `fantasypros.com`
and the nflverse GitHub release assets are blocked by the egress policy — only
the repo host is reachable. Run the fetch scripts locally instead, or widen the
environment's network policy.

## Conventions

- **Analyses read `data/warehouse/`, not the raw caches.** Manager names, draft
  slots, player keys and weekly opponents are resolved once by
  `scripts/build_warehouse.py`. Re-deriving those joins per script is what
  produced the JAC/LAR bye loss, the four silently-deleted injury seasons and
  the scrambled draft slots.
- Data-shape bugs here are silent by default, so `src/draft/validate.py` asserts
  at build time. Every validator maps to a bug that actually shipped. Run
  `python -m pytest tests/ -q` before trusting any regenerated artifact.
- **`data/export/ffb.sqlite`** is the hand-off artifact: all six tables plus
  `DATA_DICTIONARY.md`, self-contained, no dependencies. Give someone that
  directory and they have the league.
- Player joins use a normalized `name|position` key (`src/draft/ids.py`), never
  raw names. Unmatched players are reported, not silently dropped.
- Snake draft arithmetic lives in `src/draft/draftmath.py` — never re-derive it.
- **`team_weeks` has 18 rows where `win` contradicts the scores** (2015/2016/
  2018, ESPN export defect). Written through unchanged rather than silently
  "corrected"; `build_warehouse` warns. Recompute from points if you need true
  head-to-head records.
- Manager names are canonicalized via `MANAGER_ALIASES` in `src/config.py`.
  Note "Donnie Darco" in the ESPN export is **Peter Wallach**.
- Never trust the platform caches for champions — use `config/history.yaml`.
- Never trust the platform caches for **draft slot order** — Clicky Draft is
  the golden source. ESPN/Sleeper shuffle slot assignments on import. See
  `docs/DATA.md`. **Clicky Draft data is now ingested** in
  `data/clickydraft_cache.json` (2020–2022, 450 picks) with correct slot
  assignments, snake pick numbers, team-name-to-manager mappings, and per-season
  slot order metadata. `MANAGER_ALIASES` in `src/config.py` includes all
  `clickydraft` team names. ESPN slot order is wrong in 8–9 of 10 slots per
  season. Known anomaly: Donnie Darco's 2020 roster has "BAL DEF" listed twice
  (rounds 12 and 14) — one is likely Jerry Jeudy (per ESPN cross-ref).
- A separate **Gaetz Dynasty** league also exists on Sleeper from 2024. It is a
  different competition; never mix its data in.
- Regenerate research with `python -m scripts.room_study`,
  `python -m scripts.variance_study`,
  `python -m scripts.rebuild_standings --validate`,
  `python -m scripts.build_board`,
  `python -m scripts.availability_study`.

## Status

**The analysis phase is closed.** Read `research/draft_analysis_2026.md` first:
it is the synthesis and the pick-by-pick plan, it supersedes the per-finding
notes where they disagree, and its §8 lists what is still not modelled and §9
records the claims corrected along the way.

Done: data pipeline (live 2026 projections/ADP/weeklies/byes committed),
league/rules research, opponent model parameters, variance study, alpha model +
static board (`scripts/build_board.py`).

Not started: draft simulator/optimizer, live draft CLI. **The original spec
(`Fantasy Draft Portfolio Engine — Cowork Handoff v1`) needs rewriting** against
finding #1 before those get built — James wants to be engaged on that, not
handed a finished design.

Engine params are now set from the studies rather than the spec's defaults:
`lambda_risk: -0.017` (the exchange rate variance_study.md actually implies —
variance is very faintly helpful, far too faintly to act on) and
`ceiling_weight: 0.0`. `EXPECTED_GAMES` in `data.py` is measured, not guessed.

**Settled 2026-08-07** against the live 2026 league (CFTG, league_id
`1388192476728147968`, status pre_draft) — `config/league.yaml` now matches
Sleeper exactly, snapshot in `data/draft/league_settings.json`:

- **6-point passing TDs CONFIRMED** (`pass_td: 6`)
- **No IR spot** (0 IR, 0 taxi) — an injury costs a real roster spot all season,
  which raises the value of availability further still
- Interceptions are **-2**, not the assumed -1; 2-pt conversions are 2 across
  passing/rushing/receiving
- 10 teams, 8 starters + 7 bench = 15 rounds, 14-week regular season, 4 playoff
  teams — all as previously assumed

Open questions for James:

1. Confirm the 2018/2020/2024/2025 champions in `config/history.yaml`. Only
   2018 and 2020 are load-bearing — they are inferred from published cumulative
   title counts, not stated anywhere.
2. ~~`lambda_risk` / `ceiling_weight`~~ — decided, see Status.
3. ~~Whether to break the room's late-QB convention~~ — decided: James does not
   care about convention, only about the championship-maximising team. The
   engine optimises accordingly.

**Not blocked on data.** Projections (521 players, rescored), ADP, weekly
history, byes and the player index are all fetched and committed. Only ECR is
missing — the CSV export does not include consensus rank or its dispersion, so
every projection is a single-source point estimate with no uncertainty around
it.
