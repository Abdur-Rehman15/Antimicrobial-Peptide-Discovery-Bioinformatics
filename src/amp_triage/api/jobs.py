"""Turning a request into a finished run: read the proteins, check the limits, run the pipeline.

The scan is the expensive part (about 23,000 windows per second on one machine, so ~1 second per
protein of 500 residues), and the model already uses every CPU core. Jobs therefore run one at
a time in a background worker; the others wait in the queue. To keep a live run short, a run
may hold at most `Limits.max_residues` residues (default 100,000, about 4 minutes). A whole
proteome is an offline job: scripts/precompute_run.py runs it once and stores the result as a
"precomputed" run that the API serves instantly.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from io import StringIO

from Bio import SeqIO

from amp_triage import config
from amp_triage.api.schemas import AccessionSource, FastaSource, OrganismSource, RunRequest
from amp_triage.api.store import RunStore, now
from amp_triage.api.uniprot import UniProtError
from amp_triage.pipeline import Models, run_pipeline

log = logging.getLogger("amp_triage.api")
LETTERS = re.compile(r"^[A-Za-z]+$")


class InputError(ValueError):
    """The proteins given are not usable (empty, wrong format, or too big)."""


@dataclass(frozen=True)
class Limits:
    max_residues: int = int(os.environ.get("AMP_MAX_RESIDUES", 100_000))
    max_proteins: int = 5_000
    min_length: int = config.MIN_PEPTIDE_LEN


@dataclass
class Parsed:
    accessions: list[str]
    sequences: list[str]
    names: list[str]
    notes: list[str] = field(default_factory=list)
    organism: str | None = None


def parse_fasta(text: str, limits: Limits) -> Parsed:
    """Proteins from FASTA text. UniProt headers (sp|P12345|NAME ...) give the accession."""
    accs, seqs, names, notes = [], [], [], []
    seen: dict[str, int] = {}
    short, renamed = 0, 0
    organism = None
    try:
        records = list(SeqIO.parse(StringIO(text), "fasta"))
    except Exception as exc:  # Biopython raises several kinds of errors on malformed input
        raise InputError(f"Could not read the FASTA text: {exc}") from exc
    for rec in records:
        sequence = "".join(str(rec.seq).split()).rstrip("*").upper()
        if not sequence:
            continue
        if not LETTERS.match(sequence):
            raise InputError(
                f"Protein {rec.id!r} has characters that are not letters; this does not look "
                "like a protein sequence."
            )
        if len(sequence) < limits.min_length:
            short += 1
            continue
        parts = rec.id.split("|")
        acc = parts[1] if len(parts) >= 2 and parts[0] in ("sp", "tr") else parts[0]
        if acc in seen:
            seen[acc] += 1
            acc = f"{acc}_{seen[acc]}"
            renamed += 1
        else:
            seen[acc] = 1
        accs.append(acc)
        seqs.append(sequence)
        description = rec.description.split(" ", 1)[1] if " " in rec.description else ""
        names.append(description.split(" OS=")[0])
        if organism is None and " OS=" in description:
            organism = description.split(" OS=")[1].split(" OX=")[0]
    if short:
        notes.append(f"{short} protein(s) shorter than {limits.min_length} residues were skipped.")
    if renamed:
        notes.append(f"{renamed} repeated protein id(s) were renamed with a suffix.")
    if not accs:
        raise InputError(
            f"No protein of at least {limits.min_length} residues was found in the input."
        )
    return Parsed(accs, seqs, names, notes, organism)


def check_limits(parsed: Parsed, limits: Limits) -> None:
    residues = sum(map(len, parsed.sequences))
    if len(parsed.accessions) > limits.max_proteins:
        raise InputError(f"{len(parsed.accessions):,} proteins; the limit for one run is "
                         f"{limits.max_proteins:,}.")
    if residues > limits.max_residues:
        minutes = residues * 43 / 23_000 / 60
        raise InputError(
            f"{residues:,} residues; the limit for one live run is {limits.max_residues:,} "
            f"(this input would need about {minutes:.0f} minutes). Use fewer proteins, or "
            "scan it offline with scripts/precompute_run.py."
        )


def sample_proteins(parsed: Parsed, max_proteins: int, limits: Limits, seed: int) -> Parsed:
    """A random sample of proteins within the protein and residue limits."""
    order = list(range(len(parsed.accessions)))
    random.Random(seed).shuffle(order)
    picked, residues = [], 0
    for i in order:
        n = len(parsed.sequences[i])
        if len(picked) < max_proteins and residues + n <= limits.max_residues:
            picked.append(i)
            residues += n
    if not picked:
        raise InputError("None of the proteins fits the residue limit of one run.")
    picked.sort()
    notes = parsed.notes + [
        f"A random sample of {len(picked)} of {len(order):,} reviewed proteins was scanned "
        f"({residues:,} residues)."
    ]
    return Parsed([parsed.accessions[i] for i in picked], [parsed.sequences[i] for i in picked],
                  [parsed.names[i] for i in picked], notes, parsed.organism)


class SyncExecutor(Executor):
    """Runs a job immediately in the caller's thread (tests and the precompute script)."""

    def submit(self, fn, /, *args, **kwargs):
        from concurrent.futures import Future

        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirror what a real executor stores
            future.set_exception(exc)
        return future


