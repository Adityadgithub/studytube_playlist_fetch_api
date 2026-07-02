import os

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from playlist_fetch import fetch_playlist
from comments_fetch import fetch_comments
from channel_fetch import fetch_channel_videos, search_channel_videos

API_KEY = os.getenv("PLAYLIST_API_KEY", "").strip()

app = FastAPI(
    title="StudyTube YouTube API",
    description="YouTube playlist, channel videos, and video comments via yt-dlp.",
    version="1.2.0",
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
    enrich_dates: bool = Query(
        False,
        description="Fetch upload dates per video (slow for large playlists)",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_playlist(playlist_id, enrich_dates=enrich_dates)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/playlist")
def get_playlist_by_query(
    list: str = Query(..., description="Playlist ID or full playlist URL"),
    enrich_dates: bool = Query(
        False,
        description="Fetch upload dates per video (slow for large playlists)",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_playlist(list, enrich_dates=enrich_dates)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/comments/{video_id}")
def get_comments_by_id(
    video_id: str,
    offset: int = Query(0, ge=0, description="Number of top-level comments to skip"),
    limit: int = Query(10, ge=1, le=50, description="Comments per page"),
    sort: str = Query(
        "top",
        description="Comment sort: top (most liked) or new (newest first)",
    ),
    max: int | None = Query(
        None,
        ge=1,
        le=200,
        description="Deprecated — use limit instead",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_comments(
            video_id,
            offset=offset,
            limit=limit,
            sort=sort,
            max_comments=max,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/channel/{channel_ref}/videos")
def get_channel_videos(
    channel_ref: str,
    sort: str = Query(
        "newest",
        description="Video order: newest or oldest",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if sort not in {"newest", "oldest"}:
        raise HTTPException(status_code=400, detail="sort must be newest or oldest")
    try:
        return fetch_channel_videos(channel_ref, sort=sort)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/channel/videos")
def get_channel_videos_by_query(
    channel: str = Query(..., description="Channel id, @handle, or channel URL"),
    sort: str = Query(
        "newest",
        description="Video order: newest or oldest",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if sort not in {"newest", "oldest"}:
        raise HTTPException(status_code=400, detail="sort must be newest or oldest")
    try:
        return fetch_channel_videos(channel, sort=sort)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/channel/search")
def get_channel_search(
    channel: str = Query(..., description="Channel id, @handle, or channel URL"),
    q: str = Query(..., description="Search query within the channel"),
    limit: int = Query(50, ge=1, le=200, description="Max videos to return"),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return search_channel_videos(channel, q, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/comments")
def get_comments_by_query(
    v: str = Query(..., description="Video ID or full YouTube URL"),
    offset: int = Query(0, ge=0, description="Number of top-level comments to skip"),
    limit: int = Query(10, ge=1, le=50, description="Comments per page"),
    sort: str = Query(
        "top",
        description="Comment sort: top (most liked) or new (newest first)",
    ),
    max: int | None = Query(
        None,
        ge=1,
        le=200,
        description="Deprecated — use limit instead",
    ),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    try:
        return fetch_comments(
            v,
            offset=offset,
            limit=limit,
            sort=sort,
            max_comments=max,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
