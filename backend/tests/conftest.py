import pytest  # the test framework; its fixtures are shared setup/teardown helpers
from fakeredis import FakeServer  # an in-memory stand-in for a Redis server
from fakeredis.aioredis import FakeRedis  # the async client that talks to that fake server

from backend.config import llm, settings  # the real LLM wrapper object and the settings object (both get patched)
from backend.graph.nodes import agents  # the module that holds the analyst persona prompts
from backend.services import redis_service  # the module that owns the Redis connection

# Two fake news articles that the fake_news fixture hands to the fetcher instead of calling a real news API.
ARTICLES = [
    # "[+1200 chars]" is the truncation marker NewsAPI adds; a test checks the code strips it.
    {"title": "Story A", "description": "About A", "content": "More on A [+1200 chars]", "url": "https://n.example/a"},
    {"title": "Story B", "description": "About B", "content": "More on B", "url": "https://n.example/b"},
]


# autouse=True: this fixture runs automatically before EVERY test in the project.
@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    # monkeypatch changes an attribute for one test and automatically restores it afterwards.
    # Turn the heavy AI safety checks off so tests are fast and need no model downloads.
    monkeypatch.setattr(settings, "GUARDRAILS_ENABLED", False)
    # Do not start the daily-job timer inside tests.
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    # Do not wait between retries of the daily job (so failure tests finish instantly).
    monkeypatch.setattr(settings, "DAILY_RUN_RETRY_SECONDS", 0)
    # A known admin password the tests can send in the X-Admin-Token header.
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret")
    # No real Groq key, so a test can never accidentally make a paid API call.
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")


# A fixture that provides a fake Redis and plugs it into the app.
@pytest.fixture
def fake_redis(monkeypatch):
    # Create an in-memory Redis; decode_responses=True returns text instead of raw bytes, like the real client config.
    client = FakeRedis(server=FakeServer(), decode_responses=True)
    # Replace the app's cached connection with the fake one, so all app code uses it.
    monkeypatch.setattr(redis_service, "_redis", client)
    # Give the test the client too, so it can inspect Redis directly.
    return client


# A stand-in for the real LLM that records every call and returns canned answers.
class LLMRecorder:
    # Start with an empty list of recorded calls.
    def __init__(self):
        self.calls: list[dict] = []

    # Makes the object callable like a function, with the same parameters as the real llm.invoke.
    def __call__(self, system, user, max_tokens=1024, fast=False):
        # Remember what was asked, so tests can inspect the prompts afterwards.
        self.calls.append({"system": system, "user": user, "fast": fast})
        # Pick a canned reply by recognising which agent is calling, using a phrase from its system prompt.
        # The bias auditor must return JSON scores.
        if "bias auditor" in system:
            return '{"left": 0.7, "right": 0.6, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4}'
        # The moderator returns a verdict sentence.
        if "debate moderator" in system:
            return "A balanced verdict."
        # The topic extractor returns a one-sentence topic.
        if "distill a news article" in system:
            return "Should X happen?"
        # For an analyst, find which persona's prompt this is and reply "<persona> says something".
        for key, persona_text in agents.PERSONAS.items():
            if system.startswith(persona_text):
                return f"{key} says something"
        # Anything else gets a generic reply.
        return "generic reply"

    # Returns the recorded calls that were rebuttal requests from one analyst.
    def rebuttal_calls(self, persona_key: str) -> list[dict]:
        # That analyst's system prompt.
        text = agents.PERSONAS[persona_key]
        # Keep calls that used this prompt AND mention "rebuttal" in the user message.
        return [c for c in self.calls if c["system"].startswith(text) and "rebuttal" in c["user"].lower()]


# A fixture that replaces the real LLM with the recorder.
@pytest.fixture
def fake_llm(monkeypatch):
    # Create a recorder.
    recorder = LLMRecorder()
    # Swap it in for llm.invoke, so no network call is ever made.
    monkeypatch.setattr(llm, "invoke", recorder)
    # Give the test the recorder so it can check what was called.
    return recorder


# A fixture that replaces the real news APIs with the two fake articles.
@pytest.fixture
def fake_news(monkeypatch):
    # Imported inside the function so the module is only loaded when this fixture is used.
    from backend.graph.nodes import fetcher

    # NewsAPI "returns" a copy of our two articles (a copy so tests cannot change the original list).
    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: list(ARTICLES))
    # GNews returns nothing.
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    # Give the test the articles so it can compare against them.
    return ARTICLES
