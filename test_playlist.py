"""Test playlist fetch speed and video count."""
import sys
import time

from playlist_fetch import fetch_playlist

DEFAULT_ID = "PLfqMhTWNBTe137I_EPQd34TsgV6IO55pt"


def main() -> None:
    playlist_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ID
    enrich = "--enrich-dates" in sys.argv

    print(f"Fetching playlist: {playlist_id}")
    print(f"enrich_dates={enrich}\n")

    t0 = time.time()
    try:
        result = fetch_playlist(playlist_id, enrich_dates=enrich)
    except Exception as exc:
        print(f"FAILED in {time.time() - t0:.1f}s: {exc}")
        sys.exit(1)

    elapsed = time.time() - t0
    videos = result.get("videos") or []
    print(f"OK in {elapsed:.1f}s")
    print(f"Title:  {result.get('title')}")
    print(f"Author: {result.get('author')}")
    print(f"Videos: {len(videos)}")
    for v in videos[:3]:
        print(
            f"  - {v.get('id')} | {v.get('title', '')[:50]} | "
            f"date={v.get('uploadDateRaw')}"
        )


if __name__ == "__main__":
    main()
