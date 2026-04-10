"""Douyin content parser plugin."""

import re
from typing import Any, Optional
from pydantic import HttpUrl

from contenthive.plugins.context import PluginContext
from contenthive.models.enumerates import MediaType, ParserResultStatus
from contenthive.models.parser import (
    ParserAuthorInfo,
    ParserMediaInfo,
    ParserPlatformInfo,
    ParserResult,
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
from .utils import parse_cookie_string, extract_first_url, iter_gallery_items, pick_first_url

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
            url=HttpUrl(url),
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
        if not self._client:
            raise RuntimeError("Parser not initialized")
        
        video = aweme.get("video") or {}
        width = video.get("width")
        height = video.get("height")
        duration = video.get("duration")  # milliseconds


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

        if not best_stream:
            play_addr = video.get("play_addr") or {}
            url_list = [u for u in (play_addr.get("url_list") or []) if u]
            if not url_list:
                return []

            url_list.sort(key=lambda u: 0 if "watermark=0" in u else 1)

            video_url = url_list[0]
        else:
            play_addr = best_stream.get("play_addr") or {}
            url_list = [u for u in (play_addr.get("url_list") or []) if u]

            if not url_list:
                return []

            video_url = url_list[0]
        
        cover_url = extract_first_url(video.get("origin_cover"))
        
        return [
            ParserMediaInfo(
                url=HttpUrl(video_url),
                type=MediaType.VIDEO,
                title=None,
                cover=HttpUrl(cover_url) if cover_url else None,
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

            image_url = pick_first_url(
                item.get("download_url"),
                item.get("download_addr"),
                item.get("display_image"),
                item.get("owner_watermark_image"),
            )
            if not image_url:
                continue

            # Live photo: the gallery item embeds a short video clip
            video = item.get("video") if isinstance(item.get("video"), dict) else {}
            live_url = pick_first_url(
                video.get("play_addr"),
                video.get("download_addr"),
                item.get("video_play_addr"),
                item.get("video_download_addr"),
            )

            if live_url:
                media_list.append(
                    ParserMediaInfo(
                        url=HttpUrl(live_url),
                        type=MediaType.LIVEPHOTO,
                        title=None,
                        cover=HttpUrl(image_url),
                        duration=None,
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )
            else:
                media_list.append(
                    ParserMediaInfo(
                        url=HttpUrl(image_url),
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
        avatar_url = author.get("avatar_thumb", {}).get("url_list", [None])[0] or author.get("avatar_medium", {}).get("url_list", [None])[0]
        profile_url = f"{PLATFORM_URL}/user/{sec_uid}" if sec_uid else None

        return ParserAuthorInfo(
            uid=uid,
            name=nickname or None,
            username=short_id or uid,
            avatar=HttpUrl(avatar_url) if avatar_url else None,
            url=HttpUrl(profile_url) if profile_url else None,
            banner=None,
            description=author.get("signature") or None,
        )


    def _build_platform(self) -> ParserPlatformInfo:
        """Get platform information."""
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=HttpUrl(PLATFORM_URL),
            icon_url=HttpUrl(PLATFORM_ICON)
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
