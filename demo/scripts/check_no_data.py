#!/usr/bin/env python3
"""No-data guard: fail if git tracks, stages, or has ever committed dataset content.

The datasets never enter this repository: not raw files, derived files,
extracts, samples, notebook outputs, or snapshots. Attendees download the data
themselves (see data/README.md). This guard is the automated check behind that
rule. It runs as a test, as an optional pre-commit hook, and as a CI step.

Rules, applied to every path git knows about:

1. Under data/, only data/README.md and "data/data sources.md" may be tracked.
2. No data-format file (CSV, Parquet, DuckDB, SQLite, Arrow, archives, pickles,
   notebooks, JSON Lines, ...) outside the synthetic fixture directory.
3. No tracked file larger than --max-bytes (default 1 MB).
4. Synthetic fixtures are CSV files of at most 64 KB.
5. No text file carries rows shaped like the raw match records.

Usage (from anywhere inside the repository):

    python demo/scripts/check_no_data.py             # index: tracked + staged
    python demo/scripts/check_no_data.py --history   # every blob in every commit

Exit codes: 0 clean, 1 violations found, 2 the check could not run.
Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

ALLOWED_UNDER_DATA = frozenset({"data/README.md", "data/data sources.md"})
FIXTURE_DIR = "demo/tests/fixtures/synthetic/"
FIXTURE_MAX_BYTES = 64 * 1024
DEFAULT_MAX_BYTES = 1_000_000

DATA_SUFFIXES = frozenset(
    {
        ".csv", ".tsv", ".parquet", ".pq", ".duckdb", ".wal", ".sqlite", ".sqlite3",
        ".db", ".feather", ".arrow", ".ipc", ".avro", ".orc", ".zip", ".gz", ".bz2",
        ".xz", ".7z", ".tar", ".xls", ".xlsx", ".pkl", ".pickle", ".npy", ".npz",
        ".h5", ".hdf5", ".ipynb", ".jsonl", ".ndjson",
    }
)
DATA_NAME_MARKERS = (".duckdb", ".sqlite", ".parquet")

# A line shaped like a raw match record: date,team,team,score,score,...
RECORD_LINE = re.compile(r"^\s*\"?\d{4}-\d{2}-\d{2}\"?\s*,[^,\n]+,[^,\n]+,\s*\d+\s*,\s*\d+\s*,")
RECORD_LINE_LIMIT = 5
TEXT_SCAN_MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class Blob:
    path: str
    object_id: str
    size: int


def git(repo: str, *args: str, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def repo_root(start: str) -> str:
    return git(start, "rev-parse", "--show-toplevel").decode("utf-8").strip()


def object_sizes(repo: str, object_ids: list[str]) -> dict[str, int]:
    if not object_ids:
        return {}
    query = "\n".join(object_ids).encode("ascii") + b"\n"
    output = git(repo, "cat-file", "--batch-check=%(objectname) %(objectsize)", stdin=query)
    sizes: dict[str, int] = {}
    for line in output.decode("ascii").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            sizes[parts[0]] = int(parts[1])
    return sizes


def index_blobs(repo: str) -> list[Blob]:
    """Every path in the index: tracked files plus anything staged."""
    raw = git(repo, "ls-files", "--stage", "-z")
    entries: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        mode, object_id, _stage = meta.decode("ascii").split()
        if mode == "160000":  # submodule commit, not a blob
            continue
        entries.append((path.decode("utf-8"), object_id))
    sizes = object_sizes(repo, sorted({oid for _, oid in entries}))
    return [Blob(path, oid, sizes.get(oid, 0)) for path, oid in entries]


def history_blobs(repo: str) -> list[Blob]:
    """Every (path, blob) pair reachable from any ref, including stashes."""
    commits = git(repo, "rev-list", "--all").decode("ascii").split()
    seen: dict[tuple[str, str], Blob] = {}
    for commit in commits:
        raw = git(repo, "ls-tree", "-r", "-l", "-z", commit)
        for record in raw.split(b"\0"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            fields = meta.decode("ascii").split()
            if len(fields) != 4 or fields[1] != "blob":
                continue
            object_id, size = fields[2], fields[3]
            key = (path.decode("utf-8"), object_id)
            if key not in seen:
                seen[key] = Blob(key[0], object_id, int(size) if size.isdigit() else 0)
    return list(seen.values())


def is_data_format(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(name).suffix
    return suffix in DATA_SUFFIXES or any(marker in name for marker in DATA_NAME_MARKERS)


def path_violations(blob: Blob, max_bytes: int) -> list[str]:
    problems: list[str] = []
    path = blob.path
    in_fixtures = path.startswith(FIXTURE_DIR)
    if path.startswith("data/") and path not in ALLOWED_UNDER_DATA:
        problems.append("only data/README.md and 'data/data sources.md' may live under data/")
    if is_data_format(path):
        if not in_fixtures:
            problems.append("data-format file outside " + FIXTURE_DIR)
        elif PurePosixPath(path).suffix.lower() != ".csv":
            problems.append("synthetic fixtures must be small CSV files")
    if in_fixtures and blob.size > FIXTURE_MAX_BYTES:
        problems.append(f"synthetic fixture larger than {FIXTURE_MAX_BYTES} bytes")
    if blob.size > max_bytes:
        problems.append(f"{blob.size:,} bytes exceeds the {max_bytes:,}-byte limit")
    return problems


def record_rows(repo: str, blob: Blob) -> int:
    if blob.size > TEXT_SCAN_MAX_BYTES or blob.path.startswith(FIXTURE_DIR):
        return 0
    content = git(repo, "cat-file", "blob", blob.object_id)
    if b"\0" in content[:8000]:
        return 0  # binary; the format and size rules cover it
    text = content.decode("utf-8", "replace")
    return sum(1 for line in text.splitlines() if RECORD_LINE.match(line))


def check(repo: str, blobs: list[Blob], max_bytes: int) -> list[str]:
    findings: list[str] = []
    for blob in sorted(blobs, key=lambda b: (b.path, b.object_id)):
        for problem in path_violations(blob, max_bytes):
            findings.append(f"{blob.path} [{blob.object_id[:10]}]: {problem}")
        rows = record_rows(repo, blob)
        if rows >= RECORD_LINE_LIMIT:
            findings.append(
                f"{blob.path} [{blob.object_id[:10]}]: {rows} lines shaped like raw match records"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", action="store_true", help="scan every commit reachable from any ref")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="size limit per tracked file")
    parser.add_argument("--repo", default=".", help="any path inside the repository")
    args = parser.parse_args(argv)

    try:
        root = repo_root(args.repo)
        blobs = history_blobs(root) if args.history else index_blobs(root)
        findings = check(root, blobs, args.max_bytes)
    except (RuntimeError, OSError) as exc:
        print(f"no-data guard: could not run: {exc}", file=sys.stderr)
        return 2

    scope = "every commit" if args.history else "the index (tracked and staged files)"
    if findings:
        print(f"no-data guard: FAILED on {scope}. See data/README.md; data never enters git.")
        for finding in findings:
            print("  - " + finding)
        return 1
    distinct = len({blob.path for blob in blobs})
    print(f"no-data guard: OK ({distinct} paths checked in {scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
