# Data Integrity and Warehouse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop silent data corruption in the FFB draft engine by pinning the join
primitives with tests, adding a validation gate that fails loudly on the classes
of bug that have already shipped, and collapsing eleven scripts' ad-hoc joins
into one canonical warehouse.

**Architecture:** Keep the file-based, script-regenerates-artifact design — it is
correct for ~40k rows and it is why past corrections were traceable. Add three
things around it: a `tests/` suite over the pure functions, a
`src/draft/validate.py` module of assertions called by the build scripts, and a
`scripts/build_warehouse.py` that produces five tidy parquet tables with manager,
slot and player keys already resolved so no analysis script touches a raw JSON
cache again.

**Tech Stack:** Python 3.12, pandas, pyarrow, PyYAML, pytest (new dependency).

## The three things this repo is for

Stated by James, 2026-08-08. This plan is scoped by them, and the ordering below
follows from them rather than from engineering taste.

1. **Research** — trend analysis and data-driven trash talking over a clean,
   expansive league dataset. *This is a product, not a by-product.* It is the
   use case the warehouse directly serves: arbitrary questions asked of a
   trustworthy joined dataset, answered without re-deriving joins each time.
2. **Draft strategy and live execution** — and critically, **James intends to run
   the draft from inside Claude.** That means the draft tool is a *callable
   module*, not an application: record a pick, re-solve availability, recommend.
   No TUI, no web app, no polish budget. It is planned separately.
3. **In-year starters** — explicitly deferred. Nothing here should be shaped
   around it, but `rosters` and `player_weeks` are the tables it will need, so
   building them now costs nothing extra.

**What this changes versus the first draft of this plan:** the warehouse was
originally sequenced last, on the reasoning that it was refactoring with no new
capability. That was wrong once use case 1 is named — a clean joined dataset *is*
the capability. It moves ahead of the remaining tests.

**Execution order** (task numbers are stable; this is the order to run them):

    Task 1  ids tests            foundation
    Task 2  draft math           the warehouse needs it
    Task 5  validators           the warehouse builder calls them
    Task 7  warehouse            ← use case 1 unblocked here
    Task 3  scoring tests
    Task 4  replacement tests
    Task 6  wire validators into the fetch
    Task 9  drop the phantom cli command
    Task 8  docs and full suite

After Task 7, stop and reassess: if the draft is close, go build the draft
module and come back for Tasks 3/4/6/8.

**Why these specific checks:** every bug below actually shipped in this repo and
produced plausible output with no error:
- FantasyPros returned 10 of 852 players; the board was written anyway.
- `JAC`/`LAR` vs `JAX`/`LA` silently dropped bye weeks for two teams.
- 2021 injury data has `game_type` but no `season_type`; filtering on the latter
  silently deleted four of five seasons.
- ESPN scrambled the draft slot in 5 of 7 verified seasons.
- FantasyPros exports QBs at 4-point passing TDs; this league plays 6.

---

## File Structure

**Create:**
- `tests/conftest.py` — pytest fixtures (repo root path, league config)
- `tests/test_ids.py` — team/name/player-key normalization
- `tests/test_draft_math.py` — snake slot/pick arithmetic
- `tests/test_scoring.py` — projection rescoring under league rules
- `tests/test_replacement.py` — FLEX-aware replacement levels
- `src/draft/draftmath.py` — `slot_of`, `pick_of` (currently stranded in a script)
- `src/draft/validate.py` — assertion helpers used by build scripts
- `scripts/build_warehouse.py` — builds the five canonical tables

**Modify:**
- `pyproject.toml` — add pytest to dependencies
- `requirements.txt` — add pytest
- `scripts/verify_clickydraft.py` — import draft math instead of defining it
- `scripts/fetch_data.py` — call validators after each fetch
- `CLAUDE.md` — document the warehouse and the test command

---

