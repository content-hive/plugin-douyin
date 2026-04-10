
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import aiofiles
import aiohttp

from contenthive.plugins.context import PluginContext

from .api_client import DouyinAPIClient
from .const import DOMAIN, BASE_URL, USER_AGENT
from .utils import parse_cookie_string

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
        """Initialize the API client with cookies from the entry config."""
        raw_cookies = (self.entry.data or {}).get("cookies", "")
        cookies = parse_cookie_string(raw_cookies)
        self._client = DouyinAPIClient(cookies=cookies, logger=self.context.logger)
        self._max_retries = (self.entry.data or {}).get("download_max_retries", 3)
        self.context.logger.debug(f"{DOMAIN} downloader initialized")

    async def download(self, data: dict[str, Any]) -> dict[str, Any]:
        """Download content from a Douyin URL."""
        media_url = data.get("media_url")
        if not media_url:
            raise ValueError("Missing 'media_url' in download data")
        cover_url: Optional[str] = data.get("media_cover")

        self.context.logger.debug(f"Starting download for media_url={media_url}, cover_url={cover_url}")
        
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
            "Accept": "*/*",
        }
        tasks = [self._download_file(media_url, headers=headers)]
        if cover_url:
            tasks.append(self._download_file(cover_url, headers=headers))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        media_result = results[0]
        if isinstance(media_result, BaseException):
            raise media_result
        media_path: Optional[Path] = media_result

        cover_result = results[1] if cover_url else None
        if isinstance(cover_result, BaseException):
            self.context.logger.warning(f"Cover download failed, skipping: {cover_result}")
            cover_result = None
        cover_path: Optional[Path] = cover_result

        return {
            "media_path": str(media_path) if media_path else None,
            "cover_path": str(cover_path) if cover_path else None,
        }

    async def _download_file(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> Optional[Path]:
        """Download a single file to the system temp directory and return its path.

        Retries on network errors and 5xx / 429 responses with exponential backoff.
        """
        if not self._client:
            raise RuntimeError("Downloader not initialized")

        session = await self._client.ensure_session()

        last_error: Exception = Exception("Unknown error")
        for attempt in range(self._max_retries + 1):
            tmp_fd, tmp_path_str = tempfile.mkstemp()
            tmp_path = Path(tmp_path_str)
            os.close(tmp_fd)
            write_path = tmp_path.with_suffix(".tmp")

            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()

                    expected_size = response.content_length
                    written = 0
                    async with aiofiles.open(write_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            written += len(chunk)

                    if expected_size is not None and written != expected_size:
                        last_error = ValueError(
                            f"Size mismatch: expected {expected_size}, got {written}"
                        )
                        self.context.logger.warning(f"Size mismatch for {url}: {last_error}")
                        write_path.unlink(missing_ok=True)
                        tmp_path.unlink(missing_ok=True)
                        # Treat size mismatch as a retriable error
                    else:
                        os.replace(str(write_path), str(tmp_path))
                        self.context.logger.debug(f"Downloaded file from {url} -> {tmp_path}")
                        return tmp_path

            except aiohttp.ClientResponseError as e:
                write_path.unlink(missing_ok=True)
                tmp_path.unlink(missing_ok=True)
                if 400 <= e.status < 500 and e.status != 429:
                    raise
                last_error = e

            except Exception as e:
                write_path.unlink(missing_ok=True)
                tmp_path.unlink(missing_ok=True)
                last_error = e

            if attempt < self._max_retries:
                wait = 2 ** attempt
                if (
                    isinstance(last_error, aiohttp.ClientResponseError)
                    and last_error.status == 429
                    and last_error.headers is not None
                ):
                    retry_after = last_error.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            pass
                self.context.logger.warning(
                    f"Download attempt {attempt + 1}/{self._max_retries + 1} "
                    f"failed for {url}, retrying in {wait}s: {last_error}"
                )
                await asyncio.sleep(wait)

        raise last_error

    async def async_will_remove(self):
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
            self.context.logger.info(f"{DOMAIN} downloader client closed")
