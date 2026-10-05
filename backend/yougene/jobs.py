"""In-process background jobs for imports, with pollable progress.

One worker thread: imports run one at a time, which keeps DuckDB writes and
memory use predictable on a personal machine.
"""

import logging
import shutil
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from yougene.importers.base import ImportFailed
from yougene.refdata.fetch import DownloadFailed

log = logging.getLogger("yougene.jobs")
KEEP = 50


@dataclass
class Job:
    id: str
    kind: str
    state: str = "queued"  # queued | running | done | failed
    progress: float = 0.0
    message: str = "Waiting"
    sample_id: str | None = None
    error_code: str | None = None

    def public(self) -> dict:
        return asdict(self)


class Jobs:
    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yougene-job")

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self) -> bool:
        with self._lock:
            return any(j.state in ("queued", "running") for j in self._jobs.values())

    def submit(
        self,
        kind: str,
        work: Callable[[Callable[[float, str], None]], dict],
        cleanup=None,
    ):
        job = Job(id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > KEEP:
                self._jobs.popitem(last=False)

        def progress(value: float, message: str) -> None:
            job.progress = round(max(job.progress, min(value, 1.0)), 3)
            job.message = message

        def runner() -> None:
            job.state = "running"
            try:
                record = work(progress)
                if kind == "import":
                    job.sample_id = record["id"]
                job.state = "done"
                job.progress = 1.0
                job.message = "Imported" if kind == "import" else "Done"
            except (ImportFailed, DownloadFailed) as error:
                job.state, job.error_code, job.message = (
                    "failed",
                    getattr(error, "code", "download_failed"),
                    getattr(error, "message", str(error)),
                )
            except Exception:
                # Log the type only: exception text from parsers can echo file content.
                log.error("import job %s failed with an unexpected error", job.id)
                job.state, job.error_code = "failed", "internal"
                job.message = (
                    "Something went wrong while importing. Nothing was saved."
                    if kind == "import"
                    else "Something went wrong. The previous data is unchanged."
                )
            finally:
                if cleanup is not None:
                    shutil.rmtree(cleanup, ignore_errors=True)

        self._pool.submit(runner)
        return job

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Test helper: block until no job is queued or running."""
        done = threading.Event()
        self._pool.submit(done.set)
        done.wait(timeout)


jobs = Jobs()
