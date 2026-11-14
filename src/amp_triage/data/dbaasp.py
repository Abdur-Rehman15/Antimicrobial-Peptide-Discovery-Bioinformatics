"""DBAASP list download (sequences only).

DBAASP terms (https://dbaasp.org/terms-and-conditions) allow downloading and reuse with
attribution. Acknowledge DBAASP as a source in the report and cite the DBAASP v3 paper.

The list view (/peptides) gives name, sequence, terminal modifications, and monomers but NOT
activity data. Activity (MIC) and hemolysis measurements are only in the per-peptide detail
view (/peptides/{id}), which is slow, so it is fetched separately and only if needed.

Each page is saved to its own file as soon as it arrives, so an interrupted run resumes
where it stopped. A few pages are fetched in parallel; the server is slow, so keep the
worker count small.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from amp_triage import config
from amp_triage.data.download import get_with_retry, record_in_manifest

LIST_URL = "https://dbaasp.org/peptides"
PAGE_SIZE = 500  # limit=2000 is rejected by the server
WORKERS = 4


def _page_path(pages_dir: Path, offset: int) -> Path:
    return pages_dir / f"offset_{offset:06d}.json"


def _fetch_page(offset: int, pages_dir: Path) -> int:
    resp = get_with_retry(
        LIST_URL, params={"limit": PAGE_SIZE, "offset": offset}, timeout=240, tries=8
    )
    page = resp.json()
    path = _page_path(pages_dir, offset)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(page))
    tmp.replace(path)  # atomic: a page file is either complete or absent
    return len(page["data"])


def download_list(dest: Path | None = None, workers: int = WORKERS) -> Path:
    dest = dest or (config.RAW_DIR / "dbaasp" / "peptides_list.json")
    pages_dir = dest.parent / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # The first page tells us the total; reuse it if already saved.
    first = _page_path(pages_dir, 0)
    if not first.exists():
        _fetch_page(0, pages_dir)
    total = json.loads(first.read_text())["totalCount"]

    todo = [o for o in range(0, total, PAGE_SIZE) if not _page_path(pages_dir, o).exists()]
    print(f"dbaasp list: total={total}, pages to fetch={len(todo)}", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_page, o, pages_dir): o for o in todo}
        for fut in as_completed(futures):
            fut.result()  # raises if a page failed after all retries
            done += 1
            print(f"dbaasp list: {done}/{len(todo)} pages", flush=True)

    records: list[dict] = []
    for offset in range(0, total, PAGE_SIZE):
        records.extend(json.loads(_page_path(pages_dir, offset).read_text())["data"])

    ids = [r["id"] for r in records]
    if len(records) != total or len(set(ids)) != len(ids):
        raise RuntimeError(f"Got {len(records)} records ({len(set(ids))} unique), expected {total}")

    dest.write_text(json.dumps({"totalCount": total, "data": records}))
    record_in_manifest(dest, LIST_URL, "DBAASP", note=f"list view, {len(records)} entries")
    return dest


if __name__ == "__main__":
    download_list()
