#!/usr/bin/env python3
"""
Fetch a YouTube channel's videos, oldest first.

Usage:
  python oldest_videos.py CHANNEL_ID
  python oldest_videos.py CHANNEL_ID --limit 20
  python oldest_videos.py CHANNEL_ID --dates   # slower, exact upload_date sort
"""

import argparse
import yt_dlp


def get_videos_flat(channel_id):
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    # YouTube lists newest first by default -> reverse for oldest first
    return list(reversed(entries))


def get_videos_with_dates(channel_id):
    """Slower: fetches upload_date for every video, then sorts exactly."""
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    ids = [e["id"] for e in (info.get("entries") or [])]

    full_opts = {"quiet": True, "skip_download": True}
    videos = []
    with yt_dlp.YoutubeDL(full_opts) as ydl:
        for vid in ids:
            try:
                d = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                videos.append({
                    "id": vid,
                    "title": d.get("title"),
                    "upload_date": d.get("upload_date"),
                })
            except Exception as e:
                print(f"skip {vid}: {e}")

    videos.sort(key=lambda v: v.get("upload_date") or "99999999")
    return videos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("channel_id")
    p.add_argument("--limit", type=int, default=0, help="max videos to print (0 = all)")
    p.add_argument("--dates", action="store_true", help="exact sort by upload_date (slow)")
    args = p.parse_args()

    videos = get_videos_with_dates(args.channel_id) if args.dates else get_videos_flat(args.channel_id)

    if args.limit:
        videos = videos[:args.limit]

    for v in videos:
        vid = v.get("id")
        title = v.get("title")
        date = v.get("upload_date", "")
        print(f"{date}\t{vid}\t{title}\thttps://www.youtube.com/watch?v={vid}")


if __name__ == "__main__":
    main()