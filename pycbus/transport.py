"""Async transport abstraction for C-Bus PCI (serial) and CNI (TCP)."""

from __future__ import annotations

from typing import Protocol


class CbusTransport(Protocol):
    """Interface that all C-Bus transports must satisfy."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read_line(self) -> bytes: ...
    async def write(self, data: bytes) -> None: ...

    @property
    def connected(self) -> bool: ...
