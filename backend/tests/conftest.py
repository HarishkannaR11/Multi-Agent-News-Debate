import pytest
from fakeredis import FakeServer
from fakeredis.aioredis import FakeRedis

from backend.config import llm, settings
from backend.graph.nodes import agents
from backend.services import redis_service

ARTICLES = [
    {"title": "Story A", "description": "About A", "content": "More on A [+1200 chars]", "url": "https://n.example/a"},
    {"title": "Story B", "description": "About B", "content": "More on B", "url": "https://n.example/b"},
]


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "DAILY_RUN_RETRY_SECONDS", 0)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis(server=FakeServer(), decode_responses=True)
    monkeypatch.setattr(redis_service, "_redis", client)
    return client


class LLMRecorder:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, system, user, max_tokens=1024, fast=False):
        self.calls.append({"system": system, "user": user, "fast": fast})
        if "bias auditor" in system:
            return '{"left": 0.7, "right": 0.6, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4}'
        if "debate moderator" in system:
            return "A balanced verdict."
        if "distill a news article" in system:
            return "Should X happen?"
        for key, persona_text in agents.PERSONAS.items():
            if system.startswith(persona_text):
                return f"{key} says something"
        return "generic reply"

    def rebuttal_calls(self, persona_key: str) -> list[dict]:
        text = agents.PERSONAS[persona_key]
        return [c for c in self.calls if c["system"].startswith(text) and "rebuttal" in c["user"].lower()]


@pytest.fixture
def fake_llm(monkeypatch):
    recorder = LLMRecorder()
    monkeypatch.setattr(llm, "invoke", recorder)
    return recorder


@pytest.fixture
def fake_news(monkeypatch):
    from backend.graph.nodes import fetcher

    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: list(ARTICLES))
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    return ARTICLES