## Task 1: Test harness and the ids primitives

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_ids.py`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest to dependencies**

In `requirements.txt`, append after the existing `beautifulsoup4` line:

```
pytest>=8.0.0
```

In `pyproject.toml`, add `"pytest>=8.0.0",` as the last entry of the
`dependencies` list.

- [ ] **Step 2: Install it**

Run: `python3 -m pip install --quiet 'pytest>=8.0.0'`
Expected: no output, exit 0.

- [ ] **Step 3: Write the conftest**

Create `tests/conftest.py`:

```python
"""Shared fixtures. Tests run from the repo root so relative data paths work."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def league_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "league.yaml").read_text())
```

- [ ] **Step 4: Write the failing test for team normalization**

Create `tests/test_ids.py`:

```python
"""Team and player key normalization.

The JAC/LAR case is not hypothetical: FantasyPros ships JAC and LAR while
nflverse ships JAX and LA, and the mismatch silently dropped bye weeks for
every Jaguar and Ram until it was caught by eye.
"""
import pytest

from src.draft.ids import normalize_name, normalize_team, player_key


@pytest.mark.parametrize("raw,expected", [
    ("LA", "LAR"), ("STL", "LAR"), ("LAR", "LAR"),
    ("JAC", "JAX"), ("JAX", "JAX"),
    ("SD", "LAC"), ("OAK", "LV"), ("WSH", "WAS"),
    ("sea", "SEA"), (" KC ", "KC"),
])
def test_normalize_team_maps_variants_to_one_code(raw, expected):
    assert normalize_team(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "FA", "nan", "None"])
def test_normalize_team_returns_none_for_no_team(raw):
    assert normalize_team(raw) is None


def test_player_key_strips_suffix_and_keeps_position():
    assert player_key("Patrick Mahomes II", "QB") == "patrick mahomes|QB"


def test_player_key_separates_same_name_different_position():
    assert player_key("Mike Williams", "WR") != player_key("Mike Williams", "RB")


def test_normalize_name_applies_known_aliases():
    assert normalize_name("Hollywood Brown") == "marquise brown"
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_ids.py -v`
Expected: 18 passed. These pin behaviour that already works; they fail only if
someone regresses the normalizers.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_ids.py requirements.txt pyproject.toml
git commit -m "test: pin team and player key normalization"
```

---

## Task 2: Extract and test the snake draft arithmetic

**Files:**
- Create: `src/draft/draftmath.py`
- Create: `tests/test_draft_math.py`
- Modify: `scripts/verify_clickydraft.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_draft_math.py`:

```python
"""Snake draft arithmetic.

A wrong version of this shipped in scripts/harpers_index.py, which reported
James's back-to-back picks as 39 and 40 when they are 40 and 41.
"""
import pytest

from src.draft.draftmath import pick_of, slot_of

TEAMS = 10


def test_round_one_runs_left_to_right():
    assert [slot_of(p, TEAMS) for p in range(1, 11)] == list(range(1, 11))


def test_round_two_reverses():
    assert [slot_of(p, TEAMS) for p in range(11, 21)] == list(range(10, 0, -1))


def test_slot_one_holds_the_wrap_pair():
    assert pick_of(1, 1, TEAMS) == 1
    assert pick_of(2, 1, TEAMS) == 20
    assert pick_of(3, 1, TEAMS) == 21
    assert pick_of(4, 1, TEAMS) == 40
    assert pick_of(5, 1, TEAMS) == 41


def test_slot_ten_holds_the_mirror_pair():
    assert pick_of(1, 10, TEAMS) == 10
    assert pick_of(2, 10, TEAMS) == 11


@pytest.mark.parametrize("rnd", range(1, 16))
@pytest.mark.parametrize("slot", range(1, 11))
def test_pick_of_and_slot_of_are_inverses(rnd, slot):
    assert slot_of(pick_of(rnd, slot, TEAMS), TEAMS) == slot
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_draft_math.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.draft.draftmath'`

- [ ] **Step 3: Write the implementation**

Create `src/draft/draftmath.py`:

```python
"""Snake draft position arithmetic.

