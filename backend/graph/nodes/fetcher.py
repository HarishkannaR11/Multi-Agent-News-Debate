import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)
from collections.abc import Callable  # type for "a function we can call"

import httpx  # HTTP client used to call the news APIs

from ...config import settings  # the shared app settings
from ...timeutil import today_iso  # today's date as text
from ..guardrails.input_guard import check_input  # content filter for incoming text
from ..state import DebateState  # the shared state shape

# A logger named after this module.
logger = logging.getLogger(__name__)

# Web address of NewsAPI's top-headlines endpoint.
NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"
# Web address of GNews's top-headlines endpoint.
GNEWS_URL = "https://gnews.io/api/v4/top-headlines"

# How many times to try each news request.
FETCH_ATTEMPTS = 2
# How many candidate articles to content-check before giving up.
MAX_CANDIDATES_CHECKED = 5
# Pattern that matches NewsAPI's "[+1234 chars]" suffix on truncated articles.
_TRUNCATION_MARKER = re.compile(r"\s*\[\+\d+ chars\]\s*$")


# Calls a news API and returns its JSON reply, retrying once on network errors.
def _get_json(url: str, params: dict) -> dict:
    # Remember the most recent error so we can re-raise it if every attempt fails.
    last_error: Exception | None = None
    # Try up to FETCH_ATTEMPTS times.
    for _ in range(FETCH_ATTEMPTS):
        try:
            # Make the HTTP request with a 10-second timeout.
            resp = httpx.get(url, params=params, timeout=10)
            # Raise an error for bad status codes (4xx/5xx).
            resp.raise_for_status()
            # Success: return the parsed JSON.
            return resp.json()
        # Any HTTP/network problem: remember it and try again.
        except httpx.HTTPError as exc:
            last_error = exc
    # Sanity check for the type checker: after the loop there must be an error.
    assert last_error is not None
    # All attempts failed: raise the last error.
    raise last_error


# Gets top headlines from NewsAPI (returns an empty list if there is no key).
def _fetch_newsapi() -> list[dict]:
    # No key configured: skip this source.
    if not settings.NEWSAPI_KEY:
        return []
    # Ask for 10 general English headlines.
    data = _get_json(
        NEWSAPI_URL,
        {"apiKey": settings.NEWSAPI_KEY, "category": "general", "language": "en", "pageSize": 10},
    )
    # Return the list of articles (or an empty list if the field is missing).
    return data.get("articles", [])


# Gets top headlines from GNews (returns an empty list if there is no key).
def _fetch_gnews() -> list[dict]:
    # No key configured: skip this source.
    if not settings.GNEWS_API_KEY:
        return []
    # Ask for up to 10 English headlines.
    data = _get_json(GNEWS_URL, {"apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 10})
    # Return the list of articles (or an empty list if the field is missing).
    return data.get("articles", [])


# True if an article is worth debating: it has a title, some text, and was not used recently.
def _usable(article: dict, seen: set[str]) -> bool:
    # Get the title (or "") and trim spaces.
    title = (article.get("title") or "").strip()
    # Reject articles with no title or NewsAPI's "[Removed]" placeholder.
    if not title or title == "[Removed]":
        return False
    # Reject articles with neither a description nor content.
    if not (article.get("description") or article.get("content")):
        return False
    # Accept only if its URL has not been debated recently.
    return (article.get("url") or "") not in seen


# Combines an article's title, description and content into one block of text for the LLM.
def _build_context(article: dict) -> str:
    # Take the content and strip the "[+N chars]" truncation marker.
    content = _TRUNCATION_MARKER.sub("", article.get("content") or "")
    # The three text parts, in order.
    parts = [article.get("title") or "", article.get("description") or "", content]
    # Join the non-empty parts with blank lines, then cut to the maximum allowed length.
    return "\n\n".join(p.strip() for p in parts if p and p.strip())[: settings.MAX_NEWS_CONTEXT_CHARS]


# Finds usable articles from the first news source that returns any.
def _candidates(seen: set[str]) -> list[dict]:
    """Usable, not-recently-debated articles from the first source that has any."""
    # The sources in priority order: NewsAPI first, GNews as the fallback.
    sources: tuple[Callable[[], list[dict]], ...] = (_fetch_newsapi, _fetch_gnews)
    # Try each source in turn.
    for fetch in sources:
        try:
            # Fetch articles and keep only the usable ones.
            articles = [a for a in fetch() if _usable(a, seen)]
        # If this source failed, log it and move on to the next one.
        except httpx.HTTPError as exc:
            logger.warning("%s failed: %s", fetch.__name__, exc)
            continue
        # If this source gave us at least one usable article, use it and stop looking.
        if articles:
            return articles
    # No source produced anything usable.
    return []


# Graph step: picks today's article and writes it into the state.
def fetch_news_node(state: DebateState) -> dict:
    # URLs debated recently, as a set for fast lookup.
    seen = set(state.get("seen_urls") or [])
    # Get usable candidate articles.
    candidates = _candidates(seen)
    # Nothing usable at all: stop with a clear error (the daily job will retry).
    if not candidates:
        raise RuntimeError("No new article available from NewsAPI or GNews - check API keys/quota")

    # Check up to the first few candidates, in order.
    for article in candidates[:MAX_CANDIDATES_CHECKED]:
        # Run the incoming-text content filter on the article text.
        result = check_input(_build_context(article))
        # If it was blocked, log why and try the next article.
        if not result.passed:
            logger.info("Skipping article %r: input guardrail: %s", article.get("title"), result.reason)
            continue
        # Found a clean article: write its details into the state.
        return {
            # The (filter-checked) article text.
            "news_context": result.text,
            # Where the article came from.
            "source_url": article.get("url") or "",
            # Today's date.
            "date": today_iso(),
            # Record that the input check passed.
            "guardrail_input_pass": True,
            # Current stage.
            "status": "fetching",
        }

    # Every candidate was blocked by the filter: stop with an error.
    raise RuntimeError("Every candidate article was rejected by the input guardrail")
