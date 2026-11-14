"""The FastAPI application. `create_app()` builds it; `api/main.py` exposes the default one.

Endpoints (all under /api, interactive docs at /docs)
    GET    /health
    GET    /api/info                                about the models, the limits, how to read scores
    GET    /api/organisms?q=...                     organisms with reviewed UniProt proteins
    POST   /api/runs                                start a run (FASTA / accessions / organism)
    GET    /api/runs                                all runs, newest first (live and precomputed)
    GET    /api/runs/{id}                           status and progress
    DELETE /api/runs/{id}
    GET    /api/runs/{id}/results                   ranked candidates, re-ranked on the fly
    GET    /api/runs/{id}/results.csv               the same table as a CSV download
    GET    /api/runs/{id}/candidate                 one candidate: features, alignment, notes
    GET    /api/runs/{id}/proteins[/{accession}]    proteins of the run and where candidates sit

Results are re-ranked from the saved shortlist for every request (weights, assumed rarity of
AMPs, filters), so moving a slider never triggers a rescan.
"""

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from amp_triage import config
from amp_triage.alignment import smith_waterman
from amp_triage.api.jobs import InputError, JobManager, Limits
from amp_triage.api.schemas import Organism, RunCreated, RunRequest, RunStatus
from amp_triage.api.store import RunStore
from amp_triage.api.uniprot import UniProtClient, UniProtError
from amp_triage.features.descriptors import descriptors
from amp_triage.models.calibration import ActivityCalibration
from amp_triage.pipeline import (
    DEFAULT_PREVALENCE,
    Models,
    RankSettings,
    rank_candidates,
    with_prevalence,
)
from amp_triage.pipeline.run import OUTPUT_COLUMNS

SHOWN_FEATURES = [
    "length", "net_charge", "charge_density", "isoelectric_point", "hydrophobic_fraction",
    "mean_hydrophobicity", "gravy", "hydrophobic_moment_helix", "aliphatic_index",
    "boman_index", "frac_positive", "frac_negative", "frac_aromatic",
]  # fmt: skip
SCORE_CAVEAT = (
    "Activity and hemolysis numbers are model scores, calibrated as far as the data allows. "
    "The activity number assumes that {rarity} of all windows are real AMPs, which is a guess; "
    "read it as an ordering, not as a chance. The hemolysis number is only roughly calibrated "
    "(use the low / medium / high band)."
)


def hemolysis_band(risk: float) -> str:
    return "low" if risk < 1 / 3 else "medium" if risk < 2 / 3 else "high"


@dataclass
class ViewParams:
    """How the saved shortlist is re-ranked and filtered for one request."""

    activity_weight: float = 1.0
    safety_weight: float = 1.0
    novelty_weight: float = 1.0
    prevalence: float = DEFAULT_PREVALENCE
    min_activity: float | None = None
    max_hemolysis: float | None = None
    hide_known: bool = False
    novelty: str | None = None  # comma-separated classes to keep
    min_length: int | None = None
    max_length: int | None = None
    accession: str | None = None


def view_params(
    activity_weight: float = Query(1.0, ge=0, le=5, description="exponent of activity"),
    safety_weight: float = Query(1.0, ge=0, le=5, description="exponent of (1 - hemolysis risk)"),
    novelty_weight: float = Query(1.0, ge=0, le=5, description="exponent of the novelty factor"),
    prevalence: float = Query(DEFAULT_PREVALENCE, gt=0, lt=0.5,
                              description="assumed share of windows that are real AMPs"),
    min_activity: float | None = Query(None, ge=0, le=1),
    max_hemolysis: float | None = Query(None, ge=0, le=1),
    hide_known: bool = False,
    novelty: str | None = Query(None, description="e.g. 'novel,related'"),
    min_length: int | None = Query(None, ge=1),
    max_length: int | None = Query(None, le=500),
    accession: str | None = None,
) -> ViewParams:
    return ViewParams(activity_weight, safety_weight, novelty_weight, prevalence, min_activity,
                      max_hemolysis, hide_known, novelty, min_length, max_length, accession)


def ranked_view(table: pd.DataFrame, calibration, p: ViewParams) -> pd.DataFrame:
    """The shortlist with the calibrated activity for `p.prevalence`, filtered and re-ranked."""
    t = with_prevalence(table, calibration, p.prevalence)
    if p.min_activity is not None:
        t = t[t.activity >= p.min_activity]
    if p.novelty:
        t = t[t.novelty_class.isin([c.strip() for c in p.novelty.split(",")])]
    if p.min_length is not None:
        t = t[t.length >= p.min_length]
    if p.max_length is not None:
        t = t[t.length <= p.max_length]
    if p.accession:
        t = t[t.accession == p.accession]
    out = rank_candidates(
        t, RankSettings(p.activity_weight, p.safety_weight, p.novelty_weight),
        max_hemolysis=p.max_hemolysis, hide_known=p.hide_known,
    )
    out.insert(out.columns.get_loc("hemolysis_risk") + 1, "hemolysis_band",
               out.hemolysis_risk.map(hemolysis_band))
    return out


