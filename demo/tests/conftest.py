"""Shared test fixtures.

Unit tests use small synthetic CSVs with fictional teams (tests/fixtures/synthetic).
Real-data tests are marked `realdata` and skip when the raw data is absent; they
compute expectations through the deterministic layer at run time and never
hardcode values from the real datasets.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from football_insights.config import Settings
from football_insights.data.contract import FILES, FileSpec
from football_insights.reference import REFERENCE_DIR, Reference, load

TESTS = Path(__file__).parent
REPO_ROOT = TESTS.parent.parent
SYNTHETIC = TESTS / "fixtures" / "synthetic"
SYNTHETIC_REFERENCE = TESTS / "fixtures" / "synthetic_reference"
REAL_DATA = Path(os.environ.get("FOOTBALL_DATA_DIR") or REPO_ROOT / "data")

# The real contract with ranges and date bounds that the synthetic fixtures satisfy.
SYNTHETIC_FILES: tuple[FileSpec, ...] = tuple(
    replace(spec, min_rows=1, max_rows=1000,
            date_bounds=("1901-12-31", "2020-01-01") if spec.date_bounds else None)
    for spec in FILES
)


def real_data_available() -> bool:
    return all((REAL_DATA / spec.path).is_file() for spec in FILES)


requires_real_data = pytest.mark.skipif(not real_data_available(),
                                        reason="raw data not downloaded; see data/README.md")


def make_raw_dir(root: Path) -> Path:
    """Lay the flat synthetic fixtures out the way data/ is laid out."""
    for spec in FILES:
        target = root / spec.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SYNTHETIC / Path(spec.path).name, target)
    return root


def synthetic_reference(root: Path) -> Reference:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("tournaments.yaml", "eras.yaml", "lineage.yaml"):
        shutil.copy(REFERENCE_DIR / name, root / name)
    shutil.copy(SYNTHETIC_REFERENCE / "crosswalk.yaml", root / "crosswalk.yaml")
    return load(root)


def test_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    return make_raw_dir(tmp_path / "raw")


@pytest.fixture
def reference(tmp_path: Path) -> Reference:
    return synthetic_reference(tmp_path / "reference")


@pytest.fixture
def curated_store(tmp_path: Path, raw_dir: Path, reference: Reference):  # type: ignore[no-untyped-def]
    from football_insights.ingest.pipeline import run
    from football_insights.ingest.storage import LocalCuratedStorage, LocalRawSource
    from football_insights.store import load as load_store

    curated = tmp_path / "curated"
    run(LocalRawSource(raw_dir), LocalCuratedStorage(curated), platform="Test", files=SYNTHETIC_FILES,
        reference=reference)
    return load_store(test_settings(curated_dir=curated), cache_dir=tmp_path / "cache")


@pytest.fixture
def ctx(curated_store, reference):  # type: ignore[no-untyped-def]
    from football_insights.analytics.context import ToolContext

    return ToolContext(curated_store, reference=reference)
