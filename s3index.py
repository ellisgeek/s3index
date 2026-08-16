"""Entrypoint shim delegating to the src/s3index package.

Keeps `uv run s3index.py` working without an installed entrypoint or a
`[build-system]` table.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from s3index.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
