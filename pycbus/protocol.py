"""C-Bus PCI/CNI protocol state machine.

This module will implement the full PCI initialisation sequence and
runtime message loop.  The state machine manages the connection lifecycle
from power-on reset through to steady-state SAL monitoring.

State diagram::

    DISCONNECTED
        │
        ▼  transport.connect()
    CONNECTING
        │
        ▼  received '=' prompt or timeout → send reset
    RESETTING
        │  send: ~~~\r  (three tildes = PCI hard reset)
        ▼  wait for '=' prompt (confirmation of reset)
    INITIALISING
        │  1. @A3210059\r  — set Interface Options #1
        │  2. @A342000A\r  — set Interface Options #3
        │  3. ~@A3300059\r — read back options to confirm
        ▼  all confirmed with 'g.' responses
    READY
        │  • send SAL commands (lighting, trigger, enable …)
        │  • receive monitor events (level changes, triggers)
        │  • periodic keepalive if no traffic for 120s
        ▼  transport error or intentional disconnect
    DISCONNECTED

Error handling:
    If any init command receives a NEGATIVE ('!') response, the state
    machine transitions back to RESETTING for up to 3 retries before
    raising ``CbusConnectionError``.

Threading model:
    The state machine runs entirely within a single asyncio task.
    Callers interact via an async queue for outbound commands and
    callback registrations for inbound events.

This is a stub — implementation will follow in a dedicated PR.
"""

from __future__ import annotations
