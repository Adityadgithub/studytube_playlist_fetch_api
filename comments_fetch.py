import logging
import re
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

import yt_dlp

CommentSort = Literal["top", "new"]

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 20 * 60
# yt-dlp has no offset API — we cap how many top-level threads it walks per request.
_MAX_YT_DLP_COMMENTS = 200
_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_CACHE_LOCK = Lock()


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

    reply_count = raw.get("reply_count")
    if reply_count is None:
        reply_count = 0

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
        "_replyCountHint": int(reply_count) if reply_count else 0,
    }


def _attach_replies(
    comments: list[dict[str, Any]],
    *,
    include_replies: bool,
) -> list[dict[str, Any]]:
    if not include_replies:
        top_level = [c for c in comments if not c.get("parentId")]
        for comment in top_level:
            comment["replyCount"] = int(comment.pop("_replyCountHint", 0) or 0)
        return top_level

    by_id = {c["id"]: c for c in comments if c["id"]}
    top_level: list[dict[str, Any]] = []

    for comment in comments:
        parent_id = comment.get("parentId")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["replies"].append(comment)
        else:
            top_level.append(comment)

    for comment in top_level:
        nested = len(comment.get("replies") or [])
        hint = int(comment.pop("_replyCountHint", 0) or 0)
        comment["replyCount"] = max(nested, hint)

    return top_level


def _yt_dlp_raw_limit(min_top_level: int) -> int:
    """Single-value max_comments counts replies too — over-fetch for enough parents."""
    return min(max(min_top_level * 4, 40), _MAX_YT_DLP_COMMENTS)


def _fetch_top_level_comments(
    url: str,
    sort: CommentSort,
    min_top_level: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, float]]:
    """Fetch enough raw comments for `min_top_level` top-level threads."""
    min_top_level = max(1, min(min_top_level, _MAX_YT_DLP_COMMENTS))
    raw_limit = _yt_dlp_raw_limit(min_top_level)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {
                "comment_sort": [sort],
                # Single integer is the only format that reliably stops early.
                "max_comments": [str(raw_limit)],
            }
        },
    }

    timings: dict[str, float] = {}

    start = time.time()
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    timings["ytDlpSec"] = round(time.time() - start, 3)

    raw_comments = info.get("comments") or []

    start = time.time()
    normalized = [_normalize_comment(c) for c in raw_comments if c]
    timings["normalizeSec"] = round(time.time() - start, 3)

    start = time.time()
    top_level = _attach_replies(normalized, include_replies=False)
    timings["attachSec"] = round(time.time() - start, 3)

    logger.info(
        "comments fetch need=%s raw_limit=%s yt-dlp=%.3fs normalize=%.3fs "
        "attach=%.3fs raw=%s top_level=%s",
        min_top_level,
        raw_limit,
        timings["ytDlpSec"],
        timings["normalizeSec"],
        timings["attachSec"],
        len(raw_comments),
        len(top_level),
    )

    return top_level, info, timings, raw_limit


def _get_cached_entry(video_id: str, sort: CommentSort) -> dict[str, Any] | None:
    key = (video_id, sort)
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        if time.time() - entry["fetched_at"] > _CACHE_TTL_SECONDS:
            del _CACHE[key]
            return None
        return entry


def _required_fetch_count(offset: int, limit: int) -> int:
    # +1 so we can tell hasMore without downloading the full thread list.
    return min(offset + limit + 1, _MAX_YT_DLP_COMMENTS)


def _load_comments(
    video_id: str,
    url: str,
    sort: CommentSort,
    min_top_level: int,
) -> dict[str, Any]:
    cached = _get_cached_entry(video_id, sort)
    if cached is not None and len(cached["top_level"]) >= min_top_level:
        cached["cached"] = True
        cached["timings"] = {}
        return cached

    fetch_limit = min(min_top_level, _MAX_YT_DLP_COMMENTS)

    top_level, info, timings, raw_limit = _fetch_top_level_comments(
        url, sort, fetch_limit
    )
    entry = {
        "top_level": top_level,
        "info": info,
        "fetch_limit": fetch_limit,
        "raw_limit": raw_limit,
        "fetched_at": time.time(),
        "cached": False,
        "timings": timings,
    }
    key = (video_id, sort)
    with _CACHE_LOCK:
        _CACHE[key] = entry
    return entry


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

    min_top_level = _required_fetch_count(offset, limit)
    loaded = _load_comments(video_id, url, comment_sort, min_top_level)
    top_level: list[dict[str, Any]] = loaded["top_level"]
    info: dict[str, Any] = loaded["info"]
    fetch_limit = int(loaded.get("fetch_limit") or len(top_level))
    raw_limit = int(loaded.get("raw_limit") or 0)

    page = top_level[offset : offset + limit]
    has_more = len(top_level) > offset + limit
    if not has_more:
        reported = info.get("comment_count")
        if reported is not None and int(reported) > len(top_level):
            has_more = True
        elif raw_limit and len(top_level) < fetch_limit:
            has_more = True

    result: dict[str, Any] = {
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
        "cached": loaded.get("cached", False),
        "comments": page,
    }
    timings = loaded.get("timings")
    if timings:
        result["timings"] = timings
    return result


def clear_comment_cache() -> int:
    with _CACHE_LOCK:
        count = len(_CACHE)
        _CACHE.clear()
        return count