Odd rounds run slot 1..N, even rounds run N..1. Everything else in the engine
derives draft position from these two functions, so they live in one place.
"""

from __future__ import annotations


def slot_of(pick: int, teams: int) -> int:
    """Which draft slot (1..teams) made this overall pick."""
    rnd, idx = divmod(pick - 1, teams)
    return idx + 1 if rnd % 2 == 0 else teams - idx


def pick_of(rnd: int, slot: int, teams: int) -> int:
    """Overall pick number for a given round and slot."""
    return (rnd - 1) * teams + (slot if rnd % 2 else teams - slot + 1)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_draft_math.py -v`
Expected: 154 passed.

- [ ] **Step 5: Point the verifier at the shared module**

In `scripts/verify_clickydraft.py`, delete the local definitions of `slot_of`
and `pick_of` (the two functions immediately after `norm`), and add to the
imports below `from src.draft.ids import normalize_name`:

```python
from src.draft.draftmath import pick_of as _pick_of  # noqa: E402
from src.draft.draftmath import slot_of as _slot_of  # noqa: E402


def slot_of(pick: int) -> int:
    return _slot_of(pick, TEAMS)


def pick_of(rnd: int, slot: int) -> int:
    return _pick_of(rnd, slot, TEAMS)
```

- [ ] **Step 6: Verify the verifier still agrees with the boards**

Run: `python3 -m scripts.verify_clickydraft`
Expected: unchanged output — 2015, 2017, 2022 at 150/150; 2014 at 149/150;
2019 at 148/150.

- [ ] **Step 7: Commit**

```bash
git add src/draft/draftmath.py tests/test_draft_math.py scripts/verify_clickydraft.py
git commit -m "refactor: extract snake draft arithmetic, with tests"
```

---

## Task 3: Test the projection rescoring

**Files:**
- Create: `tests/test_scoring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scoring.py`:

```python
"""Projection rescoring under this league's rules.

FantasyPros exports QB projections at 4-point passing TDs and -1 INT; this
league plays 6 and -2. Reading its FPTS column directly understates Josh Allen
by 43.5 points and moves Matthew Stafford from QB15 to QB8.
"""
import pandas as pd

from scripts.ingest_projections import score


def test_scores_a_quarterback_at_six_point_passing_tds(league_cfg):
    # Josh Allen's 2026 FantasyPros component line.
    df = pd.DataFrame([{
        "pass_yd": 3814.0, "pass_td": 27.4, "pass_int": 11.2,
        "rush_yd": 585.2, "rush_td": 11.8, "fl": 4.1,
    }])
    got = float(score(df, league_cfg["scoring"]).iloc[0])
    # 152.56 + 164.4 - 22.4 + 58.52 + 70.8 - 8.2
    assert got == 415.7


def test_the_same_line_at_four_point_tds_is_the_published_number(league_cfg):
    df = pd.DataFrame([{
        "pass_yd": 3814.0, "pass_td": 27.4, "pass_int": 11.2,
        "rush_yd": 585.2, "rush_td": 11.8, "fl": 4.1,
    }])
    four_pt = dict(league_cfg["scoring"], pass_td=4.0, pass_int=-1.0)
    got = float(score(df, four_pt).iloc[0])
    assert abs(got - 372.2) < 0.2   # FantasyPros' own FPTS column


def test_half_ppr_receptions_are_worth_half_a_point(league_cfg):
    df = pd.DataFrame([{"rec": 100.0}])
    assert float(score(df, league_cfg["scoring"]).iloc[0]) == 50.0


def test_missing_stat_columns_contribute_nothing(league_cfg):
    """A tight end export has no rushing columns; that must not error."""
    df = pd.DataFrame([{"rec": 10.0, "rec_yd": 100.0, "rec_td": 1.0}])
    assert float(score(df, league_cfg["scoring"]).iloc[0]) == 21.0
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_scoring.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_scoring.py
git commit -m "test: pin projection rescoring at 6-point passing TDs"
```

---

## Task 4: Test the FLEX-aware replacement levels

**Files:**
- Create: `tests/test_replacement.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_replacement.py`:

```python
"""FLEX-aware replacement levels.

