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
