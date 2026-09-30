"""The no-data guard: the repository passes, and each rule catches its case."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT

GUARD = REPO_ROOT / "demo" / "scripts" / "check_no_data.py"
spec = importlib.util.spec_from_file_location("check_no_data", GUARD)
guard = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
assert spec and spec.loader
sys.modules["check_no_data"] = guard
spec.loader.exec_module(guard)


def blob(path: str, size: int = 10):  # type: ignore[no-untyped-def]
    return guard.Blob(path, "0" * 40, size)


def test_repository_index_is_clean() -> None:
    result = subprocess.run([sys.executable, str(GUARD), "--repo", str(REPO_ROOT)], capture_output=True, text=True,
                            check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_repository_history_is_clean() -> None:
    result = subprocess.run([sys.executable, str(GUARD), "--history", "--repo", str(REPO_ROOT)], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rules() -> None:
    violations = guard.path_violations
    assert violations(blob("data/README.md"), 1_000_000) == []
    assert violations(blob("data/data sources.md"), 1_000_000) == []
    assert violations(blob("data/football_stats/results.csv"), 1_000_000)
    assert violations(blob("data/notes.txt"), 1_000_000)
    assert violations(blob("demo/extract.parquet"), 1_000_000)
    assert violations(blob("demo/store.duckdb.wal"), 1_000_000)
    assert violations(blob("docs/big.md", 2_000_000), 1_000_000)
    assert violations(blob("demo/tests/fixtures/synthetic/results.csv"), 1_000_000) == []
    assert violations(blob("demo/tests/fixtures/synthetic/results.csv", 70_000), 1_000_000)
    assert violations(blob("demo/tests/fixtures/synthetic/table.parquet"), 1_000_000)


def test_record_shaped_lines_are_detected(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    rows = "\n".join(f"2001-01-0{i},Avalon,Borealis,{i},0,Friendly,X,Y,FALSE" for i in range(1, 7))
    (tmp_path / "pasted.md").write_text(rows + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "pasted.md"], check=True)
    result = subprocess.run([sys.executable, str(GUARD), "--repo", str(tmp_path)], capture_output=True, text=True,
                            check=False)
    assert result.returncode == 1
    assert "lines shaped like raw match records" in result.stdout