Hand-picking replacement ranks (RB27/WR30/TE13) is really a guess at how the
two FLEX slots split. Derived properly, the 20 flex slots go 10 RB / 10 WR and
zero TE, so RB and WR replacement converge and TE stays far below.
"""
import pandas as pd

from src.draft.data import replacement_levels

CFG = {
    "teams": 10,
    "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
    "flex_eligible": ["RB", "WR", "TE"],
}


def _pool(pos: str, n: int, top: float, step: float) -> pd.DataFrame:
    return pd.DataFrame({"pos": [pos] * n,
                         "proj": [top - i * step for i in range(n)]})


def test_replacement_is_the_best_player_who_never_starts():
    # 10 QBs needed; give it 12 descending from 300 by 10 -> 11th is 200.
    proj = _pool("QB", 12, 300.0, 10.0)
    proj = pd.concat([proj, _pool("RB", 40, 300.0, 5.0),
                      _pool("WR", 40, 300.0, 5.0),
                      _pool("TE", 20, 150.0, 5.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["QB"] == 200.0


def test_flex_pulls_rb_and_wr_replacement_together():
    """Identical RB and WR pools must land at the same replacement level."""
    proj = pd.concat([_pool("QB", 20, 300.0, 5.0),
                      _pool("RB", 60, 300.0, 4.0),
                      _pool("WR", 60, 300.0, 4.0),
                      _pool("TE", 20, 120.0, 4.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["RB"] == levels["WR"]


def test_a_weak_tight_end_pool_wins_no_flex_slots():
    """With TEs far below RB/WR, TE replacement is the 11th TE, not deeper."""
    proj = pd.concat([_pool("QB", 20, 300.0, 5.0),
                      _pool("RB", 60, 300.0, 2.0),
                      _pool("WR", 60, 300.0, 2.0),
                      _pool("TE", 20, 100.0, 2.0)], ignore_index=True)
    levels = replacement_levels(proj, CFG)
    assert levels["TE"] == 100.0 - 10 * 2.0   # the 11th TE
    assert levels["TE"] < levels["RB"]
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_replacement.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_replacement.py
git commit -m "test: pin FLEX-aware replacement levels"
```

---

## Task 5: The validation module

**Files:**
- Create: `src/draft/validate.py`
- Create: `tests/test_validate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate.py`:

```python
"""Validators. Each one corresponds to a bug that actually shipped."""
import pandas as pd
import pytest

from src.draft.validate import (ValidationError, check_min_rows,
                                check_seasons_balanced, check_team_codes,
                                check_draft_complete)


def test_min_rows_rejects_a_paywalled_slice():
    """FantasyPros served 10 of 852 players and the board was written anyway."""
    with pytest.raises(ValidationError, match="10 rows"):
        check_min_rows(pd.DataFrame({"a": range(10)}), 120, "projections")


def test_min_rows_accepts_a_full_pull():
    check_min_rows(pd.DataFrame({"a": range(500)}), 120, "projections")


def test_team_codes_rejects_unknown_codes():
    """JAC/LAR vs JAX/LA silently dropped bye weeks for two teams."""
    df = pd.DataFrame({"team": ["KC", "JAC", "SEA"]})
    with pytest.raises(ValidationError, match="JAC"):
        check_team_codes(df, "team", "byes")


def test_team_codes_allows_nulls():
    check_team_codes(pd.DataFrame({"team": ["KC", None]}), "team", "byes")


def test_seasons_balanced_catches_a_silently_dropped_season():
    """2021 injuries had game_type but no season_type; the filter deleted
    four of five seasons and nothing raised."""
    df = pd.DataFrame({"season": [2025] * 100 + [2024] * 2})
    with pytest.raises(ValidationError, match="2024"):
        check_seasons_balanced(df, [2024, 2025], "injuries", min_share=0.25)


def test_seasons_balanced_passes_when_even():
    df = pd.DataFrame({"season": [2024] * 50 + [2025] * 50})
    check_seasons_balanced(df, [2024, 2025], "injuries", min_share=0.25)


def test_draft_complete_catches_a_duplicate_pick():
    df = pd.DataFrame({"season": [2025] * 4, "round": [1, 1, 2, 2],
                       "pick": [1, 1, 3, 4], "manager": list("abab")})
    with pytest.raises(ValidationError, match="duplicate"):
        check_draft_complete(df, teams=2, rounds=2)


def test_draft_complete_passes_on_a_clean_snake():
    df = pd.DataFrame({"season": [2025] * 4, "round": [1, 1, 2, 2],
                       "pick": [1, 2, 3, 4], "manager": list("abba")})
    check_draft_complete(df, teams=2, rounds=2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.draft.validate'`

- [ ] **Step 3: Write the implementation**

Create `src/draft/validate.py`:

```python
"""Build-time assertions.

