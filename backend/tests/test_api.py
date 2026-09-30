import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import scheduler
from backend.config import settings
from backend.main import app
from backend.services import redis_service as rs

STATE = {"status": "done", "topic": "T", "verdict": "V", "arguments": {"left": "a"},
         "rebuttals": {"left": "r"}, "bias_scores": {"left": 0.5}}
DEBATE_ID = "2026-09-30:some-topic"


@pytest.fixture
def client(fake_redis):
    with TestClient(app) as c:
        c.portal.call(rs.save_debate, "2026-09-30", "some-topic", STATE)
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_debate_lookup_variants(client):
    for debate_id in ("latest", "2026-09-30", DEBATE_ID):
        body = client.get(f"/api/debate/{debate_id}").json()
        assert body["id"] == DEBATE_ID and body["topic"] == "T" and body["date"] == "2026-09-30"


@pytest.mark.parametrize("bad", ["nope", "2026-09-30:missing", "2026-01-01", "a:b:c", "x%3Ay"])
def test_bad_ids_are_404_not_500(client, bad):
    assert client.get(f"/api/debate/{bad}").status_code == 404


def test_list_debates_pagination_validation(client):
    assert len(client.get("/api/debates").json()) == 1
    assert client.get("/api/debates?limit=0").status_code == 422
    assert client.get("/api/debates?limit=1000").status_code == 422


def test_websocket_replays_stored_debate_without_calling_the_llm(client, monkeypatch):
    monkeypatch.setattr(scheduler, "build_graph", lambda: pytest.fail("WebSocket must not run the graph"))
    with client.websocket_connect("/ws/debate/latest") as ws:
        events = [ws.receive_json() for _ in range(3)]
    assert [e["status"] for e in events] == ["debating", "rebuttal", "done"]
    assert events[-1]["verdict"] == "V" and events[-1]["rebuttals"] == {"left": "r"}
    assert events[0]["data"] == {"left": "a"}


def test_websocket_unknown_debate_closes_with_error(client):
    with client.websocket_connect("/ws/debate/2026-01-01") as ws:
        assert ws.receive_json()["error"] == "not_found"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4404


class TestOpinion:
    @pytest.fixture(autouse=True)
    def stub_llm(self, monkeypatch):
        from backend.config import llm

        reply = "[Mode: AGREE]\nYou make a fair point per the left analyst.\n\nWhy do you think so?"
        monkeypatch.setattr(llm, "invoke", lambda **kw: reply)

    def post(self, client, **body):
        payload = {"user_id": "guest", "opinion": "I think so"} | body
        return client.post(f"/api/opinion/{DEBATE_ID}", json=payload)

    def test_success_and_history(self, client):
        entry = self.post(client).json()
        assert entry["mode"] == "AGREE" and entry["followup"] == "Why do you think so?"
        history = client.get(f"/api/opinions/{DEBATE_ID}?user_id=guest").json()
        assert [h["user_opinion"] for h in history] == ["I think so"]

    def test_accepts_latest_alias(self, client):
        assert client.post("/api/opinion/latest", json={"user_id": "g", "opinion": "hi"}).status_code == 200

    @pytest.mark.parametrize("body", [
        {"opinion": ""}, {"opinion": "x" * (settings.MAX_OPINION_CHARS + 1)},
        {"user_id": "../../etc"}, {"user_id": ""}, {"user_id": "a" * 65},
    ])
    def test_input_validation(self, client, body):
        assert self.post(client, **body).status_code == 422

    def test_unknown_debate(self, client):
        assert client.post("/api/opinion/nope", json={"user_id": "g", "opinion": "hi"}).status_code == 404

    def test_rate_limited(self, client, monkeypatch):
        monkeypatch.setattr(settings, "OPINION_RATE_LIMIT", 2)
        codes = [self.post(client).status_code for _ in range(3)]
        assert codes == [200, 200, 429]

    def test_content_filter_rejection(self, client, monkeypatch):
        from backend.graph.guardrails.common import GuardResult
        from backend.routers import opinion

        monkeypatch.setattr(opinion, "check_input", lambda t: GuardResult(False, t, "toxic"))
        assert self.post(client).status_code == 422

    def test_guard_outage_is_503_not_a_bypass(self, client, monkeypatch):
        from backend.graph.guardrails.common import GuardUnavailable
        from backend.routers import opinion

        def down(text):
            raise GuardUnavailable("no torch")

        monkeypatch.setattr(opinion, "check_input", down)
        assert self.post(client).status_code == 503


class TestAdmin:
    @pytest.fixture(autouse=True)
    def stub_generation(self, monkeypatch):
        self.generated = []

        async def fake_generate(date):
            self.generated.append(date)

        from backend.routers import admin
        monkeypatch.setattr(admin, "generate_debate", fake_generate)
        monkeypatch.setattr(admin, "today_iso", lambda: "2026-10-01")

    def test_requires_token(self, client):
        assert client.post("/internal/run-daily").status_code == 401
        assert client.post("/internal/run-daily", headers={"x-admin-token": "wrong"}).status_code == 401
        assert self.generated == []

    def test_disabled_without_configured_token(self, client, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
        assert client.post("/internal/run-daily", headers={"x-admin-token": ""}).status_code == 503

    def test_idempotent_unless_forced(self, client):
        h = {"x-admin-token": "secret"}
        first = client.post("/internal/run-daily", headers=h)
        second = client.post("/internal/run-daily", headers=h)
        forced = client.post("/internal/run-daily?force=true", headers=h)
        assert (first.status_code, first.json()["status"]) == (202, "accepted")
        assert (second.status_code, second.json()["status"]) == (200, "already_ran")
        assert forced.status_code == 202
        assert self.generated == ["2026-10-01", "2026-10-01"]


def test_redis_outage_is_503_not_500(client, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def down(*_a, **_k):
        raise RedisConnectionError("refused")

    monkeypatch.setattr("backend.routers.debate.list_debates", down)
    assert client.get("/api/debates").status_code == 503


def test_llm_failure_is_a_502_with_cors_headers(client, monkeypatch):
    from backend.config import llm

    def boom(**_):
        raise RuntimeError("GROQ_API_KEY is not set")

    monkeypatch.setattr(llm, "invoke", boom)
    r = client.post(
        f"/api/opinion/{DEBATE_ID}",
        json={"user_id": "guest", "opinion": "hi"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 502
    assert "unavailable" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
