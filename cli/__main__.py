"""Allow the CLI to be run as ``python -m cli``.

Usage::

    python -m cli --help
    python -m cli light on --host 192.168.1.50 --group 1
    python -m cli monitor --host 192.168.1.50
"""

import sys

from cli.cbus_cli import main

sys.exit(main())
