"""A small client for the public UniProt REST service (https://rest.uniprot.org).

Only reviewed (Swiss-Prot) entries are used: they are curated, a model organism has a few
thousand of them, and a full proteome that includes the unreviewed TrEMBL entries can be a
hundred thousand proteins (mouse: 228,903), far more than a scan can handle.

Three calls:
  search_organisms  organisms that have reviewed proteins matching a name, with exact counts;
  organism_info     name and reviewed protein count of one taxon id;
  fetch_organism_fasta / fetch_accessions_fasta   protein sequences as FASTA text.

Every network failure becomes a `UniProtError` with a readable message, so the API can pass it
on to the user instead of crashing.
"""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

BASE_URL = "https://rest.uniprot.org"
USER_AGENT = "amp-triage-student-project"
# UniProt's official accession format (https://www.uniprot.org/help/accession_numbers)
ACCESSION = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})(-\d+)?$"
)
MAX_ORGANISM_PROTEINS = 60_000  # refuse to download more than this many reviewed proteins


class UniProtError(RuntimeError):
    """UniProt could not be reached, rejected the request, or returned something unexpected."""


class UniProtClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 60.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get(self, path: str, params: dict, stream: bool = False):
        try:
            response = self.session.get(
                f"{BASE_URL}{path}",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
                stream=stream,
            )
        except requests.RequestException as exc:
            raise UniProtError(f"Could not reach UniProt ({type(exc).__name__}). "
                               "Check the internet connection.") from exc
        if response.status_code != 200:
            raise UniProtError(f"UniProt answered with HTTP {response.status_code}.")
        return response

    # ---- organisms -----------------------------------------------------------------------

    def organism_info(self, taxon_id: int) -> dict:
        """{'taxon_id', 'name', 'reviewed_proteins'} for one organism id."""
        response = self._get(
            "/uniprotkb/search",
            {"query": f"organism_id:{int(taxon_id)} AND reviewed:true", "size": 1,
             "format": "tsv", "fields": "organism_name"},
        )
        count = int(response.headers.get("x-total-results", 0))
        lines = response.text.strip().split("\n")
        name = lines[1].strip() if len(lines) > 1 else ""
        return {"taxon_id": int(taxon_id), "name": name, "reviewed_proteins": count}

    def search_organisms(self, query: str, limit: int = 8) -> list[dict]:
        """Organisms with reviewed proteins that match `query`, most proteins first."""
        query = query.strip().replace('"', "")
        if len(query) < 2:
            raise UniProtError("Type at least 2 letters of the organism name.")
        response = self._get(
            "/uniprotkb/search",
            {"query": f'(organism_name:"{query}") AND reviewed:true', "size": 500,
             "format": "tsv", "fields": "organism_id,organism_name"},
        )
        rows = [line.split("\t") for line in response.text.strip().split("\n")[1:]]
        seen = Counter((r[0], r[1]) for r in rows if len(r) == 2)
        top = [taxon for taxon, _ in seen.most_common(limit)]
        with ThreadPoolExecutor(max_workers=min(4, max(len(top), 1))) as pool:
            infos = list(pool.map(lambda t: self.organism_info(int(t[0])), top))
        infos = [i for i in infos if i["reviewed_proteins"] > 0]
        return sorted(infos, key=lambda i: -i["reviewed_proteins"])

    # ---- sequences -----------------------------------------------------------------------

    def fetch_organism_fasta(self, taxon_id: int) -> str:
        """All reviewed proteins of one organism as FASTA text."""
        info = self.organism_info(taxon_id)
        if info["reviewed_proteins"] == 0:
            raise UniProtError(f"UniProt has no reviewed proteins for taxon {taxon_id}.")
        if info["reviewed_proteins"] > MAX_ORGANISM_PROTEINS:
            raise UniProtError(
                f"{info['name']} has {info['reviewed_proteins']:,} reviewed proteins; "
                f"the limit is {MAX_ORGANISM_PROTEINS:,}."
            )
        response = self._get(
            "/uniprotkb/stream",
            {"query": f"organism_id:{int(taxon_id)} AND reviewed:true", "format": "fasta"},
        )
        return response.text

    def fetch_accessions_fasta(self, accessions: list[str]) -> str:
        """FASTA text for UniProt accessions (e.g. P69905)."""
        cleaned = [a.strip().upper() for a in accessions if a.strip()]
        bad = [a for a in cleaned if not ACCESSION.match(a)]
        if bad:
            raise UniProtError(f"Not a UniProt accession: {', '.join(bad[:5])}")
        if not cleaned:
            raise UniProtError("No accessions given.")
        parts = []
        for i in range(0, len(cleaned), 100):
            chunk = cleaned[i : i + 100]
            response = self._get(
                "/uniprotkb/accessions", {"accessions": ",".join(chunk), "format": "fasta"}
            )
            parts.append(response.text)
        text = "".join(parts)
        found = {line.split("|")[1] for line in text.split("\n") if line.startswith(">")
                 and "|" in line}
        missing = [a for a in cleaned if a.split("-")[0] not in found and a not in found]
        if missing and not found:
            raise UniProtError(f"UniProt found none of: {', '.join(missing[:5])}")
        return text
