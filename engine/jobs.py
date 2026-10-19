"""RQ jobs (PS-2.6). Every job is wrapped by `traced_job` in a `job.<name>`
CHAIN span; a test checks that each name in `__all__` is traced."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from rq import get_current_job

from harness_telemetry import chain_span

__all__ = ["noop"]

F = TypeVar("F", bound=Callable[..., Any])


def traced_job(fn: F) -> F:
    """Run the job inside `job.<name>`, tagged with the RQ job id and queue
    (absent when called outside RQ)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with chain_span(f"job.{fn.__name__}") as span:
            job = get_current_job()
            if job is not None:
                span.set_attribute("ke.job.id", job.id)
                span.set_attribute("ke.job.queue", job.origin)
            return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


@traced_job
def noop(token: str) -> int:
    """`INCR ke:noop:<token>` on the job's own connection; returns the count."""
    job = get_current_job()
    assert job is not None, "noop runs only inside an RQ worker"
    return int(job.connection.incr(f"ke:noop:{token}"))
