"""Per-application SAL command definitions.

C-Bus supports dozens of applications, each with its own SAL command set.
Rather than encoding every application into a single monolithic module,
pycbus uses an *application registry* pattern:

Architecture::

    pycbus/applications/
    ├── __init__.py          ← this file, registry + base class
    ├── lighting.py          ← Lighting (app 56)  — Phase 1
    ├── trigger.py           ← Trigger (app 202)  — Phase 1
    ├── enable.py            ← Enable (app 203)   — Phase 1
    ├── temperature.py       ← Temperature (app 25)  — Phase 2
    ├── climate.py           ← Air Conditioning (app 172) — Phase 2
    └── ...                  ← one file per application chapter

Adding a new application:
    1. Create ``pycbus/applications/<name>.py``.
    2. Define a dataclass with the app's SAL command builders.
    3. Register it in ``APPLICATION_REGISTRY`` keyed by
       :class:`pycbus.constants.ApplicationId`.

The protocol layer uses the registry to dispatch incoming SAL events
to the correct parser, and entity platforms use it to build outgoing
commands for their domain.

This is a stub — per-application modules will be added as each
application chapter is implemented.
"""

from __future__ import annotations
