"""Where raw files come from and where curated versions go: a local folder or
private Azure Blob Storage, behind one small interface.

Blob access is keyless (DefaultAzureCredential: workload identity on AKS,
managed identity on ACA, the operator's sign-in locally). Shared-key access is
disabled on the storage account, so there is no key path to fall back to.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

POINTER = "ACTIVE.json"
MANIFEST = "manifest.json"


class CuratedStorage(Protocol):
    description: str

    def read_pointer(self) -> dict[str, Any] | None: ...
    def read_manifest(self, version: str) -> dict[str, Any] | None: ...
    def publish(self, version: str, source_dir: Path) -> None: ...
    def write_pointer(self, pointer: dict[str, Any]) -> None: ...
    def write_run(self, name: str, report: dict[str, Any]) -> None: ...
    def fetch(self, version: str, files: list[str], dest: Path) -> Path: ...


class LocalCuratedStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.description = f"local folder {self.root}"

    def read_pointer(self) -> dict[str, Any] | None:
        path = self.root / POINTER
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def read_manifest(self, version: str) -> dict[str, Any] | None:
        path = self.root / version / MANIFEST
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def publish(self, version: str, source_dir: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        final = self.root / version
        if final.exists():
            shutil.rmtree(final)
        staging = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=self.root))
        for item in source_dir.iterdir():
            shutil.copy2(item, staging / item.name)
        os.replace(staging, final)

    def write_pointer(self, pointer: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".{POINTER}.tmp"
        tmp.write_text(json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        os.replace(tmp, self.root / POINTER)

    def write_run(self, name: str, report: dict[str, Any]) -> None:
        runs = self.root / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{name}.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

    def fetch(self, version: str, files: list[str], dest: Path) -> Path:
        return self.root / version


class BlobCuratedStorage:
    def __init__(self, account_url: str, container: str) -> None:
        from azure.storage.blob import ContainerClient

        from ..identity import azure_credential

        self.container = ContainerClient(account_url, container, credential=azure_credential())
        self.description = f"blob container {container} at {account_url}"

    def _read_json(self, name: str) -> dict[str, Any] | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            data = self.container.download_blob(name).readall()
        except ResourceNotFoundError:
            return None
        return json.loads(data)

    def read_pointer(self) -> dict[str, Any] | None:
        return self._read_json(POINTER)

    def read_manifest(self, version: str) -> dict[str, Any] | None:
        return self._read_json(f"{version}/{MANIFEST}")

    def publish(self, version: str, source_dir: Path) -> None:
        # The manifest goes last: a version without a manifest is incomplete and never read.
        items = sorted(source_dir.iterdir(), key=lambda p: p.name == MANIFEST)
        for item in items:
            with item.open("rb") as handle:
                self.container.upload_blob(f"{version}/{item.name}", handle, overwrite=True)

    def write_pointer(self, pointer: dict[str, Any]) -> None:
        body = json.dumps(pointer, indent=2, sort_keys=True).encode()
        self.container.upload_blob(POINTER, body, overwrite=True)

    def write_run(self, name: str, report: dict[str, Any]) -> None:
        body = json.dumps(report, indent=2, sort_keys=True).encode()
        self.container.upload_blob(f"runs/{name}.json", body, overwrite=True)

    def fetch(self, version: str, files: list[str], dest: Path) -> Path:
        target = dest / version
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            with (target / name).open("wb") as handle:
                self.container.download_blob(f"{version}/{name}").readinto(handle)
        return target


class RawSource(Protocol):
    description: str

    def materialize(self, relative_paths: list[str], dest: Path) -> Path: ...


class LocalRawSource:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.description = f"local folder {self.root}"

    def materialize(self, relative_paths: list[str], dest: Path) -> Path:
        return self.root


class BlobRawSource:
    def __init__(self, account_url: str, container: str) -> None:
        from azure.storage.blob import ContainerClient

        from ..identity import azure_credential

        self.container = ContainerClient(account_url, container, credential=azure_credential())
        self.description = f"blob container {container} at {account_url}"

    def materialize(self, relative_paths: list[str], dest: Path) -> Path:
        from azure.core.exceptions import ResourceNotFoundError

        for rel in relative_paths:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with target.open("wb") as handle:
                    self.container.download_blob(rel).readinto(handle)
            except ResourceNotFoundError:
                target.unlink(missing_ok=True)  # verify-data then reports the missing file
        return dest
