"""Standalone CLI for pycbus — exercises the library without Home Assistant.

This package is a *consumer* of the ``pycbus`` library, exactly like the
Home Assistant integration (``custom_components/cbus``).  It imports from
``pycbus`` using absolute imports and never touches library internals.

Run with::

    python -m cli --help
"""
