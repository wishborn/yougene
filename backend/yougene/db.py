"""DuckDB connections that can never reach the network."""

from pathlib import Path

import duckdb


def connect(path: Path | str = ":memory:", read_only: bool = False):
    """Open DuckDB with extension auto-install/auto-load disabled.

    DuckDB would otherwise download extensions (e.g. httpfs) on demand, which
    is a network call. Nothing in YouGene needs an extension.
    """
    con = duckdb.connect(
        str(path),
        read_only=read_only,
        config={
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    )
    return con
