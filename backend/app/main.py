from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import apple_music, auth, pipeline, spotify

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


@app.get("/health")
def health():
    return {"status": "ok"}
