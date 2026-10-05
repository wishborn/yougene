"""Command-line entry point."""

import argparse
import json
import shutil
from pathlib import Path

import uvicorn

from yougene import __version__
from yougene.config import data_dir
from yougene.refdata import manager
from yougene.refdata.sources import SOURCES


def run_refdata(parser: argparse.ArgumentParser, args) -> None:
    if args.action == "status":
        print(json.dumps(manager.status(), indent=2))
        return
    ids = args.source or list(manager.CORE)
    local = {}
    for item in args.file:
        source_id, _, path = item.partition("=")
        if source_id not in SOURCES or not Path(path).is_file():
            parser.error(
                f"--file needs ID=PATH with a known id and existing file: {item}"
            )
        local[source_id] = Path(path)
    downloads = manager.ref_dir() / "downloads"
    for source_id, path in local.items():
        shutil.copyfile(path, downloads / SOURCES[source_id].filename)

    def progress(value: float, message: str) -> None:
        print(f"[{value:4.0%}] {message}", flush=True)

    result = manager.install(ids, progress, refresh=not local)
    print(json.dumps(result, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="yougene")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version")
    serve = commands.add_parser("serve")
    serve.add_argument(
        "--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1"]
    )
    serve.add_argument("--port", default=8765, type=int)
    refdata = commands.add_parser("refdata", help="reference data")
    refdata.add_argument("action", choices=["status", "install"])
    refdata.add_argument(
        "--source", action="append", choices=sorted(SOURCES), help="default: all"
    )
    refdata.add_argument(
        "--file",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="use an already-downloaded file instead of downloading it",
    )
    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return
    if args.command == "refdata":
        run_refdata(parser, args)
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    data_dir()  # Fail early if a storage override points into the checkout.
    uvicorn.run("yougene.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
