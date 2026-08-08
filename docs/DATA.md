# Getting draft data onto the engine

The engine reads only from local files, so draft day has no live dependencies.
This doc covers how to populate them.

## The one command

On a machine with normal internet access (your laptop):

```bash
pip install -r requirements.txt
python -m scripts.fetch_data
git add data/draft data/inputs && git commit -m "Add fetched draft data" && git push
```

It prints a status line per source and tells you what, if anything, is missing.
Partial success is fine — sources are independent.

## Where each piece comes from

| Data | Primary source | Used for |
|---|---|---|
| Season projections | FantasyPros API → scrape → your CSV | alpha model (VOR) |
| ECR + rank stdev | FantasyPros API | consensus prior, uncertainty |
| ADP | Sleeper (our platform) → FantasyPros | market price, opponent model |
| Weekly points 2021–25 | nflverse releases | risk model (per-player variance) |
| Bye weeks | nflverse schedules | season simulator |
| Player index | Sleeper | live-draft name matching |

ECR and ADP are different things and the engine wants both: **ECR is what
experts think a player is worth, ADP is what the draft actually charges.**
The gap between them is a large part of where the edge lives.

## FantasyPros API key

A premium fantasypros.com account is not automatically API access — the key is
separate, requested at <https://www.fantasypros.com/apis/>. If you get one:

```bash
echo 'FANTASYPROS_API_KEY=your_key_here' >> .env
```

If the key path 401s or the endpoints have moved, the script says so and falls
back automatically. **You do not need the key** — the CSV path below is just as
good and is what your premium account gives you directly.

## CSV path (no key needed, never breaks)

Your premium account has a "Download CSV" button on the projections and ADP
pages. Save them into `data/inputs/` and they override everything else.

`data/inputs/projections.csv`

| column | required | notes |
|---|---|---|
| `name` | yes | "Bijan Robinson" |
| `pos` | yes | QB / RB / WR / TE |
| `proj` | yes | projected season fantasy points, half-PPR |
| `team` | no | improves bye-week and correlation modeling |
| `games` | no | projected games played; defaults to positional averages |

`data/inputs/adp.csv`

| column | required | notes |
|---|---|---|
| `name` | yes | must be the same player naming as projections |
| `pos` | yes | QB / RB / WR / TE |
| `adp` | yes | average draft position, half-PPR, 10-team if offered |

Raw FantasyPros CSV headers differ from these (they use `Player`, `POS`,
`FPTS`, `AVG`). Rename the columns or let the fetch script's scrape path
handle it — the loader validates and tells you what it couldn't match.

Half-PPR, and 10-team ADP if the source offers it; 12-team ADP is an
acceptable approximation at the top of the board and diverges later.

## Name matching

Everything joins on a normalized `name|position` key (accents, punctuation,
and Jr./III stripped; known aliases like Hollywood → Marquise Brown mapped in
`src/draft/ids.py`). Unmatched players are reported rather than silently
dropped — if a name mismatch hides a first-rounder, you want to know.

## Offline development fixture

Without any network, `python -m src.draft.cli bootstrap` derives a working
dataset from this repo's committed league caches (2024–25 weekly scoring and
the 2025 draft board). It is real data but *stale*: 2025 prices and 2025
production, useful only for building and testing the engine. Anything produced
from it is watermarked `source: fixture`. Never draft off it.

## Reading live league settings from Sleeper

`api.sleeper.app` is blocked from the cloud sandbox, so run this on your laptop:

```bash
python -m scripts.sleeper_settings           # show settings and diff vs config
python -m scripts.sleeper_settings --write   # apply them to config/league.yaml
```

It finds the current season's league from your Sleeper username (Sleeper mints a
new league id every season, so `SLEEPER_LEAGUE_ID` in `.env` goes stale each
year) and prints every non-zero scoring value, the roster slots, IR/taxi slots,
and the playoff field. That settles the items the email archive could not:
exact passing-yard/interception/fumble/2-pt values, whether an IR spot exists,
and the playoff team count.

If you're in more than one league that season it stops and lists them — pick the
**redraft** league with `--league-id`, not Gaetz Dynasty.

Two things Sleeper cannot express, so they stay hand-maintained in
`config/league.yaml`: the **two-week aggregate final** and the **#1 seed picking
its semifinal opponent**.
