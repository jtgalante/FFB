"""One-command data fetch — run this on your laptop, then push the results.

    python -m scripts.fetch_data

Pulls everything the draft engine needs into data/draft/ and prints a status
line per source. Sources are independent: if one fails the rest still land,
and the script tells you exactly what's missing and how to supply it by hand.

Optional but recommended in .env:
    FANTASYPROS_API_KEY=...     # https://www.fantasypros.com/apis/

No key? Two options that work just as well:
  * Download CSVs from FantasyPros (premium "Download CSV" button) into
    data/inputs/ as projections.csv and adp.csv — see docs/DATA.md.
  * Let the script fall back to scraping the public pages.

When it finishes:
    git add data/draft data/inputs && git commit -m "Add fetched draft data" && git push
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from src.draft import fantasypros as fp  # noqa: E402
from src.draft import sources  # noqa: E402
from src.draft.sources import DRAFT_DATA_DIR, INPUTS_DIR  # noqa: E402

load_dotenv()

SEASON = 2026
HISTORY_YEARS = [2021, 2022, 2023, 2024, 2025]


class Status:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def ok(self, source: str, detail: str):
        self.rows.append(("OK", source, detail))
        print(f"  [ok]   {source}: {detail}")

    def warn(self, source: str, detail: str):
        self.rows.append(("WARN", source, detail))
        print(f"  [warn] {source}: {detail}")

    def fail(self, source: str, detail: str):
        self.rows.append(("FAIL", source, detail))
        print(f"  [FAIL] {source}: {detail}")

    def count(self, level: str) -> int:
        return sum(1 for r in self.rows if r[0] == level)


def _write(df, name: str, st: Status, label: str):
    path = DRAFT_DATA_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    st.ok(label, f"{len(df)} rows -> {path}")
    return path


def fetch_projections_and_ecr(st: Status) -> None:
    key = fp.api_key()
    if key:
        try:
            df = fp.fetch_projections(SEASON, key)
            _write(df, "projections", st, "projections (FantasyPros API)")
        except Exception as e:
            st.warn("projections (FantasyPros API)", f"{e}; trying scrape")
            key_failed = True
        else:
            key_failed = False
        try:
            ecr = fp.fetch_consensus_rankings(SEASON, key)
            _write(ecr, "ecr", st, "ECR (FantasyPros API)")
        except Exception as e:
            st.warn("ECR (FantasyPros API)", str(e))
        if not key_failed:
            return
    else:
        st.warn("FantasyPros API", "no FANTASYPROS_API_KEY set; using scrape")

    try:
        df = sources.fetch_fantasypros_projections()
        _write(df, "projections", st, "projections (scrape)")
    except Exception as e:
        st.fail("projections", f"{e}\n         -> put projections.csv in data/inputs/ instead")


def fetch_adp(st: Status) -> None:
    """ADP is the market price — try Sleeper (our platform) first, then FP."""
    try:
        df = fp.fetch_sleeper_adp(SEASON)
        _write(df, "adp", st, "ADP (Sleeper, half-PPR)")
        return
    except Exception as e:
        st.warn("ADP (Sleeper)", str(e))

    key = fp.api_key()
    if key:
        try:
            df = fp.fetch_adp(SEASON, key)
            _write(df, "adp", st, "ADP (FantasyPros API)")
            return
        except Exception as e:
            st.warn("ADP (FantasyPros API)", str(e))

    try:
        df = sources.fetch_fantasypros_adp()
        _write(df, "adp", st, "ADP (FantasyPros scrape)")
    except Exception as e:
        st.fail("ADP", f"{e}\n         -> put adp.csv in data/inputs/ instead")


def fetch_history(st: Status) -> None:
    import yaml
    scoring = yaml.safe_load(Path("config/league.yaml").read_text()).get("scoring", {})
    try:
        weekly = sources.fetch_nflverse_weekly(HISTORY_YEARS)
        pts = sources.weekly_fantasy_points(weekly, scoring)
        _write(pts, "weekly_points", st,
               f"weekly points {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]} (nflverse)")
    except Exception as e:
        st.fail("weekly points (nflverse)", str(e))


def fetch_extras(st: Status) -> None:
    try:
        players = sources.fetch_sleeper_players()
        _write(players, "players", st, "player index (Sleeper)")
    except Exception as e:
        st.warn("player index (Sleeper)", str(e))
    try:
        byes = sources.fetch_byes(SEASON)
        _write(byes, "byes", st, "bye weeks (nflverse schedule)")
    except Exception as e:
        st.warn("bye weeks", f"{e}; season sim will randomize byes")


def main() -> int:
    DRAFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    st = Status()

    print(f"Fetching {SEASON} draft data into {DRAFT_DATA_DIR}/\n")
    print("Projections / ECR:")
    fetch_projections_and_ecr(st)
    print("ADP (market price):")
    fetch_adp(st)
    print("Historical weekly scoring (risk model):")
    fetch_history(st)
    print("Extras:")
    fetch_extras(st)

    have_proj = (DRAFT_DATA_DIR / "projections.parquet").exists() or \
                (INPUTS_DIR / "projections.csv").exists()
    have_adp = (DRAFT_DATA_DIR / "adp.parquet").exists() or \
               (INPUTS_DIR / "adp.csv").exists()
    have_weekly = (DRAFT_DATA_DIR / "weekly_points.parquet").exists()

    (DRAFT_DATA_DIR / "meta.json").write_text(json.dumps({
        "source": "live",
        "season": SEASON,
        "fetched_at": time.time(),
        "history_years": HISTORY_YEARS,
        "status": [{"level": l, "source": s, "detail": d} for l, s, d in st.rows],
    }, indent=2))

    print(f"\n{st.count('OK')} ok, {st.count('WARN')} warnings, {st.count('FAIL')} failures")
    missing = [n for n, have in
               (("projections", have_proj), ("ADP", have_adp),
                ("weekly history", have_weekly)) if not have]
    if missing:
        print(f"\nStill missing: {', '.join(missing)}")
        print("The engine needs projections + ADP at minimum. Supply by hand:")
        print("  1. FantasyPros -> Draft Projections (half-PPR) -> Download CSV")
        print(f"     save as {INPUTS_DIR}/projections.csv  (columns: name, pos, proj)")
        print("  2. FantasyPros -> ADP (half-PPR) -> Download CSV")
        print(f"     save as {INPUTS_DIR}/adp.csv          (columns: name, pos, adp)")
        print("  See docs/DATA.md for the full column spec.")
    else:
        print("\nAll required data present.")

    print("\nNow push it back so the engine can be built against real data:")
    print("  git add data/draft data/inputs && \\")
    print('    git commit -m "Add fetched 2026 draft data" && git push')
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
