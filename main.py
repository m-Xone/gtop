"""PyInstaller entry point for the ``gtop`` binary.

Kept as a top-level module so PyInstaller can trace imports starting here
without colliding with the ``gtop`` package directory. All logic lives in
the package; this file just forwards.
"""

import sys

from gtop.cli import main

if __name__ == "__main__":
    sys.exit(main())
