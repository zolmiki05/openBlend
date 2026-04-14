import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import apple_music, auth, lastfm, llm_audit, pipeline, playlist, spotify, taste_profile
from app.routers import settings as settings_router
from app.routers import validation, rejected_tracks
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="OpenBlend API",
    description="Cross-platform shared playlist engine for Spotify and Apple Music",
    version="0.1.0-dev",
    lifespan=lifespan,
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
app.include_router(lastfm.router)
app.include_router(pipeline.router)
app.include_router(playlist.router)
app.include_router(llm_audit.router)
app.include_router(settings_router.router)
app.include_router(validation.router)
app.include_router(rejected_tracks.router)
app.include_router(taste_profile.router)


@app.get("/health")
def health():
    return {"status": "ok"}
