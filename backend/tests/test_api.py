import pytest  # the test framework
from fastapi.testclient import TestClient  # runs the FastAPI app in-process, so no real server is needed
from starlette.websockets import WebSocketDisconnect  # the error raised when a WebSocket is closed by the server

from backend import scheduler  # the daily-job module (patched to prove WebSocket never runs it)
from backend.config import settings  # the settings object (tests change limits)
from backend.main import app  # the real FastAPI application under test
from backend.services import redis_service as rs  # Redis helpers, shortened to "rs"

# A finished debate used as test data.
STATE = {"status": "done", "topic": "T", "verdict": "V", "arguments": {"left": "a"},
         "rebuttals": {"left": "r"}, "bias_scores": {"left": 0.5}}
# The id this debate gets when saved: "<date>:<slug>".
DEBATE_ID = "2026-09-30:some-topic"


# A fixture: a running test client with one saved debate.
@pytest.fixture
def client(fake_redis):
    # "with TestClient(app)" runs the app's startup and shutdown code too.
    with TestClient(app) as c:
        # Save the sample debate into the fake Redis (c.portal runs an async function from this sync test).
        c.portal.call(rs.save_debate, "2026-09-30", "some-topic", STATE)
        # Hand the client to the test; code after "yield" would run as cleanup.
        yield c


# The health endpoints should answer.
def test_health(client):
    # Liveness: always ok.
    assert client.get("/health").json() == {"status": "ok"}
    # Readiness: ok because the fake Redis answers.
    assert client.get("/health/ready").status_code == 200


# "latest", a bare date and a full id should all find the same debate.
def test_debate_lookup_variants(client):
    for debate_id in ("latest", "2026-09-30", DEBATE_ID):
        body = client.get(f"/api/debate/{debate_id}").json()
        # Every variant returns the full id, the topic and the date.
        assert body["id"] == DEBATE_ID and body["topic"] == "T" and body["date"] == "2026-09-30"


# Run this test once for each bad id in the list.
@pytest.mark.parametrize("bad", ["nope", "2026-09-30:missing", "2026-01-01", "a:b:c", "x%3Ay"])
def test_bad_ids_are_404_not_500(client, bad):
    # Garbage or missing ids must give a clean "not found", never a server crash.
    assert client.get(f"/api/debate/{bad}").status_code == 404


# Both the single-debate and list endpoints include when the debate was created.
def test_debates_carry_a_creation_timestamp(client):
    # A timestamp like "2026-..." starts with "20".
    assert client.get("/api/debate/latest").json()["created_at"].startswith("20")
    assert client.get("/api/debates").json()[0]["created_at"].startswith("20")


# The list endpoint rejects out-of-range paging values.
def test_list_debates_pagination_validation(client):
    # One debate is stored, so the list has one item.
    assert len(client.get("/api/debates").json()) == 1
    # limit must be between 1 and 100; 422 means "invalid input".
    assert client.get("/api/debates?limit=0").status_code == 422
    assert client.get("/api/debates?limit=1000").status_code == 422


# The WebSocket must replay saved data and never trigger the paid AI pipeline.
def test_websocket_replays_stored_debate_without_calling_the_llm(client, monkeypatch):
    # If anything tries to build the graph, fail the test immediately.
    monkeypatch.setattr(scheduler, "build_graph", lambda: pytest.fail("WebSocket must not run the graph"))
    # Open the WebSocket and read the three messages the server sends.
    with client.websocket_connect("/ws/debate/latest") as ws:
        events = [ws.receive_json() for _ in range(3)]
    # The stages arrive in order.
    assert [e["status"] for e in events] == ["debating", "rebuttal", "done"]
    # The last message carries the verdict and rebuttals.
    assert events[-1]["verdict"] == "V" and events[-1]["rebuttals"] == {"left": "r"}
    # The first message carries the opening arguments.
    assert events[0]["data"] == {"left": "a"}


