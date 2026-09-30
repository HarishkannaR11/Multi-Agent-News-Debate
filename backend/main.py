import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from .config import settings
from .logging_config import configure_logging
from .routers import admin, debate, opinion, ws
from .scheduler import start_scheduler, stop_scheduler
from .services.redis_service import ping, rebuild_index_if_empty

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        added = await rebuild_index_if_empty()
        if added:
            logger.info("Indexed %d existing debates", added)
    except Exception:
        logger.exception("Could not reach Redis at startup; continuing (see /health/ready)")
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="News Debate System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(debate.router)
app.include_router(opinion.router)
app.include_router(ws.router)
app.include_router(admin.router)


@app.exception_handler(RedisError)
async def redis_unavailable(_: Request, exc: RedisError):
    logger.error("Redis error: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable"})


@app.get("/health")
async def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    """Readiness: Redis is reachable."""
    try:
        await ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    return {"status": "ready"}
