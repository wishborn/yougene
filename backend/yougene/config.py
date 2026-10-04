"""Resolve storage outside the source checkout."""

import os
from pathlib import Path

from platformdirs import user_data_dir


def data_dir() -> Path:
    path = Path(os.environ.get("YOUGENE_DATA_DIR") or user_data_dir("yougene"))
    path = path.expanduser().resolve()
    # Installed wheels have no checkout; editable installs must protect the repo.
    package = Path(__file__).resolve()
    for parent in package.parents:
        if (parent / ".git").exists():
            if path == parent or parent in path.parents:
                raise ValueError(
                    "YouGene data directory must be outside the repository"
                )
            break
    return path
