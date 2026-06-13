import re
from typing import Any

import yt_dlp


def extract_playlist_id(playlist_id_or_url: str) -> str:
    text = playlist_id_or_url.strip()
    match = re.search(r"list=([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
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

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
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
        upload_date = entry.get("upload_date") or entry.get("release_date")
        if upload_date and len(str(upload_date)) == 8:
            # yt-dlp YYYYMMDD -> YYYY-MM-DD
            d = str(upload_date)
            upload_date = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"

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
