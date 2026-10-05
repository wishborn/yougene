"""Command-line entry point."""

import argparse

import uvicorn

from yougene import __version__
from yougene.config import data_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="yougene")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version")
    serve = commands.add_parser("serve")
    serve.add_argument(
        "--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1"]
    )
    serve.add_argument("--port", default=8765, type=int)
    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    data_dir()  # Fail early if a storage override points into the checkout.
    uvicorn.run("yougene.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
