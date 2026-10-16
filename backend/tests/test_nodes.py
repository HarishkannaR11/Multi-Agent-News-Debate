import httpx  # the HTTP library (used to simulate a network error)
import pytest  # the test framework

from backend.graph.guardrails.common import GuardResult  # the result type a safety check returns
from backend.graph.nodes import fetcher  # the node that fetches and filters news articles
from backend.graph.nodes.moderator import parse_bias_scores  # turns the auditor's reply into a dict of scores


# Run this test once per (raw reply, expected result) pair.
@pytest.mark.parametrize("raw,expected", [
    # Clean JSON is parsed as is.
    ('{"left": 0.7, "right": 0.2}', {"left": 0.7, "right": 0.2}),
    # JSON wrapped in a markdown code fence is found, and out-of-range values are clamped to 0..1.
    ('Here you go:\n```json\n{"left": 1.4, "devil": -1}\n```', {"left": 1.0, "devil": 0.0}),
    # Non-number values and unknown analyst names are dropped.
    ('{"left": "high", "right": true, "bogus": 0.5}', {}),
    # No JSON at all, JSON that is a list, or broken JSON all give an empty result instead of crashing.
    ("no json here", {}),
    ("[0.1, 0.2]", {}),
    ('{"left": 0.5', {}),
])
def test_parse_bias_scores(raw, expected):
    assert parse_bias_scores(raw) == expected


# If the safety check rejects the first article, the fetcher moves on to the next one.
def test_fetcher_rejected_by_input_guard_moves_to_next_article(fake_news, monkeypatch):
    # Fake check: reject text starting with "Story A", accept everything else.
    monkeypatch.setattr(
        fetcher, "check_input",
        lambda text: GuardResult(False, text, "toxic") if text.startswith("Story A") else GuardResult(True, text),
    )
    state = fetcher.fetch_news_node({})
    # Article B was chosen, and the state records that the input check passed.
    assert state["source_url"] == "https://n.example/b"
    assert state["guardrail_input_pass"] is True


# If every article is rejected, the node fails with a clear error instead of returning nothing.
def test_fetcher_raises_when_every_article_rejected(fake_news, monkeypatch):
    monkeypatch.setattr(fetcher, "check_input", lambda text: GuardResult(False, text, "toxic"))
    with pytest.raises(RuntimeError, match="input guardrail"):
        fetcher.fetch_news_node({})


# If both news sources return nothing, the node fails with a clear error.
def test_fetcher_raises_without_articles(monkeypatch):
    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: [])
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    with pytest.raises(RuntimeError, match="No new article"):
        fetcher.fetch_news_node({})


# If NewsAPI is down, the fetcher falls back to GNews.
def test_fetcher_falls_back_to_gnews_when_newsapi_errors(monkeypatch):
    # A stand-in for NewsAPI that simulates a connection failure.
    def boom():
        raise httpx.ConnectError("down")

    monkeypatch.setattr(fetcher, "_fetch_newsapi", boom)
    # GNews returns one usable article.
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [{"title": "G", "description": "d", "url": "u"}])
    assert fetcher.fetch_news_node({})["source_url"] == "u"


# Deleted ("[Removed]") articles and ones without a description are ignored, leaving nothing, so an error is raised.
def test_fetcher_ignores_removed_and_empty_articles(monkeypatch):
    junk = [{"title": "[Removed]", "description": "x", "url": "1"}, {"title": "T", "url": "2"}]
    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: junk)
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    with pytest.raises(RuntimeError):
        fetcher.fetch_news_node({})
