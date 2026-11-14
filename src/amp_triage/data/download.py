"""Download helpers. Every file fetched is recorded in data/MANIFEST.json for provenance."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from amp_triage import config

MANIFEST_PATH = config.DATA_DIR / "MANIFEST.json"
USER_AGENT = "amp-triage-student-project/0.1 (university bioinformatics course)"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_in_manifest(path: Path, url: str, source: str, note: str = "") -> dict:
    """Add or replace the entry for `path` in the manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else []
    rel = path.resolve().relative_to(config.ROOT).as_posix()
    entry = {
        "file": rel,
        "source": source,
        "url": url,
        "downloaded_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "note": note,
    }
    manifest = [m for m in manifest if m["file"] != rel] + [entry]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    return entry


def get_with_retry(url: str, *, params=None, timeout=120, tries=5, stream=False):
    """GET with exponential back-off. Raises after `tries` failures."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, tries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout, stream=stream)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt == tries:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def download_file(url: str, dest: Path, source: str, note: str = "", **kwargs) -> dict:
    """Download `url` to `dest` (streamed) and record it in the manifest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = get_with_retry(url, stream=True, **kwargs)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    return record_in_manifest(dest, url, source, note)
