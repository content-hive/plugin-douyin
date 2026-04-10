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


def extract_first_url(source: Any) -> Optional[str]:
    """Return the first non-empty URL from a url_list dict, a list, or a plain string."""
    if isinstance(source, dict):
        url_list = source.get("url_list")
        if isinstance(url_list, list) and url_list:
            first = url_list[0]
            return first if isinstance(first, str) and first else None
    elif isinstance(source, list) and source:
        first = source[0]
        return first if isinstance(first, str) and first else None
    elif isinstance(source, str) and source:
        return source
    return None


def pick_first_url(*sources: Any) -> Optional[str]:
    """Return the first non-empty URL found across multiple sources."""
    for src in sources:
        url = extract_first_url(src)
        if url:
            return url
    return None


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
