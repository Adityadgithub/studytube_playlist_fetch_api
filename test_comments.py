"""Temporary test: can yt-dlp fetch YouTube video comments?"""
import json
import sys

import yt_dlp

TEST_URL = "https://www.youtube.com/watch?v=m3fg2PRY1u4"


def fetch_comments(video_url: str, max_comments: int = 10) -> list[dict]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {"youtube": {"max_comments": [str(max_comments)]}},
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    comments = info.get("comments") or []
    return comments


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else TEST_URL
    print(f"Testing comments for: {url}\n")

    try:
        comments = fetch_comments(url, max_comments=10)
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)

    print(f"Comments returned: {len(comments)}")
    if not comments:
        print("No comments in response.")
        sys.exit(2)

    for i, c in enumerate(comments[:5], start=1):
        print(f"\n--- Comment {i} ---")
        print(f"Author:   {c.get('author')}")
        print(f"Date:     {c.get('_timestamp') or c.get('timestamp')}")
        print(f"Likes:    {c.get('like_count')}")
        print(f"Parent:   {c.get('parent')}")
        text = (c.get("text") or "")[:200]
        print(f"Text:     {text.encode('ascii', 'replace').decode()}")

    print("\nSample raw keys:", list(comments[0].keys())[:15])
    print("\nOK — yt-dlp can fetch comments.")


if __name__ == "__main__":
    main()
