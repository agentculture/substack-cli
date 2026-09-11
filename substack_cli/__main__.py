"""Entry point for ``python -m substack_cli``."""

from __future__ import annotations

import sys

from substack_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
