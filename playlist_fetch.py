import re
from typing import Any

import yt_dlp


def extract_playlist_id(playlist_id_or_url: str) -> str:
    text = playlist_id_or_url.strip()
    match = re.search(r"list=([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    return text


def _format_upload_date(upload_date: Any) -> str | None:
    if not upload_date:
        return None
    text = str(upload_date)
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _normalize_author(name: str | None) -> str:
    if not name:
        return "Unknown"
    trimmed = name.strip()
    if trimmed.lower().startswith("by "):
        return trimmed[3:].strip()
    return trimmed


def fetch_playlist(playlist_id_or_url: str) -> dict[str, Any]:
    playlist_id = extract_playlist_id(playlist_id_or_url)
    url = (
        playlist_id_or_url
        if playlist_id_or_url.startswith("http")
        else f"https://www.youtube.com/playlist?list={playlist_id}"
    )

    # Full metadata in one call (includes upload_date). Slower than extract_flat.
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15,
        "ignoreerrors": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    playlist_author = _normalize_author(
        info.get("uploader") or info.get("channel") or info.get("channel_id")
    )

    videos: list[dict[str, Any]] = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id:
            continue

        duration = entry.get("duration")
        upload_date = _format_upload_date(
            entry.get("upload_date") or entry.get("release_date")
        )

        videos.append(
            {
                "id": video_id,
                "title": entry.get("title") or "",
                "author": _normalize_author(
                    entry.get("uploader")
                    or entry.get("channel")
                    or playlist_author
                ),
                "url": entry.get("url")
                or entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={video_id}",
                "thumbnailUrl": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                "durationSeconds": int(duration) if duration is not None else None,
                "uploadDateRaw": upload_date,
            }
        )

    if not videos:
        raise ValueError("No videos found in playlist")

    return {
        "id": playlist_id,
        "title": info.get("title") or "Untitled Playlist",
        "author": playlist_author,
        "videoCount": len(videos),
        "videos": videos,
    }
