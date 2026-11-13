from fastapi.testclient import TestClient

from amp_triage import config
from amp_triage.api.main import app


def test_config_paths_exist():
    assert config.DATA_DIR.exists()
    assert config.MODELS_DIR.exists()


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_scientific_stack_imports():
    import Bio  # noqa: F401
    import modlamp  # noqa: F401
    import peptides  # noqa: F401
    import sklearn  # noqa: F401
