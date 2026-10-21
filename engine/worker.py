"""The worker service (architecture §2.4): RQ on Valkey, one queue. It runs
the same startup refusals as the api, then consumes `default`."""

from __future__ import annotations

from typing import Any

import redis
import rq
from rq.serializers import JSONSerializer

import engine.jobs
from engine.config import Settings
from engine.startup import startup

QUEUE = "default"
REFUSED_REASON = "refused: job function is not in engine.jobs.__all__"


class AllowListWorker(rq.SimpleWorker):
    """Runs only the functions named in `engine.jobs.__all__` (security M-1)."""

    def execute_job(self, job: Any, queue: Any) -> None:
        if job.func_name not in {f"engine.jobs.{name}" for name in engine.jobs.__all__}:
            # Never resolve or call it; fail it with a fixed reason.
            self.handle_job_failure(job, queue=queue, exc_string=REFUSED_REASON)
            return
        super().execute_job(job, queue)


def run(settings: Settings) -> None:
    """Consume `QUEUE` until stopped. A SimpleWorker runs jobs in-process, so
    the spans `startup()` set up export (a forked child would never flush).
    Job data is JSON, never pickle (M-1)."""
    valkey = settings.stores.valkey
    connection = redis.Redis(host=valkey.host, port=valkey.port)
    AllowListWorker([QUEUE], connection=connection,
                    serializer=JSONSerializer).work(with_scheduler=False)


def main() -> None:
    run(startup())


if __name__ == "__main__":  # pragma: no cover
    main()
