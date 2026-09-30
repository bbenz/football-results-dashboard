"""ingest on synthetic fixtures: expected tables, data-quality counts, determinism, idempotency."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import SYNTHETIC_FILES
from football_insights.ingest.pipeline import IngestError, run
from football_insights.ingest.storage import LocalCuratedStorage, LocalRawSource


def ingest(raw_dir: Path, curated: Path, reference):  # type: ignore[no-untyped-def]
    return run(LocalRawSource(raw_dir), LocalCuratedStorage(curated), platform="Test", files=SYNTHETIC_FILES,
               reference=reference)


def test_data_quality_counts_match_hand_counts(tmp_path: Path, raw_dir: Path, reference) -> None:  # type: ignore[no-untyped-def]
    dq = ingest(raw_dir, tmp_path / "curated", reference).data_quality
    assert dq["matches"]["rows"] == 13
    assert dq["matches"]["teams"] == 5
    assert dq["matches"]["tournaments"] == 7
    assert dq["matches"]["neutral"] == 2
    assert dq["matches"]["goals"] == 33
    # Scorer rows: four matches have rows; three are complete timelines (2021 has 1 of 4 goals).
    assert dq["goalscorers"]["rows"] == 8
    assert dq["goalscorers"]["matches_with_rows"] == 4
    assert dq["goalscorers"]["complete_timelines"] == 3
    assert dq["goalscorers"]["minute_missing"] == 1
    assert dq["shootouts"] == {"rows": 3, "joined": 2, "excluded_without_match": 1, "after_non_drawn_match": 0}
    # Two neutral matches in Dunmore between other teams; 2016's "Old Elbaria" reconciles to Elbaria.
    venues = dq["venues"]
    assert venues["third_party_hosted"] == 2
    assert venues["home_matches_agreeing"] == 11
    assert venues["reconciled_via_former_names"] == 1
    assert venues["neutral_flag_but_venue_is_participant"] == 0
    # Crosswalk: Elbaria unmapped; Dunmore mapped only from 2000 (all its matches are later).
    assert dq["crosswalk"]["by_mapping"] == {"alias": 1, "exact": 2, "none": 1, "shared": 1}
    assert dq["crosswalk"]["both_teams_mapped_pct"] == 69.2
    assert dq["crosswalk"]["either_team_mapped_pct"] == 100.0
    # WDI: five entities, one aggregate excluded; 4 economies x 3 indicators x 65 non-empty years.
    assert dq["wdi"]["entities_in_file"] == 5
    assert dq["wdi"]["economies"] == 4
    assert dq["wdi"]["rows_long_format"] == 4 * 3 * 65


def test_rerun_reuses_version_with_identical_checksums(tmp_path: Path, raw_dir: Path, reference) -> None:  # type: ignore[no-untyped-def]
    first = ingest(raw_dir, tmp_path / "curated", reference)
    second = ingest(raw_dir, tmp_path / "curated", reference)
    assert not first.reused and second.reused
    assert first.version == second.version
    assert first.manifest["outputs"] == second.manifest["outputs"]
    elsewhere = ingest(raw_dir, tmp_path / "other", reference)
    assert elsewhere.manifest["outputs"] == first.manifest["outputs"]
    pointer = LocalCuratedStorage(tmp_path / "curated").read_pointer()
    assert pointer is not None and pointer["version"] == first.version


def test_changed_input_changes_version(tmp_path: Path, raw_dir: Path, reference) -> None:  # type: ignore[no-untyped-def]
    first = ingest(raw_dir, tmp_path / "curated", reference)
    path = raw_dir / "football_stats" / "results.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("Avalon,Borealis,2,0", "Avalon,Borealis,3,0", 1),
                    encoding="utf-8")
    second = ingest(raw_dir, tmp_path / "curated", reference)
    assert second.version != first.version
    assert not second.reused


def test_unclassified_tournament_fails(tmp_path: Path, raw_dir: Path, reference) -> None:  # type: ignore[no-untyped-def]
    path = raw_dir / "football_stats" / "results.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("Gold Cup", "Invented Cup"), encoding="utf-8")
    with pytest.raises(IngestError, match="Invented Cup"):
        ingest(raw_dir, tmp_path / "curated", reference)


def test_failed_verification_blocks_ingest(tmp_path: Path, raw_dir: Path, reference) -> None:  # type: ignore[no-untyped-def]
    (raw_dir / "football_stats" / "goalscorers.csv").unlink()
    with pytest.raises(IngestError, match="verify-data failed"):
        ingest(raw_dir, tmp_path / "curated", reference)
    assert LocalCuratedStorage(tmp_path / "curated").read_pointer() is None


def test_scorer_names_are_not_stored(curated_store) -> None:  # type: ignore[no-untyped-def]
    columns = [row[0] for row in curated_store.query("select column_name from (describe goals)")]
    assert "scorer" not in columns
