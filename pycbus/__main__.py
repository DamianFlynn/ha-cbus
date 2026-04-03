"""Allow pycbus to be run as ``python -m pycbus``.

This shim makes the CLI accessible via::

    python -m pycbus --help
    python -m pycbus build on --group 1
    python -m pycbus checksum 05 38 00 79 01 FF

It delegates to :func:`pycbus.cli.main`.
"""

import sys

from pycbus.cli import main

sys.exit(main())
