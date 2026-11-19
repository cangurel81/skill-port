#!/usr/bin/env python3
"""Standalone entry point; runs without installing the package."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skill_port.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
