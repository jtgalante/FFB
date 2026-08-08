# Dashboard Rewiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Streamlit dashboard agree with the verified record. Its data
layer is already rewired; five call sites in the UI still read ESPN's `finish`
field, and several labels now describe something different from what they say.

**Architecture:** No new modules. `src/league_data.py` already bridges the
dashboard to the trusted sources (`config/history.yaml` for champions,
`scripts/rebuild_standings.py` for dual-points standings, `data/warehouse/` for
everything else), and `src/analytics.py` already consumes it. This plan changes
`src/dashboard.py` only.

**Tech Stack:** Python 3.12, Streamlit, pandas, plotly.

**CRITICAL — the dashboard's dependencies are only in the venv.** Use
`.venv/bin/python` for anything importing `src.dashboard` or `src.normalize`.
Plain `python3` is fine for `src.analytics`, `src.league_data` and the
warehouse.

---

## Why this matters

The dashboard counted a championship as "ESPN says you finished first". That is
meaningless here: the regular season awards TWO points a week (matchup win plus
a top-5 weekly score) and the #1 seed picks its own semifinal opponent, neither
of which ESPN can represent. Measured against the owner-verified record it was
wrong for **7 of 10 managers** — Bryan Cannon shown with 1 title against 3, Matt
McCauley 3 against 4, James Galante 2 against 1.

`analytics.championships_and_sackos` and `analytics.head_to_head` are already
fixed. What remains is UI that either bypasses them or mislabels their output.

## Known state

- `python3 -m pytest tests/ -q` → **228 passed**
- `.venv/bin/python -c "import sys; sys.path.insert(0,'.'); import src.dashboard"` → imports clean
- Verified titles: McCauley 4, Lettieri 3, Cannon 3, Darco 3, Gamble 1,
  Wiggins 1, Rogers 1, Galante 1, Clark 1, Dzuris 0 — **18 total**

---

## Task 1: The fifth call site still counts titles from ESPN

`src/dashboard.py` lines ~625-637, inside `_compute_manager_facts`, counts a
manager's championships and sackos directly from the `finish` column instead of
calling the corrected analytics function. This is what drives the Manager
Spotlight pod.

**Files:** Modify `src/dashboard.py`

- [ ] **Step 1: See the wrong number in situ**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src.normalize import load_all_data
from src import analytics, league_data
_,_,summaries = load_all_data()
print('analytics (corrected):')
print(analytics.championships_and_sackos(summaries)[['manager','championships']].to_string(index=False))
print()
print('league_data (source of truth):')
print(league_data.title_counts()[['manager','championships']].to_string(index=False))
" 2>&1 | grep -v WARNING
```

Expected: the two agree. Record Bryan Cannon's number — it must be 3 over all
18 seasons, or 2 if the call is restricted to the 2010-2025 window the weekly
data covers.

- [ ] **Step 2: Read the block and identify the local count**

```bash
sed -n '585,660p' src/dashboard.py
```

Find where `finish` is used to compute a champion or sacko count for the single
selected manager.

- [ ] **Step 3: Replace the local count with the corrected function**

Call `analytics.championships_and_sackos(summaries_df)` once and take this
manager's row, rather than recomputing from `finish`. Do not change the pod's
visual layout or the shape of the facts list it returns.

- [ ] **Step 4: Verify the spotlight now matches**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src.normalize import load_all_data
from src import dashboard, analytics
w,s,summaries = load_all_data()
stats = analytics.manager_weekly_stats(w)
seasons = sorted(w['season'].unique())
facts = dashboard._compute_manager_facts('Bryan Cannon', w, summaries, stats, seasons)
print(facts)
" 2>&1 | grep -v WARNING
```

Expected: the championship figure for Bryan Cannon agrees with Step 1. Before
the fix it reads 1.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard.py
git commit -m "fix: count titles from the verified record in the manager spotlight"
```

---

## Task 2: The finish histogram contradicts the table above it

Lines ~1137-1141 plot a distribution of ESPN `finish` values. It now sits
directly beneath a championships table sourced from the verified record, and
the two disagree on screen.

**Files:** Modify `src/dashboard.py`

- [ ] **Step 1: Confirm the disagreement**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src.normalize import load_all_data
from src import league_data
_,_,summaries = load_all_data()
print('ESPN finish==1 counts:')
print(summaries[summaries.finish==1].groupby('manager').size().sort_values(ascending=False).to_string())
print()
print('verified:')
print(league_data.title_counts()[['manager','championships']].to_string(index=False))
" 2>&1 | grep -v WARNING
```

- [ ] **Step 2: Replace the source with the dual-points seed**

Plot the distribution of `seed` from `league_data.dual_points_standings()`
instead of `finish`. That is the real regular-season placing under this
league's rules, and it is the same quantity the surrounding text describes.

