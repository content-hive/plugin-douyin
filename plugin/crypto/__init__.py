"""Cryptographic signature helpers for the Douyin plugin."""

from .xbogus import XBogus

try:
    from .abogus import ABogus, BrowserFingerprintGenerator
except Exception:  # pragma: no cover - optional dependency (requires gmssl)
    ABogus = None  # type: ignore[assignment,misc]
    BrowserFingerprintGenerator = None  # type: ignore[assignment,misc]

__all__ = ["XBogus", "ABogus", "BrowserFingerprintGenerator"]
