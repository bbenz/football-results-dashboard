"""download-data: an optional helper that fetches the two Kaggle datasets into data/.

It calls Kaggle's dataset download API (the endpoint the Kaggle CLI uses),
asks for the exact version this demo was verified against unless told
otherwise, and extracts only the files named in the data contract. Kaggle's
terms require an account: set KAGGLE_API_TOKEN (or keep a token in
~/.kaggle/access_token) and the helper sends it; it never prints it.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .contract import DATASETS, FILES, README_HINT, Dataset

API = "https://www.kaggle.com/api/v1/datasets/download/{slug}"
USER_AGENT = "football-insights-demo/1.0"


class DownloadError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _token() -> str | None:
    token = os.environ.get("KAGGLE_API_TOKEN", "").strip()
    if token:
        return token
    path = Path.home() / ".kaggle" / "access_token"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def _archive_url(dataset: Dataset, version: int | None) -> str:
    url = API.format(slug=dataset.kaggle_slug) + (f"?datasetVersionNumber={version}" if version else "")
    headers = {"User-Agent": USER_AGENT}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(url, headers=headers), timeout=60)  # noqa: S310 - fixed https URL
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
            return str(exc.headers["Location"])
        wanted = f"version {version}" if version else "the latest version"
        raise DownloadError(f"Kaggle returned HTTP {exc.code} for {dataset.kaggle_slug} {wanted}. "
                            f"{'Set KAGGLE_API_TOKEN, or ' if not token else ''}download it in a browser. "
                            f"{README_HINT}") from exc
    raise DownloadError(f"Kaggle did not return a download link for {dataset.kaggle_slug}. {README_HINT}")


def download(key: str, data_dir: Path, latest: bool = False) -> list[Path]:
    dataset = DATASETS[key]
    version = None if latest else dataset.verified_version
    wanted = {Path(spec.path).name: spec.path for spec in FILES if spec.dataset == key}
    url = _archive_url(dataset, version)
    if not url.startswith("https://"):
        raise DownloadError(f"refusing a non-HTTPS download link for {dataset.kaggle_slug}")
    with tempfile.TemporaryDirectory(prefix="kaggle-") as tmp:
        archive = Path(tmp) / "archive.zip"
        # Signed URL from Kaggle's redirect (scheme checked above); the token is not sent to it.
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=600) as response, archive.open("wb") as out:  # noqa: S310
            shutil.copyfileobj(response, out)
        if not zipfile.is_zipfile(archive):
            raise DownloadError(f"the download for {dataset.kaggle_slug} is not a zip archive. {README_HINT}")
        written = []
        with zipfile.ZipFile(archive) as zf:
            members = {Path(name).name: name for name in zf.namelist() if not name.endswith("/")}
            missing = sorted(set(wanted) - set(members))
            if missing:
                raise DownloadError(f"{dataset.kaggle_slug} archive lacks {missing}; the dataset layout changed. "
                                    f"{README_HINT}")
            for base, relative in sorted(wanted.items()):
                target = data_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(members[base]) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                written.append(target)
    return written
