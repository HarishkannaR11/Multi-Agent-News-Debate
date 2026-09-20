from datetime import date

import httpx

from ..guardrails.input_guard import input_guard
from ..state import DebateState
from ...config import settings

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"
GNEWS_URL = "https://gnews.io/api/v4/top-headlines"


def _fetch_newsapi():
    if not settings.NEWSAPI_KEY:
        return None
    resp = httpx.get(
        NEWSAPI_URL,
        params={
            "apiKey": settings.NEWSAPI_KEY,
            "category": "general",
            "language": "en",
            "pageSize": 5,
        },
        timeout=10,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    return articles[0] if articles else None


def _fetch_gnews():
    if not settings.GNEWS_API_KEY:
        return None
    resp = httpx.get(
        GNEWS_URL,
        params={"apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 5},
        timeout=10,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    return articles[0] if articles else None


def fetch_news_node(state: DebateState) -> DebateState:
    state["status"] = "fetching"
    article = None
    for fetch in (_fetch_newsapi, _fetch_gnews):
        try:
            article = fetch()
        except httpx.HTTPError:
            article = None
        if article:
            break

    if not article:
        raise RuntimeError("No article available from NewsAPI or GNews - check API keys/quota")

    title = article.get("title") or ""
    description = article.get("description") or ""
    content = article.get("content") or ""
    news_context = f"{title}\n\n{description}\n\n{content}"[: settings.MAX_NEWS_CONTEXT_CHARS]

    try:
        input_guard.validate(news_context)
        state["guardrail_input_pass"] = True
    except Exception:
        state["guardrail_input_pass"] = False

    state["news_context"] = news_context
    state["date"] = date.today().isoformat()
    state["arguments"] = {}
    state["rebuttals"] = {}
    state["round"] = 1
    return state


if __name__ == "__main__":
    result = fetch_news_node({})
    print(result["news_context"][:500])
