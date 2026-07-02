"""Smoke tests for channel_fetch (run manually: python test_channel.py)."""

from channel_fetch import fetch_channel_videos, search_channel_videos

CHANNEL = "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # Google Developers
QUERY = "flutter"


def test_fetch_newest():
    data = fetch_channel_videos(CHANNEL, sort="newest")
    assert data["videoCount"] > 0
    assert data["videos"][0]["title"]
    print(f"newest: {data['videoCount']} videos, first={data['videos'][0]['title'][:40]}")


def test_fetch_oldest():
    data = fetch_channel_videos(CHANNEL, sort="oldest")
    assert data["videoCount"] > 0
    print(f"oldest: {data['videoCount']} videos")


def test_search_in_channel():
    data = search_channel_videos(CHANNEL, QUERY, limit=5)
    assert data["videoCount"] > 0
    print(f"search: {data['videoCount']} hits for {QUERY!r}")


if __name__ == "__main__":
    test_fetch_newest()
    test_fetch_oldest()
    test_search_in_channel()
    print("ok")
