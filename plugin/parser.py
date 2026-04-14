"""Douyin content parser plugin."""

import re
from typing import Any, Optional

from contenthive.plugins.context import PluginContext
from contenthive.plugins.contracts import (
    MediaType, ParserResultStatus,
    ParserAuthorInfo, ParserMediaInfo, ParserPlatformInfo, ParserResult,
)

from .const import (
    DOMAIN,
    URL_PATTERN,
    GALLERY_AWEME_TYPES,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
)
from .utils import parse_cookie_string, extract_all_urls, extract_video_urls, extract_image_urls, iter_gallery_items

from .api_client import DouyinAPIClient

_AWEME_ID_RE = re.compile(r"/(?:video|note|gallery|slides)/(\d+)")


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = Parser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class Parser:
    """Douyin content parser."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._client: Optional[DouyinAPIClient] = None

    async def async_setup(self):
        """Initialize the API client with cookies from the entry config."""
        raw_cookies = (self.entry.data or {}).get("cookies", "")
        cookies = parse_cookie_string(raw_cookies)
        self._client = DouyinAPIClient(cookies=cookies, logger=self.context.logger)
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    def can_parse(self, data: dict[str, Any]) -> bool:
        """Return True if the URL matches a supported Douyin pattern."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    async def parse(self, data: dict[str, Any]) -> ParserResult:
        """Parse a Douyin URL and return a ParserResult."""
        if not self._client:
            raise RuntimeError("Parser not initialized")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            # Resolve short links (v.douyin.com/…) to canonical douyin.com URLs
            canonical = await self._client.resolve_short_url(url)

            aweme_id = _extract_aweme_id(canonical)
            if not aweme_id:
                raise ValueError(f"Cannot extract aweme_id from URL: {canonical}")

            aweme = await self._client.get_aweme_detail(aweme_id)
            if not aweme:
                raise Exception(f"Failed to fetch aweme detail for {aweme_id}")

            return self._build_result(url, aweme)

        except Exception:
            self.context.logger.exception(f"Failed to parse {url}")
            raise

    def _build_result(self, url: str, aweme: dict) -> ParserResult:
        """Assemble a complete ParserResult from a raw aweme dict."""
        return ParserResult(
            pid=str(aweme["aweme_id"]),
            url=url,
            title=None,
            content=aweme.get("desc") or None,
            media=self._build_media(aweme),
            author=self._build_author(aweme),
            platform=self._build_platform(),
            post_time=aweme.get("create_time") or None,
            parser=DOMAIN,
            state=ParserResultStatus.SUCCESS,
        )
    
    def _detect_media_type(self, aweme: dict) -> str:
        """Return 'gallery' or 'video' based on aweme fields."""
        if aweme.get("image_post_info") or aweme.get("images") or aweme.get("image_list"):
            return "gallery"
        aweme_type = aweme.get("aweme_type")
        if isinstance(aweme_type, int) and aweme_type in GALLERY_AWEME_TYPES:
            return "gallery"
        return "video"

    def _build_media(self, aweme: dict) -> list[ParserMediaInfo]:
        """Build media info list based on aweme content."""
        media_type = self._detect_media_type(aweme)
        if media_type == "video":
            return self._build_video_media(aweme)
        elif media_type == "gallery":
            return self._build_gallery_media(aweme)
        else:
            return []
    
    def _build_video_media(self, aweme: dict) -> list[ParserMediaInfo]:
        """Build a single-item list with the video's ParserMediaInfo."""
        video = aweme.get("video") or {}
        width = video.get("width")
        height = video.get("height")
        duration = video.get("duration")  # milliseconds

        video_urls = extract_video_urls(video)
        if not video_urls:
            return []

        cover_urls = extract_all_urls(video.get("origin_cover"))

        return [
            ParserMediaInfo(
                url=video_urls[0],
                url_fallbacks=video_urls[1:] or None,
                type=MediaType.VIDEO,
                title=None,
                cover=cover_urls[0] if cover_urls else None,
                cover_fallbacks=cover_urls[1:] or None,
                duration=duration,
                width=width,
                height=height,
            )
        ]


    def _build_gallery_media(self, aweme: dict) -> list[ParserMediaInfo]:
        """Build a list of ParserMediaInfo for each image/live-photo in the gallery."""
        media_list: list[ParserMediaInfo] = []

        for item in iter_gallery_items(aweme):
            if not isinstance(item, dict):
                continue

            image_urls = extract_image_urls(item)
            if not image_urls:
                continue

            item_video = item.get("video")
            video = item_video if isinstance(item_video, dict) else {}
            video_urls = extract_video_urls(video)

            if video_urls:
                media_list.append(
                    ParserMediaInfo(
                        url=video_urls[0],
                        url_fallbacks=video_urls[1:] or None,
                        type=MediaType.LIVEPHOTO,
                        title=None,
                        cover=image_urls[0],
                        cover_fallbacks=image_urls[1:] or None,
                        duration=video.get("duration"),
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )
            else:
                media_list.append(
                    ParserMediaInfo(
                        url=image_urls[0],
                        url_fallbacks=image_urls[1:] or None,
                        type=MediaType.IMAGE,
                        title=None,
                        cover=None,
                        duration=None,
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )

        return media_list


    def _build_author(self, aweme: dict) -> ParserAuthorInfo:
        """Build a ParserAuthorInfo from aweme author data."""
        author = aweme.get("author") or {}
        uid = str(author.get("uid") or "")
        sec_uid = author.get("sec_uid") or ""
        nickname = author.get("nickname") or ""
        short_id = author.get("short_id") or ""
        unique_id = author.get("unique_id") or ""
        avatar_url = author.get("avatar_thumb", {}).get("url_list", [None])[0] or author.get("avatar_medium", {}).get("url_list", [None])[0]
        profile_url = f"{PLATFORM_URL}/user/{sec_uid}" if sec_uid else None

        return ParserAuthorInfo(
            uid=uid,
            name=nickname or None,
            username=unique_id or short_id or uid,
            avatar=avatar_url or None,
            url=profile_url,
            banner=None,
            description=author.get("signature") or None,
        )


    def _build_platform(self) -> ParserPlatformInfo:
        """Get platform information."""
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )

    async def async_will_remove(self):
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
            self.context.logger.info(f"{DOMAIN} parser client closed")


def _extract_aweme_id(url: str) -> Optional[str]:
    match = _AWEME_ID_RE.search(url)
    return match.group(1) if match else None