# An unknown debate should produce an error message, then a close with our special code.
def test_websocket_unknown_debate_closes_with_error(client):
    with client.websocket_connect("/ws/debate/2026-01-01") as ws:
        # First the error message...
        assert ws.receive_json()["error"] == "not_found"
        # ...then trying to read again raises because the server closed the connection.
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    # 4404 is the app's own "debate not found" close code.
    assert exc.value.code == 4404


# A group of tests for the opinion endpoints.
class TestOpinion:
    # Runs before each test in this class: replace the LLM with a function that always returns the same reply.
    @pytest.fixture(autouse=True)
    def stub_llm(self, monkeypatch):
        from backend.config import llm

        # A reply in the format the opinion agent is told to use: a mode tag, the answer, then a follow-up question.
        reply = "[Mode: AGREE]\nYou make a fair point per the left analyst.\n\nWhy do you think so?"
        monkeypatch.setattr(llm, "invoke", lambda **kw: reply)

    # Helper: POST an opinion; "body" overrides the default fields (the | operator merges two dicts).
    def post(self, client, **body):
        payload = {"user_id": "guest", "opinion": "I think so"} | body
        return client.post(f"/api/opinion/{DEBATE_ID}", json=payload)

    # A normal submission works and is saved to the user's history.
    def test_success_and_history(self, client):
        entry = self.post(client).json()
        # The reply text was parsed into a mode and a follow-up.
        assert entry["mode"] == "AGREE" and entry["followup"] == "Why do you think so?"
        # The history endpoint returns what was submitted.
        history = client.get(f"/api/opinions/{DEBATE_ID}?user_id=guest").json()
        assert [h["user_opinion"] for h in history] == ["I think so"]

    # "latest" can be used instead of a full id.
    def test_accepts_latest_alias(self, client):
        assert client.post("/api/opinion/latest", json={"user_id": "g", "opinion": "hi"}).status_code == 200

    # Each of these bad bodies must be rejected with 422 (invalid input).
    @pytest.mark.parametrize("body", [
        # An empty opinion, and one that is one character too long.
        {"opinion": ""}, {"opinion": "x" * (settings.MAX_OPINION_CHARS + 1)},
        # A user id that tries a path trick, an empty id, and one that is too long (limit is 64).
        {"user_id": "../../etc"}, {"user_id": ""}, {"user_id": "a" * 65},
    ])
    def test_input_validation(self, client, body):
        assert self.post(client, **body).status_code == 422

    # An opinion about a debate that does not exist gives 404.
    def test_unknown_debate(self, client):
        assert client.post("/api/opinion/nope", json={"user_id": "g", "opinion": "hi"}).status_code == 404

    # The per-user limit: two allowed, the third is refused with 429 (too many requests).
    def test_rate_limited(self, client, monkeypatch):
        monkeypatch.setattr(settings, "OPINION_RATE_LIMIT", 2)
        codes = [self.post(client).status_code for _ in range(3)]
        assert codes == [200, 200, 429]

    # The site-wide hourly cap counts all users together (each request here uses a different user id).
    def test_global_hourly_cap_applies_across_users(self, client, monkeypatch):
        monkeypatch.setattr(settings, "OPINION_GLOBAL_LIMIT_PER_HOUR", 2)
        codes = [self.post(client, user_id=f"user-{i}").status_code for i in range(3)]
        assert codes == [200, 200, 429]

    # Setting the global cap to 0 turns it off.
    def test_global_cap_can_be_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "OPINION_GLOBAL_LIMIT_PER_HOUR", 0)
        # Raise the per-user limit too, so only the global cap could have blocked these.
        monkeypatch.setattr(settings, "OPINION_RATE_LIMIT", 100)
        assert all(self.post(client).status_code == 200 for _ in range(4))

    # If the safety filter says the text is toxic, the API refuses it with 422.
    def test_content_filter_rejection(self, client, monkeypatch):
        from backend.graph.guardrails.common import GuardResult
        from backend.routers import opinion

        # Pretend the input check always fails.
        monkeypatch.setattr(opinion, "check_input", lambda t: GuardResult(False, t, "toxic"))
        assert self.post(client).status_code == 422

    # If the safety filter itself is broken, the API must refuse (503), NOT skip the check.
    def test_guard_outage_is_503_not_a_bypass(self, client, monkeypatch):
        from backend.graph.guardrails.common import GuardUnavailable
        from backend.routers import opinion

        # A stand-in check that raises the "guard is unavailable" error.
        def down(text):
            raise GuardUnavailable("no torch")

        monkeypatch.setattr(opinion, "check_input", down)
        assert self.post(client).status_code == 503


