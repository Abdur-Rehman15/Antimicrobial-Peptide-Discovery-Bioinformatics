"""FastAPI entry point:  uvicorn amp_triage.api.main:app --reload"""

from amp_triage.api.app import create_app

app = create_app()
