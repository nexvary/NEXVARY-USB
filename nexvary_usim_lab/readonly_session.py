"""Session lifecycle for consented, read-only APDU diagnostics.

This is a transport-independent adapter. It does not register a PC/SC reader,
install drivers, or establish a SIM session by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from .readonly_apdu_gateway import ReadOnlyApduGateway


class SessionClosed(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionInfo:
    connected: bool
    generation: int


class ReadOnlySession:
    """One explicitly opened, fail-closed diagnostic session."""

    def __init__(self, transport: Callable[[bytes], bytes]):
        self._gateway = ReadOnlyApduGateway(transport)
        self._lock = RLock()
        self._connected = False
        self._generation = 0

    def open(self, *, consent: bool) -> SessionInfo:
        with self._lock:
            if not consent:
                raise PermissionError("Explicit consent is required")
            if self._connected:
                raise RuntimeError("Session already open")
            self._connected = True
            self._generation += 1
            return self.status()

    def close(self) -> None:
        with self._lock:
            self._connected = False

    def status(self) -> SessionInfo:
        with self._lock:
            return SessionInfo(self._connected, self._generation)

    def transmit(self, command: bytes) -> bytes:
        with self._lock:
            if not self._connected:
                raise SessionClosed("Read-only session is closed")
            try:
                return self._gateway.transmit(command)
            except (OSError, TimeoutError, ConnectionError):
                self._connected = False
                raise
