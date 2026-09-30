import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    # llama-3.1-70b-versatile / llama-3.3-70b-versatile / llama-3.1-8b-instant are
    # deprecated on Groq; check https://console.groq.com/docs/deprecations before changing.
    GROQ_MODEL_MAIN = os.environ.get("GROQ_MODEL_MAIN", "openai/gpt-oss-120b")
    GROQ_MODEL_FAST = os.environ.get("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
    GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", 60))
    # gpt-oss models spend part of max_tokens on hidden reasoning, so give them headroom.
    REASONING_TOKEN_HEADROOM = int(os.environ.get("REASONING_TOKEN_HEADROOM", 1024))
    NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
    GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
    LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "counterpoint")

    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", True)
    SCHEDULER_HOUR = int(os.environ.get("SCHEDULER_HOUR", 7))
    SCHEDULER_MINUTE = int(os.environ.get("SCHEDULER_MINUTE", 0))
    SCHEDULER_TIMEZONE = os.environ.get("SCHEDULER_TIMEZONE", "UTC")
    DAILY_RUN_ATTEMPTS = int(os.environ.get("DAILY_RUN_ATTEMPTS", 3))
    DAILY_RUN_RETRY_SECONDS = float(os.environ.get("DAILY_RUN_RETRY_SECONDS", 60))
    # Shared secret for POST /internal/run-daily (EventBridge, cron, manual). Empty = endpoint disabled.
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

    # Guardrails load torch/transformers models; turn off only for local dev/tests.
    GUARDRAILS_ENABLED = _bool("GUARDRAILS_ENABLED", True)
    MAX_REBUTTAL_RETRIES = int(os.environ.get("MAX_REBUTTAL_RETRIES", 2))
    GRAPH_RECURSION_LIMIT = int(os.environ.get("GRAPH_RECURSION_LIMIT", 25))

    MAX_NEWS_CONTEXT_CHARS = 8000
    MAX_OPINION_CHARS = int(os.environ.get("MAX_OPINION_CHARS", 1000))
    DEBATE_TTL_SECONDS = 60 * 60 * 24 * 30
    OPINION_TTL_SECONDS = 60 * 60 * 24 * 7

    OPINION_RATE_LIMIT = int(os.environ.get("OPINION_RATE_LIMIT", 10))
    OPINION_RATE_WINDOW_SECONDS = int(os.environ.get("OPINION_RATE_WINDOW_SECONDS", 60))
    # Only honour X-Forwarded-For when running behind a trusted proxy (ALB/CloudFront).
    TRUST_PROXY_HEADERS = _bool("TRUST_PROXY_HEADERS", False)
    # Proxies between the client and this app (ALB = 1, CloudFront + ALB = 2). The client IP is
    # the Nth entry from the right of X-Forwarded-For; entries further left are client-controlled.
    TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", 1))

    CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]


settings = Settings()

PERSONA_KEYS = ("left", "right", "economist", "geopolitical", "devil")


class _LLMWrapper:
    """Thin Groq client. The client is created on first use so importing this
    module (tests, tooling) needs no API key."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq

            if not settings.GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY is not set")
            self._client = Groq(api_key=settings.GROQ_API_KEY, timeout=settings.GROQ_TIMEOUT_SECONDS)
        return self._client

    def invoke(self, system: str, user: str, max_tokens: int = 1024, fast: bool = False) -> str:
        model = settings.GROQ_MODEL_FAST if fast else settings.GROQ_MODEL_MAIN
        kwargs: dict = {}
        if "gpt-oss" in model:
            kwargs["reasoning_effort"] = "low"
            kwargs["include_reasoning"] = False
            max_tokens += settings.REASONING_TOKEN_HEADROOM
        response = self._get_client().chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError(f"Empty completion from {model} (finish_reason={response.choices[0].finish_reason})")
        return content


llm = _LLMWrapper()
