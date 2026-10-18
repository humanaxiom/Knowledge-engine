import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from opentelemetry.trace import StatusCode

from harness_telemetry import agent_span, chain_span, setup_tracing, tool_span
from tests.support import EXPORTER, finished_spans

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from custom_agent import GRAPH_QUERY, run_agent  # noqa: E402

KIND = "openinference.span.kind"


class TracingTest(unittest.TestCase):
    def setUp(self):
        EXPORTER.clear()

    def test_agent_loop_renders_as_nested_tree(self):
        run_agent("What does Project X need?", "Project X", session_id="s-1")
        spans = finished_spans()
        agent = spans["Agent Reasoning Loop"]
        retrieval = spans["Graph Search"]
        llm = spans["Synthesize Answer"]

        self.assertEqual(agent.attributes[KIND], "AGENT")
        self.assertEqual(retrieval.attributes[KIND], "RETRIEVER")
        self.assertEqual(llm.attributes[KIND], "LLM")
        self.assertIsNone(agent.parent)
        self.assertEqual(retrieval.parent.span_id, agent.context.span_id)
        self.assertEqual(llm.parent.span_id, agent.context.span_id)
        self.assertEqual(agent.attributes["session.id"], "s-1")
        self.assertEqual(agent.status.status_code, StatusCode.OK)
        self.assertEqual(agent.resource.attributes["openinference.project.name"], "harness-tests")

    def test_retriever_records_parameterised_query_and_documents(self):
        run_agent("q", "Robert'); DROP", session_id=None)
        retrieval = finished_spans()["Graph Search"]

        recorded = json.loads(retrieval.attributes["input.value"])
        self.assertEqual(recorded["query"], GRAPH_QUERY)
        self.assertEqual(recorded["parameters"], {"name": "Robert'); DROP"})
        self.assertEqual(retrieval.attributes["input.mime_type"], "application/json")
        self.assertEqual(retrieval.attributes["retrieval.documents.0.document.id"], "component-y")
        self.assertEqual(
            retrieval.attributes["retrieval.documents.0.document.content"],
            "Project X relies on Component Y.",
        )

    def test_llm_records_model_and_token_usage(self):
        run_agent("q", "Project X")
        llm = finished_spans()["Synthesize Answer"]

        self.assertEqual(llm.attributes["llm.model_name"], "stub-model")
        self.assertEqual(llm.attributes["llm.token_count.prompt"], 15)
        self.assertEqual(llm.attributes["llm.token_count.completion"], 10)
        self.assertEqual(llm.attributes["llm.token_count.total"], 25)
        self.assertEqual(llm.attributes["input.mime_type"], "text/plain")

    def test_exception_marks_span_error_and_propagates(self):
        with self.assertRaises(RuntimeError):
            with agent_span("failing agent"):
                with tool_span("lookup"):
                    raise RuntimeError("tool down")
        spans = finished_spans()
        for name in ("failing agent", "lookup"):
            self.assertEqual(spans[name].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans["lookup"].events[0].name, "exception")
        self.assertEqual(spans["lookup"].attributes["tool.name"], "lookup")

    def test_hide_inputs_and_outputs_redacts_values(self):
        env = {"OPENINFERENCE_HIDE_INPUTS": "true", "OPENINFERENCE_HIDE_OUTPUTS": "true"}
        with mock.patch.dict(os.environ, env):
            run_agent("student 301234567 question", "Project X")
        spans = finished_spans()

        self.assertEqual(spans["Agent Reasoning Loop"].attributes["input.value"], "__REDACTED__")
        self.assertEqual(spans["Agent Reasoning Loop"].attributes["output.value"], "__REDACTED__")
        self.assertEqual(
            spans["Graph Search"].attributes["retrieval.documents.0.document.content"],
            "__REDACTED__",
        )

    def test_chain_span_kind(self):
        with chain_span("route", input="x"):
            pass
        self.assertEqual(finished_spans()["route"].attributes[KIND], "CHAIN")

    def test_setup_tracing_is_idempotent(self):
        self.assertIs(setup_tracing(), setup_tracing())


if __name__ == "__main__":
    unittest.main()
