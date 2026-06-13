import re
from datetime import datetime, timezone
from typing import Any

import yt_dlp


def extract_video_id(video_id_or_url: str) -> str:
    text = video_id_or_url.strip()
    match = re.search(
        r"(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})",
        text,
    )
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", text):
        return text
    return text


def _format_timestamp(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        value = int(ts)
        return (
            datetime.fromtimestamp(value, tz=timezone.utc)
            .strftime("%Y-%m-%d")
        )
    except (TypeError, ValueError, OSError):
        return None


def _normalize_comment(raw: dict[str, Any]) -> dict[str, Any]:
    parent = raw.get("parent")
    parent_id = None if parent in (None, "root") else str(parent)

    return {
        "id": str(raw.get("id") or ""),
        "parentId": parent_id,
        "author": raw.get("author") or "Unknown",
        "authorId": raw.get("author_id"),
        "text": raw.get("text") or "",
        "likeCount": int(raw.get("like_count") or 0),
        "publishedTime": raw.get("_time_text") or _format_timestamp(
            raw.get("timestamp")
        ),
        "publishedTimestamp": raw.get("timestamp"),
        "isPinned": bool(raw.get("is_pinned")),
        "isHearted": bool(raw.get("is_favorited")),
        "authorIsUploader": bool(raw.get("author_is_uploader")),
        "authorIsVerified": bool(raw.get("author_is_verified")),
        "replies": [],
    }


def _attach_replies(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {c["id"]: c for c in comments if c["id"]}
    top_level: list[dict[str, Any]] = []

    for comment in comments:
        parent_id = comment.get("parentId")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["replies"].append(comment)
        else:
            top_level.append(comment)

    for comment in top_level:
        comment["replyCount"] = len(comment.get("replies") or [])

    return top_level


def _fetch_top_level_comments(
    url: str,
    needed_top_level: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch enough yt-dlp comments to cover `needed_top_level` top-level items."""
    fetch_max = min(max(needed_top_level * 3, 20), 200)
    info: dict[str, Any] = {}
    top_level: list[dict[str, Any]] = []

    while fetch_max <= 200:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "getcomments": True,
            "extractor_args": {"youtube": {"max_comments": [str(fetch_max)]}},
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        raw_comments = info.get("comments") or []
        normalized = [_normalize_comment(c) for c in raw_comments if c]
        top_level = _attach_replies(normalized)

        if len(top_level) >= needed_top_level:
            break
        if len(raw_comments) < fetch_max:
            break
        if fetch_max >= 200:
            break

        fetch_max = min(fetch_max + needed_top_level * 2, 200)

    return top_level, info


def fetch_comments(
    video_id_or_url: str,
    offset: int = 0,
    limit: int = 10,
    max_comments: int | None = None,
) -> dict[str, Any]:
    video_id = extract_video_id(video_id_or_url)
    url = (
        video_id_or_url
        if video_id_or_url.startswith("http")
        else f"https://www.youtube.com/watch?v={video_id}"
    )

    offset = max(0, offset)
    limit = max(1, min(limit, 50))

    # Backwards compatibility for older clients using `max` only.
    if max_comments is not None and offset == 0 and limit == 10:
        limit = max(1, min(max_comments, 50))

    needed = offset + limit + 1
    top_level, info = _fetch_top_level_comments(url, needed)

    page = top_level[offset : offset + limit]
    has_more = len(top_level) > offset + limit

    return {
        "videoId": video_id,
        "title": info.get("title") or "",
        "channel": info.get("uploader") or info.get("channel") or "Unknown",
        "offset": offset,
        "limit": limit,
        "commentCount": info.get("comment_count") or len(top_level),
        "returnedCount": len(page),
        "hasMore": has_more,
        "totalFetched": len(top_level),
        "comments": page,
    }
