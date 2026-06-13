import re
from datetime import datetime, timezone
from typing import Any, Literal

import yt_dlp

CommentSort = Literal["top", "new"]


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


def normalize_sort(sort: str | None) -> CommentSort:
    value = (sort or "top").lower().strip()
    if value in {"top", "likes", "popular", "top_comments"}:
        return "top"
    return "new"


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
    sort: CommentSort,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch top-level comments using YouTube's sort (top / newest)."""
    # max_comments format: total, parents, replies, replies-per-thread
    parent_cap = min(max(needed_top_level, 1), 200)
    max_spec = f"all,{parent_cap},all,all"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {
                "comment_sort": [sort],
                "max_comments": [max_spec],
            }
        },
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    raw_comments = info.get("comments") or []
    normalized = [_normalize_comment(c) for c in raw_comments if c]
    top_level = _attach_replies(normalized)
    return top_level, info


def fetch_comments(
    video_id_or_url: str,
    offset: int = 0,
    limit: int = 10,
    sort: str | None = "top",
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
    comment_sort = normalize_sort(sort)

    if max_comments is not None and offset == 0 and limit == 10:
        limit = max(1, min(max_comments, 50))

    needed = offset + limit + 1
    top_level, info = _fetch_top_level_comments(url, needed, comment_sort)

    page = top_level[offset : offset + limit]
    has_more = len(top_level) > offset + limit

    return {
        "videoId": video_id,
        "title": info.get("title") or "",
        "channel": info.get("uploader") or info.get("channel") or "Unknown",
        "sort": comment_sort,
        "offset": offset,
        "limit": limit,
        "commentCount": info.get("comment_count") or len(top_level),
        "returnedCount": len(page),
        "hasMore": has_more,
        "totalFetched": len(top_level),
        "comments": page,
    }