Every check here corresponds to a bug that shipped in this repo and produced
plausible output with no error. The point is to fail loudly at the moment the
data is written, not to be discovered later by eye.
"""

from __future__ import annotations

import pandas as pd

from .ids import _TEAM_ALIASES

VALID_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
}


class ValidationError(RuntimeError):
    """A build produced data that is structurally wrong."""


def check_min_rows(df: pd.DataFrame, minimum: int, label: str) -> None:
    """Reject a gated or truncated payload masquerading as a full pull."""
    if len(df) < minimum:
        raise ValidationError(
            f"{label}: only {len(df)} rows, expected at least {minimum}. "
            f"This is the signature of a paywalled or filtered response, not "
            f"of real data.")


def check_team_codes(df: pd.DataFrame, col: str, label: str) -> None:
    """Every team code must be canonical; nulls are allowed (free agents)."""
    seen = {t for t in df[col].dropna().unique()}
    bad = sorted(seen - VALID_TEAMS)
    if bad:
        hint = {b: _TEAM_ALIASES.get(b) for b in bad if b in _TEAM_ALIASES}
        raise ValidationError(
            f"{label}: non-canonical team codes {bad}. Run them through "
            f"ids.normalize_team first. Known mappings: {hint}")


def check_seasons_balanced(df: pd.DataFrame, seasons: list[int], label: str,
                           min_share: float = 0.5) -> None:
    """Each season must carry a plausible share of the rows.

    A schema difference between years can make a filter delete whole seasons
    while leaving a healthy-looking total.
    """
    counts = df.groupby("season").size()
    expected = len(df) / len(seasons)
    thin = [int(s) for s in seasons
            if counts.get(s, 0) < expected * min_share]
    if thin:
        raise ValidationError(
            f"{label}: seasons {thin} are missing or far too thin "
            f"({dict(counts)}). Check for a schema difference between years.")


def check_draft_complete(df: pd.DataFrame, teams: int, rounds: int) -> None:
    """Per season: picks are unique, contiguous, one per manager per round."""
    for season, g in df.groupby("season"):
        picks = sorted(g["pick"].tolist())
        if len(picks) != len(set(picks)):
            raise ValidationError(
                f"draft {season}: duplicate pick numbers")
        expected = list(range(1, len(g) + 1))
        if picks != expected:
            raise ValidationError(
                f"draft {season}: picks are not contiguous 1..{len(g)}")
        per_round = g.groupby("round")["manager"].nunique()
        bad = per_round[per_round != min(teams, len(g))].to_dict()
        if bad and len(g) >= teams:
            raise ValidationError(
                f"draft {season}: rounds without one pick per manager: {bad}")
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_validate.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/draft/validate.py tests/test_validate.py
git commit -m "feat: add build-time validators for known corruption modes"
```

---

## Task 6: Wire the validators into the fetch

**Files:**
- Modify: `scripts/fetch_data.py`

- [ ] **Step 1: Import the validators**

In `scripts/fetch_data.py`, below the existing
`from src.draft.sources import DRAFT_DATA_DIR, INPUTS_DIR  # noqa: E402`:

```python
from src.draft.validate import (ValidationError, check_min_rows,  # noqa: E402
                                check_seasons_balanced, check_team_codes)
```

- [ ] **Step 2: Validate ADP before writing**

In `fetch_adp`, replace the FFC success block:

```python
    try:
        df = sources.fetch_ffc_adp(SEASON)
        meta = df.attrs.get("ffc_meta", {})
        _write(df, "adp", st, "ADP (FantasyFootballCalculator, half-PPR)")
```

with:

```python
    try:
        df = sources.fetch_ffc_adp(SEASON)
        check_min_rows(df, 100, "ADP (FFC)")
        check_team_codes(df, "team", "ADP (FFC)")
        meta = df.attrs.get("ffc_meta", {})
        _write(df, "adp", st, "ADP (FantasyFootballCalculator, half-PPR)")
```

- [ ] **Step 3: Validate the injury pull before writing**

In `fetch_extras`, replace:

```python
    try:
        inj = sources.fetch_injuries(HISTORY_YEARS)
        _write(inj, "injuries", st, "injury reports (nflverse)")
```

with:

```python
    try:
        inj = sources.fetch_injuries(HISTORY_YEARS)
        check_seasons_balanced(inj, HISTORY_YEARS, "injury reports")
        check_team_codes(inj, "team", "injury reports")
        _write(inj, "injuries", st, "injury reports (nflverse)")
```

- [ ] **Step 4: Validate the weekly history before writing**

In `fetch_history`, replace:

```python
        pts = sources.weekly_fantasy_points(weekly, scoring)
        _write(pts, "weekly_points", st,
```

with:

```python
        pts = sources.weekly_fantasy_points(weekly, scoring)
        check_seasons_balanced(pts, HISTORY_YEARS, "weekly points")
        check_min_rows(pts, 20000, "weekly points")
        _write(pts, "weekly_points", st,
```

- [ ] **Step 5: Run the fetch and confirm everything still passes**

Run: `python3 -m scripts.fetch_data`
Expected: the same `[ok]` lines as before — ADP 179 rows, weekly points 29340,
injuries 8479, byes 32. No `ValidationError`. The FantasyPros API warnings are
expected and unchanged.

- [ ] **Step 6: Prove a validator actually fires**

Run:

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
import pandas as pd
from src.draft.validate import check_seasons_balanced, ValidationError
df = pd.DataFrame({'season':[2025]*1750})
try:
    check_seasons_balanced(df, [2021,2022,2023,2024,2025], 'injuries')
except ValidationError as e:
    print('caught:', e)
"
```

Expected: `caught: injuries: seasons [2021, 2022, 2023, 2024] are missing or far
too thin ...` — i.e. it reproduces the exact bug that shipped.

- [ ] **Step 7: Commit**

```bash
git add scripts/fetch_data.py
git commit -m "feat: validate fetched data before writing it"
```

---

## Task 7: The canonical warehouse

**Files:**
- Create: `scripts/build_warehouse.py`
- Create: `tests/test_warehouse.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_warehouse.py`:

```python
"""The warehouse tables must be internally consistent.

