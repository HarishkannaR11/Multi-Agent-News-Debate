"""Whole path with only the LLM, news APIs and Redis faked: admin trigger -> real graph ->
Redis -> REST + WebSocket -> opinion."""
import pytest  # the test framework
from fastapi.testclient import TestClient  # runs the FastAPI app in-process

from backend.graph.nodes.agents import PERSONAS  # the analyst prompts, keyed by analyst name
from backend.main import app  # the real FastAPI application

# Apply the fake Redis, fake news and fake LLM fixtures to every test in this file.
pytestmark = pytest.mark.usefixtures("fake_redis", "fake_news", "fake_llm")


# One test that walks the whole product: generate a debate, browse it, replay it over WebSocket, add an opinion.
def test_daily_run_then_browse_replay_and_opinion(monkeypatch):
    # Use our LLM stand-in that can also answer the opinion prompt.
    monkeypatch.setattr("backend.config.llm.invoke", _ModeAwareLLM())
    # Start the app (running its startup code) and get a test client.
    with TestClient(app) as client:
        assert client.get("/api/debate/latest").status_code == 404      # nothing generated yet

        # Trigger the daily job with the admin token; 202 = accepted.
        r = client.post("/internal/run-daily", headers={"x-admin-token": "secret"})
        assert r.status_code == 202

        # The debate is now stored and complete.
        debate = client.get("/api/debate/latest").json()
        assert debate["status"] == "done"
        assert debate["topic"] == "Should X happen?"
        # All five analysts have both an opening and a rebuttal.
        assert set(debate["arguments"]) == set(PERSONAS) == set(debate["rebuttals"])
        assert debate["source_url"] == "https://n.example/a"
        # The archive list contains exactly this debate.
        assert [d["id"] for d in client.get("/api/debates").json()] == [debate["id"]]

        # Today's story is now "seen": a forced second run picks the other article.
        client.post("/internal/run-daily?force=true", headers={"x-admin-token": "secret"})
        assert client.get("/api/debate/latest").json()["source_url"] == "https://n.example/b"

        # Replay the first debate over the WebSocket: three stages in order.
        with client.websocket_connect(f"/ws/debate/{debate['id']}") as ws:
            assert [ws.receive_json()["status"] for _ in range(3)] == ["debating", "rebuttal", "done"]

        # Submit an opinion; the fake LLM answers in CHALLENGE mode.
        opinion = client.post("/api/opinion/latest", json={"user_id": "guest", "opinion": "I disagree"})
        assert opinion.status_code == 200 and opinion.json()["mode"] == "CHALLENGE"


# A fake LLM that behaves like the shared recorder, except for the opinion prompt.
class _ModeAwareLLM:
    """Delegates to the shared recorder, but answers the opinion prompt in CHALLENGE mode."""

    def __init__(self):
        # Imported here to avoid loading the test helpers until needed.
        from backend.tests.conftest import LLMRecorder

        # The shared recorder that answers all the other prompts.
        self.inner = LLMRecorder()

    # Same signature as the real llm.invoke.
    def __call__(self, system, user, max_tokens=1024, fast=False):
        # The opinion agent's prompt contains "opinion analyst": answer in the format the code expects.
        if "opinion analyst" in system:
            return (
                "[Mode: CHALLENGE]\nRespectfully, the right analyst disagrees.\n\n"
                "What evidence would change your mind?"
            )
        # Everything else goes to the shared recorder.
        return self.inner(system, user, max_tokens, fast)
