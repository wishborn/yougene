"""Download reference files. The only part of YouGene that uses the network,
and only when the user asks for it."""

import hashlib
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from yougene import __version__
from yougene.refdata.sources import Source

CHUNK = 1024 * 1024
TIMEOUT = 60


class DownloadFailed(Exception):
    pass


def download(
    source: Source,
    target_dir: Path,
    progress: Callable[[int, int | None], None] = lambda done, total: None,
    opener=urllib.request.urlopen,
) -> dict:
    """Fetch ``source`` into ``target_dir``; returns provenance metadata."""
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.filename
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(
        source.url, headers={"User-Agent": f"YouGene/{__version__} (local app)"}
    )
    digest = hashlib.sha256()
    done = 0
    try:
        with opener(request, timeout=TIMEOUT) as response:
            total = response.headers.get("Content-Length")
            total = int(total) if total and total.isdigit() else None
            modified = response.headers.get("Last-Modified")
            with partial.open("wb") as out:
                while chunk := response.read(CHUNK):
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    progress(done, total)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise DownloadFailed(
            f"Couldn't download {source.title}. Check the internet connection "
            "and try again."
        ) from error
    if total is not None and done != total:
        partial.unlink(missing_ok=True)
        raise DownloadFailed(f"The {source.title} download was incomplete.")
    partial.replace(target)
    released = None
    if modified:
        try:
            released = parsedate_to_datetime(modified).astimezone(UTC).isoformat()
        except (TypeError, ValueError):
            released = None
    return {
        "source": source.id,
        "url": source.url,
        "bytes": done,
        "sha256": digest.hexdigest(),
        "released": released,
        "fetched_at": datetime.now(UTC).isoformat(),
        "path": str(target),
    }
