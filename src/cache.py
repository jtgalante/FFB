"""Disk caching for league data to avoid redundant API calls."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from .config import WeeklyScore, SlotScore, SeasonSummary, DraftPick

# Default cache locations
DEFAULT_CACHE_PATH = Path("data/league_cache.json")
ESPN_CACHE_PATH = Path("data/espn_cache.json")
SLEEPER_CACHE_PATH = Path("data/sleeper_cache.json")
DRAFT_CACHE_PATH = Path("data/draft_cache.json")

# Mapping from type key to dataclass constructor
_DATACLASS_MAP = {
    "weekly": WeeklyScore,
    "slots": SlotScore,
    "summaries": SeasonSummary,
}


def save_to_disk(
    weekly: list[WeeklyScore],
    slots: list[SlotScore],
    summaries: list[SeasonSummary],
    path: Path = DEFAULT_CACHE_PATH,
) -> None:
    """Serialize dataclass lists to a JSON file with a timestamp."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": time.time(),
        "weekly": [asdict(w) for w in weekly],
        "slots": [asdict(s) for s in slots],
        "summaries": [asdict(s) for s in summaries],
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_from_disk(
    path: Path = DEFAULT_CACHE_PATH,
) -> tuple[list[WeeklyScore], list[SlotScore], list[SeasonSummary]] | None:
    """Deserialize cached JSON back to dataclass instances.

    Returns None if the cache file does not exist or is malformed.
    """
    path = Path(path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict) or "weekly" not in data:
        return None

    try:
        weekly = [WeeklyScore(**r) for r in data["weekly"]]
        slots = [SlotScore(**r) for r in data["slots"]]
        summaries = [SeasonSummary(**r) for r in data["summaries"]]
    except (TypeError, KeyError):
        return None

    return weekly, slots, summaries


def cache_age(path: Path = DEFAULT_CACHE_PATH) -> float | None:
    """Return the age of the cache in hours, or None if no cache exists."""
    path = Path(path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("timestamp")
        if ts is None:
            return None
        return (time.time() - ts) / 3600.0
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def save_platform_cache(
    weekly: list[WeeklyScore],
    slots: list[SlotScore],
    summaries: list[SeasonSummary],
    path: Path,
) -> None:
    """Save data for a single platform to its own cache file."""
    save_to_disk(weekly, slots, summaries, path)


def load_platform_cache(
    path: Path,
) -> tuple[list[WeeklyScore], list[SlotScore], list[SeasonSummary]] | None:
    """Load data for a single platform from its cache file."""
    return load_from_disk(path)


def save_draft_cache(
    drafts: list[DraftPick],
    path: Path = DRAFT_CACHE_PATH,
) -> None:
    """Save draft picks to a separate cache file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "drafts": [asdict(d) for d in drafts],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_draft_cache(
    path: Path = DRAFT_CACHE_PATH,
) -> list[DraftPick] | None:
    """Load cached draft picks. Returns None if no cache."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [DraftPick(**r) for r in data.get("drafts", [])]
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return None
