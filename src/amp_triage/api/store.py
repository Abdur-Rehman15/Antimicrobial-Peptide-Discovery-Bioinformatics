"""Where runs live: a folder per run, so results survive a server restart.

    runs/<id>/meta.json       status, progress, counts, options, error
    runs/<id>/table.csv       the ranked candidates of the run (pipeline OUTPUT_COLUMNS)
    runs/<id>/proteins.json   {accession: {"name": ..., "length": ..., "sequence": ...}}

Progress changes often, so it is kept in memory and written to disk only when the status
changes. Precomputed runs (scripts/precompute_run.py) use the same folders and appear in the
same list. All methods are safe to call from several threads.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

RUN_ID = re.compile(r"^[0-9a-f]{12}$")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._meta: dict[str, dict] = {}
        for folder in sorted(self.root.iterdir()):
            meta_file = folder / "meta.json"
            if folder.is_dir() and RUN_ID.match(folder.name) and meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta["status"] in ("queued", "running"):  # the server died mid-run
                    meta.update(status="failed", error="The server restarted during this run.",
                                message="interrupted")
                    meta_file.write_text(json.dumps(meta, indent=1), encoding="utf-8")
                self._meta[meta["id"]] = meta

    # ---- metadata ------------------------------------------------------------------------

    def create(self, label: str, kind: str, options: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        meta = {"id": run_id, "label": label, "kind": kind, "status": "queued", "progress": 0.0,
                "message": "waiting for a free worker", "created_at": now(), "started_at": None,
                "finished_at": None, "n_proteins": None, "n_residues": None, "n_windows": None,
                "seconds": None, "error": None, "notes": [], "options": options}
        with self._lock:
            (self.root / run_id).mkdir(parents=True)
            self._meta[run_id] = meta
            self._write(run_id)
        return run_id

    def _write(self, run_id: str) -> None:
        path = self.root / run_id / "meta.json"
        path.write_text(json.dumps(self._meta[run_id], indent=1), encoding="utf-8")

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            meta = self._meta.get(run_id)
            return dict(meta) if meta else None

    def update(self, run_id: str, persist: bool = False, **fields) -> None:
        with self._lock:
            self._meta[run_id].update(fields)
            if persist:
                self._write(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            return sorted((dict(m) for m in self._meta.values()),
                          key=lambda m: m["created_at"], reverse=True)

    def delete(self, run_id: str) -> bool:
        with self._lock:
            if run_id not in self._meta:
                return False
            del self._meta[run_id]
            shutil.rmtree(self.root / run_id, ignore_errors=True)
            return True

    # ---- results -------------------------------------------------------------------------

    def save_result(self, run_id: str, table: pd.DataFrame, proteins: dict) -> None:
        folder = self.root / run_id
        table.to_csv(folder / "table.csv", index=False)
        (folder / "proteins.json").write_text(json.dumps(proteins), encoding="utf-8")

    def load_table(self, run_id: str) -> pd.DataFrame:
        return pd.read_csv(self.root / run_id / "table.csv", keep_default_na=True)

    def load_proteins(self, run_id: str) -> dict:
        return json.loads((self.root / run_id / "proteins.json").read_text(encoding="utf-8"))
