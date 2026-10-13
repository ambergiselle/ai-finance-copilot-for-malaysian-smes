from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_invoices_requires_login():
    assert client.get("/invoices").status_code in (401, 403)
