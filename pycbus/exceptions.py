"""Exceptions for the pycbus library.

All pycbus-specific exceptions inherit from :class:`CbusError` so callers
can catch the entire family with a single ``except CbusError`` block.
"""

from __future__ import annotations


class CbusError(Exception):
    """Base exception for all pycbus errors."""


class CbusConnectionError(CbusError):
    """Raised when a transport cannot connect or loses its connection."""


class CbusTimeoutError(CbusError):
    """Raised when a transport or protocol operation times out."""
