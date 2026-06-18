#!/usr/bin/env python
"""Wrapper script to allow running the CLI via 'uv run main.py'"""

import sys
from pathlib import Path

# Add the src directory to the python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cli import main

if __name__ == "__main__":
    main()
