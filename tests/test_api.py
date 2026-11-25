import json
import time

import numpy as np
import pytest
import requests
from fastapi.testclient import TestClient

from amp_triage.api.app import create_app
from amp_triage.api.jobs import Limits, SyncExecutor
from amp_triage.api.store import RunStore
from amp_triage.api.uniprot import UniProtClient, UniProtError
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.calibration import ActivityCalibration, LogisticRecalibrator
from amp_triage.novelty.search import NoveltyIndex
from amp_triage.pipeline import Models

COL = {name: k for k, name in enumerate(FEATURE_NAMES)}
KNOWN = "GIGKFLHSAKKFGKFGKAFVGEIMNS"
AA = list("ACDEFGHIKLMNPQRSTVWY")


class FakeActivity:
    def predict_proba(self, X):
        p = 1.0 / (1.0 + np.exp(-0.5 * X[:, COL["net_charge"]]))
        return np.column_stack([1.0 - p, p])


class FakeHemolysis:
    def predict_proba(self, X):
        p = X[:, COL["hydrophobic_fraction"]]
        return np.column_stack([1.0 - p, p])


def protein(seed, n=120):
    return "".join(np.random.default_rng(seed).choice(AA, n))


def fasta(*records):
    """records: (accession, sequence[, organism])"""
    out = []
    for rec in records:
        acc, seq = rec[0], rec[1]
        organism = rec[2] if len(rec) > 2 else "Homo sapiens"
        out.append(f">sp|{acc}|{acc}_TEST Test protein {acc} OS={organism} OX=9606 PE=1 SV=1")
        out.append(seq)
    return "\n".join(out) + "\n"


class FakeUniProt:
    def __init__(self, text="", fail=None, organisms=None):
        self.text, self.fail, self._organisms = text, fail, organisms or []

    def _check(self):
        if self.fail:
            raise UniProtError(self.fail)

    def search_organisms(self, query):
        self._check()
        return self._organisms

    def fetch_accessions_fasta(self, accessions):
        self._check()
        return self.text

    def fetch_organism_fasta(self, taxon_id):
        self._check()
        return self.text


@pytest.fixture
def models():
    return Models(FakeActivity(), FakeHemolysis(), NoveltyIndex([KNOWN], ids=["KNOWN1"]), 0.8)


def make_client(tmp_path, models, uniprot=None, limits=None, executor=None, calibration=None,
                **extra):
    app = create_app(
        models_provider=lambda: models,
        store=RunStore(tmp_path / "runs"),
        uniprot=uniprot or FakeUniProt(),
        limits=limits or Limits(),
        executor=executor or SyncExecutor(),
        calibration=calibration or ActivityCalibration(),
        **extra,
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path, models):
    return make_client(tmp_path, models)


