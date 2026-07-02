import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yt_dlp


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


def _format_views(count: Any) -> str:
    if count is None:
        return ""
    try:
        n = int(count)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B views"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K views"
    return f"{n} views"


def normalize_channel_ref(channel: str) -> str:
    text = channel.strip()
    if not text:
        raise ValueError("Channel id or URL is required")

    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        path = parsed.path.strip("/")
        if not path:
            raise ValueError("Invalid channel URL")
        first = path.split("/")[0]
        if first.startswith("@"):
            return first
        if first == "channel" and len(path.split("/")) >= 2:
            return f"channel/{path.split('/')[1]}"
        return path

    if text.startswith("@"):
        return text

    if re.fullmatch(r"UC[\w-]{22}", text):
        return f"channel/{text}"

    return text


def channel_base_url(channel_ref: str) -> str:
    ref = normalize_channel_ref(channel_ref)
    if ref.startswith("@"):
        return f"https://www.youtube.com/{ref}"
    if ref.startswith("channel/"):
        return f"https://www.youtube.com/{ref}"
    return f"https://www.youtube.com/channel/{ref}"


def _channel_videos_url(channel: str) -> str:
    return f"{channel_base_url(channel)}/videos"


def _channel_search_url(channel: str, query: str) -> str:
    base = channel_base_url(channel)
    return f"{base}/search?query={urllib.parse.quote(query.strip())}"


def _ydl_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def _video_detail_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def _fetch_video_details(video_url: str) -> dict[str, Any]:
    try:
        with yt_dlp.YoutubeDL(_video_detail_opts()) as ydl:
            info = ydl.extract_info(video_url, download=False)
        upload_date = _format_upload_date(
            info.get("upload_date") or info.get("release_date")
        )
        view_count = info.get("view_count")
        return {
            "uploadDateRaw": upload_date,
            "viewCount": view_count,
            "viewsText": _format_views(view_count),
            "description": info.get("description") or "",
        }
    except Exception as exc:
        print(f"video detail fetch failed for {video_url}: {exc}")
        return {}


def _enrich_videos(videos: list[dict[str, Any]], max_workers: int = 6) -> None:
    if not videos:
        return

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_video_details, video["url"]): idx
            for idx, video in enumerate(videos)
        }
        for future in as_completed(futures):
            idx = futures[future]
            details = future.result()
            if details:
                videos[idx].update(details)


def _sort_videos_by_date(videos: list[dict[str, Any]], *, sort: str) -> None:
    if sort == "oldest":
        videos.sort(key=lambda v: v.get("uploadDateRaw") or "9999-99-99")
    else:
        videos.sort(
            key=lambda v: v.get("uploadDateRaw") or "0000-00-00",
            reverse=True,
        )


def _entry_to_video(entry: dict[str, Any], channel_author: str) -> dict[str, Any] | None:
    video_id = entry.get("id")
    if not video_id:
        return None
    video_id = str(video_id)
    if video_id.startswith(("PL", "UC", "LL", "RD", "FL")):
        return None

    duration = entry.get("duration")
    upload_date = _format_upload_date(
        entry.get("upload_date") or entry.get("release_date")
    )

    return {
        "id": video_id,
        "title": entry.get("title") or "",
        "author": _normalize_author(
            entry.get("uploader") or entry.get("channel") or channel_author
        ),
        "url": entry.get("url")
        or entry.get("webpage_url")
        or f"https://www.youtube.com/watch?v={video_id}",
        "thumbnailUrl": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        "durationSeconds": int(duration) if duration is not None else None,
        "uploadDateRaw": upload_date,
        "viewCount": entry.get("view_count"),
        "viewsText": _format_views(entry.get("view_count")),
        "description": entry.get("description") or "",
    }


def _extract_videos(info: dict[str, Any]) -> tuple[str, str, str, list[dict[str, Any]]]:
    channel_author = _normalize_author(
        info.get("uploader") or info.get("channel") or info.get("title")
    )
    channel_id = str(info.get("channel_id") or info.get("id") or "")
    thumbnails = info.get("thumbnails") or []
    channel_thumb = ""
    if thumbnails:
        channel_thumb = thumbnails[-1].get("url") or ""

    videos: list[dict[str, Any]] = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        item = _entry_to_video(entry, channel_author)
        if item is not None:
            videos.append(item)

    return channel_id, channel_author, channel_thumb, videos


def fetch_channel_videos(channel: str, *, sort: str = "newest") -> dict[str, Any]:
    sort_key = "oldest" if sort == "oldest" else "newest"
    url = _channel_videos_url(channel)

    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    channel_id, channel_name, channel_thumb, videos = _extract_videos(info)
    if not videos:
        raise ValueError("No videos found in channel")

    # YouTube lists newest first; reverse gives a fast oldest-first approximation
    # before per-video enrichment (same approach as test.py get_videos_flat).
    if sort_key == "oldest":
        videos.reverse()

    _enrich_videos(videos)
    _sort_videos_by_date(videos, sort=sort_key)

    return {
        "channelId": channel_id,
        "channelName": channel_name,
        "channelThumbnail": channel_thumb,
        "sort": sort_key,
        "videoCount": len(videos),
        "videos": videos,
    }


def search_channel_videos(
    channel: str,
    query: str,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    q = query.strip()
    if not q:
        raise ValueError("Search query is required")

    url = _channel_search_url(channel, q)

    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    channel_id, channel_name, channel_thumb, videos = _extract_videos(info)
    if limit > 0:
        videos = videos[:limit]

    return {
        "channelId": channel_id,
        "channelName": channel_name,
        "channelThumbnail": channel_thumb,
        "query": q,
        "videoCount": len(videos),
        "videos": videos,
    }
