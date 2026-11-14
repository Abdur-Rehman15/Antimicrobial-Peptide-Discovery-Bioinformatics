"""Request and response shapes of the API (pydantic)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class FastaSource(BaseModel):
    type: Literal["fasta"]
    text: str = Field(description="One or more proteins in FASTA format")


class AccessionSource(BaseModel):
    type: Literal["accessions"]
    accessions: list[str] = Field(min_length=1, max_length=200,
                                  description="UniProt accessions, e.g. P69905")


class OrganismSource(BaseModel):
    type: Literal["organism"]
    taxon_id: int = Field(gt=0, description="UniProt organism id, e.g. 83333 for E. coli K-12")
    max_proteins: int = Field(default=100, ge=1, le=5000,
                              description="a random sample of this many reviewed proteins")
    seed: int = 0


Source = Annotated[FastaSource | AccessionSource | OrganismSource, Field(discriminator="type")]


class RunOptions(BaseModel):
    top_n: int = Field(default=200, ge=1, le=1000, description="candidates kept after merging")
    max_overlap: float = Field(default=0.5, ge=0.0, le=1.0)
    prevalence: float = Field(
        default=1e-3, gt=0.0, lt=0.5,
        description="assumed share of windows that are real AMPs (sets the calibrated numbers)",
    )


class RunRequest(BaseModel):
    source: Source
    options: RunOptions = RunOptions()
    label: str | None = Field(default=None, max_length=120)


class RunStatus(BaseModel):
    id: str
    label: str
    kind: str  # fasta / accessions / organism / precomputed
    status: Literal["queued", "running", "done", "failed"]
    progress: float
    message: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    n_proteins: int | None = None
    n_residues: int | None = None
    n_windows: int | None = None
    seconds: float | None = None
    error: str | None = None
    notes: list[str] = []
    options: dict = {}


class RunCreated(BaseModel):
    id: str
    status_url: str


class Organism(BaseModel):
    taxon_id: int
    name: str
    reviewed_proteins: int
