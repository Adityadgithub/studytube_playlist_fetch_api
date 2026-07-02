"""Smoke tests for channel_fetch (run manually: python test_channel.py)."""

from channel_fetch import fetch_channel_videos, search_channel_videos

CHANNEL = "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # Google Developers
QUERY = "flutter"


def test_fetch_newest_page():
    data = fetch_channel_videos(CHANNEL, sort="newest", limit=10, offset=0)
    assert data["videoCount"] > 0
    assert data["videos"][0]["title"]
    assert data["limit"] == 10
    assert data["offset"] == 0
    print(
        f"newest page: {data['videoCount']} videos, "
        f"total={data['totalCount']}, hasMore={data['hasMore']}"
    )


def test_fetch_oldest_page():
    data = fetch_channel_videos(CHANNEL, sort="oldest", limit=10, offset=0)
    assert data["videoCount"] > 0
    print(
        f"oldest page: {data['videoCount']} videos, "
        f"total={data['totalCount']}, hasMore={data['hasMore']}"
    )


def test_search_in_channel():
    data = search_channel_videos(CHANNEL, QUERY, limit=5)
    assert data["videoCount"] > 0
    print(f"search: {data['videoCount']} hits for {QUERY!r}")


if __name__ == "__main__":
    test_fetch_newest_page()
    test_fetch_oldest_page()
    test_search_in_channel()
    print("ok")
