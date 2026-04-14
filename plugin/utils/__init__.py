"""Utility helpers for the Douyin parser plugin."""

from typing import Any, Optional


def parse_cookie_string(raw: str) -> dict[str, str]:
    """Parse a browser cookie string (e.g. 'k1=v1; k2=v2') into a dict."""
    if not raw or not isinstance(raw, str):
        return {}
    result: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            result[key.strip()] = value.strip()
    return result


def extract_all_urls(source: Any) -> list[str]:
    """Return all non-empty URLs from a url_list dict, a list, or a plain string."""
    if isinstance(source, dict):
        url_list = source.get("url_list")
        if isinstance(url_list, list):
            return [u for u in url_list if isinstance(u, str) and u]
    elif isinstance(source, list):
        return [u for u in source if isinstance(u, str) and u]
    elif isinstance(source, str) and source:
        return [source]
    return []


def extract_video_urls(video: dict) -> list[str]:
    """Extract video URLs from a video dict, returning all available URLs.

    Prefers the highest-quality stream from bit_rate entries; falls back to
    play_addr.  Returns a list where the first element is the preferred URL
    and the rest are fallbacks.  Returns an empty list when no playable URL
    is found.
    """
    bit_rates = video.get("bit_rate") or []

    def score(stream: dict) -> tuple:
        play = stream.get("play_addr") or {}
        height = play.get("height") or 0
        fps = stream.get("FPS", 0)
        is_mp4 = 1 if stream.get("format") == "mp4" else 0
        is_h265 = stream.get("is_h265", 0)
        bitrate = stream.get("bit_rate", 0)

        return (
            height,    # higher resolution is better
            fps,       # higher frame rate is better
            is_mp4,    # prefer mp4 over dash (single file, no separate audio stream)
            is_h265,   # H.265 offers better compression efficiency
            bitrate,   # higher bitrate is better
        )

    best_stream = None
    if bit_rates:
        valid_streams = [br for br in bit_rates if (br.get("play_addr") or {}).get("url_list")]
        if valid_streams:
            valid_streams.sort(key=score, reverse=True)
            best_stream = valid_streams[0]

    if best_stream:
        play_addr = best_stream.get("play_addr") or {}
    else:
        play_addr = video.get("play_addr") or {}

    url_list = [u for u in (play_addr.get("url_list") or []) if u]
    if not url_list:
        return []

    if not best_stream:
        url_list.sort(key=lambda u: 0 if "watermark=0" in u else 1)

    return url_list


def extract_image_urls(item: dict) -> list[str]:
    """Extract all unique image URLs from a gallery item.

    Collects URLs from url_list first, then download_url_list as supplements.
    Returns a list where the first element is the preferred URL and the
    rest are fallbacks. Returns an empty list when no URL is found.
    """
    seen: set[str] = set()
    result: list[str] = []
    for src in [item.get("url_list"), item.get("download_url_list")]:
        for u in extract_all_urls(src):
            if u not in seen:
                seen.add(u)
                result.append(u)
    return result


def iter_gallery_items(aweme: dict) -> list:
    """Return the list of image/gallery items from an aweme dict."""
    image_post = aweme.get("image_post_info")
    if isinstance(image_post, dict):
        for key in ("images", "image_list"):
            candidate = image_post.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
    images = aweme.get("images") or aweme.get("image_list") or []
    return images if isinstance(images, list) else []