# A group of tests for the protected endpoint that starts the daily debate.
class TestAdmin:
    # Runs before each test: replace the real (slow, paid) generation with a function that just records the date.
    @pytest.fixture(autouse=True)
    def stub_generation(self, monkeypatch):
        # Dates for which generation was requested.
        self.generated = []

        async def fake_generate(date):
            self.generated.append(date)

        from backend.routers import admin

        monkeypatch.setattr(admin, "generate_debate", fake_generate)
        # Pin "today" so the test does not depend on the real date.
        monkeypatch.setattr(admin, "today_iso", lambda: "2026-10-01")

    # No token or a wrong token must be refused with 401, and nothing may be generated.
    def test_requires_token(self, client):
        assert client.post("/internal/run-daily").status_code == 401
        assert client.post("/internal/run-daily", headers={"x-admin-token": "wrong"}).status_code == 401
        assert self.generated == []

    # If the server has no admin token configured, the endpoint is switched off (503).
    def test_disabled_without_configured_token(self, client, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
        assert client.post("/internal/run-daily", headers={"x-admin-token": ""}).status_code == 503

    # Running twice on the same day does nothing the second time, unless force=true is passed.
    def test_idempotent_unless_forced(self, client):
        h = {"x-admin-token": "secret"}
        first = client.post("/internal/run-daily", headers=h)
        second = client.post("/internal/run-daily", headers=h)
        forced = client.post("/internal/run-daily?force=true", headers=h)
        # 202 = accepted and started; 200 "already_ran" = skipped.
        assert (first.status_code, first.json()["status"]) == (202, "accepted")
        assert (second.status_code, second.json()["status"]) == (200, "already_ran")
        assert forced.status_code == 202
        # Generation really ran twice: the first call and the forced one.
        assert self.generated == ["2026-10-01", "2026-10-01"]


# If Redis is down, the API should say "service unavailable" (503) rather than crash (500).
def test_redis_outage_is_503_not_500(client, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    # A stand-in for list_debates that raises the connection error (the *_a, **_k accept and ignore any arguments).
    async def down(*_a, **_k):
        raise RedisConnectionError("refused")

    monkeypatch.setattr("backend.routers.debate.list_debates", down)
    assert client.get("/api/debates").status_code == 503


# If the AI service fails, the API answers 502, and the answer still carries CORS headers so browsers can read it.
def test_llm_failure_is_a_502_with_cors_headers(client, monkeypatch):
    from backend.config import llm

    # A stand-in LLM that always raises.
    def boom(**_):
        raise RuntimeError("GROQ_API_KEY is not set")

    monkeypatch.setattr(llm, "invoke", boom)
    # Send the request as if it came from the frontend page at localhost:3000 (the Origin header).
    r = client.post(
        f"/api/opinion/{DEBATE_ID}",
        json={"user_id": "guest", "opinion": "hi"},
        headers={"Origin": "http://localhost:3000"},
    )
    # 502 = bad gateway (an upstream service failed).
    assert r.status_code == 502
    # The error text tells the user the AI is unavailable.
    assert "unavailable" in r.json()["detail"]
    # The CORS header lets the browser show this error instead of a vague "network error".
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
