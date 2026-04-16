
import asyncio
from pathlib import Path
from typing import Any, Optional

from contenthive.plugins.context import PluginContext

from .api_client import DouyinAPIClient
from .const import DOMAIN

async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up downloader entities from a config entry."""
    downloader = Downloader(context, entry)
    await downloader.async_setup()
    await async_add_entities([downloader])

    if context.register_service:
        context.register_service(DOMAIN, "download", downloader.download)

    context.logger.info(f"{DOMAIN} downloader platform setup completed")


class Downloader:
    """Douyin content downloader."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._client: Optional[DouyinAPIClient] = None

    async def async_setup(self):
        """Retrieve the shared API client and config from plugin data."""
        entry_data = self.context.data[DOMAIN]
        self._client = entry_data["client"]
        self._max_retries = entry_data["config"].download_max_retries
        self.context.logger.debug(f"{DOMAIN} downloader initialized")

    async def download(self, data: dict[str, Any]) -> dict[str, Any]:
        """Download content from a Douyin URL."""
        if not self._client:
            raise RuntimeError("Downloader not initialized")
        media = data.get("media")
        if not media:
            raise ValueError("Missing 'media' in download data")

        media_url = media.get("url")
        fallbacks = [u for u in (media.get("url_fallbacks") or [])]
        media_urls = ([media_url] if media_url else []) + fallbacks
        if not media_urls:
            raise ValueError("Missing 'url' and 'url_fallbacks' in media object")

        cover_urls = (
            [media["cover"]] + [u for u in (media.get("cover_fallbacks") or [])]
            if media.get("cover") else []
        )

        self.context.logger.debug(
            f"Starting download: {len(media_urls)} media URL(s), "
            f"primary={media_urls[0]}, cover={media.get('cover') or 'none'}"
        )

        tasks = [self._client.download_file(media_urls, max_retries=self._max_retries)]
        if cover_urls:
            tasks.append(self._client.download_file(cover_urls, max_retries=self._max_retries))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        media_result = results[0]
        if isinstance(media_result, BaseException):
            raise media_result
        media_path: Path = media_result

        cover_result = results[1] if cover_urls else None
        if isinstance(cover_result, BaseException):
            self.context.logger.warning(f"Cover download failed, skipping: {cover_result}")
            cover_result = None
        cover_path: Optional[Path] = cover_result

        return {
            "media_path": str(media_path) if media_path else None,
            "cover_path": str(cover_path) if cover_path else None,
        }

