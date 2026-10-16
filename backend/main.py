import logging  # Python's built-in logging system
from contextlib import asynccontextmanager  # turns a function into a start-up/shutdown context for the app

from fastapi import FastAPI, HTTPException, Request  # the web framework, error response, and request type
from fastapi.middleware.cors import CORSMiddleware  # adds the headers that let browsers call this API cross-site
from fastapi.responses import JSONResponse  # lets us build a JSON response by hand
from redis.exceptions import RedisError  # the error type Redis raises when it fails

from .config import settings  # the shared app settings
from .logging_config import configure_logging  # sets up log formatting
from .routers import admin, debate, opinion, ws  # the groups of endpoints
from .scheduler import start_scheduler, stop_scheduler  # start and stop the daily job
from .services.redis_service import ping, rebuild_index_if_empty  # Redis helpers used at start-up and for health

# Set up logging once, as soon as the app module loads.
configure_logging()
# A logger named after this module.
logger = logging.getLogger(__name__)


# Code that runs when the app starts (before "yield") and when it stops (after "yield").
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Start-up step 1: make sure the Redis index exists (guarded so a Redis outage does not stop the app).
    try:
        # Rebuild the index if it is empty; returns how many debates were indexed.
        added = await rebuild_index_if_empty()
        # Mention it in the logs if anything was indexed.
        if added:
            logger.info("Indexed %d existing debates", added)
    # Redis could not be reached: log it and keep starting (the readiness check will report it).
    except Exception:
        logger.exception("Could not reach Redis at startup; continuing (see /health/ready)")
    # Start-up step 2: start the daily job.
    start_scheduler()
    # The app runs while execution is paused here.
    yield
    # Shutdown: stop the daily job.
    stop_scheduler()


# Create the web application and attach the start-up/shutdown code.
app = FastAPI(title="News Debate System", lifespan=lifespan)

# Add CORS: rules about which websites may call this API from a browser.
app.add_middleware(
    CORSMiddleware,
    # Only these website addresses are allowed.
    allow_origins=settings.CORS_ORIGINS,
    # Only these HTTP methods are allowed.
    allow_methods=["GET", "POST", "OPTIONS"],
    # Only this request header is allowed.
    allow_headers=["Content-Type"],
)

# Attach each group of endpoints to the app.
app.include_router(debate.router)
app.include_router(opinion.router)
app.include_router(ws.router)
app.include_router(admin.router)


# Whenever any Redis error escapes an endpoint, answer with a clean 503 instead of a crash.
@app.exception_handler(RedisError)
async def redis_unavailable(_: Request, exc: RedisError):
    # Log the underlying error.
    logger.error("Redis error: %s", exc)
    # Reply "503 Service Unavailable" with a JSON message.
    return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable"})


# GET /health : is the process alive?
@app.get("/health")
async def health():
    """Liveness: the process is up."""
    # Always "ok" if the app can answer at all.
    return {"status": "ok"}


# GET /health/ready : is the app ready to serve traffic (can it reach Redis)?
@app.get("/health/ready")
async def ready():
    """Readiness: Redis is reachable."""
    try:
        # Send a PING to Redis.
        await ping()
    # Redis did not answer: report "503 Service Unavailable".
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    # Redis answered: we are ready.
    return {"status": "ready"}
