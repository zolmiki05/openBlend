import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import apple_music, auth, llm_audit, pipeline, playlist, spotify
from app.routers import settings as settings_router
from app.routers import validation
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="OpenBlend API",
    description="Cross-platform shared playlist engine for Spotify and Apple Music",
    version="0.1.0-dev",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(spotify.router)
app.include_router(apple_music.router)
app.include_router(pipeline.router)
app.include_router(playlist.router)
app.include_router(llm_audit.router)
app.include_router(settings_router.router)
app.include_router(validation.router)


@app.on_event("startup")
def on_startup() -> None:
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


@app.get("/health")
def health():
    return {"status": "ok"}
