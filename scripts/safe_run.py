"""Entrypoint for manual testing: every real S3 write is blocked.

Run this instead of s3index.py while developing. Any write attempt raises
BlockedWriteError; pass --output-dir for local mode, or --dry-run to
preview without writing anywhere.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from dev_guard import install  # noqa: E402

install()

from s3index.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
