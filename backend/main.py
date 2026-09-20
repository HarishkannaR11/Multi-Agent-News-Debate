from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import debate, opinion, ws
from .scheduler import start_scheduler

app = FastAPI(title="News Debate System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(debate.router)
app.include_router(opinion.router)
app.include_router(ws.router)


@app.on_event("startup")
async def on_startup():
    start_scheduler()
