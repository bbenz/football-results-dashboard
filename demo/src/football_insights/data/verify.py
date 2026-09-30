"""verify-data: check the raw downloads against the data contract.

Fails (exit 1) on schema drift: a missing file or column, invalid encoding, an
unparseable value, or a row count or date outside the sanity range. Warns on
checksum drift, because a newer Kaggle version is expected to change counts.
Every failure message points to data/README.md.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from .contract import DATASETS, FILES, README_HINT, FileSpec

Status = Literal["pass", "warn", "fail"]

_KIND_SQL = {
    "date": "try_cast({c} as date) is null",
    "int": "try_cast({c} as bigint) is null or try_cast({c} as bigint) < 0",
    "bool": "upper({c}) not in ('TRUE', 'FALSE')",
    "int_or_na": "{c} <> 'NA' and try_cast({c} as bigint) is null",
    "number_or_empty": "{c} <> '' and try_cast({c} as double) is null",
    "text": "{c} is null or trim({c}) = ''",
}


@dataclass
class Check:
    file: str
    name: str
    status: Status
    detail: str


@dataclass
class FileFacts:
    path: str
    bytes: int = 0
    sha256: str = ""
    rows: int = 0
    matches_verified: bool = False
    columns: list[str] = field(default_factory=list)


@dataclass
class VerifyReport:
    data_dir: str
    checks: list[Check] = field(default_factory=list)
    files: dict[str, FileFacts] = field(default_factory=dict)
    match_dates: tuple[str, str] | None = None

    @property
    def ok(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    def dataset_versions(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, ds in DATASETS.items():
            specs = [s for s in FILES if s.dataset == key]
            same = all(self.files.get(s.path, FileFacts(s.path)).matches_verified for s in specs)
            out[key] = {
                "title": ds.title,
                "kaggle": ds.kaggle_slug,
                "license": ds.license,
                "verified_version": ds.verified_version,
                "matches_verified_version": same,
                "version_label": f"v{ds.verified_version}" if same else f"differs from v{ds.verified_version}",
            }
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_dir": self.data_dir,
            "ok": self.ok,
            "checks": [asdict(c) for c in self.checks],
            "files": {k: asdict(v) for k, v in self.files.items()},
            "match_dates": list(self.match_dates) if self.match_dates else None,
            "datasets": self.dataset_versions(),
        }


def _hash_and_decode(path: Path) -> tuple[int, str, str | None]:
    """Stream the file once: size, SHA-256, and strict UTF-8 validation."""
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    size = 0
    error: str | None = None
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            size += len(chunk)
            digest.update(chunk)
            if error is None:
                try:
                    decoder.decode(chunk)
                except UnicodeDecodeError as exc:
                    error = f"not valid UTF-8 near byte {size - len(chunk) + exc.start}"
    if error is None:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            error = "truncated UTF-8 sequence at end of file"
    return size, digest.hexdigest(), error


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle), [])


def _quote(column: str) -> str:
    return '"' + column.replace('"', '""') + '"'


def _verify_file(con: Any, root: Path, spec: FileSpec, report: VerifyReport) -> None:
    path = root / spec.path
    facts = FileFacts(path=spec.path)
    report.files[spec.path] = facts
    if not path.is_file():
        report.checks.append(Check(spec.path, "present", "fail", f"missing file {path}. {README_HINT}"))
        return
    report.checks.append(Check(spec.path, "present", "pass", "found"))

    facts.bytes, facts.sha256, decode_error = _hash_and_decode(path)
    if decode_error:
        report.checks.append(Check(spec.path, "encoding", "fail", f"{decode_error}. {README_HINT}"))
        return
    report.checks.append(Check(spec.path, "encoding", "pass", "UTF-8"))

    facts.columns = _header(path)
    missing = [c for c in spec.columns if c not in facts.columns]
    extra = [c for c in facts.columns if c not in spec.columns and c not in spec.known_unused]
    if missing:
        report.checks.append(Check(spec.path, "columns", "fail",
                                   f"missing columns {missing}; the schema changed. {README_HINT}"))
        return
    report.checks.append(Check(spec.path, "columns", "pass", f"{len(spec.columns)} expected columns present"))
    if extra:
        shown = ", ".join(extra[:5]) + (" ..." if len(extra) > 5 else "")
        report.checks.append(Check(spec.path, "extra columns", "warn", f"{len(extra)} columns not used: {shown}"))

    source = f"read_csv('{path.as_posix()}', header=true, all_varchar=true)"
    facts.rows = int(con.execute(f"select count(*) from {source}").fetchone()[0])
    if not spec.min_rows <= facts.rows <= spec.max_rows:
        report.checks.append(Check(spec.path, "row count", "fail",
                                   f"{facts.rows:,} rows, outside {spec.min_rows:,}-{spec.max_rows:,}. "
                                   f"{README_HINT}"))
    else:
        report.checks.append(Check(spec.path, "row count", "pass", f"{facts.rows:,} rows"))

    for column, kind in spec.kinds.items():
        condition = _KIND_SQL[kind].format(c=_quote(column))
        bad, example = con.execute(
            f"select count(*), any_value({_quote(column)}) from {source} where {condition}"
        ).fetchone()
        if bad:
            report.checks.append(Check(spec.path, f"type {column}", "fail",
                                       f"{bad:,} values are not {kind}, e.g. {example!r}. {README_HINT}"))
    if spec.date_bounds:
        earliest_max, latest_min = spec.date_bounds
        first, last = con.execute(f"select min(cast(date as date)), max(cast(date as date)) from {source}").fetchone()
        report.match_dates = (str(first), str(last))
        tomorrow = date.today() + timedelta(days=1)
        if str(first) > earliest_max or str(last) < latest_min or last > tomorrow:
            report.checks.append(Check(spec.path, "date range", "fail",
                                       f"matches run {first} to {last}; expected a start by {earliest_max} and an "
                                       f"end after {latest_min}. {README_HINT}"))
        else:
            report.checks.append(Check(spec.path, "date range", "pass", f"{first} to {last}"))

    facts.matches_verified = facts.sha256 == spec.verified_sha256
    if facts.matches_verified:
        report.checks.append(Check(spec.path, "checksum", "pass", "matches the verified version"))
    else:
        ds = DATASETS[spec.dataset]
        report.checks.append(Check(
            spec.path, "checksum", "warn",
            f"differs from Kaggle version {ds.verified_version} ({ds.verified_updated}) that this demo was "
            f"verified against; counts and results may differ ({facts.rows:,} rows here, "
            f"{spec.verified_rows:,} verified)."))


def verify(data_dir: Path, files: tuple[FileSpec, ...] = FILES) -> VerifyReport:
    import duckdb

    root = Path(data_dir)
    report = VerifyReport(data_dir=str(root))
    if not root.is_dir():
        report.checks.append(Check(str(root), "data folder", "fail", f"folder not found: {root}. {README_HINT}"))
        return report
    con = duckdb.connect()
    try:
        for spec in files:
            _verify_file(con, root, spec, report)
    finally:
        con.close()
    return report


def render(report: VerifyReport) -> str:
    symbol = {"pass": "ok  ", "warn": "WARN", "fail": "FAIL"}
    lines = [f"verify-data: {report.data_dir}"]
    for check in report.checks:
        if check.status == "pass" and check.name not in ("row count", "checksum", "date range", "present"):
            continue
        lines.append(f"  {symbol[check.status]} {check.file:48} {check.name:14} {check.detail}")
    fails = sum(c.status == "fail" for c in report.checks)
    warns = len(report.warnings)
    verdict = "PASSED" if report.ok else "FAILED"
    lines.append(f"verify-data {verdict}: {fails} failure(s), {warns} warning(s).")
    if not report.ok:
        lines.append(README_HINT)
    return "\n".join(lines)