def records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe rows (NaN becomes null, numpy numbers become plain numbers)."""
    return json.loads(df.to_json(orient="records"))


def candidate_notes(row: pd.Series, prevalence: float) -> list[str]:
    notes = []
    if row.novelty_class == "known":
        notes.append(f"Identical to, or a piece of, a known AMP ({row.closest_id or 'database'}):"
                     " this would be a rediscovery, not a new peptide.")
    elif row.novelty_class == "related":
        notes.append(f"Related to a known AMP (similarity {row.max_similarity:.2f} to "
                     f"{row.closest_id or 'a database entry'}): probably the same family.")
    else:
        notes.append("Not clearly similar to any known AMP in the reference of 17,492.")
    band = hemolysis_band(row.hemolysis_risk)
    notes.append(f"Hemolysis risk band: {band}.")
    if row.length <= 12:
        notes.append("Short candidate (8-12 residues). Isolated short hot spots are over-"
                     "represented near the top of the list; treat with extra caution.")
    notes.append(SCORE_CAVEAT.format(rarity=f"1 in {round(1 / prevalence):,}"))
    return notes


def create_app(
    models_provider: Callable[[], Models] | None = None,
    store: RunStore | None = None,
    uniprot=None,
    limits: Limits | None = None,
    executor=None,
    calibration=None,
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AMP Triage",
        version="0.2.0",
        description="Find hidden antimicrobial peptides in proteins, then rank them.",
    )
    origins = os.environ.get(
        "AMP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"],
                       allow_headers=["*"])

    store = store or RunStore(config.CACHE_DIR / "runs")
    uniprot = uniprot or UniProtClient()
    limits = limits or Limits()

    if models_provider is None:
        cache: dict = {}
        lock = threading.Lock()

        def models_provider() -> Models:  # loaded once, on the first run
            with lock:
                if "models" not in cache:
                    cache["models"] = Models.load()
                return cache["models"]

    if calibration is None:
        path = config.MODELS_DIR / "activity_calibration.json"
        calibration = ActivityCalibration.from_json(path) if path.exists() else (
            ActivityCalibration())
    jobs = JobManager(store, models_provider, uniprot, limits, executor)
    app.state.store, app.state.jobs = store, jobs

    # ---- helpers -------------------------------------------------------------------------

    def get_meta(run_id: str) -> dict:
        meta = store.get(run_id)
        if meta is None:
            raise HTTPException(404, f"No run with id {run_id!r}.")
        return meta

    def finished_table(run_id: str) -> pd.DataFrame:
        meta = get_meta(run_id)
        if meta["status"] == "failed":
            raise HTTPException(409, f"This run failed: {meta['error']}")
        if meta["status"] != "done":
            raise HTTPException(409, f"This run is {meta['status']} ({meta['progress']:.0%}).")
        return store.load_table(run_id)

    # ---- general -------------------------------------------------------------------------

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/info")
    def info() -> dict:
        def report(name: str):
            path = config.ROOT / "reports" / name
            return json.loads(path.read_text()) if path.exists() else None

        activity = report("activity_final_test.json")
        hemolysis = report("hemolysis_final_test.json")
        return {
            "default_prevalence": DEFAULT_PREVALENCE,
            "limits": {"max_residues": limits.max_residues, "max_proteins": limits.max_proteins,
                       "scan_speed_windows_per_second": 23000},
            "rank_formula": "activity ^ a  x  (1 - hemolysis risk) ^ s  x  novelty factor ^ n",
            "novelty_labels": {"known": "identical to / part of a known AMP",
                               "related": "similar to a known AMP, above chance",
                               "novel": "not clearly similar to any known AMP"},
            "activity_test": activity and activity["test"],
            "hemolysis_test": hemolysis and hemolysis["test"],
            "caveat": SCORE_CAVEAT.format(rarity="1 in 1,000"),
        }

    @app.get("/api/organisms", response_model=list[Organism])
    def organisms(q: str = Query(..., min_length=2)) -> list[dict]:
        try:
            return uniprot.search_organisms(q)
        except UniProtError as exc:
            raise HTTPException(503, str(exc)) from exc

    # ---- runs ----------------------------------------------------------------------------

    @app.post("/api/runs", response_model=RunCreated, status_code=202)
    def create_run(request: Request, body: RunRequest) -> RunCreated:
        try:
            run_id = jobs.submit(body)
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        return RunCreated(id=run_id, status_url=str(request.url_for("run_status", run_id=run_id)))

    @app.get("/api/runs", response_model=list[RunStatus])
    def list_runs() -> list[dict]:
        return store.list()

    @app.get("/api/runs/{run_id}", response_model=RunStatus)
    def run_status(run_id: str) -> dict:
        return get_meta(run_id)

    @app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(run_id: str) -> Response:
        if get_meta(run_id)["status"] == "running":
            raise HTTPException(409, "A running job cannot be deleted.")
        store.delete(run_id)
        return Response(status_code=204)

    # ---- results -------------------------------------------------------------------------

    @app.get("/api/runs/{run_id}/results")
    def results(run_id: str, view: ViewParams = Depends(view_params),
                limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
        table = ranked_view(finished_table(run_id), calibration, view)
        page = table.iloc[offset : offset + limit]
        return {"total": len(table), "offset": offset, "limit": limit,
                "prevalence": view.prevalence,
                "weights": {"activity": view.activity_weight, "safety": view.safety_weight,
                            "novelty": view.novelty_weight},
                "rows": records(page)}

    @app.get("/api/runs/{run_id}/results.csv")
    def results_csv(run_id: str, view: ViewParams = Depends(view_params),
                    limit: int = Query(1000, ge=1, le=10000)) -> Response:
        table = ranked_view(finished_table(run_id), calibration, view).head(limit)
        columns = [c for c in OUTPUT_COLUMNS if c in table.columns]
        columns.insert(columns.index("hemolysis_risk") + 1, "hemolysis_band")
        return Response(
            table[columns].to_csv(index=False), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="amp_candidates_{run_id}.csv"'},
        )

    @app.get("/api/runs/{run_id}/candidate")
    def candidate(run_id: str, accession: str, start: int, end: int,
                  prevalence: float = Query(DEFAULT_PREVALENCE, gt=0, lt=0.5)) -> dict:
        table = ranked_view(finished_table(run_id), calibration,
                            ViewParams(prevalence=prevalence))
        hit = table[(table.accession == accession) & (table.start == start) & (table.end == end)]
        if hit.empty:
            raise HTTPException(404, "No such candidate in this run.")
        row = hit.iloc[0]
        features = descriptors(row.sequence)
        proteins = store.load_proteins(run_id)
        protein = proteins.get(accession, {})
        seq = protein.get("sequence", "")
        alignment = None
        if isinstance(row.closest_known, str) and row.closest_known:
            aln = smith_waterman(row.sequence, row.closest_known)
            alignment = {
                "known_sequence": row.closest_known, "known_id": row.closest_id,
                "score": aln.score, "identity": aln.identity, "similarity": aln.similarity,
                "gaps": aln.gaps, "query_start": aln.query_start, "target_start": aln.target_start,
                "aligned_query": aln.aligned_query, "aligned_target": aln.aligned_target,
                "midline": aln.midline,
                "text": aln.format(query_name="candidate", target_name="known AMP"),
            }
        return {
            "candidate": records(hit)[0],
            "features": {k: features[k] for k in SHOWN_FEATURES},
            "composition": {k[4:]: v for k, v in features.items() if k.startswith("aac_")},
            "alignment": alignment,
            "protein": {"accession": accession, "name": protein.get("name", ""),
                        "length": protein.get("length"), "sequence": seq,
                        "context": seq[max(start - 11, 0) : end + 10]},
            "notes": candidate_notes(row, prevalence),
        }

    @app.get("/api/runs/{run_id}/proteins")
    def run_proteins(run_id: str) -> list[dict]:
        table = finished_table(run_id)
        proteins = store.load_proteins(run_id)
        per = table.groupby("accession").agg(n_candidates=("rank", "size"),
                                             best_activity_score=("activity_score", "max"))
        return [{"accession": acc, "name": p["name"], "length": p["length"],
                 "n_candidates": int(per.n_candidates.get(acc, 0)),
                 "best_activity_score": float(per.best_activity_score.get(acc, 0.0))}
                for acc, p in proteins.items()]

    @app.get("/api/runs/{run_id}/proteins/{accession}")
    def run_protein(run_id: str, accession: str, view: ViewParams = Depends(view_params)) -> dict:
        proteins = store.load_proteins(run_id) if finished_table(run_id) is not None else {}
        if accession not in proteins:
            raise HTTPException(404, "No such protein in this run.")
        table = ranked_view(finished_table(run_id), calibration, view)
        mine = table[table.accession == accession]
        return {"accession": accession, **proteins[accession],
                "candidates": records(mine[["rank", "start", "end", "length", "sequence",
                                            "activity", "hemolysis_risk", "hemolysis_band",
                                            "novelty_class", "rank_score"]])}

    # ---- the web dashboard (frontend/dist, built with `npm run build`) -----------------------
    dist = (static_dir if static_dir is not None else config.ROOT / "frontend" / "dist").resolve()
    if (dist / "index.html").exists():

        @app.get("/{path:path}", include_in_schema=False)
        def dashboard(path: str) -> FileResponse:
            """Files of the built dashboard; any other address gets index.html, so that a
            deep link such as /runs/abc123 opens the right page. API paths stay 404."""
            if path.startswith("api/") or path == "health":
                raise HTTPException(404, "Not found.")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def default_store_path() -> Path:
    return config.CACHE_DIR / "runs"
