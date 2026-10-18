"""Finds real news articles related to a visitor's question, to use as sources.

These are *related coverage*, not fact-checked evidence: the app never invents a source, and never marks a claim
verified because an article exists. If no news key is set or the lookups fail, the debate simply has no sources
(and says so)."""
import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)
from urllib.parse import urlparse  # splits a web address into its parts

from ..config import llm, settings  # the shared LLM wrapper and settings
from ..graph.nodes.fetcher import _TRUNCATION_MARKER, GNEWS_URL, NEWSAPI_URL, _get_json  # shared news-API plumbing

# A logger named after this module.
logger = logging.getLogger(__name__)

# Longest excerpt, title and publisher name we keep from an article.
MAX_EXCERPT = 300
MAX_TITLE = 200
MAX_PUBLISHER = 80
# NewsAPI and GNews dates look like "2026-10-17T09:30:00Z"; we keep only the day.
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Instructions for turning a natural-language question into a short news search query.
QUERY_SYSTEM = """You write news search queries. Given a debate question, reply with 3 to 6 plain keywords that
would find relevant news articles. No quotes, no operators, no explanation, just the keywords."""


# Builds the search text. Uses the fast model, and falls back to the first words of the question.
def build_query(question: str) -> str:
    # The fallback: the first eight words, letters and digits only.
    fallback = " ".join(re.findall(r"[^\W_]+", question)[:8])
    try:
        # Ask the small model for keywords (the question is only a request here, never an instruction to follow).
        reply = llm.invoke(system=QUERY_SYSTEM, user=f"Question: {question}", max_tokens=40, fast=True)
    # A failed model call must not stop the debate: just use the fallback.
    except Exception:
        logger.warning("Search-query generation failed; using the question's own words")
        return fallback
    # Keep letters, digits and spaces only, at most 80 characters.
    query = " ".join(re.findall(r"[^\W_]+", reply))[:80].strip()
    return query or fallback


# Calls NewsAPI's search endpoint (returns [] with no key).
def _search_newsapi(query: str, limit: int) -> list[dict]:
    if not settings.NEWSAPI_KEY:
        return []
    data = _get_json(
        f"{NEWSAPI_URL.rsplit('/', 1)[0]}/everything",
        {"apiKey": settings.NEWSAPI_KEY, "q": query, "language": "en", "sortBy": "relevancy", "pageSize": limit},
    )
    return data.get("articles", [])


# Calls GNews's search endpoint (returns [] with no key).
def _search_gnews(query: str, limit: int) -> list[dict]:
    if not settings.GNEWS_API_KEY:
        return []
    data = _get_json(
        f"{GNEWS_URL.rsplit('/', 1)[0]}/search",
        {"apikey": settings.GNEWS_API_KEY, "q": query, "lang": "en", "max": limit},
    )
    return data.get("articles", [])


# Turns one raw article into our stored source shape, or None if it is unusable.
def _clean(article: dict) -> dict | None:
    title = " ".join(str(article.get("title") or "").split())[:MAX_TITLE]
    url = str(article.get("url") or "").strip()
    # Reject placeholders, and anything whose link is not a plain http(s) address (never javascript: or data:).
    parsed = urlparse(url)
    bad_link = parsed.scheme not in ("http", "https") or not parsed.netloc or len(url) > 500
    if not title or title == "[Removed]" or bad_link:
        return None
    # The excerpt: the description, else the start of the content (without the "[+N chars]" marker).
    text = str(article.get("description") or "") or _TRUNCATION_MARKER.sub("", str(article.get("content") or ""))
    excerpt = " ".join(text.split())
    if len(excerpt) > MAX_EXCERPT:
        excerpt = excerpt[: MAX_EXCERPT - 1].rstrip() + "…"
    # The publisher: the source's name, else the web host.
    raw_source = article.get("source")
    source = raw_source if isinstance(raw_source, dict) else {}
    publisher = " ".join(str(source.get("name") or parsed.netloc).split())[:MAX_PUBLISHER]
    # The date: only a well-formed YYYY-MM-DD, otherwise left empty rather than guessed.
    match = _DATE.match(str(article.get("publishedAt") or ""))
    return {
        "title": title,
        "publisher": publisher,
        "url": url,
        "published_at": match.group(0) if match else "",
        "excerpt": excerpt,
    }


# Finds up to settings.USER_DEBATE_SOURCES_MAX related articles. Never raises: a failure means "no sources".
def find_sources(question: str) -> list[dict]:
    """Return sources as [{id: 'S1', title, publisher, url, published_at, excerpt}], most relevant first."""
    limit = settings.USER_DEBATE_SOURCES_MAX
    # Switched off, or no news key at all: nothing to look up.
    if limit <= 0 or not (settings.NEWSAPI_KEY or settings.GNEWS_API_KEY):
        return []
    query = build_query(question)
    found: list[dict] = []
    seen: set[str] = set()
    # Try each news service in turn until we have enough.
    for search in (_search_newsapi, _search_gnews):
        if len(found) >= limit:
            break
        try:
            articles = search(query, limit)
        # A failing news service must not fail the debate.
        except Exception:
            logger.warning("Source lookup failed in %s", search.__name__, exc_info=True)
            continue
        for article in articles:
            cleaned = _clean(article) if isinstance(article, dict) else None
            # Skip unusable items and repeats (same link or same title).
            if not cleaned or cleaned["url"] in seen or cleaned["title"].lower() in seen:
                continue
            seen.update((cleaned["url"], cleaned["title"].lower()))
            found.append(cleaned)
            if len(found) >= limit:
                break
    # Number them S1, S2, ... in order; these ids are what the analysts may cite.
    return [{"id": f"S{index}", **item} for index, item in enumerate(found, start=1)]
