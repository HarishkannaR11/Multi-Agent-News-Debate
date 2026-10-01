import httpx
import pytest

from backend.graph.guardrails.common import GuardResult
from backend.graph.nodes import fetcher
from backend.graph.nodes.moderator import parse_bias_scores


@pytest.mark.parametrize("raw,expected", [
    ('{"left": 0.7, "right": 0.2}', {"left": 0.7, "right": 0.2}),
    ('Here you go:\n```json\n{"left": 1.4, "devil": -1}\n```', {"left": 1.0, "devil": 0.0}),
    ('{"left": "high", "right": true, "bogus": 0.5}', {}),
    ("no json here", {}),
    ("[0.1, 0.2]", {}),
    ('{"left": 0.5', {}),
])
def test_parse_bias_scores(raw, expected):
    assert parse_bias_scores(raw) == expected


def test_fetcher_rejected_by_input_guard_moves_to_next_article(fake_news, monkeypatch):
    monkeypatch.setattr(
        fetcher, "check_input",
        lambda text: GuardResult(False, text, "toxic") if text.startswith("Story A") else GuardResult(True, text),
    )
    state = fetcher.fetch_news_node({})
    assert state["source_url"] == "https://n.example/b"
    assert state["guardrail_input_pass"] is True


def test_fetcher_raises_when_every_article_rejected(fake_news, monkeypatch):
    monkeypatch.setattr(fetcher, "check_input", lambda text: GuardResult(False, text, "toxic"))
    with pytest.raises(RuntimeError, match="input guardrail"):
        fetcher.fetch_news_node({})


def test_fetcher_raises_without_articles(monkeypatch):
    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: [])
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    with pytest.raises(RuntimeError, match="No new article"):
        fetcher.fetch_news_node({})


def test_fetcher_falls_back_to_gnews_when_newsapi_errors(monkeypatch):
    def boom():
        raise httpx.ConnectError("down")

    monkeypatch.setattr(fetcher, "_fetch_newsapi", boom)
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [{"title": "G", "description": "d", "url": "u"}])
    assert fetcher.fetch_news_node({})["source_url"] == "u"


def test_fetcher_ignores_removed_and_empty_articles(monkeypatch):
    junk = [{"title": "[Removed]", "description": "x", "url": "1"}, {"title": "T", "url": "2"}]
    monkeypatch.setattr(fetcher, "_fetch_newsapi", lambda: junk)
    monkeypatch.setattr(fetcher, "_fetch_gnews", lambda: [])
    with pytest.raises(RuntimeError):
        fetcher.fetch_news_node({})
