"""Check and repair the draft archive against the original ClickyDraft boards.

    python -m scripts.verify_clickydraft            # report
    python -m scripts.verify_clickydraft --write    # repair data/draft_cache.json

ClickyDraft is where this league actually drafted; ESPN was keyed in afterwards.
Two golden sources are read:

* `data/clickydraft_cache.json` — 2020-2022, already carries manager, team name
  and true slot per pick.
* `data/inputs/clickydraft/<season>.tsv` — a board screenshot transcribed as
  15 rows x 10 tab-separated columns in draft-slot order. These have no manager
  names, which turns out not to matter (see below).

## What ESPN actually gets wrong

Measured against ClickyDraft for 2020-2022:

    manager -> players    144/150, 146/150, 150/150   (96-100%)
    manager -> round      144/144, 146/146, 150/150   (100%)
    manager -> draft slot     2/10,   1/10,   1/10    (10-20%)

**ESPN preserves who drafted whom, and in which round, perfectly. It scrambles
only the draft SLOT** — and therefore the overall pick number, which is derived
from it. The whole board comes out as a consistent column permutation.

That distinction matters and is easy to get backwards. A permutation looks
alarming — nothing lines up — but it does NOT mean players are attached to the
wrong managers. Anything measured in ROUNDS (first-QB round, first-TE round,
loyalty, positional mix) was always safe. Only things measured in PICK NUMBERS
were wrong: "QB1 goes at pick 25", "12 RBs are gone by pick 19", and who held
1.01.

## Why the missing header row does not matter

Recovering the true slot needs no team names. ESPN's manager-to-player mapping
is correct, so matching each manager's ROUND 1 pick against the board's top row
identifies his column directly. That resolved 10/10 managers in every season
tested.

A snake-shape check cannot detect any of this: ESPN's draft tool enforces the
snake regardless, so a mis-slotted board still looks perfectly structured.
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
from src.draft.draftmath import pick_of as _pick_of  # noqa: E402
from src.draft.draftmath import slot_of as _slot_of  # noqa: E402

BOARDS = Path("data/inputs/clickydraft")
CLICKY = Path("data/clickydraft_cache.json")
CACHE = Path("data/draft_cache.json")
TEAMS = 10


def slot_of(pick: int) -> int:
    return _slot_of(pick, TEAMS)


def pick_of(rnd: int, slot: int) -> int:
    return _pick_of(rnd, slot, TEAMS)

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
         "la": "LAR"}


def norm(name: str) -> str:
    s = str(name).strip()
    m = re.match(r"^([A-Za-z0-9]{2,3})\s*DEF$", s, re.I)
    if m:
        c = m.group(1).upper()
        return "DEF:" + ALIAS.get(c.lower(), c)
    if re.search(r"D/ST|DEF|DST", s, re.I):
        first = re.split(r"\s+", s)[0].lower()
        return "DEF:" + NICK.get(first, first.upper())
    return normalize_name(s)


def load_boards() -> dict[int, list[list[str]]]:
    """season -> grid[round][slot-1] of player names."""
    out = {}
    for p in sorted(BOARDS.glob("*.tsv")):
        out[int(p.stem)] = [ln.split("\t") for ln in
                            p.read_text().rstrip("\n").split("\n")]
    if CLICKY.exists():
        cd = json.loads(CLICKY.read_text())
        by: dict[int, dict] = {}
        for p in cd["drafts"]:
            by.setdefault(p["season"], {})[(p["round"], p["slot"])] = p
        for season, cells in by.items():
            rounds = max(r for r, _ in cells)
            out.setdefault(season, [
                [cells.get((r, c), {}).get("player_name", "")
                 for c in range(1, TEAMS + 1)] for r in range(1, rounds + 1)])
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    blob = json.loads(CACHE.read_text())
    picks = blob["drafts"]
    boards = load_boards()
    repaired = 0

    for season, grid in boards.items():
        mine = [p for p in picks if p["season"] == season]
        if not mine:
            print(f"{season}: not in draft_cache, skipping")
            continue
        row1 = {norm(n): c + 1 for c, n in enumerate(grid[0]) if n}

        # Recover each manager's true slot from his round-1 pick.
        true_slot, cur_slot = {}, {}
        for p in mine:
            if p["round"] != 1:
                continue
            m = get_canonical_name(p["platform"], p["manager"])
            true_slot[m] = row1.get(norm(p["player_name"]))
            cur_slot[m] = slot_of(p["pick"])
        unresolved = [m for m, s in true_slot.items() if s is None]
        moved = [m for m, s in true_slot.items()
                 if s is not None and s != cur_slot[m]]

        if a.write and not unresolved and moved:
            for p in mine:
                m = get_canonical_name(p["platform"], p["manager"])
                p["pick"] = pick_of(p["round"], true_slot[m])
            repaired += 1

        # score the board after any repair
        cells = {(p["round"], slot_of(p["pick"])): p for p in mine}
        n = len(grid) * TEAMS
        bad = [(r, c, grid[r - 1][c - 1], cells[(r, c)]["player_name"])
               for r in range(1, len(grid) + 1) for c in range(1, TEAMS + 1)
               if (r, c) in cells and grid[r - 1][c - 1]
               and norm(grid[r - 1][c - 1]) != norm(cells[(r, c)]["player_name"])]

        print(f"\n{season}: {n - len(bad)}/{n} cells match "
              f"({100 * (n - len(bad)) / n:.1f}%)")
        if unresolved:
            print(f"   could not place: {unresolved}")
        if moved:
            verb = "moved" if a.write else "need moving"
            print(f"   slot order was wrong for {len(moved)}/{TEAMS} managers "
                  f"({verb}) — players and rounds were correct throughout")
            for m in sorted(moved, key=lambda m: true_slot[m]):
                print(f"      slot {true_slot[m]:>2}  {m:<20} "
                      f"(ESPN had {cur_slot[m]})")
        for r, c, b, cc in bad[:8]:
            print(f"   DIFF R{r} slot {c}: board={b!r} cache={cc!r}")
        if len(bad) > 8:
            print(f"   ... and {len(bad) - 8} more")

    if a.write:
        CACHE.write_text(json.dumps(blob, indent=1))
        print(f"\nRe-slotted {repaired} seasons in {CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
