# FFB — fantasy football draft engine

Two things live here: the original Streamlit analytics dashboard (`src/*.py`,
2010–2025 league history), and a **draft engine** being built for James's 2026
draft (`src/draft/`, `scripts/`, `research/`, `config/`).

James drafts from **slot 1** (picks 1, 20, 21, 40, 41, …) in a 10-team league.
The draft is imminent — August 2026.

## Read these first

| File | What it is |
|---|---|
| `research/room_study.md` | 16 years of opponent draft tendencies + scouting reports |
| `research/variance_study.md` | **Rejects the original spec's core premise** — read before designing anything |
| `research/league_rules.md` | Dated rule timeline with quoted evidence |
| `config/league.yaml` | League settings + engine parameters |
| `config/history.yaml` | Verified champions per season (the platform data is wrong) |
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
2. **The room's QB market is late.** No QB in the first 19 picks in five years;
   QB1 goes ~pick 25. 13 of 16 champions took their first QB in round 5+.
3. **Round 1 is 74% RB in this room** while national boards skew WR — so the
   pick 20/21 wrap should offer WR value. This is the main structural edge.
4. Per-opponent tendencies are in `research/room_tendencies.json`.

## Data

The engine reads only local files (`data/draft/`), so draft day needs no network.

```bash
python -m scripts.sleeper_settings          # live league settings -> config diff
python -m scripts.fetch_data                # projections, ADP, weeklies, byes
python -m src.draft.cli bootstrap           # offline fixture from committed caches
```

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

- Player joins use a normalized `name|position` key (`src/draft/ids.py`), never
  raw names. Unmatched players are reported, not silently dropped.
- Manager names are canonicalized via `MANAGER_ALIASES` in `src/config.py`.
  Note "Donnie Darco" in the ESPN export is **Peter Wallach**.
- Never trust the platform caches for champions — use `config/history.yaml`.
- A separate **Gaetz Dynasty** league also exists on Sleeper from 2024. It is a
  different competition; never mix its data in.
- Regenerate research with `python -m scripts.room_study`,
  `python -m scripts.variance_study`,
  `python -m scripts.rebuild_standings --validate`.

## Status

Done: data pipeline scaffolding, league/rules research, opponent model
parameters, variance study.

Not started: alpha model + static board, draft simulator/optimizer, live draft
CLI. **The original spec (`Fantasy Draft Portfolio Engine — Cowork Handoff v1`)
needs rewriting** against finding #1 before those get built — James wants to be
engaged on that, not handed a finished design.

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

Open questions for James: confirm the 2018/2020/2024/2025 champions in
`config/history.yaml`. **Blocked on James: 2026 projections + ECR.** Log in to
FantasyPros and use the "Download CSV" button, save to `data/inputs/`
(`projections.csv`, `adp.csv` optional) — see `docs/DATA.md`. Nothing else is
missing; ADP, weekly history, byes and the player index are all fetched and
committed.
