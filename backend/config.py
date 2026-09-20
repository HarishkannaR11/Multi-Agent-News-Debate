import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


class Settings:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL_MAIN = os.environ.get("GROQ_MODEL_MAIN", "llama-3.1-70b-versatile")
    GROQ_MODEL_FAST = os.environ.get("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
    GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
    LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "news-debate-system")
    SCHEDULER_HOUR = int(os.environ.get("SCHEDULER_HOUR", 7))
    SCHEDULER_MINUTE = int(os.environ.get("SCHEDULER_MINUTE", 0))
    MAX_NEWS_CONTEXT_CHARS = 8000
    DEBATE_TTL_SECONDS = 60 * 60 * 24 * 30
    OPINION_TTL_SECONDS = 60 * 60 * 24 * 7
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")


settings = Settings()

_client = Groq(api_key=settings.GROQ_API_KEY)


class _LLMWrapper:
    def invoke(self, system: str, user: str, max_tokens: int = 1024) -> str:
        response = _client.chat.completions.create(
            model=settings.GROQ_MODEL_MAIN,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content


llm = _LLMWrapper()
