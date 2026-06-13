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


def fetch_comments(
    video_id_or_url: str,
    max_comments: int = 50,
) -> dict[str, Any]:
    video_id = extract_video_id(video_id_or_url)
    url = (
        video_id_or_url
        if video_id_or_url.startswith("http")
        else f"https://www.youtube.com/watch?v={video_id}"
    )

    max_comments = max(1, min(max_comments, 200))

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {"youtube": {"max_comments": [str(max_comments)]}},
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    raw_comments = info.get("comments") or []
    normalized = [_normalize_comment(c) for c in raw_comments if c]
    top_level = _attach_replies(normalized)

    return {
        "videoId": video_id,
        "title": info.get("title") or "",
        "channel": info.get("uploader") or info.get("channel") or "Unknown",
        "commentCount": len(top_level),
        "totalFetched": len(raw_comments),
        "comments": top_level,
    }
