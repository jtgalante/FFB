"""Normalize and combine data from ESPN and Sleeper into unified DataFrames."""

import pandas as pd
from dataclasses import asdict

from .config import (
    ESPNConfig, SleeperConfig, WeeklyScore, SlotScore, SeasonSummary, DraftPick,
    get_canonical_name,
)
from .sleeper_client import fetch_all_sleeper_data, fetch_all_sleeper_drafts
from .espn_client import fetch_all_espn_data, fetch_all_espn_drafts
from .cache import (
    save_to_disk, load_from_disk, cache_age,
    save_platform_cache, load_platform_cache,
    save_draft_cache, load_draft_cache,
    ESPN_CACHE_PATH, SLEEPER_CACHE_PATH, DRAFT_CACHE_PATH,
)

# Maximum age (hours) before Sleeper cache is considered stale
# ESPN cache never expires (league is frozen on ESPN)
_SLEEPER_CACHE_MAX_AGE_HOURS = 24


def _apply_canonical_names(records: list[dict]) -> list[dict]:
    """Replace platform-specific manager names with canonical names."""
    for r in records:
        r["manager"] = get_canonical_name(r["platform"], r["manager"])
    return records


def _to_dataframe(records: list, sort_cols: list[str] | None = None) -> pd.DataFrame:
    """Convert a list of dataclass instances to a DataFrame."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(r) for r in records])
    df = pd.DataFrame(_apply_canonical_names(df.to_dict("records")))
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df


def _deduplicate_seasons(df: pd.DataFrame, prefer_platform: str = "sleeper") -> pd.DataFrame:
    """When a season exists on both platforms, keep only the preferred one.

    This handles 2024/2025 which exist on both ESPN and Sleeper.
    We prefer Sleeper data since it has better bracket/finish resolution.
    """
    if df.empty or "platform" not in df.columns:
        return df

    # Find seasons that appear on both platforms
    season_platforms = df.groupby("season")["platform"].apply(set).reset_index()
    overlap_seasons = season_platforms[
        season_platforms["platform"].apply(lambda s: len(s) > 1)
    ]["season"].tolist()

    if not overlap_seasons:
        return df

    # Remove the non-preferred platform rows for overlapping seasons
    drop_platform = "espn" if prefer_platform == "sleeper" else "sleeper"
    mask = (df["season"].isin(overlap_seasons)) & (df["platform"] == drop_platform)
    return df[~mask].reset_index(drop=True)


def load_all_data(
    sleeper_cfg: SleeperConfig | None = None,
    espn_cfg: ESPNConfig | None = None,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and combine data from all configured platforms.

    Uses a disk cache to avoid redundant API calls. Cached data is reused
    when less than 24 hours old, unless *force_refresh* is True.

    Returns (weekly_scores_df, slot_scores_df, season_summaries_df).
    """
    # ------------------------------------------------------------------
    # 1. Try the disk cache (unless caller explicitly wants fresh data)
    # ------------------------------------------------------------------
    # Check if APIs are configured — if not, always use cache (deployed mode)
    has_apis = (sleeper_cfg and sleeper_cfg.league_id) or (espn_cfg and espn_cfg.is_configured)

    if not force_refresh:
        age = cache_age()
        # Use cache if fresh enough, or always if no APIs configured
        if age is not None and (age < _SLEEPER_CACHE_MAX_AGE_HOURS or not has_apis):
            cached = load_from_disk()
            if cached is not None:
                all_weekly, all_slots, all_summaries = cached
                return _build_dataframes(all_weekly, all_slots, all_summaries)

    # ------------------------------------------------------------------
    # 2. ESPN: always load from frozen cache (never re-fetch)
    # ------------------------------------------------------------------
    all_weekly: list[WeeklyScore] = []
    all_slots: list[SlotScore] = []
    all_summaries: list[SeasonSummary] = []

    espn_cached = load_platform_cache(ESPN_CACHE_PATH)
    if espn_cached is not None:
        ew, es, eu = espn_cached
        all_weekly.extend(ew)
        all_slots.extend(es)
        all_summaries.extend(eu)
    elif espn_cfg and espn_cfg.is_configured:
        ew, es, eu, _ed = fetch_all_espn_data(espn_cfg)
        all_weekly.extend(ew)
        all_slots.extend(es)
        all_summaries.extend(eu)
        save_platform_cache(ew, es, eu, ESPN_CACHE_PATH)

    # ------------------------------------------------------------------
    # 3. Sleeper: refresh if stale or forced
    # ------------------------------------------------------------------
    sleeper_age = cache_age(SLEEPER_CACHE_PATH)
    sleeper_fresh = sleeper_age is not None and sleeper_age < _SLEEPER_CACHE_MAX_AGE_HOURS

    if not force_refresh and sleeper_fresh:
        sleeper_cached = load_platform_cache(SLEEPER_CACHE_PATH)
        if sleeper_cached is not None:
            sw, ss, su = sleeper_cached
            all_weekly.extend(sw)
            all_slots.extend(ss)
            all_summaries.extend(su)
    elif sleeper_cfg and sleeper_cfg.league_id:
        sw, ss, su, _sd = fetch_all_sleeper_data(sleeper_cfg.league_id)
        all_weekly.extend(sw)
        all_slots.extend(ss)
        all_summaries.extend(su)
        save_platform_cache(sw, ss, su, SLEEPER_CACHE_PATH)

    # ------------------------------------------------------------------
    # 4. Save combined cache for deployed mode
    # ------------------------------------------------------------------
    if all_weekly or all_slots or all_summaries:
        save_to_disk(all_weekly, all_slots, all_summaries)

    return _build_dataframes(all_weekly, all_slots, all_summaries)


