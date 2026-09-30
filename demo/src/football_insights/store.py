"""The curated store as the services see it: one verified version in memory.

At startup a service resolves the ACTIVE pointer (local folder or private Blob
Storage), fetches that version's files, checks every checksum against the
manifest, and loads the tables into an in-memory DuckDB database. The store is
read-only from then on; tools only run SELECT statements written in this repo.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .ingest.pipeline import OUTPUTS
from .ingest.storage import BlobCuratedStorage, CuratedStorage, LocalCuratedStorage

TABLES = ("matches", "goals", "teams", "economies", "indicators", "former_names")


class StoreError(RuntimeError):
    pass


def storage_for(settings: Settings) -> CuratedStorage:
    if settings.curated_source == "blob":
        if not settings.storage_account_url:
            raise StoreError("CURATED_SOURCE=blob needs STORAGE_ACCOUNT_URL")
        return BlobCuratedStorage(settings.storage_account_url, settings.curated_container)
    return LocalCuratedStorage(settings.curated_dir)


@dataclass
class CuratedStore:
    version: str
    dataset_label: str
    manifest: dict[str, Any]
    data_quality: dict[str, Any]
    con: Any
    source: str
    _lock: threading.Lock

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        # One connection, serialized: DuckDB connections are not safe for concurrent use.
        with self._lock:
            return self.con.execute(sql, params or []).fetchall()

    def query_one(self, sql: str, params: list[Any] | None = None) -> tuple[Any, ...]:
        rows = self.query(sql, params)
        if not rows:
            raise StoreError("query returned no rows")
        return rows[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load(settings: Settings, cache_dir: Path | None = None) -> CuratedStore:
    import duckdb

    storage = storage_for(settings)
    pointer = storage.read_pointer()
    if not pointer:
        raise StoreError(f"no curated version in {storage.description}; run ingest first")
    version = str(pointer["version"])
    manifest = storage.read_manifest(version)
    if not manifest:
        raise StoreError(f"version {version} has no manifest in {storage.description}")
    cache = cache_dir or Path(tempfile.gettempdir()) / "football-insights-curated"
    folder = storage.fetch(version, list(OUTPUTS), cache)
    for name in OUTPUTS:
        expected = manifest["outputs"][name]["sha256"]
        actual = _sha256(folder / name)
        if actual != expected:
            raise StoreError(f"{name} in version {version} fails its checksum; refusing to serve it")

    con = duckdb.connect(":memory:")
    for table in TABLES:
        parquet = (folder / (table + ".parquet")).as_posix()
        con.execute(f"create table {table} as select * from read_parquet('{parquet}')")
    data_quality = json.loads((folder / "data_quality.json").read_text(encoding="utf-8"))
    return CuratedStore(
        version=version,
        dataset_label=str(manifest.get("dataset_label", "")),
        manifest=manifest,
        data_quality=data_quality,
        con=con,
        source=storage.description,
        _lock=threading.Lock(),
    )
