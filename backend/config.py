import os  # standard library: gives access to environment variables (os.environ)
from typing import TYPE_CHECKING  # lets us import names only for type checking (free at runtime)

from dotenv import load_dotenv  # reads a local ".env" file and loads its KEY=value lines into the environment

# This block runs only for type checkers (mypy), never when the app runs.
if TYPE_CHECKING:
    # Import the Groq client class just so the type hint below is understood.
    from groq import Groq

# Load variables from a ".env" file (if one exists) into os.environ.
load_dotenv()


# Helper that turns an environment variable into True/False.
def _bool(name: str, default: bool) -> bool:
    # Read the variable (or the default), trim spaces, lowercase it, and check it is a "true-ish" word.
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# One place that holds every setting the app uses, read from environment variables.
class Settings:
    # Secret key for the Groq LLM service; empty string if not set.
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    # llama-3.1-70b-versatile / llama-3.3-70b-versatile / llama-3.1-8b-instant are
    # deprecated on Groq; check https://console.groq.com/docs/deprecations before changing.
    # The big, smart model used for arguments and verdicts.
    GROQ_MODEL_MAIN = os.environ.get("GROQ_MODEL_MAIN", "openai/gpt-oss-120b")
    # The small, fast model used for cheap steps (topic extraction, bias scoring).
    GROQ_MODEL_FAST = os.environ.get("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
    # How many seconds to wait for one Groq reply before giving up.
    GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", 60))
    # The SDK retries 429/5xx with backoff (honouring Retry-After); free tiers rate-limit the parallel calls.
    # How many times the Groq SDK retries a failed/rate-limited call.
    GROQ_MAX_RETRIES = int(os.environ.get("GROQ_MAX_RETRIES", 5))
    # gpt-oss models spend part of max_tokens on hidden reasoning, so give them headroom.
    # Extra tokens added to the limit for models that "think" before answering.
    REASONING_TOKEN_HEADROOM = int(os.environ.get("REASONING_TOKEN_HEADROOM", 1024))
    # API key for the NewsAPI news service.
    NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
    # API key for the GNews news service (the fallback source).
    GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
    # Address of the Redis database.
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # Turns LangSmith tracing on/off (read by LangChain/LangGraph itself).
    LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    # LangSmith API key (only needed if tracing is on).
    LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
    # Project name that traces are filed under in LangSmith.
    LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "counterpoint")

    # Whether the app runs its own daily scheduler (turn off if something else triggers the job).
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", True)
    # Hour of day (0-23) the daily debate is generated.
    SCHEDULER_HOUR = int(os.environ.get("SCHEDULER_HOUR", 7))
    # Minute of that hour.
    SCHEDULER_MINUTE = int(os.environ.get("SCHEDULER_MINUTE", 0))
    # Timezone used for the schedule and for "today's date".
    SCHEDULER_TIMEZONE = os.environ.get("SCHEDULER_TIMEZONE", "UTC")
    # How many times the daily job tries before giving up.
    DAILY_RUN_ATTEMPTS = int(os.environ.get("DAILY_RUN_ATTEMPTS", 3))
    # Seconds to wait between those attempts.
    DAILY_RUN_RETRY_SECONDS = float(os.environ.get("DAILY_RUN_RETRY_SECONDS", 60))
    # Shared secret for POST /internal/run-daily (EventBridge, cron, manual). Empty = endpoint disabled.
    # The password that protects the "generate a debate now" endpoint.
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

    # Guardrails load torch/transformers models; turn off only for local dev/tests.
    # Master switch for the content filters.
    GUARDRAILS_ENABLED = _bool("GUARDRAILS_ENABLED", True)
    # How many times a blocked piece of text is regenerated before being dropped.
    MAX_REBUTTAL_RETRIES = int(os.environ.get("MAX_REBUTTAL_RETRIES", 2))
    # Hard cap on graph steps so a stuck loop cannot run forever.
    GRAPH_RECURSION_LIMIT = int(os.environ.get("GRAPH_RECURSION_LIMIT", 25))

    # How much detail the logs contain (DEBUG, INFO, WARNING, ...).
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    # "text" for humans, "json" for log tools such as CloudWatch.
    LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")  # "json" for CloudWatch/log shippers

    # Maximum characters of news text sent to the LLM.
    MAX_NEWS_CONTEXT_CHARS = 8000
    # Maximum length of a user's opinion.
    MAX_OPINION_CHARS = int(os.environ.get("MAX_OPINION_CHARS", 1000))
    # Debates are kept for 30 days (seconds = 60 * 60 * 24 * 30).
    DEBATE_TTL_SECONDS = 60 * 60 * 24 * 30
    # Opinions are kept for 7 days.
    OPINION_TTL_SECONDS = 60 * 60 * 24 * 7

    # Max opinion requests allowed per client in one time window.
    OPINION_RATE_LIMIT = int(os.environ.get("OPINION_RATE_LIMIT", 10))
    # Length of that window, in seconds.
    OPINION_RATE_WINDOW_SECONDS = int(os.environ.get("OPINION_RATE_WINDOW_SECONDS", 60))
    # Site-wide cap per hour on opinion requests: protects the LLM quota even if every visitor appears
    # to share one IP (a proxy that hides client addresses). 0 disables it.
    # Max opinion requests per hour across ALL visitors combined.
    OPINION_GLOBAL_LIMIT_PER_HOUR = int(os.environ.get("OPINION_GLOBAL_LIMIT_PER_HOUR", 300))
    # Only honour X-Forwarded-For when running behind a trusted proxy (ALB/CloudFront).
    # Whether to believe the X-Forwarded-For header to find the real client IP.
    TRUST_PROXY_HEADERS = _bool("TRUST_PROXY_HEADERS", False)
    # Proxies between the client and this app (ALB = 1, CloudFront + ALB = 2). The client IP is
    # the Nth entry from the right of X-Forwarded-For; entries further left are client-controlled.
    # How many proxies sit in front of the app (used to pick the right IP from the header).
    TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", 1))

    # Websites allowed to call this API from a browser: split the comma-separated value, trim each, drop blanks.
    CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]


