"""platform-stack-ready (2b), PS-2.6: the RQ worker's jobs and its compose
wiring (fast).

Design: docs/architecture.md §2.4 "Worker", concrete shape (2b plan), adopted
by the orchestrator: jobs live in `engine/jobs.py` (job path
`engine.jobs.noop`); `@traced_job` wraps each job in a `job.<name>` CHAIN
span with `ke.job.id` and `ke.job.queue` from `rq.get_current_job()`;
`noop(token)` returns `int(get_current_job().connection.incr("ke:noop:<token>"))`;
every function in `engine.jobs.__all__` is traced. The worker gets
`depends_on: valkey: {condition: service_healthy}`.

The entrypoint tests (startup before run, refusals) are in
tests/test_stack_entrypoints.py WorkerEntrypointTest (ruling W1).
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator
from unittest import mock

from tests import compose_support as cs


@contextmanager
def current_job(job_id: str = "job-123", queue: str = "default") -> Iterator[mock.MagicMock]:
    """A stub RQ job, returned by every `get_current_job` the jobs module
    could call (the module attribute and `rq.get_current_job`)."""
    import engine.jobs as jobs

    connection = mock.MagicMock(name="redis connection")
    connection.incr.return_value = 1
    job = mock.MagicMock(name="rq job")
    job.id = job_id
    job.origin = queue
    job.connection = connection
    with ExitStack() as stack:
        stack.enter_context(mock.patch("rq.get_current_job", return_value=job))
        if hasattr(jobs, "get_current_job"):
            stack.enter_context(mock.patch.object(jobs, "get_current_job", return_value=job))
        yield job


class WorkerJobTracingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests import support

        cls.support = support

    def test_worker_job_is_traced(self):
        import engine.jobs as jobs

        self.support.EXPORTER.clear()
        with current_job() as job:
            result = jobs.noop("tok-1")
        self.assertEqual(result, 1)
        job.connection.incr.assert_called_once_with("ke:noop:tok-1")
        spans = [s for s in self.support.EXPORTER.get_finished_spans() if s.name == "job.noop"]
        self.assertEqual(len(spans), 1, "one job.noop span per job")
        span = spans[0]
        self.assertEqual(span.attributes.get("openinference.span.kind"), "CHAIN")
        self.assertEqual(span.attributes.get("ke.job.id"), "job-123")
        self.assertEqual(span.attributes.get("ke.job.queue"), "default")

    def test_every_job_is_traced(self):
        import engine.jobs as jobs

        names = list(getattr(jobs, "__all__", []))
        self.assertIn("noop", names, "engine.jobs.__all__ must list noop")
        for name in names:
            with self.subTest(job=name):
                fn: Any = getattr(jobs, name)
                self.support.EXPORTER.clear()
                with current_job(job_id=f"id-{name}"):
                    fn("tok")
                spans = [s for s in self.support.EXPORTER.get_finished_spans()
                         if s.name == f"job.{name}"]
                self.assertEqual(len(spans), 1, f"{name} is not traced as job.{name}")
                self.assertEqual(spans[0].attributes.get("ke.job.id"), f"id-{name}")

    def test_failing_job_marks_its_span(self):
        from opentelemetry.trace import StatusCode

        import engine.jobs as jobs

        self.support.EXPORTER.clear()
        with current_job() as job:
            job.connection.incr.side_effect = ConnectionError("valkey went away")
            with self.assertRaises(ConnectionError):
                jobs.noop("tok-2")
        span = next(s for s in self.support.EXPORTER.get_finished_spans() if s.name == "job.noop")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)


@contextmanager
def built_worker() -> Iterator[Any]:
    """The worker `engine.worker.run` builds, captured instead of working.

    `redis.Redis` is a stub (no socket), and `BaseWorker.work` is replaced so
    the worker run() constructs is returned instead of consuming the queue.
    Every RQ worker class inherits `work` from `BaseWorker`."""
    from rq.worker.base import BaseWorker

    import engine.worker as worker_module
    from tests.engine_support import base_env, load_settings

    connection = mock.MagicMock(name="valkey connection")
    connection.connection_pool.connection_kwargs = {}
    settings = load_settings(base_env(KE_ENV="ci"))
    with mock.patch("redis.Redis", return_value=connection), \
            mock.patch.object(BaseWorker, "work", autospec=True) as work:
        worker_module.run(settings)
    assert work.call_count == 1, "run() must start exactly one worker"
    yield work.call_args.args[0]


class WorkerJobAllowlistTest(unittest.TestCase):
    """Rework 1, security M-1 (engine side; handoff "rework round 1 of 5"):
    the worker decodes jobs with RQ's JSONSerializer (never pickle) and runs
    only functions named in `engine.jobs.__all__`. Review nit N2 (mutant
    WK3): the worker is an `rq.SimpleWorker`, so job spans export in-process.

    Seam: a job reaches its function through the worker's `execute_job(job,
    queue)`, the call RQ's work loop makes for each dequeued job. The refusal
    must happen there or below (perform_job, the job class, ...)."""

    def test_worker_is_a_simple_worker(self):  # review N2, mutant WK3
        import rq

        with built_worker() as worker:
            self.assertIsInstance(worker, rq.SimpleWorker,
                                  "a forking worker never flushes job spans (§2.4 Worker)")

    def test_worker_uses_json_serializer(self):  # M-1
        from rq.serializers import JSONSerializer

        with built_worker() as worker:
            self.assertIs(worker.serializer, JSONSerializer,
                          "job data must be decoded as JSON, never unpickled (M-1)")
            for queue in worker.queues:
                with self.subTest(queue=queue.name):
                    self.assertIs(queue.serializer, JSONSerializer)

    def _run_job(self, worker: Any, func: str, *args: Any) -> tuple[Any, BaseException | None]:
        queue = worker.queues[0]
        job = queue.enqueue(func, *args)  # as in security's repro (S1 W1/W2)
        error: BaseException | None = None
        try:
            worker.execute_job(job, queue)
        except Exception as exc:  # a refusal may raise; it must not run the job
            error = exc
        return job, error

    def test_worker_refuses_a_job_outside_engine_jobs(self):  # M-1
        from rq.job import JobStatus

        refused = {"platform.node": "platform.node",
                   "os.getcwd": "os.getcwd",
                   "engine.jobs.traced_job (in the module, not in __all__)": "engine.jobs.traced_job"}
        for case, func in refused.items():
            with self.subTest(job=case), built_worker() as worker, \
                    mock.patch(func, return_value="ran") as target:
                job, _ = self._run_job(worker, func)
                target.assert_not_called()
                self.assertNotEqual(job.get_status(refresh=False), JobStatus.FINISHED,
                                    f"{func} is not in engine.jobs.__all__ and must not finish")

    def test_worker_never_resolves_a_refused_jobs_function(self):  # review N-R1, mutant WK5
        # Resolving a dotted path imports its module, and the import runs that
        # module's top-level code. A refused job must fail on its name alone:
        # neither `Job.func` nor RQ's `import_attribute` is touched.
        import rq.job
        import rq.utils

        refused = ("platform.node", "os.getcwd", "engine.jobs.traced_job")
        for func in refused:
            with self.subTest(job=func), built_worker() as worker:
                queue = worker.queues[0]
                job = queue.enqueue(func)
                func_prop = mock.PropertyMock(side_effect=AssertionError("Job.func resolved"))
                with mock.patch.object(rq.job.Job, "func", new_callable=lambda: func_prop), \
                        mock.patch.object(rq.job, "import_attribute",
                                          side_effect=AssertionError("import_attribute")) as job_import, \
                        mock.patch.object(rq.utils, "import_attribute",
                                          side_effect=AssertionError("import_attribute")) as utils_import:
                    try:
                        worker.execute_job(job, queue)
                    except Exception:  # noqa: BLE001 - the touch counts below decide
                        pass
                self.assertEqual(func_prop.call_count, 0,
                                 f"the refused job's Job.func was read ({func}): its module would be imported")
                job_import.assert_not_called()
                utils_import.assert_not_called()

    def test_worker_runs_a_job_in_engine_jobs(self):  # control for the refusal
        from rq.job import JobStatus

        import engine.jobs as jobs

        self.assertIn("noop", jobs.__all__)
        with built_worker() as worker, mock.patch("engine.jobs.noop", return_value=1) as noop:
            job, error = self._run_job(worker, "engine.jobs.noop", "tok-allow")
        self.assertIsNone(error)
        noop.assert_called_once_with("tok-allow")
        self.assertEqual(job.get_status(refresh=False), JobStatus.FINISHED)


class WorkerComposeTest(unittest.TestCase):
    def test_compose_worker_waits_for_valkey(self):  # architecture §2.4 Worker
        worker = cs.services().get("worker", {})
        depends = worker.get("depends_on") or {}
        self.assertIsInstance(depends, dict, "depends_on needs the long form with a condition")
        self.assertEqual((depends.get("valkey") or {}).get("condition"), "service_healthy",
                         "the worker must wait for a healthy valkey")

    def test_worker_command_unchanged(self):
        self.assertEqual(cs.services()["worker"].get("command"),
                         ["python", "-m", "engine.worker"])


if __name__ == "__main__":
    unittest.main()
