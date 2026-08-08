# FFB League Data - Dictionary

One SQLite file, `ffb.sqlite`, containing the tables below. Every figure is derived from league exports and public NFL data; nothing is hand-entered except the champion list.

```bash
sqlite3 ffb.sqlite 'SELECT * FROM picks LIMIT 5;'
```

```python
import sqlite3, pandas as pd
con = sqlite3.connect('ffb.sqlite')
picks = pd.read_sql('SELECT * FROM picks', con)
```

**There is deliberately no single flat table.** Three grains live here - pick, team-week, player-week. Joining them into one sheet would repeat a manager's season across thousands of rows.

## The league

10 managers, the same ten since 2010. Half-PPR, **6-point passing TDs**, no kickers or defences since 2024. The regular season is NOT plain head-to-head: each week awards two points, one for winning your matchup and one for finishing in the week's top five scorers.

## Tables

### `picks`

One row per draft pick, 2010-2025. **2,420 rows.**

> Draft slot and pick number are corrected against the original ClickyDraft boards where those exist; ESPN scrambled the slot in 5 of 7 verified seasons. Manager and round were always correct.

| column | type |
|---|---|
| `season` | int64 |
| `round` | int64 |
| `pick` | int64 |
| `slot` | int64 |
| `manager` | str |
| `player_name` | str |
| `position` | str |
| `key_name` | str |

### `team_weeks`

One row per manager per week, 2010-2025. **2,498 rows.**

> `opponent` is RECONSTRUCTED by matching each manager's opponent_points to another manager's points in the same week. It resolves for 99.9% of rows; genuine score ties are left NULL rather than guessed. NOTE: 18 rows carry a `win` flag that contradicts the scores - a defect in the ESPN export, written through unchanged.

| column | type |
|---|---|
| `season` | int64 |
| `week` | int64 |
| `manager` | str |
| `opponent` | str |
| `points` | float64 |
| `opponent_points` | float64 |
| `win` | bool |
| `is_playoff` | bool |
| `platform` | str |

### `player_weeks`

One row per NFL player per week, 2021-2025. **29,340 rows.**

> `pts` is recomputed under THIS league's scoring (6-point passing TDs, half PPR, -2 INT), not the source's default. Regular season only.

| column | type |
|---|---|
| `name` | str |
| `pos` | str |
| `team` | str |
| `season` | int32 |
| `week` | int32 |
| `pts` | float64 |
| `key_name` | str |

### `rosters`

One row per started lineup slot per week, 2019-2025. **9,086 rows.**

> Starters only - bench players were never exported, so 'points left on the bench' is not answerable from this.

| column | type |
|---|---|
| `season` | int64 |
| `week` | int64 |
| `manager` | str |
| `slot` | str |
| `player_name` | str |
| `points` | float64 |
| `is_playoff` | bool |

### `players`

One row per NFL player. **3,042 rows.**

> From the Sleeper player index; covers currently-active players only.

| column | type |
|---|---|
| `sleeper_id` | str |
| `name` | str |
| `pos` | str |
| `team` | str |
| `age` | float64 |
| `years_exp` | float64 |
| `key_name` | str |

### `champions`

One row per season, 2008-2025. **18 rows.**

> Confirmed by the league owner. Do NOT use platform data for this - ESPN records the wrong champion in at least three seasons because it cannot represent the dual-points format.

| column | type |
|---|---|
| `season` | int64 |
| `champion` | str |
| `runner_up` | str |
| `scoring` | str |
| `source` | str |
| `verified` | bool |