# Create the single shared settings object the rest of the app imports.
settings = Settings()

# The five analyst names; used to validate the model's bias-score output.
PERSONA_KEYS = ("left", "right", "economist", "geopolitical", "devil")


# A thin wrapper around the Groq client so every LLM call goes through one place.
class _LLMWrapper:
    """Thin Groq client. The client is created on first use so importing this
    module (tests, tooling) needs no API key."""

    # Runs when the wrapper is created.
    def __init__(self) -> None:
        # Start with no client; it is built lazily on the first real call.
        self._client: Groq | None = None

    # Returns the Groq client, creating it the first time it is needed.
    def _get_client(self):
        # Only build it if we have not already.
        if self._client is None:
            # Import here so merely importing this file does not need the groq package loaded.
            from groq import Groq

            # Refuse to continue without an API key, with a clear message.
            if not settings.GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY is not set")
            # Build the client with our key, timeout and retry settings.
            self._client = Groq(
                api_key=settings.GROQ_API_KEY,
                timeout=settings.GROQ_TIMEOUT_SECONDS,
                max_retries=settings.GROQ_MAX_RETRIES,
            )
        # Hand back the (possibly just created) client.
        return self._client

    # Sends one prompt to the model and returns its text answer.
    def invoke(self, system: str, user: str, max_tokens: int = 1024, fast: bool = False) -> str:
        # Choose the fast model or the main model.
        model = settings.GROQ_MODEL_FAST if fast else settings.GROQ_MODEL_MAIN
        # Extra options to pass to the API (filled in below when needed).
        kwargs: dict = {}
        # "gpt-oss" models think before answering, so they need special settings.
        if "gpt-oss" in model:
            # Use little thinking effort to save time and tokens.
            kwargs["reasoning_effort"] = "low"
            # Do not return the hidden reasoning text.
            kwargs["include_reasoning"] = False
            # Allow extra tokens because thinking uses part of the budget.
            max_tokens += settings.REASONING_TOKEN_HEADROOM
        # Make the actual API call to the chat-completions endpoint.
        response = self._get_client().chat.completions.create(
            # Which model to use.
            model=model,
            # Maximum length of the answer.
            max_tokens=max_tokens,
            # The conversation: instructions (system) first, then the actual request (user).
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Add the optional settings from above.
            **kwargs,
        )
        # Take the first answer's text (or "" if missing) and trim surrounding spaces.
        content = (response.choices[0].message.content or "").strip()
        # An empty answer is treated as an error instead of silently returning "".
        if not content:
            raise RuntimeError(f"Empty completion from {model} (finish_reason={response.choices[0].finish_reason})")
        # Return the model's text.
        return content


# The single shared LLM wrapper the rest of the app uses.
llm = _LLMWrapper()
