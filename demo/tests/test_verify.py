"""verify-data against synthetic fixtures: passes, then fails clearly on each kind of drift."""

from __future__ import annotations

from pathlib import Path

from conftest import SYNTHETIC_FILES
from football_insights.data.contract import README_HINT
from football_insights.data.verify import render, verify


def failures(report):  # type: ignore[no-untyped-def]
    return [c for c in report.checks if c.status == "fail"]


def test_synthetic_data_passes_with_checksum_warnings(raw_dir: Path) -> None:
    report = verify(raw_dir, SYNTHETIC_FILES)
    assert report.ok, render(report)
    # Fixtures are not the Kaggle files, so every checksum differs: a warning, never a failure.
    checksum = [c for c in report.checks if c.name == "checksum"]
    assert len(checksum) == len(SYNTHETIC_FILES)
    assert all(c.status == "warn" for c in checksum)
    assert report.match_dates == ("1901-03-02", "2021-07-01")


def test_missing_file_fails_and_points_to_readme(raw_dir: Path) -> None:
    (raw_dir / "football_stats" / "shootouts.csv").unlink()
    report = verify(raw_dir, SYNTHETIC_FILES)
    assert not report.ok
    [failure] = failures(report)
    assert failure.file == "football_stats/shootouts.csv"
    assert failure.name == "present"
    assert README_HINT in failure.detail
    assert "verify-data FAILED" in render(report)


def test_missing_folder_fails(tmp_path: Path) -> None:
    report = verify(tmp_path / "nowhere", SYNTHETIC_FILES)
    assert not report.ok
    assert failures(report)[0].name == "data folder"


def test_renamed_column_is_schema_drift(raw_dir: Path) -> None:
    path = raw_dir / "football_stats" / "results.csv"
    text = path.read_text(encoding="utf-8").replace("neutral", "is_neutral", 1)
    path.write_text(text, encoding="utf-8")
    report = verify(raw_dir, SYNTHETIC_FILES)
    [failure] = failures(report)
    assert failure.name == "columns"
    assert "neutral" in failure.detail


def test_unparseable_score_fails(raw_dir: Path) -> None:
    path = raw_dir / "football_stats" / "results.csv"
    text = path.read_text(encoding="utf-8").replace("Avalon,Borealis,2,0", "Avalon,Borealis,two,0", 1)
    path.write_text(text, encoding="utf-8")
    report = verify(raw_dir, SYNTHETIC_FILES)
    assert any(c.name == "type home_score" for c in failures(report))


def test_invalid_utf8_fails(raw_dir: Path) -> None:
    path = raw_dir / "football_stats" / "former_names.csv"
    path.write_bytes(path.read_bytes() + b"Caf\xe9,Old,1900-01-01,1901-01-01\n")
    report = verify(raw_dir, SYNTHETIC_FILES)
    assert any(c.name == "encoding" for c in failures(report))


def test_new_extra_column_only_warns(raw_dir: Path) -> None:
    path = raw_dir / "football_stats" / "former_names.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [lines[0] + ",note"] + [line + ",x" for line in lines[1:]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = verify(raw_dir, SYNTHETIC_FILES)
    assert report.ok
    assert any(c.name == "extra columns" and c.status == "warn" for c in report.checks)


def test_row_count_outside_range_fails(raw_dir: Path) -> None:
    from dataclasses import replace

    strict = tuple(replace(s, min_rows=100) if s.path.endswith("results.csv") else s for s in SYNTHETIC_FILES)
    report = verify(raw_dir, strict)
    assert any(c.name == "row count" for c in failures(report))
