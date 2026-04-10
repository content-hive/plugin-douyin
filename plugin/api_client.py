"""Douyin API client for the douyin parser plugin."""
# ==============================================================================
# Adapted from the douyin-downloader project.
# Reference: core/api_client.py, auth/ms_token_manager.py
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import random
import string
import time
import urllib.request
from http.cookies import SimpleCookie
from threading import Lock
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import aiohttp

from .const import BASE_URL, USER_AGENT, REQUEST_HEADERS
from .crypto import XBogus, ABogus, BrowserFingerprintGenerator


class MsTokenManager:
    """
    Generates a valid msToken for Douyin API requests.

    Strategy (mirrors douyin-downloader auth/ms_token_manager.py):
    1. Use existing msToken from cookies if it looks valid (length 164 or 184).
    2. Try to obtain a real token from the mssdk endpoint (config fetched from F2).
    3. Fall back to a randomly-generated false token.
    """

    F2_CONF_URL = (
        "https://raw.githubusercontent.com/Johnserf-Seed/f2/main/f2/conf/conf.yaml"
    )

    _cached_conf: Optional[Dict[str, Any]] = None
    _cached_at: float = 0
    _cache_ttl: int = 3600
    _lock = Lock()

    def __init__(self, user_agent: str = USER_AGENT, timeout: int = 15):
        self.user_agent = user_agent
        self.timeout = timeout

    @staticmethod
    def _is_valid(token: Optional[str]) -> bool:
        return bool(token and isinstance(token, str) and len(token.strip()) in (164, 184))

    @staticmethod
    def gen_false_ms_token() -> str:
        return (
            "".join(random.choices(string.ascii_letters + string.digits, k=182)) + "=="
        )

    def ensure_ms_token(self, cookies: Dict[str, str]) -> str:
        existing = (cookies or {}).get("msToken", "").strip()
        if self._is_valid(existing):
            return existing
        real = self._gen_real_ms_token()
        if real:
            return real
        return self.gen_false_ms_token()

    def _gen_real_ms_token(self) -> Optional[str]:
        conf = self._load_f2_conf()
        if not conf:
            return None

        payload = {
            "magic": conf["magic"],
            "version": conf["version"],
            "dataType": conf["dataType"],
            "strData": conf["strData"],
            "ulr": conf["ulr"],
            "tspFromClient": int(time.time() * 1000),
        }
        req = urllib.request.Request(
            conf["url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                token = self._extract_token_from_headers(resp.headers)
            if self._is_valid(token):
                return token
        except Exception:
            pass
        return None

    def _load_f2_conf(self) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            if self._cached_conf and (now - self._cached_at) < self._cache_ttl:
                return self._cached_conf

        try:
            import yaml  # optional dependency

            with urllib.request.urlopen(self.F2_CONF_URL, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
            data = yaml.safe_load(raw) or {}
            conf = data.get("f2", {}).get("douyin", {}).get("msToken", {})
            required = {"url", "magic", "version", "dataType", "ulr", "strData"}
            if not required.issubset(conf.keys()):
                return None
            with self._lock:
                self._cached_conf = conf
                self._cached_at = now
            return conf
        except Exception:
            return None

    @staticmethod
    def _extract_token_from_headers(headers: Any) -> Optional[str]:
        set_cookies = (
            headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else []
        )
        for header in set_cookies or []:
            cookie = SimpleCookie()
            cookie.load(header)
            morsel = cookie.get("msToken")
            if morsel and morsel.value:
                return morsel.value.strip()
        return None


class DouyinAPIClient:
    """
    Minimal Douyin web API client for single-aweme detail fetching.

    Mirrors core/api_client.py from the douyin-downloader reference project,
    trimmed to only what the parser plugin needs.
    """

    _DETAIL_AIDS = ("6383", "1128")

    def __init__(self, cookies: Dict[str, str], logger: Optional[Any] = None):
        self.logger = logger
        self.cookies: Dict[str, str] = dict(cookies or {})
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = REQUEST_HEADERS
        self._signer = XBogus(user_agent=USER_AGENT)
        self._ms_token_manager = MsTokenManager(user_agent=USER_AGENT)
        self._ms_token: str = self.cookies.get("msToken", "").strip()
        self._abogus_enabled = (
            ABogus is not None and BrowserFingerprintGenerator is not None
        )

    async def __aenter__(self) -> "DouyinAPIClient":
        await self.ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                cookies=self.cookies,
                timeout=aiohttp.ClientTimeout(total=30),
                raise_for_status=False,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _ensure_ms_token(self) -> str:
        if self._ms_token:
            return self._ms_token
        token = await asyncio.to_thread(
            self._ms_token_manager.ensure_ms_token, self.cookies
        )
        self._ms_token = token.strip()
        if self._ms_token:
            self.cookies["msToken"] = self._ms_token
            if self._session and not self._session.closed:
                self._session.cookie_jar.update_cookies({"msToken": self._ms_token})
        return self._ms_token

    async def _default_params(self) -> Dict[str, Any]:
        ms_token = await self._ensure_ms_token()
        return {
            "device_platform": "webapp",
            "channel": "channel_pc_web",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "130.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "130.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "12",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "100",
            "msToken": ms_token,
        }

    def _build_signed_path(self, path: str, params: Dict[str, Any]) -> Tuple[str, str]:
        """Build a signed URL, preferring ABogus over XBogus when available."""
        query = urlencode(params)
        base_url = f"{BASE_URL}{path}"
        ab_result = self._build_abogus_url(base_url, query)
        if ab_result:
            return ab_result
        signed_url, _xb, ua = self._signer.build(f"{base_url}?{query}")
        return signed_url, ua

    def _build_abogus_url(self, base_url: str, query: str) -> Optional[Tuple[str, str]]:
        """Try to build an ABogus-signed URL; return None to fall back to XBogus."""
        if not self._abogus_enabled:
            return None
        try:
            browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Edge")
            signer = ABogus(fp=browser_fp, user_agent=USER_AGENT)
            params_with_ab, _ab, ua, _body = signer.generate_abogus(query, "")
            return f"{base_url}?{params_with_ab}", ua
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"ABogus signing failed, falling back to XBogus: {exc}")
            return None

    async def _request_json(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Send a signed GET request with retries, mirroring the reference _request_json."""
        await self.ensure_session()
        assert self._session is not None
        delays = [1, 2, 5]

        for attempt in range(max_retries):
            # Re-sign on every attempt so the XBogus timestamp stays fresh.
            signed_url, ua = self._build_signed_path(path, params)
            try:
                async with self._session.get(
                    signed_url,
                    headers={**self._headers, "User-Agent": ua},
                ) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        return data if isinstance(data, dict) else {}
                    # 4xx (except 429) are not retryable
                    if response.status < 500 and response.status != 429:
                        return {}
            except Exception:
                pass

            if attempt < max_retries - 1:
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])

        return {}

    async def get_aweme_detail(self, aweme_id: str) -> Optional[Dict[str, Any]]:
        """Fetch aweme detail. Tries aid=6383 first (gallery/note), then aid=1128 (video)."""
        for aid in self._DETAIL_AIDS:
            params = await self._default_params()
            params.update(
                {
                    "aweme_id": aweme_id,
                    "aid": aid,
                }
            )
            data = await self._request_json(
                "/aweme/v1/web/aweme/detail/",
                params,
            )
            if not data:
                continue

            detail = data.get("aweme_detail")
            if detail:
                return detail

            # Content filtered by this aid (e.g. images_base) — try next aid
            filter_info = data.get("filter_detail")
            if isinstance(filter_info, dict) and filter_info.get("filter_reason"):
                continue

            # aweme_detail is null with no filter reason — no point retrying other aids
            break

        return None

    async def resolve_short_url(self, url: str) -> str:
        """Follow HTTP redirects and return the final URL."""
        await self.ensure_session()
        assert self._session is not None
        try:
            async with self._session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception:
            return url
