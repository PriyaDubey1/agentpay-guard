from fastapi.testclient import TestClient

from app.main import app


def test_health():
    # No `with` block: skips lifespan so the real DB isn't touched.
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
