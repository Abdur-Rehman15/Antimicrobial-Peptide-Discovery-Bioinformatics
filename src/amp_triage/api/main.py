"""FastAPI entry point. Endpoints are added in the API phase."""

from fastapi import FastAPI

app = FastAPI(title="AMP Triage", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
