"""Phase 1 smoke test: the FastAPI app imports and responds.

This is the only test Phase 1 is responsible for — model/constraint tests
arrive in Phase 2.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "talentflow-ai-backend"}
