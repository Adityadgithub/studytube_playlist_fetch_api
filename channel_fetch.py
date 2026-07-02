import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yt_dlp

_CACHE_TTL_SEC = 15 * 60
# channel ref -> (expires_at, total video count)
_COUNT_CACHE: dict[str, tuple[float, int]] = {}
# channel ref -> (expires_at, reversed video list) — fallback when tail slice fails
_OLDEST_LIST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


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


def _ydl_opts(
    *,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
    playlist_items: str | None = None,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    if playlist_items:
        opts["playlist_items"] = playlist_items
    else:
        if playlist_start is not None and playlist_start > 0:
            opts["playliststart"] = playlist_start
        if playlist_end is not None and playlist_end > 0:
            opts["playlistend"] = playlist_end
    return opts


def _video_detail_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def _extract_info(
    url: str,
    *,
    playlist_start: int | None = None,
    playlist_end: int | None = None,
    playlist_items: str | None = None,
) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(
        _ydl_opts(
            playlist_start=playlist_start,
            playlist_end=playlist_end,
            playlist_items=playlist_items,
        )
    ) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("Failed to extract channel videos")
    return info


def _total_from_info(info: dict[str, Any], fallback: int) -> int:
    raw = info.get("playlist_count")
    if raw is not None:
        try:
            return max(int(raw), fallback)
        except (TypeError, ValueError):
            pass
    return fallback


def _cache_get_count(channel_ref: str) -> int | None:
    key = normalize_channel_ref(channel_ref)
    entry = _COUNT_CACHE.get(key)
    if not entry:
        return None
    expires_at, total = entry
    if time.time() > expires_at:
        _COUNT_CACHE.pop(key, None)
        return None
    return total


def _cache_set_count(channel_ref: str, total: int) -> None:
    key = normalize_channel_ref(channel_ref)
    _COUNT_CACHE[key] = (time.time() + _CACHE_TTL_SEC, total)


def _cache_get_oldest_list(channel_ref: str) -> dict[str, Any] | None:
    key = normalize_channel_ref(channel_ref)
    entry = _OLDEST_LIST_CACHE.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _OLDEST_LIST_CACHE.pop(key, None)
        return None
    return payload


def _cache_set_oldest_list(channel_ref: str, payload: dict[str, Any]) -> None:
    key = normalize_channel_ref(channel_ref)
    _OLDEST_LIST_CACHE[key] = (time.time() + _CACHE_TTL_SEC, payload)


def _playlist_items_for_oldest(offset: int, limit: int) -> str:
    """yt-dlp negative indices: last N entries from the channel (the oldest videos)."""
    far = offset + limit
    near = offset + 1
    if near <= 1:
        return f"-{far}:"
    return f"-{far}:-{near}"


def _fetch_oldest_from_full_list(
    channel: str,
    *,
    limit: int,
    offset: int,
) -> tuple[str, str, str, list[dict[str, Any]], int, bool]:
    cached = _cache_get_oldest_list(channel)
    if cached:
        all_videos = cached["videos"]
    else:
        url = _channel_videos_url(channel)
        info = _extract_info(url)
        channel_id, channel_name, channel_thumb, all_videos = _extract_videos(info)
        if not all_videos:
            raise ValueError("No videos found in channel")
        all_videos.reverse()
        _cache_set_oldest_list(
            channel,
            {
                "channelId": channel_id,
                "channelName": channel_name,
                "channelThumbnail": channel_thumb,
                "videos": all_videos,
            },
        )
        cached = _cache_get_oldest_list(channel)
        assert cached is not None

    all_videos = cached["videos"]
    return (
        cached["channelId"],
        cached["channelName"],
        cached["channelThumbnail"],
        all_videos[offset : offset + limit],
        len(all_videos),
        True,
    )


def _fetch_oldest_page(
    channel: str,
    *,
    limit: int,
    offset: int,
) -> tuple[str, str, str, list[dict[str, Any]], int, bool]:
    """Fetch oldest videos: tail slice via yt-dlp negative indices, else full-list cache."""
    url = _channel_videos_url(channel)
    items = _playlist_items_for_oldest(offset, limit)

    try:
        info = _extract_info(url, playlist_items=items)
        channel_id, channel_name, channel_thumb, videos = _extract_videos(info)
        if videos:
            videos.reverse()
            if offset == 0:
                probe = _extract_info(url, playlist_start=1, playlist_end=1)
                _, _, _, newest_head = _extract_videos(probe)
                if newest_head and videos[0]["id"] == newest_head[0]["id"]:
                    print(
                        "oldest tail-slice matched newest head; "
                        "using full-list cache"
                    )
                    return _fetch_oldest_from_full_list(
                        channel, limit=limit, offset=offset
                    )
            playlist_count_known = info.get("playlist_count") is not None
            total = _total_from_info(info, offset + len(videos))
            if playlist_count_known:
                _cache_set_count(channel, total)
            return (
                channel_id,
                channel_name,
                channel_thumb,
                videos,
                total,
                playlist_count_known,
            )
    except Exception as exc:
        print(f"oldest tail-slice fetch failed: {exc}")

    return _fetch_oldest_from_full_list(channel, limit=limit, offset=offset)


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


def _build_response(
    *,
    channel_id: str,
    channel_name: str,
    channel_thumb: str,
    sort_key: str,
    videos: list[dict[str, Any]],
    limit: int,
    offset: int,
    total_count: int,
    playlist_count_known: bool,
) -> dict[str, Any]:
    page_end = offset + len(videos)
    if len(videos) < limit:
        has_more = False
    elif page_end < total_count:
        has_more = True
    else:
        has_more = not playlist_count_known and len(videos) == limit

    return {
        "channelId": channel_id,
        "channelName": channel_name,
        "channelThumbnail": channel_thumb,
        "sort": sort_key,
        "limit": limit,
        "offset": offset,
        "totalCount": total_count,
        "hasMore": has_more,
        "videoCount": len(videos),
        "videos": videos,
    }


def fetch_channel_videos(
    channel: str,
    *,
    sort: str = "newest",
    limit: int = 30,
    offset: int = 0,
    enrich: bool = False,
) -> dict[str, Any]:
    sort_key = "oldest" if sort == "oldest" else "newest"
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    playlist_count_known = False

    if sort_key == "newest":
        url = _channel_videos_url(channel)
        info = _extract_info(
            url,
            playlist_start=offset + 1,
            playlist_end=offset + limit,
        )
        channel_id, channel_name, channel_thumb, videos = _extract_videos(info)
        if not videos and offset == 0:
            raise ValueError("No videos found in channel")
        playlist_count_known = info.get("playlist_count") is not None
        total_count = _total_from_info(info, offset + len(videos))
        if playlist_count_known:
            _cache_set_count(channel, total_count)
    else:
        (
            channel_id,
            channel_name,
            channel_thumb,
            videos,
            total_count,
            playlist_count_known,
        ) = _fetch_oldest_page(channel, limit=limit, offset=offset)
        if not videos and offset == 0:
            raise ValueError("No videos found in channel")

    if enrich and videos:
        _enrich_videos(videos)
        _sort_videos_by_date(videos, sort=sort_key)

    return _build_response(
        channel_id=channel_id,
        channel_name=channel_name,
        channel_thumb=channel_thumb,
        sort_key=sort_key,
        videos=videos,
        limit=limit,
        offset=offset,
        total_count=total_count,
        playlist_count_known=playlist_count_known,
    )


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
