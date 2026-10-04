"""Resolve storage outside the source checkout."""

import os
import re
from pathlib import Path

from platformdirs import user_data_dir

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def allowed_hosts() -> set[str]:
    """Optional literal hostnames, never wildcard or host:port patterns."""
    extra = os.environ.get("YOUGENE_ALLOWED_HOSTS", "")
    hosts = {value.strip().lower() for value in extra.split(",") if value.strip()}
    for host in hosts:
        if host not in LOOPBACK_HOSTS and not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*",
            host,
        ):
            raise ValueError("YOUGENE_ALLOWED_HOSTS must contain literal hostnames")
    return LOOPBACK_HOSTS | hosts


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
