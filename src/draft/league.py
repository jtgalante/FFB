"""League configuration for the draft engine.

Loads config/league.yaml and provides snake-draft pick math. Can also
refresh structural settings straight from the Sleeper API (on a machine
with network access) via `refresh_from_sleeper`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config/league.yaml")

POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass
class LeagueConfig:
    teams: int = 10
    my_draft_slot: int = 1
    rounds: int = 15
    starters: dict[str, int] = field(default_factory=lambda: {
        "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2,
    })
    flex_eligible: tuple[str, ...] = ("RB", "WR", "TE")
    regular_season_weeks: int = 14
    playoff_weeks: tuple[int, ...] = (15, 16, 17)
    playoff_teams: int = 6
    playoff_byes: int = 2
    opponent_weekly_mean: float = 100.7
    opponent_weekly_sd: float = 20.8
    scoring: dict[str, float] = field(default_factory=dict)

    # Engine parameters
    lambda_risk: float = 0.5
    opponent_adp_noise: float = 4.0
    n_draft_sims: int = 200
    n_season_sims: int = 1000
    n_season_sims_fast: int = 60
    replacement_baseline_method: str = "worst_starter"
    ceiling_weight: float = 0.25

    @property
    def total_picks(self) -> int:
        return self.teams * self.rounds

    @property
    def total_weeks(self) -> int:
        return self.regular_season_weeks + len(self.playoff_weeks)

    @property
    def starter_count(self) -> int:
        return sum(self.starters.values())

    @property
    def bench_size(self) -> int:
        return self.rounds - self.starter_count

    def required_starters(self, position: str) -> int:
        """Dedicated (non-flex) starting slots for a position."""
        return self.starters.get(position, 0)

    def snake_slot_for_pick(self, overall_pick: int) -> int:
        """Draft slot (1-based) on the clock for a 1-based overall pick."""
        rnd, idx = divmod(overall_pick - 1, self.teams)
        return idx + 1 if rnd % 2 == 0 else self.teams - idx

    def picks_for_slot(self, slot: int) -> list[int]:
        """All 1-based overall picks belonging to a draft slot."""
        return [p for p in range(1, self.total_picks + 1)
                if self.snake_slot_for_pick(p) == slot]

    def my_picks(self) -> list[int]:
        return self.picks_for_slot(self.my_draft_slot)

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "LeagueConfig":
        raw = yaml.safe_load(Path(path).read_text())
        kwargs = {}
        for f in cls.__dataclass_fields__:
            if f in raw:
                kwargs[f] = raw[f]
        cfg = cls(**kwargs)
        cfg.flex_eligible = tuple(cfg.flex_eligible)
        cfg.playoff_weeks = tuple(cfg.playoff_weeks)
        return cfg


def refresh_from_sleeper(league_id: str,
                         path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    """Pull roster/scoring/playoff settings from Sleeper and rewrite the
    structural fields of league.yaml in place. Returns the fetched settings.

    Requires network access to api.sleeper.app (run on your laptop).
    """
    from ..sleeper_client import get_league

    league = get_league(league_id)
    positions = league.get("roster_positions", [])
    settings = league.get("settings", {})
    scoring = league.get("scoring_settings", {})

    starters: dict[str, int] = {}
    for slot in positions:
        if slot == "BN":
            continue
        name = {"DEF": "DST", "SUPER_FLEX": "SFLEX"}.get(slot, slot)
        starters[name] = starters.get(name, 0) + 1

    playoff_start = settings.get("playoff_week_start", 15)
    raw = yaml.safe_load(Path(path).read_text())
    raw.update({
        "teams": settings.get("num_teams", len(positions) and raw.get("teams", 10)),
        "starters": starters,
        "playoff_teams": settings.get("playoff_teams", raw.get("playoff_teams", 6)),
        "regular_season_weeks": playoff_start - 1,
        "playoff_weeks": list(range(playoff_start, playoff_start + 3)),
    })
    sc = raw.setdefault("scoring", {})
    mapping = {
        "rec": "rec", "pass_yd": "pass_yd", "pass_td": "pass_td",
        "pass_int": "pass_int", "rush_yd": "rush_yd", "rush_td": "rush_td",
        "rec_yd": "rec_yd", "rec_td": "rec_td", "fum_lost": "fum_lost",
    }
    for ours, theirs in mapping.items():
        if theirs in scoring:
            sc[ours] = float(scoring[theirs])
    Path(path).write_text(yaml.safe_dump(raw, sort_keys=False))
    return {"starters": starters, "scoring": sc, "settings": settings}
