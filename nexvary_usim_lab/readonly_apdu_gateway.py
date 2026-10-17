"""Conservative APDU policy for an opt-in virtual reader bridge.

This module does not register a Windows PC/SC reader or install a driver.
It constrains APDUs *before* they reach a modem transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

class ApduRejected(ValueError):
    """Command is outside the read-only virtual-reader contract."""

@dataclass(frozen=True)
class ReadOnlyApduPolicy:
    max_response_bytes: int = 256
    max_command_bytes: int = 5

    def validate(self, command: bytes) -> bytes:
        if not isinstance(command, bytes):
            raise ApduRejected("APDU must be bytes")
        if len(command) != 5 or len(command) > self.max_command_bytes:
            raise ApduRejected("Only short case-2 read APDUs are supported")
        cla, ins, p1, p2, le = command
        if cla != 0x00:
            raise ApduRejected("Only basic-channel CLA=00 is supported")
        if ins not in (0xB0, 0xB2, 0xC0):
            raise ApduRejected("Only READ BINARY/RECORD/GET RESPONSE are supported")
        if ins == 0xB0 and p1 & 0x80:
            raise ApduRejected("SFI addressing not supported")
        if ins == 0xB2 and (p1 == 0 or p2 != 0x04):
            raise ApduRejected("Only absolute record addressing is supported")
        if ins == 0xC0 and (p1 != 0 or p2 != 0):
            raise ApduRejected("Invalid GET RESPONSE parameters")
        size = 256 if le == 0 else le
        if size > self.max_response_bytes:
            raise ApduRejected("Requested response exceeds configured bound")
        return command

class ReadOnlyApduGateway:
    """Transport adapter; caller must separately establish an authorized card session.

    The transport callback accepts an APDU and returns data + SW1/SW2.
    SELECT and session setup remain the responsibility of the existing
    explicitly consented engine. Never expose this gateway as a general
    purpose smart-card reader.
    """
    def __init__(self, transport: Callable[[bytes], bytes],
                 policy: ReadOnlyApduPolicy | None = None):
        self.transport = transport
        self.policy = policy or ReadOnlyApduPolicy()

    def transmit(self, command: bytes) -> bytes:
        validated = self.policy.validate(command)
        response = self.transport(validated)
        if not isinstance(response, bytes) or len(response) < 2:
            raise ValueError("Transport did not return a complete status word")
        if len(response) > self.policy.max_response_bytes + 2:
            raise ValueError("Transport response exceeded configured bound")
        return response
