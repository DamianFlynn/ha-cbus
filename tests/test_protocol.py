"""Tests for pycbus protocol state machine.

Will test the PCI/CNI init sequence, state transitions, command queuing,
monitor event parsing, and error recovery.

Planned test cases:
    - DISCONNECTED → CONNECTING → RESETTING → INITIALISING → READY
    - Init command retry on NEGATIVE response
    - Max retries exceeded → CbusConnectionError
    - SAL command send and POSITIVE confirmation
    - Monitor event callback dispatch
    - Keepalive timeout handling
    - Transport disconnect recovery

This is a stub — tests will be added alongside the protocol implementation.
"""

from __future__ import annotations
