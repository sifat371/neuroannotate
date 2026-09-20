from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file's bytes."""
    with Path(path).open("rb") as file_handle:
        return hashlib.file_digest(file_handle, "sha256").hexdigest()