These run against the real committed data, so they double as a regression
check on the archive itself.
"""
from pathlib import Path

import pandas as pd
import pytest

WAREHOUSE = Path("data/warehouse")
pytestmark = pytest.mark.skipif(
    not (WAREHOUSE / "picks.parquet").exists(),
    reason="run `python3 -m scripts.build_warehouse` first")


def test_picks_has_one_row_per_manager_per_round():
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    counts = p.groupby(["season", "round"])["manager"].nunique()
    assert set(counts.unique()) == {10}


def test_picks_slots_agree_with_pick_numbers():
    from src.draft.draftmath import slot_of
    p = pd.read_parquet(WAREHOUSE / "picks.parquet")
    assert (p["slot"] == [slot_of(x, 10) for x in p["pick"]]).all()


def test_team_weeks_resolve_an_opponent_for_almost_every_row():
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet")
    assert t["opponent"].notna().mean() > 0.99


def test_team_weeks_opponents_are_symmetric():
    """If A played B in a week, B played A."""
    t = pd.read_parquet(WAREHOUSE / "team_weeks.parquet").dropna(
        subset=["opponent"])
    pairs = {(r.season, r.week, r.manager, r.opponent) for r in t.itertuples()}
    missing = [p for p in pairs
               if (p[0], p[1], p[3], p[2]) not in pairs]
    assert not missing[:5]


def test_player_weeks_cover_every_history_season():
    w = pd.read_parquet(WAREHOUSE / "player_weeks.parquet")
    assert set(w["season"].unique()) >= {2021, 2022, 2023, 2024, 2025}
```

- [ ] **Step 2: Run it to verify it skips**

Run: `python3 -m pytest tests/test_warehouse.py -v`
Expected: 5 skipped, with the reason "run `python3 -m scripts.build_warehouse`
first".

- [ ] **Step 3: Write the warehouse builder**

Create `scripts/build_warehouse.py`:

```python
"""Build the canonical tables every analysis reads.