def _build_dataframes(
    all_weekly: list[WeeklyScore],
    all_slots: list[SlotScore],
    all_summaries: list[SeasonSummary],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convert dataclass lists to DataFrames with canonical names and dedup."""
    weekly_df = _to_dataframe(all_weekly, ["season", "week", "manager"])
    slots_df = _to_dataframe(all_slots, ["season", "week", "manager", "slot"])
    summaries_df = _to_dataframe(all_summaries, ["season", "manager"])

    # Deduplicate overlapping seasons (prefer Sleeper for 2024+)
    weekly_df = _deduplicate_seasons(weekly_df)
    slots_df = _deduplicate_seasons(slots_df)
    summaries_df = _deduplicate_seasons(summaries_df)

    return weekly_df, slots_df, summaries_df


def load_draft_data(
    sleeper_cfg: SleeperConfig | None = None,
    espn_cfg: ESPNConfig | None = None,
) -> pd.DataFrame:
    """Load and combine draft data from all configured platforms.

    Uses disk cache to avoid re-fetching.
    Returns a DataFrame with columns: manager, season, platform, round, pick,
    player_name, player_id, position, season_points.
    """
    # Try cache first
    cached = load_draft_cache()
    if cached is not None:
        drafts_df = _to_dataframe(cached, ["season", "pick", "manager"])
        return _deduplicate_seasons(drafts_df)

    all_drafts: list[DraftPick] = []

    if sleeper_cfg and sleeper_cfg.league_id:
        all_drafts.extend(fetch_all_sleeper_drafts(sleeper_cfg.league_id))

    if espn_cfg and espn_cfg.is_configured:
        all_drafts.extend(fetch_all_espn_drafts(espn_cfg))

    if all_drafts:
        save_draft_cache(all_drafts)

    drafts_df = _to_dataframe(all_drafts, ["season", "pick", "manager"])
    drafts_df = _deduplicate_seasons(drafts_df)

    return drafts_df


if __name__ == "__main__":
    sleeper = SleeperConfig()
    espn = ESPNConfig()

    weekly_df, slots_df, summaries_df = load_all_data(sleeper, espn)
    print(f"Weekly scores: {len(weekly_df)} rows")
    print(f"Slot scores: {len(slots_df)} rows")
    print(f"Season summaries: {len(summaries_df)} rows")

    drafts_df = load_draft_data(sleeper, espn)
    print(f"Draft picks: {len(drafts_df)} rows")

    if not weekly_df.empty:
        print(f"\nSeasons: {sorted(weekly_df['season'].unique())}")
        print(f"Managers: {sorted(weekly_df['manager'].unique())}")
