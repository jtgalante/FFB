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

| Data | Working source (verified 2026-08-07) | Used for |
|---|---|---|
| Season projections | **your CSV export only** — everything else is gated | alpha model (VOR) |
| ECR + rank stdev | **your CSV export only** — API is capped at 10 players | consensus prior, uncertainty |
| ADP | FantasyFootballCalculator (public, no key) | market price, opponent model |
| Weekly points 2021–25 | nflverse `stats_player` release | risk model (per-player variance) |
| Bye weeks | nflverse `nfldata/games.csv` | season simulator |
| Player index | Sleeper `/players/nfl` | live-draft name matching |

ECR and ADP are different things and the engine wants both: **ECR is what
experts think a player is worth, ADP is what the draft actually charges.**
The gap between them is a large part of where the edge lives.

## FantasyPros: what actually happens (tested 2026-08-07)

The endpoints are correct and the key authenticates. The problem is the **tier**,
and it is worth stating plainly because it is not what you would expect from a
premium subscription:

```
GET /public/v2/json/nfl/2026/consensus-rankings  ->  200 OK
    { "count": 852, "limit": 10, "public_api_limited": true, "tier": "free",
      "players": [ ...10 of them... ] }
```

- `count` is the real number of players. `limit` is what you get: **10**.
- Passing an explicit `limit=1000` does **not** lift it — tested, still 10.
- `/2026/projections` behaves identically: 10 of 599.
- The **public web pages are gated the same way**. The logged-out HTML for
  `nfl/projections/rb.php` contains only 10 `<tr>` rows, and the ADP page no
  longer ships an `id="data"` table at all. So the scrape fallback is dead too.

A premium **fantasypros.com website** subscription and premium **API** access
are two different products. The site subscription is what gives you the
"Download CSV" buttons; the API key defaults to the free public tier and reports
itself as `tier: free`. If you want the API path to work, API access has to be
requested separately at <https://www.fantasypros.com/apis/>.

The client now treats a capped payload as an **error**, not a success. That
matters: a 10-row "success" would have silently overwritten `projections.parquet`
with a board that stops at the 10th player, and nothing downstream would have
complained. The same guard exists on the scrape path (`MIN_PROJECTION_ROWS`).

**Consequence: projections and ECR must come from the CSV export below.** It is
the only path that is not gated, and your account already has it.

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

## ADP: Fantasy Football Calculator (this is what the pipeline uses)

`sources.fetch_ffc_adp()` — public JSON, no key, no gate:

```
https://fantasyfootballcalculator.com/api/v1/adp/half-ppr?teams=10&year=2026&position=all
```

Verified 2026-08-07: 209 players (177 at QB/RB/WR/TE), half-PPR, 15 rounds,
pooled from 1,808 drafts over the trailing week. It also returns `stdev`,
`high` and `low` per player, which is strictly better than the single global
`opponent_adp_noise` sigma in `config/league.yaml` — the market disagrees far
more about a round-9 RB than about the 1.01.

**Caveat, do not lose this:** the `teams` parameter is echoed back in the
response `meta` but does **not** change the data. `teams=10` and `teams=12`
return byte-identical ADP for all 209 players. So this is a *pooled* half-PPR
ADP, not a true 10-team ADP. For a 10-team league the practical effect is that
positional runs are compressed relative to what this file implies. If you want
genuine 10-team ADP, Sleeper's own completed-draft data is the right source —
but `api.sleeper.app/v1/players/nfl/adp/half_ppr/2026` **404s** (that endpoint
is undocumented and appears not to exist), so today it would have to come from
your own mock drafts.

## Draft slot order: Clicky Draft is the golden source

The league drafts live on **Clicky Draft**. When the draft is imported to ESPN
(2010–2023) or Sleeper (2024+), the snake slot assignments sometimes get
reshuffled — the rosters are correct but the slot numbers disagree. This was
confirmed by cross-checking the 2023 Clicky Draft board against the ESPN cache:
all 150 player-to-manager assignments matched, but 8 of 10 managers had
different slot numbers.

**Rule: when there is a discrepancy in snake position between Clicky Draft and
the platform cache, Clicky Draft wins.** The platform data is reconstructed or
re-ordered on import; Clicky Draft reflects the actual live draft.

This matters for the opponent model (who drafts from which slot affects the
pick-gap analysis and availability simulations) and for any historical
slot-level analysis.

## Name matching

Everything joins on a normalized `name|position` key (accents, punctuation,
and Jr./III stripped; known aliases like Hollywood → Marquise Brown mapped in
`src/draft/ids.py`). Unmatched players are reported rather than silently
dropped — if a name mismatch hides a first-rounder, you want to know.

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