Eleven scripts each used to re-derive the same joins from raw JSON caches:
manager canonicalization, slot arithmetic, player keys, opponent resolution.
That is where the bugs bred. This does each join once, validates the result,
and writes tidy parquet to data/warehouse/.

Tables:
    picks         season x round x slot   who drafted whom, where
    team_weeks    season x week x manager scores, WITH the opponent resolved
    player_weeks  season x week x player  NFL scoring under our rules
    rosters       season x week x slot    started lineups (2019+)
    players       player                  name, position, birth date

Opponent resolution deserves a note: the platform exports record your score and
your opponent's score but never the opponent's NAME. Matching a manager's
opponent_points against the other scores in the same week recovers it uniquely
for 99.5% of manager-weeks; genuine score ties are left null rather than
guessed.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_canonical_name  # noqa: E402
from src.draft.draftmath import slot_of  # noqa: E402
from src.draft.ids import normalize_team, player_key  # noqa: E402
from src.draft.validate import check_draft_complete  # noqa: E402

OUT = Path("data/warehouse")
LEAGUE = Path("data/league_cache.json")
DRAFTS = Path("data/draft_cache.json")
CONFIG = Path("config/league.yaml")


def build_picks(teams: int) -> pd.DataFrame:
    rows = json.loads(DRAFTS.read_text())["drafts"]
    df = pd.DataFrame(rows)
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    df["slot"] = [slot_of(p, teams) for p in df["pick"]]
    df["key_name"] = [player_key(n, pos) for n, pos
                      in zip(df["player_name"], df["position"])]
    return df[["season", "round", "pick", "slot", "manager", "player_name",
               "position", "key_name"]].sort_values(["season", "pick"])


