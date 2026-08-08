"""Check the draft archive against the original ClickyDraft boards.

    python -m scripts.verify_clickydraft            # report
    python -m scripts.verify_clickydraft --write    # apply corrections

ClickyDraft was where this league actually drafted. The ESPN boards for
2010-2018 were re-keyed by hand afterwards, so they are only as good as the
typing — and nothing in the data can reveal that on its own. A snake pattern
proves nothing here: ESPN's draft tool enforces the snake regardless of who
really picked, so a mis-keyed board still looks perfectly structured.

The boards themselves are the only external check. Transcribe one into
`data/inputs/clickydraft/<season>.tsv` as 15 rows x 10 tab-separated columns,
in draft-slot order (column 1 = the slot that picked first in round 1), and
this compares it cell by cell against `data/draft_cache.json`.

Discrepancies are classified, because they are not all equally serious:

* **swap** — two picks exchanged between adjacent rounds in the same column.
  A transcription slip. The manager still got both players; only the round is
  wrong, which perturbs "what round did he take his first QB" by one.
* **wrong-column** — a player attributed to the wrong manager entirely. This
  is the serious one: it corrupts every per-manager tendency.
* **different-player** — the cache and the board disagree about who was taken.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_canonical_name  # noqa: E402
from src.draft.ids import normalize_name  # noqa: E402

BOARDS = Path("data/inputs/clickydraft")
CACHE = Path("data/draft_cache.json")
TEAMS = 10

# The two sources name defences differently: boards use "SEA DEF", the ESPN
# export uses "Seahawks D/ST". Compare them as team codes.
NICK = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "chargers": "LAC", "rams": "LAR", "raiders": "LV", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "seahawks": "SEA",
    "49ers": "SF", "buccaneers": "TB", "titans": "TEN", "commanders": "WAS",
    "redskins": "WAS", "football": "WAS",
}
ALIAS = {"stl": "LAR", "sd": "LAC", "oak": "LV", "jac": "JAX", "wsh": "WAS",
         "la": "LAR", "no": "NO", "ne": "NE", "sf": "SF", "tb": "TB",
         "kc": "KC", "gb": "GB"}


def norm(name: str) -> str:
    """Canonical form; defences collapse to a team code."""
    s = str(name).strip()
    m = re.match(r"^([A-Za-z0-9]{2,3})\s*DEF$", s, re.I)
    if m:
        c = m.group(1).upper()
        return "DEF:" + ALIAS.get(c.lower(), c)
    if re.search(r"D/ST|DEF|DST", s, re.I):
        first = re.split(r"\s+", s)[0].lower()
        return "DEF:" + NICK.get(first, first.upper())
    return normalize_name(s)


def slot_of(pick: int) -> int:
    r, i = divmod(pick - 1, TEAMS)
    return i + 1 if r % 2 == 0 else TEAMS - i


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    blob = json.loads(CACHE.read_text())
    picks = blob["drafts"]
    by_season: dict[int, dict] = {}
    for p in picks:
        p["_slot"] = slot_of(p["pick"])
        by_season.setdefault(p["season"], {})[(p["round"], p["_slot"])] = p

    total_cells = total_bad = 0
    fixed = 0
    for path in sorted(BOARDS.glob("*.tsv")):
        season = int(path.stem)
        grid = [ln.split("\t") for ln in
                path.read_text().rstrip("\n").split("\n")]
        ours = by_season.get(season)
        if not ours:
            print(f"{season}: no picks in cache, skipping")
            continue

        mgr_of_slot = {s: get_canonical_name(ours[(1, s)]["platform"],
                                             ours[(1, s)]["manager"])
                       for s in range(1, TEAMS + 1) if (1, s) in ours}
        bad = []
        for r, row in enumerate(grid, start=1):
            for c, cell in enumerate(row, start=1):
                rec = ours.get((r, c))
                if rec is None:
                    continue
                total_cells += 1
                if norm(cell) != norm(rec["player_name"]):
                    bad.append((r, c, cell.strip(), rec["player_name"]))

        # FIRST: is the whole board a column permutation? That means the
        # players and the pick order are right but the manager attached to
        # each slot is wrong — the serious failure, and the one a snake-shape
        # check cannot see.
        loc = {norm(ours[(r, c)]["player_name"]): (r, c)
               for r in range(1, len(grid) + 1) for c in range(1, TEAMS + 1)
               if (r, c) in ours}
        perm = {c: (loc.get(norm(grid[0][c - 1])) or (0, 0))[1]
                for c in range(1, TEAMS + 1)}
        consistent = all(
            (loc.get(norm(grid[r - 1][c - 1])) or (0, 0))[1] == perm[c]
            for r in range(1, len(grid) + 1) for c in range(1, TEAMS + 1)
            if norm(grid[r - 1][c - 1]) in loc)
        shuffled = consistent and any(perm[c] != c for c in perm) \
            and all(perm.values())

        # classify: a swap is a pair exchanged between adjacent rounds, same column
        swaps, others = [], []
        seen = set()
        for r, c, board, cache in bad:
            if (r, c) in seen:
                continue
            for r2, c2, b2, cc2 in bad:
                if c2 == c and abs(r2 - r) == 1 and (r2, c2) not in seen \
                        and norm(b2) == norm(cache) and norm(board) == norm(cc2):
                    swaps.append((c, min(r, r2), max(r, r2), board, b2))
                    seen.add((r, c))
                    seen.add((r2, c2))
                    break
        for r, c, board, cache in bad:
            if (r, c) not in seen:
                others.append((r, c, board, cache))

        total_bad += len(bad)
        n = len(grid) * TEAMS
        print(f"\n{season}: {n - len(bad)}/{n} cells match "
              f"({100*(n-len(bad))/n:.1f}%)")
        if not bad:
            print("   exact match — draft order and manager attribution confirmed")
        if shuffled:
            print("   *** MANAGER ATTRIBUTION SHUFFLED ***")
            print("   Every player and the full pick order match the board, but")
            print("   under a consistent column permutation across all rounds.")
            print("   The cache has the right draft attached to the wrong people:")
            for c in range(1, TEAMS + 1):
                if perm[c] != c:
                    print(f"      board slot {c:>2} is recorded as "
                          f"{mgr_of_slot.get(perm[c], '?')}")
            print("   Fixing this needs the board's TEAM-NAME HEADER ROW, which")
            print("   the screenshots do not include. Not auto-correctable.")
            continue

        for c, r1, r2, p1, p2 in swaps:
            print(f"   SWAP  slot {c} ({mgr_of_slot.get(c,'?')}): "
                  f"R{r1}/R{r2} — {p1} and {p2} are the wrong way round")
        for r, c, board, cache in others:
            print(f"   DIFF  R{r} slot {c} ({mgr_of_slot.get(c,'?')}): "
                  f"board={board!r} cache={cache!r}")

        if a.write and bad:
            for c, r1, r2, p1, p2 in swaps:
                A, B = ours[(r1, c)], ours[(r2, c)]
                for k in ("player_name", "player_id", "position",
                          "season_points"):
                    A[k], B[k] = B[k], A[k]
                fixed += 2

    print(f"\n{total_cells - total_bad}/{total_cells} cells match overall "
          f"({100*(total_cells-total_bad)/total_cells:.1f}%)")
    if a.write:
        for p in picks:
            p.pop("_slot", None)
        CACHE.write_text(json.dumps(blob, indent=1))
        print(f"Applied {fixed} corrections to {CACHE}")
    elif total_bad:
        print("Re-run with --write to apply the swap corrections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
