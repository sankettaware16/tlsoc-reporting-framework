#!/usr/bin/env python3
"""Convenience launcher: ./reportgen.py <cmd> from any working directory."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from framework.cli import main   # noqa: E402

sys.exit(main())