def build_team_weeks() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["weekly"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    opponents = []
    for (_, _, _), g in df.groupby(["season", "week", "is_playoff"]):
        by_score = defaultdict(list)
        for r in g.itertuples():
            by_score[round(r.points, 2)].append(r.manager)
        for r in g.itertuples():
            cand = [m for m in by_score.get(round(r.opponent_points, 2), [])
                    if m != r.manager]
            opponents.append((r.Index, cand[0] if len(cand) == 1 else None))
    df["opponent"] = pd.Series(dict(opponents))
    return df[["season", "week", "manager", "opponent", "points",
               "opponent_points", "win", "is_playoff", "platform"]]


def build_rosters() -> pd.DataFrame:
    blob = json.loads(LEAGUE.read_text())
    df = pd.DataFrame(blob["slots"])
    df["manager"] = [get_canonical_name(p, m)
                     for p, m in zip(df["platform"], df["manager"])]
    df = df[~df["player_name"].isin(["Empty", ""])]
    return df[["season", "week", "manager", "slot", "player_name", "points",
               "is_playoff"]]


def build_player_weeks() -> pd.DataFrame:
    df = pd.read_parquet("data/draft/weekly_points.parquet")
    df["team"] = df["team"].map(normalize_team)
    return df


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    picks = build_picks(cfg["teams"])
    check_draft_complete(picks, cfg["teams"], cfg["rounds"])
    picks.to_parquet(OUT / "picks.parquet", index=False)
    print(f"  picks         {len(picks):>6} rows")

    tw = build_team_weeks()
    resolved = tw["opponent"].notna().mean()
    tw.to_parquet(OUT / "team_weeks.parquet", index=False)
    print(f"  team_weeks    {len(tw):>6} rows "
          f"({resolved*100:.1f}% opponents resolved)")

    pw = build_player_weeks()
    pw.to_parquet(OUT / "player_weeks.parquet", index=False)
    print(f"  player_weeks  {len(pw):>6} rows")

    ro = build_rosters()
    ro.to_parquet(OUT / "rosters.parquet", index=False)
    print(f"  rosters       {len(ro):>6} rows "
          f"(seasons {ro.season.min()}-{ro.season.max()})")

    pl = pd.read_parquet("data/draft/players.parquet")
    pl.to_parquet(OUT / "players.parquet", index=False)
    print(f"  players       {len(pl):>6} rows")
    print(f"\nWrote {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Build it**

Run: `python3 -m scripts.build_warehouse`
Expected:

```
  picks           2420 rows
  team_weeks      2498 rows (99.5% opponents resolved)
  player_weeks   29340 rows
  rosters         9086 rows (seasons 2019-2025)
  players         3042 rows

Wrote data/warehouse/
```

- [ ] **Step 5: Run the warehouse tests**

Run: `python3 -m pytest tests/test_warehouse.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_warehouse.py tests/test_warehouse.py data/warehouse
git commit -m "feat: build canonical warehouse tables with resolved joins"
```

---

## Task 8: Documentation and the full suite

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the whole suite**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass, no skips.

- [ ] **Step 2: Document the warehouse and the tests**

In `CLAUDE.md`, in the fenced command block under `## Data`, add after the
`ingest_projections` line:

```
python -m scripts.build_warehouse         # canonical joined tables -> data/warehouse/
python -m scripts.verify_clickydraft      # check draft slots vs the golden boards
python -m pytest tests/ -q                # invariants
```

In the `## Conventions` section, add as a new bullet after the player-joins one:

```markdown
- **Analyses read `data/warehouse/`, not the raw caches.** Manager names, draft
  slots, player keys and weekly opponents are resolved once by
  `scripts/build_warehouse.py`. Re-deriving those joins per script is what
  produced the JAC/LAR bye loss, the four silently-deleted injury seasons and
  the scrambled draft slots.
- Data-shape bugs here are silent by default, so `src/draft/validate.py` asserts
  at build time and every validator maps to a bug that actually shipped.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document the warehouse, validators and test suite"
```

---

## Task 9: Remove the command that does not exist

`CLAUDE.md` and `docs/DATA.md` both instruct the reader to run
`python -m src.draft.cli bootstrap`. There is no `src/draft/cli.py`; the command
fails with `No module named src.draft.cli`. It was meant to build an offline
fixture from the committed caches — `data.build_fixtures()` still exists — but
the fixture is now pointless: real 2026 projections, ADP, weeklies and byes are
all committed, and `docs/DATA.md` itself says never to draft off the fixture.

Delete the instruction rather than build the module.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/DATA.md`

- [ ] **Step 1: Confirm it is still broken**

Run: `python3 -m src.draft.cli bootstrap`
Expected: `/usr/bin/python3: No module named src.draft.cli`

- [ ] **Step 2: Remove it from CLAUDE.md**

In the fenced command block under `## Data`, delete this line:

```
python -m src.draft.cli bootstrap           # offline fixture from committed caches
```

- [ ] **Step 3: Remove it from docs/DATA.md**

Delete the whole `## Offline development fixture` section — its heading, the
fenced `python -m src.draft.cli bootstrap` block, and the paragraph beginning
"Without any network".

- [ ] **Step 4: Confirm no references remain**

Run: `grep -rn "draft.cli" --include="*.md" . | grep -v .venv`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/DATA.md
git commit -m "docs: drop the bootstrap command, which never existed"
```

---

## Deliberately out of scope

- **A database.** ~40k rows total; parquet plus pandas is correct here, and
  file-based artifacts are why past corruption was traceable through git.
- **The live draft module.** Separate subsystem, separate plan. Shaped by the
  fact that James runs the draft *from inside Claude*: it needs a small callable
  surface — `record_pick`, `available`, `recommend` — reading `board.parquet`
  and re-solving in seconds. Not an app, not a CLI, no UI. Build it immediately
  after Task 7 if the draft is near.
- **In-year starter optimisation.** Deferred by James. The `rosters` and
  `player_weeks` tables this plan builds are its future inputs, so no work is
  wasted, but nothing here should be designed around it.
- **DuckDB.** Tempting for use case 1, since ad-hoc SQL over parquet suits
  trash-talk research well. Deliberately not adopted yet: pandas over five tidy
  tables covers it, and adding a query engine before the tables exist is
  premature. Revisit once the warehouse has been used in anger for a few weeks.
- **Rewriting the studies.** `room_study`, `variance_study` and the availability
  work stay as they are; only their inputs get more trustworthy.
- **Merging the three availability documents.** Editorial, not structural. Worth
  doing, but it is not a build-integrity task and should not gate one.
