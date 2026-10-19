from fastapi.testclient import TestClient

from app import main
from app.auth import current_business
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_invoices_requires_login():
    assert client.get("/invoices").status_code in (401, 403)


def test_chat_docs_returns_answers(monkeypatch):
    main.app.dependency_overrides[current_business] = lambda: {
        "id": "x",
        "name": "Test",
    }
    monkeypatch.setattr(main, "ask_docs", lambda q: {"answer": "ok", "citations": []})
    assert client.post("/chat/docs", json={"question": "hi"}).json()["answer"] == "ok"
    main.app.dependency_overrides.clear()
