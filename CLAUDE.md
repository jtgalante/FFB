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
commits it, enforces a daily ledger, and supports `dry_run=True`. A full refresh
costs ≤6 calls. Prefer the CSV export path (`data/inputs/`) for bulk data.

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

Open questions for James: confirm the 2018/2020/2024/2025 champions in
`config/history.yaml`; confirm minor scoring values and whether an IR spot
exists (`scripts/sleeper_settings.py` answers both).
