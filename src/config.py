import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SleeperConfig:
    league_id: str = os.getenv("SLEEPER_LEAGUE_ID", "")


@dataclass
class ESPNConfig:
    league_id: int = int(os.getenv("ESPN_LEAGUE_ID") or "0")
    espn_s2: str = os.getenv("ESPN_S2", "")
    swid: str = os.getenv("ESPN_SWID", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.league_id and self.espn_s2 and self.swid)


# Manager name mapping: canonical name -> {platform: platform_name}
# Update this after first data pull to unify names across platforms
MANAGER_ALIASES: dict[str, dict[str, list[str] | str]] = {
    "James Galante": {"espn": "James Galante", "sleeper": "jtgalante"},
    "Bryan Cannon": {"espn": "Bryan Cannon", "sleeper": "BCannon21"},
    "Matt McCauley": {"espn": "Matt McCauley", "sleeper": "mmccauley24"},
    "Tyler Clark": {"espn": "Tyler Clark", "sleeper": "dtylerclark"},
    "Stephen Rogers": {"espn": "Stephen Rogers", "sleeper": "CaptRogers22"},
    "Anthony Lettieri": {"espn": "Anthony Lettieri", "sleeper": "Tonethar"},
    "Brendan Gamble": {"espn": ["Brendan Gamble", "Britney Bear"], "sleeper": "bcg3k"},
    "Brian Dzuris": {"espn": ["Brian Dzuris", "Brittany Dzuris", "Brittany Burke", "Ward Burke"], "sleeper": "dizzy21"},
    "Donnie Darco": {"espn": ["Donnie Darco ", "Peter Wallach"], "sleeper": "pdwall"},
    "Jonathan Wiggins": {"espn": "Jonathan Wiggins", "sleeper": "jdub504"},
}


def get_canonical_name(platform: str, platform_name: str) -> str:
    """Resolve a platform-specific name to the canonical manager name."""
    for canonical, aliases in MANAGER_ALIASES.items():
        alias_val = aliases.get(platform)
        if isinstance(alias_val, list):
            if platform_name in alias_val:
                return canonical
        elif alias_val == platform_name:
            return canonical
    return platform_name


@dataclass
class WeeklyScore:
    manager: str
    season: int
    week: int
    points: float
    opponent_points: float
    win: bool
    platform: str
    is_playoff: bool = False


@dataclass
class SlotScore:
    manager: str
    season: int
    week: int
    slot: str  # QB, RB1, RB2, WR1, WR2, FLEX, TE, K, DST
    player_name: str
    points: float
    platform: str
    is_playoff: bool = False


@dataclass
class SeasonSummary:
    manager: str
    season: int
    platform: str
    wins: int
    losses: int
    total_points: float
    total_points_against: float
    finish: int  # final standing


@dataclass
class DraftPick:
    manager: str
    season: int
    platform: str
    round: int
    pick: int  # overall pick number
    player_name: str
    player_id: str
    position: str  # QB, RB, WR, TE, K, DST
    season_points: float = 0.0  # total points scored that season (filled later)
