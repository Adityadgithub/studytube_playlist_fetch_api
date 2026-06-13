import os

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from playlist_fetch import fetch_playlist
from comments_fetch import fetch_comments

API_KEY = os.getenv("PLAYLIST_API_KEY", "").strip()

app = FastAPI(
    title="StudyTube YouTube API",
    description="YouTube playlist and video comments via yt-dlp.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_api_key(x_api_key: str | None) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/playlist/{playlist_id}")
def get_playlist_by_id(
    playlist_id: str,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_playlist(playlist_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/playlist")
def get_playlist_by_query(
    list: str = Query(..., description="Playlist ID or full playlist URL"),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_playlist(list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/comments/{video_id}")
def get_comments_by_id(
    video_id: str,
    max: int = Query(50, ge=1, le=200, description="Max comments to fetch"),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_comments(video_id, max_comments=max)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/comments")
def get_comments_by_query(
    v: str = Query(..., description="Video ID or full YouTube URL"),
    max: int = Query(50, ge=1, le=200, description="Max comments to fetch"),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_comments(v, max_comments=max)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
