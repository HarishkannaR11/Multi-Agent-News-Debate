"""Whole path with only the LLM, news APIs and Redis faked: admin trigger -> real graph ->
Redis -> REST + WebSocket -> opinion."""
import pytest
from fastapi.testclient import TestClient

from backend.graph.nodes.agents import PERSONAS
from backend.main import app

pytestmark = pytest.mark.usefixtures("fake_redis", "fake_news", "fake_llm")


def test_daily_run_then_browse_replay_and_opinion(monkeypatch):
    monkeypatch.setattr("backend.config.llm.invoke", _ModeAwareLLM())
    with TestClient(app) as client:
        assert client.get("/api/debate/latest").status_code == 404      # nothing generated yet

        r = client.post("/internal/run-daily", headers={"x-admin-token": "secret"})
        assert r.status_code == 202

        debate = client.get("/api/debate/latest").json()
        assert debate["status"] == "done"
        assert debate["topic"] == "Should X happen?"
        assert set(debate["arguments"]) == set(PERSONAS) == set(debate["rebuttals"])
        assert debate["source_url"] == "https://n.example/a"
        assert [d["id"] for d in client.get("/api/debates").json()] == [debate["id"]]

        # Today's story is now "seen": a forced second run picks the other article.
        client.post("/internal/run-daily?force=true", headers={"x-admin-token": "secret"})
        assert client.get("/api/debate/latest").json()["source_url"] == "https://n.example/b"

        with client.websocket_connect(f"/ws/debate/{debate['id']}") as ws:
            assert [ws.receive_json()["status"] for _ in range(3)] == ["debating", "rebuttal", "done"]

        opinion = client.post("/api/opinion/latest", json={"user_id": "guest", "opinion": "I disagree"})
        assert opinion.status_code == 200 and opinion.json()["mode"] == "CHALLENGE"


class _ModeAwareLLM:
    """Delegates to the shared recorder, but answers the opinion prompt in CHALLENGE mode."""

    def __init__(self):
        from backend.tests.conftest import LLMRecorder

        self.inner = LLMRecorder()

    def __call__(self, system, user, max_tokens=1024, fast=False):
        if "opinion analyst" in system:
            return "[Mode: CHALLENGE]\nRespectfully, the right analyst disagrees.\n\nWhat evidence would change your mind?"
        return self.inner(system, user, max_tokens, fast)