def start(client, text, **options):
    body = {"source": {"type": "fasta", "text": text}, "options": {"top_n": 30, **options}}
    response = client.post("/api/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()["id"]


TEXT = fasta(("P00001", protein(1, 150)), ("P00002", protein(2, 100)))


# ---- basics --------------------------------------------------------------------------------


def test_health_and_info(client):
    assert client.get("/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert info["default_prevalence"] == 1e-3
    assert info["limits"]["max_residues"] > 0 and "caveat" in info


def test_a_fasta_run_finishes_with_progress_and_counts(client):
    run_id = start(client, TEXT)
    meta = client.get(f"/api/runs/{run_id}").json()
    assert meta["status"] == "done" and meta["progress"] == 1.0
    assert meta["n_proteins"] == 2 and meta["n_residues"] == 250
    assert meta["n_windows"] > 0 and meta["seconds"] is not None
    assert meta["kind"] == "fasta" and "2 proteins" in meta["label"]
    assert [r["id"] for r in client.get("/api/runs").json()] == [run_id]


def test_results_are_ranked_and_have_the_expected_columns(client):
    run_id = start(client, TEXT)
    body = client.get(f"/api/runs/{run_id}/results").json()
    rows = body["rows"]
    # at most top_n=30; fewer when the proteins hold fewer non-overlapping regions
    assert body["total"] == len(rows) and 5 <= len(rows) <= 30
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    scores = [r["rank_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    for key in ("accession", "start", "end", "sequence", "activity", "activity_score",
                "hemolysis_risk", "hemolysis_band", "novelty_class", "closest_known"):
        assert key in rows[0]
    assert rows[0]["hemolysis_band"] in ("low", "medium", "high")
    sequence = {"P00001": protein(1, 150), "P00002": protein(2, 100)}
    for row in rows:
        assert sequence[row["accession"]][row["start"] - 1 : row["end"]] == row["sequence"]


# ---- re-ranking and filters ----------------------------------------------------------------


def test_weights_change_the_ranking_exactly_as_the_formula_says(client):
    run_id = start(client, TEXT)
    a, s, n = 2.0, 3.0, 0.5
    rows = client.get(f"/api/runs/{run_id}/results",
                      params={"activity_weight": a, "safety_weight": s,
                              "novelty_weight": n}).json()["rows"]
    factor = {"known": 0.05, "related": 0.5, "novel": 1.0}
    for r in rows:
        expected = r["activity"] ** a * (1 - r["hemolysis_risk"]) ** s * (
            factor[r["novelty_class"]] ** n)
        assert r["rank_score"] == pytest.approx(expected)
    default = client.get(f"/api/runs/{run_id}/results").json()["rows"]
    assert [r["sequence"] for r in rows] != [r["sequence"] for r in default]


def test_assumed_rarity_changes_the_calibrated_activity_not_the_raw_score(tmp_path, models):
    calibration = ActivityCalibration(LogisticRecalibrator(1.2, 0.5), 0.03)
    client = make_client(tmp_path, models, calibration=calibration)
    run_id = start(client, TEXT)
    common = client.get(f"/api/runs/{run_id}/results", params={"prevalence": 1e-2}).json()["rows"]
    rarer = client.get(f"/api/runs/{run_id}/results", params={"prevalence": 1e-4}).json()["rows"]
    by_key = {(r["accession"], r["start"], r["end"]): r for r in common}
    for r in rarer:
        same = by_key.get((r["accession"], r["start"], r["end"]))
        if same:
            assert r["activity"] < same["activity"]
            assert r["activity_score"] == pytest.approx(same["activity_score"])
            expected = calibration.activity_probability(np.array([r["activity_score"]]), 1e-4)
            assert r["activity"] == pytest.approx(float(expected[0]))


def test_filters_pagination_and_novelty_classes(tmp_path, models):
    client = make_client(tmp_path, models)
    planted = fasta(("P00009", "DE" * 20 + KNOWN + "ED" * 20), ("P00001", protein(1, 150)))
    run_id = start(client, planted)
    url = f"/api/runs/{run_id}/results"
    everything = client.get(url, params={"limit": 1000}).json()
    assert {r["novelty_class"] for r in everything["rows"]} >= {"known"}

    only_known = client.get(url, params={"novelty": "known", "limit": 1000}).json()
    assert only_known["total"] > 0
    assert {r["novelty_class"] for r in only_known["rows"]} == {"known"}
    hidden = client.get(url, params={"hide_known": True, "limit": 1000}).json()
    assert hidden["total"] == everything["total"] - only_known["total"]

    longer = client.get(url, params={"min_length": 20, "max_length": 30, "limit": 1000}).json()
    assert all(20 <= r["length"] <= 30 for r in longer["rows"])
    one = client.get(url, params={"accession": "P00001", "limit": 1000}).json()
    assert {r["accession"] for r in one["rows"]} == {"P00001"}
    safe = client.get(url, params={"max_hemolysis": 0.4, "limit": 1000}).json()
    assert all(r["hemolysis_risk"] <= 0.4 for r in safe["rows"])
    assert [r["rank"] for r in safe["rows"]] == list(range(1, safe["total"] + 1))

    page1 = client.get(url, params={"limit": 5, "offset": 0}).json()["rows"]
    page2 = client.get(url, params={"limit": 5, "offset": 5}).json()["rows"]
    n = min(10, everything["total"])
    assert [r["rank"] for r in page1 + page2] == list(range(1, n + 1))
    assert page1 == everything["rows"][:5]


def test_csv_export_matches_the_json_view(client):
    run_id = start(client, TEXT)
    response = client.get(f"/api/runs/{run_id}/results.csv", params={"safety_weight": 2})
    assert response.headers["content-type"].startswith("text/csv")
    assert f"amp_candidates_{run_id}.csv" in response.headers["content-disposition"]
    lines = response.text.strip().split("\n")
    header = lines[0].split(",")
    assert header[0] == "rank" and "hemolysis_band" in header and "sequence" in header
    rows = client.get(f"/api/runs/{run_id}/results",
                      params={"safety_weight": 2, "limit": 1000}).json()["rows"]
    assert len(lines) - 1 == len(rows)
    assert lines[1].split(",")[header.index("sequence")] == rows[0]["sequence"]


# ---- candidate detail and proteins ---------------------------------------------------------


def test_candidate_detail_has_features_alignment_and_notes(tmp_path, models):
    client = make_client(tmp_path, models)
    run_id = start(client, fasta(("P00009", "DE" * 20 + KNOWN + "ED" * 20)))
    rows = client.get(f"/api/runs/{run_id}/results", params={"novelty": "known"}).json()["rows"]
    top = rows[0]
    detail = client.get(f"/api/runs/{run_id}/candidate",
                        params={"accession": top["accession"], "start": top["start"],
                                "end": top["end"]}).json()
    assert detail["candidate"]["sequence"] == top["sequence"]
    assert set(detail["features"]) >= {"net_charge", "hydrophobic_moment_helix", "length"}
    assert sum(detail["composition"].values()) == pytest.approx(1.0)
    aln = detail["alignment"]
    assert aln["known_id"] == "KNOWN1" and aln["identity"] == pytest.approx(1.0)
    assert len(aln["aligned_query"]) == len(aln["aligned_target"]) == len(aln["midline"])
    assert "candidate" in aln["text"]
    assert detail["protein"]["accession"] == "P00009"
    assert top["sequence"] in detail["protein"]["context"]
    assert any("known AMP" in note for note in detail["notes"])
    assert any("1 in 1,000" in note for note in detail["notes"])


def test_unknown_candidate_is_404(client):
    run_id = start(client, TEXT)
    response = client.get(f"/api/runs/{run_id}/candidate",
                          params={"accession": "NOPE", "start": 1, "end": 10})
    assert response.status_code == 404


def test_protein_endpoints(client):
    run_id = start(client, TEXT)
    proteins = client.get(f"/api/runs/{run_id}/proteins").json()
    assert {p["accession"] for p in proteins} == {"P00001", "P00002"}
    total = client.get(f"/api/runs/{run_id}/results").json()["total"]
    assert sum(p["n_candidates"] for p in proteins) == total
    one = client.get(f"/api/runs/{run_id}/proteins/P00001").json()
    assert one["length"] == 150 and one["sequence"] == protein(1, 150)
    assert all(c["end"] <= 150 for c in one["candidates"])
    assert client.get(f"/api/runs/{run_id}/proteins/NOPE").status_code == 404


# ---- bad input and errors ------------------------------------------------------------------


@pytest.mark.parametrize("text, fragment", [
    ("", "No protein"),
    (">only a header\n", "No protein"),
    (">x\nSHORT\n", "No protein"),
    (">x\n" + "ACDE1234" * 4 + "\n", "not letters"),
])
def test_unusable_fasta_is_rejected_with_a_clear_message(client, text, fragment):
    response = client.post("/api/runs", json={"source": {"type": "fasta", "text": text}})
    assert response.status_code == 422
    assert fragment.lower() in response.json()["detail"].lower()
    assert client.get("/api/runs").json() == []  # no run was created


def test_size_limits(tmp_path, models):
    client = make_client(tmp_path, models, limits=Limits(max_residues=200, max_proteins=2))
    big = fasta(("P00001", protein(1, 150)), ("P00002", protein(2, 100)))
    response = client.post("/api/runs", json={"source": {"type": "fasta", "text": big}})
    assert response.status_code == 422 and "limit" in response.json()["detail"]
    many = fasta(*[(f"P0000{i}", protein(i, 20)) for i in range(3)])
    response = client.post("/api/runs", json={"source": {"type": "fasta", "text": many}})
    assert response.status_code == 422 and "proteins" in response.json()["detail"]


def test_request_validation(client):
    run_id = start(client, TEXT)
    for params in ({"safety_weight": -1}, {"prevalence": 0}, {"prevalence": 0.9}, {"limit": 0},
                   {"activity_weight": 99}):
        assert client.get(f"/api/runs/{run_id}/results", params=params).status_code == 422
    bad = {"source": {"type": "fasta", "text": TEXT}, "options": {"top_n": 0}}
    assert client.post("/api/runs", json=bad).status_code == 422
    assert client.post("/api/runs", json={"source": {"type": "nope"}}).status_code == 422


def test_unknown_run_and_delete(client):
    assert client.get("/api/runs/abcdef012345").status_code == 404
    assert client.get("/api/runs/abcdef012345/results").status_code == 404
    run_id = start(client, TEXT)
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get("/api/runs").json() == []


def test_repeated_protein_ids_are_renamed_with_a_note(client):
    run_id = start(client, fasta(("P00001", protein(1)), ("P00001", protein(2))))
    meta = client.get(f"/api/runs/{run_id}").json()
    assert any("renamed" in note for note in meta["notes"])
    accessions = {p["accession"] for p in client.get(f"/api/runs/{run_id}/proteins").json()}
    assert accessions == {"P00001", "P00001_2"}


# ---- UniProt sources -----------------------------------------------------------------------


def test_run_from_accessions(tmp_path, models):
    uniprot = FakeUniProt(fasta(("P69905", protein(3, 142)), ("P02788", protein(4, 200))))
    client = make_client(tmp_path, models, uniprot=uniprot)
    body = {"source": {"type": "accessions", "accessions": ["P69905", "P02788"]},
            "options": {"top_n": 10}}
    run_id = client.post("/api/runs", json=body).json()["id"]
    meta = client.get(f"/api/runs/{run_id}").json()
    assert meta["status"] == "done" and meta["n_proteins"] == 2 and meta["kind"] == "accessions"


def test_uniprot_failure_marks_the_run_failed_and_blocks_results(tmp_path, models):
    client = make_client(tmp_path, models,
                         uniprot=FakeUniProt(fail="Could not reach UniProt (Timeout)."))
    body = {"source": {"type": "accessions", "accessions": ["P69905"]}}
    run_id = client.post("/api/runs", json=body).json()["id"]
    meta = client.get(f"/api/runs/{run_id}").json()
    assert meta["status"] == "failed" and "Could not reach UniProt" in meta["error"]
    response = client.get(f"/api/runs/{run_id}/results")
    assert response.status_code == 409 and "failed" in response.json()["detail"]


def test_organism_run_samples_proteins_within_the_limits(tmp_path, models):
    text = fasta(*[(f"P{i:05d}", protein(i, 100), "Escherichia coli (strain K12)")
                   for i in range(40)])
    client = make_client(tmp_path, models, uniprot=FakeUniProt(text),
                         limits=Limits(max_residues=1000, max_proteins=5000))
    body = {"source": {"type": "organism", "taxon_id": 83333, "max_proteins": 25, "seed": 1},
            "options": {"top_n": 10}}
    run_id = client.post("/api/runs", json=body).json()["id"]
    meta = client.get(f"/api/runs/{run_id}").json()
    assert meta["status"] == "done"
    assert meta["n_proteins"] == 10 and meta["n_residues"] == 1000  # the residue limit binds
    assert "Escherichia coli" in meta["label"]
    assert any("random sample" in note for note in meta["notes"])
    # the same seed gives the same sample
    again = client.post("/api/runs", json=body).json()["id"]
    first = {p["accession"] for p in client.get(f"/api/runs/{run_id}/proteins").json()}
    second = {p["accession"] for p in client.get(f"/api/runs/{again}/proteins").json()}
    assert first == second


def test_organism_search_endpoint(tmp_path, models):
    found = [{"taxon_id": 83333, "name": "Escherichia coli (strain K12)",
              "reviewed_proteins": 4531}]
    client = make_client(tmp_path, models, uniprot=FakeUniProt(organisms=found))
    assert client.get("/api/organisms", params={"q": "coli"}).json() == found
    assert client.get("/api/organisms", params={"q": "c"}).status_code == 422
    offline = make_client(tmp_path / "b", models, uniprot=FakeUniProt(fail="offline"))
    response = offline.get("/api/organisms", params={"q": "coli"})
    assert response.status_code == 503 and "offline" in response.json()["detail"]


# ---- persistence and the real background worker --------------------------------------------


def test_runs_survive_a_restart_and_interrupted_runs_are_marked_failed(tmp_path, models):
    first = make_client(tmp_path, models)
    run_id = start(first, TEXT)
    total = first.get(f"/api/runs/{run_id}/results").json()["total"]
    stuck = first.app.state.store.create("stuck", "fasta", {})
    first.app.state.store.update(stuck, status="running", persist=True)

    second = make_client(tmp_path, models)  # a new server on the same folder
    assert second.get(f"/api/runs/{run_id}").json()["status"] == "done"
    assert second.get(f"/api/runs/{run_id}/results").json()["total"] == total
    interrupted = second.get(f"/api/runs/{stuck}").json()
    assert interrupted["status"] == "failed" and "restarted" in interrupted["error"]


def test_the_default_background_worker_runs_jobs_one_at_a_time(tmp_path, models):
    app = create_app(models_provider=lambda: models, store=RunStore(tmp_path / "runs"),
                     uniprot=FakeUniProt(), calibration=ActivityCalibration())
    client = TestClient(app)
    ids = [client.post("/api/runs", json={"source": {"type": "fasta", "text": TEXT},
                                           "options": {"top_n": 5}}).json()["id"]
           for _ in range(2)]
    deadline = time.time() + 60
    while time.time() < deadline:
        statuses = [client.get(f"/api/runs/{i}").json()["status"] for i in ids]
        if all(s in ("done", "failed") for s in statuses):
            break
        time.sleep(0.2)
    assert statuses == ["done", "done"]


def test_meta_files_are_valid_json(tmp_path, models):
    client = make_client(tmp_path, models)
    run_id = start(client, TEXT)
    saved = json.loads((tmp_path / "runs" / run_id / "meta.json").read_text())
    assert saved["status"] == "done" and saved["id"] == run_id
    assert (tmp_path / "runs" / run_id / "table.csv").exists()


# ---- the UniProt client itself -------------------------------------------------------------


class FakeResponse:
    def __init__(self, text="", status=200, headers=None):
        self.text, self.status_code, self.headers = text, status, headers or {}


class FakeSession:
    """Answers by URL fragment; remembers every request."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        self.calls.append((url, params))
        for fragment, answer in self.routes.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer(params) if callable(answer) else answer
        raise AssertionError(f"unexpected request {url}")


def test_uniprot_organism_search_counts_each_organism():
    def search(params):
        if params["fields"] == "organism_id,organism_name":
            body = "Organism (ID)\tOrganism\n" + "\n".join(
                ["83333\tEscherichia coli (strain K12)"] * 3 + ["562\tEscherichia coli"])
            return FakeResponse(body)
        taxon = params["query"].split("organism_id:")[1].split(" ")[0]
        count = {"83333": "4531", "562": "745"}[taxon]
        return FakeResponse("Organism\nEscherichia coli (strain K12)\n",
                            headers={"x-total-results": count})

    client = UniProtClient(FakeSession({"/uniprotkb/search": search}))
    found = client.search_organisms("escherichia coli")
    assert [f["taxon_id"] for f in found] == [83333, 562]
    assert found[0]["reviewed_proteins"] == 4531
    with pytest.raises(UniProtError):
        client.search_organisms("e")


def test_uniprot_errors_become_readable_messages():
    http = UniProtClient(FakeSession({"/uniprotkb": FakeResponse(status=503)}))
    with pytest.raises(UniProtError, match="HTTP 503"):
        http.fetch_accessions_fasta(["P69905"])
    down = UniProtClient(FakeSession({"/uniprotkb": requests.ConnectionError("no network")}))
    with pytest.raises(UniProtError, match="Could not reach UniProt"):
        down.fetch_accessions_fasta(["P69905"])
    with pytest.raises(UniProtError, match="Not a UniProt accession"):
        UniProtClient(FakeSession({})).fetch_accessions_fasta(["not an accession!"])
    # six to ten letters and digits, but not the real accession format
    with pytest.raises(UniProtError, match="Not a UniProt accession: NONSENSE"):
        UniProtClient(FakeSession({})).fetch_accessions_fasta(["nonsense"])
    with pytest.raises(UniProtError, match="No accessions"):
        UniProtClient(FakeSession({})).fetch_accessions_fasta(["  "])


def test_uniprot_refuses_oversized_or_empty_organisms():
    def info(count):
        return {"/uniprotkb/search": FakeResponse("Organism\nX\n", headers={
            "x-total-results": str(count)})}

    with pytest.raises(UniProtError, match="no reviewed proteins"):
        UniProtClient(FakeSession(info(0))).fetch_organism_fasta(1)
    with pytest.raises(UniProtError, match="limit"):
        UniProtClient(FakeSession(info(10**6))).fetch_organism_fasta(1)
    session = FakeSession({**info(3), "/uniprotkb/stream": FakeResponse(">sp|P1|X\nAAAA\n")})
    assert UniProtClient(session).fetch_organism_fasta(7).startswith(">sp|P1|X")


# ---- serving the built dashboard ----------------------------------------------------------


def test_the_built_dashboard_is_served_with_a_fallback_for_deep_links(tmp_path, models):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>dashboard</html>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")
    (tmp_path / "secret.txt").write_text("outside the dist folder")
    client = make_client(tmp_path, models, static_dir=dist)

    assert client.get("/").text == "<html>dashboard</html>"
    assert client.get("/assets/app.js").text == "console.log('hi')"
    assert client.get("/runs/abcdef012345").text == "<html>dashboard</html>"  # deep link
    assert client.get("/health").json() == {"status": "ok"}  # API routes still win
    assert client.get("/api/runs").json() == []
    unknown = client.get("/api/nothing-here")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
    assert client.get("/docs").status_code == 200  # the API docs are not swallowed
    leak = client.get("/..%2Fsecret.txt")
    assert "outside the dist folder" not in leak.text


def test_without_a_built_dashboard_unknown_paths_are_plain_404(tmp_path, models):
    client = make_client(tmp_path, models, static_dir=tmp_path / "missing")
    assert client.get("/").status_code == 404


def test_the_protein_view_carries_the_calibrated_score_profile(tmp_path, models):
    calibration = ActivityCalibration(LogisticRecalibrator(1.2, 0.5), 0.03)
    client = make_client(tmp_path, models, calibration=calibration)
    run_id = start(client, TEXT)
    body = client.get(f"/api/runs/{run_id}/proteins/P00001").json()
    profile = body["profile"]
    assert len(profile) == body["length"] == 150
    assert all(0.0 <= p <= 1.0 for p in profile)
    # the same calibration the table uses, so the curve and the rows agree
    rarer = client.get(
        f"/api/runs/{run_id}/proteins/P00001", params={"prevalence": 1e-4}
    ).json()["profile"]
    assert max(rarer) < max(profile)


def test_a_run_from_before_profiles_existed_still_opens(tmp_path, models):
    client = make_client(tmp_path, models)
    run_id = start(client, TEXT)
    (tmp_path / "runs" / run_id / "profiles.json").unlink()
    body = client.get(f"/api/runs/{run_id}/proteins/P00001").json()
    assert body["profile"] == []
    assert body["length"] == 150
