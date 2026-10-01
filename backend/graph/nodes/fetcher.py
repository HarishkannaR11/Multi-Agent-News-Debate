import logging
import re
from collections.abc import Callable

import httpx

from ...config import settings
from ...timeutil import today_iso
from ..guardrails.input_guard import check_input
from ..state import DebateState

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"
GNEWS_URL = "https://gnews.io/api/v4/top-headlines"

FETCH_ATTEMPTS = 2
MAX_CANDIDATES_CHECKED = 5
_TRUNCATION_MARKER = re.compile(r"\s*\[\+\d+ chars\]\s*$")


def _get_json(url: str, params: dict) -> dict:
    last_error: Exception | None = None
    for _ in range(FETCH_ATTEMPTS):
        try:
            resp = httpx.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _fetch_newsapi() -> list[dict]:
    if not settings.NEWSAPI_KEY:
        return []
    data = _get_json(
        NEWSAPI_URL,
        {"apiKey": settings.NEWSAPI_KEY, "category": "general", "language": "en", "pageSize": 10},
    )
    return data.get("articles", [])


def _fetch_gnews() -> list[dict]:
    if not settings.GNEWS_API_KEY:
        return []
    data = _get_json(GNEWS_URL, {"apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 10})
    return data.get("articles", [])


def _usable(article: dict, seen: set[str]) -> bool:
    title = (article.get("title") or "").strip()
    if not title or title == "[Removed]":
        return False
    if not (article.get("description") or article.get("content")):
        return False
    return (article.get("url") or "") not in seen


def _build_context(article: dict) -> str:
    content = _TRUNCATION_MARKER.sub("", article.get("content") or "")
    parts = [article.get("title") or "", article.get("description") or "", content]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())[: settings.MAX_NEWS_CONTEXT_CHARS]


def _candidates(seen: set[str]) -> list[dict]:
    """Usable, not-recently-debated articles from the first source that has any."""
    sources: tuple[Callable[[], list[dict]], ...] = (_fetch_newsapi, _fetch_gnews)
    for fetch in sources:
        try:
            articles = [a for a in fetch() if _usable(a, seen)]
        except httpx.HTTPError as exc:
            logger.warning("%s failed: %s", fetch.__name__, exc)
            continue
        if articles:
            return articles
    return []


def fetch_news_node(state: DebateState) -> dict:
    seen = set(state.get("seen_urls") or [])
    candidates = _candidates(seen)
    if not candidates:
        raise RuntimeError("No new article available from NewsAPI or GNews - check API keys/quota")

    for article in candidates[:MAX_CANDIDATES_CHECKED]:
        result = check_input(_build_context(article))
        if not result.passed:
            logger.info("Skipping article %r: input guardrail: %s", article.get("title"), result.reason)
            continue
        return {
            "news_context": result.text,
            "source_url": article.get("url") or "",
            "date": today_iso(),
            "guardrail_input_pass": True,
            "status": "fetching",
        }

    raise RuntimeError("Every candidate article was rejected by the input guardrail")
