from contextlib import contextmanager

from ..config import settings

try:
    import langsmith
except ImportError:
    langsmith = None


@contextmanager
def trace_run(name: str, tags: list[str]):
    if not settings.LANGCHAIN_API_KEY or langsmith is None:
        yield
        return
    with langsmith.trace(name, tags=tags):
        yield