- [ ] **Step 3: Verify the chart renders**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src import league_data
d = league_data.dual_points_standings()
print(d.groupby('seed').size().to_string())
print('seasons:', d.season.nunique(), 'rows:', len(d))
" 2>&1 | grep -v WARNING
```

Expected: seeds 1..10, roughly even counts, 16 seasons.

- [ ] **Step 4: Commit**

```bash
git add src/dashboard.py
git commit -m "fix: plot the dual-points seed, not ESPN's finish"
```

---

## Task 3: Three labels now describe the wrong quantity

Lines ~1112, ~1117, ~1126, ~1130 say "Avg Finish", "Best Finish", "Worst
Finish". Those values now come from the dual-points regular-season **seed**,
which is a different thing from a final placing — it excludes the playoff
bracket entirely.

**Files:** Modify `src/dashboard.py`

- [ ] **Step 1: Relabel**

Change to "Avg Seed", "Best Seed", "Worst Seed", and add a one-line caption
under the block: *"Seed is the regular-season placing under this league's
dual-points system — one point for winning your matchup, one for a top-five
weekly score. It is not the final standing; the playoff bracket decides that."*

- [ ] **Step 2: Check no other copy still says "finish"**

```bash
grep -n "Finish" src/dashboard.py
```

Expected: no user-facing label claims "finish" where a seed is displayed.

- [ ] **Step 3: Commit**

```bash
git add src/dashboard.py
git commit -m "docs: relabel finish as seed where the dual-points seed is shown"
```

---

## Task 4: "Weeks compared" is now real matchups

Lines ~779, ~800, ~806, ~1419, ~1434, ~1439 label head-to-head output as "weeks
scored higher" and "Weeks Compared". `analytics.head_to_head` no longer works
that way: it now uses `team_weeks.opponent` and reports the ACTUAL record
between two managers.

The difference is large and needs saying: McCauley vs Galante is **14-13 over
27 real meetings**, where the old shared-weeks measure reported **135-113 over
248 "weeks"**.

**Files:** Modify `src/dashboard.py`

- [ ] **Step 1: See both numbers**

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from src import analytics, league_data
tw = league_data.team_weeks()
print(analytics.head_to_head(tw, 'Matt McCauley', 'James Galante'))
"
```

- [ ] **Step 2: Relabel and surface the new keys**

"Weeks Compared" becomes "Meetings". "Weeks scored higher" becomes "Wins".
Surface the biggest blowout if `head_to_head` returns it. Check the returned
dict's actual keys before writing the UI against them — do not assume.

- [ ] **Step 3: Verify the head-to-head pod renders for several pairs**

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from src import analytics, league_data
tw = league_data.team_weeks()
for a,b in [('Matt McCauley','James Galante'),('Bryan Cannon','Tyler Clark'),('Donnie Darco','Stephen Rogers')]:
    h = analytics.head_to_head(tw, a, b)
    print(a,'vs',b,'->',{k:h[k] for k in list(h)[:6]})
"
```

Expected: meeting counts in the 20s or 30s, not the hundreds.

- [ ] **Step 4: Commit**

```bash
git add src/dashboard.py
git commit -m "fix: label head-to-head as real matchups, not shared weeks"
```

---

## Task 5: State the 16-vs-18 season caveat on screen

The dashboard's weekly data covers 2010-2025, but the verified title record
covers 2008-2025. So its championships tab shows **16 seasons** — Matt McCauley
with 3 and Bryan Cannon with 2 — while the true counts are 4 and 3.

This is not a bug to fix; the 2008 and 2009 weekly data does not exist. It is a
caveat to display, so the dashboard does not quietly contradict
`config/history.yaml`.

**Files:** Modify `src/dashboard.py`

- [ ] **Step 1: Confirm the gap**

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from src import league_data
all_ = league_data.title_counts()
recent = league_data.title_counts(seasons=range(2010,2026))
m = all_.merge(recent, on='manager', suffixes=('_all','_2010on'))
print(m[['manager','championships_all','championships_2010on']].to_string(index=False))
"
```

- [ ] **Step 2: Add the caption**

Under the championships table add: *"Titles cover all 18 seasons (2008-2025).
Every other figure on this page covers 2010-2025, which is as far back as the
weekly scoring data goes."* Show the all-18 counts in the table itself, since
those are the verified ones.

- [ ] **Step 3: Commit**

```bash
git add src/dashboard.py
git commit -m "docs: note that titles span 18 seasons and scoring spans 16"
```

---

## Task 6: Run it and look at it

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest tests/ -q`
Expected: 228 passed.

- [ ] **Step 2: Launch and click through**

```bash
.venv/bin/streamlit run src/dashboard.py
```

Check: the championships table shows McCauley 4 / Cannon 3 / Darco 3 /
Lettieri 3; the Manager Spotlight agrees with it; head-to-head shows meetings
in the tens; nothing is labelled "finish" where a seed is displayed.

- [ ] **Step 3: Commit anything the click-through turned up**

---

## Deliberately out of scope

- **Rebuilding the dashboard's own data path onto the warehouse.**
  `src/normalize.py` still reads the raw caches. It works and its outputs are
  correct; migrating it is a separate, larger job with no user-visible payoff.
- **Backfilling 2008-2009 weekly data.** It does not exist. Task 5 states the
  limit rather than hiding it.
- **Bench-points analysis.** Bench players were never exported in any season.
  See `docs/DATA_DEFICIENCIES.md` §5.