class JobManager:
    def __init__(
        self,
        store: RunStore,
        models_provider: Callable[[], Models],
        uniprot,
        limits: Limits | None = None,
        executor: Executor | None = None,
    ):
        self.store = store
        self.models_provider = models_provider
        self.uniprot = uniprot
        self.limits = limits or Limits()
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan")

    def submit(self, request: RunRequest, kind: str | None = None) -> str:
        """Queue a run and return its id. Raises InputError for pasted FASTA that is unusable."""
        source = request.source
        parsed = None
        if isinstance(source, FastaSource):
            parsed = parse_fasta(source.text, self.limits)
            check_limits(parsed, self.limits)
        kind = kind or source.type
        label = request.label or {
            "fasta": f"Pasted FASTA ({len(parsed.accessions)} proteins)" if parsed else "FASTA",
            "accessions": f"{len(getattr(source, 'accessions', []))} UniProt accession(s)",
            "organism": f"Organism {getattr(source, 'taxon_id', '')}",
        }[source.type]
        run_id = self.store.create(label, kind, request.options.model_dump())
        self.executor.submit(self._execute, run_id, request, parsed, request.label is None)
        return run_id

    # ---- the job itself ------------------------------------------------------------------

    def _resolve(self, source) -> Parsed:
        if isinstance(source, AccessionSource):
            text = self.uniprot.fetch_accessions_fasta(source.accessions)
            parsed = parse_fasta(text, self.limits)
            check_limits(parsed, self.limits)
            return parsed
        if isinstance(source, OrganismSource):
            text = self.uniprot.fetch_organism_fasta(source.taxon_id)
            return sample_proteins(
                parse_fasta(text, self.limits), source.max_proteins, self.limits, source.seed
            )
        raise InputError("Unknown source.")

    def _execute(self, run_id: str, request: RunRequest, parsed: Parsed | None,
                 auto_label: bool) -> None:
        store, started = self.store, time.time()
        try:
            store.update(run_id, status="running", started_at=now(), persist=True,
                         message="loading models")
            models = self.models_provider()
            if parsed is None:
                store.update(run_id, message="fetching proteins from UniProt")
                parsed = self._resolve(request.source)
            residues = sum(map(len, parsed.sequences))
            label_update = {}
            if auto_label and parsed.organism:
                label_update["label"] = (
                    f"{parsed.organism} ({len(parsed.accessions)} proteins)"
                    if request.source.type == "organism" else store.get(run_id)["label"]
                )
            store.update(run_id, n_proteins=len(parsed.accessions), n_residues=residues,
                         notes=parsed.notes, message="scanning", **label_update)
            opts = request.options
            result = run_pipeline(
                parsed.accessions, parsed.sequences, models, top_n=opts.top_n,
                max_overlap=opts.max_overlap, prevalence=opts.prevalence,
                progress=lambda fraction, message: store.update(
                    run_id, progress=round(float(fraction), 4), message=message),
            )
            proteins = {
                acc: {"name": name, "length": len(seq), "sequence": seq}
                for acc, name, seq in zip(parsed.accessions, parsed.names, parsed.sequences,
                                          strict=True)
            }
            store.save_result(run_id, result.table, proteins)
            store.update(run_id, status="done", progress=1.0, message="done",
                         finished_at=now(), n_windows=result.n_windows,
                         seconds=round(time.time() - started, 1), persist=True)
        except (InputError, UniProtError) as exc:
            store.update(run_id, status="failed", error=str(exc), message="failed",
                         finished_at=now(), persist=True)
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            log.exception("run %s failed", run_id)
            store.update(run_id, status="failed", message="failed", finished_at=now(),
                         error=f"Unexpected error ({type(exc).__name__}): {exc}", persist=True)
