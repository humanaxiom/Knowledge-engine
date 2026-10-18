"""A pure-Python agent loop traced with OpenInference conventions.

Runs without external services: the retriever and LLM are stubs. Replace them
with your graph/vector store and model client; keep the spans.

    HARNESS_TRACING=console python examples/custom_agent.py   # print spans
    python examples/custom_agent.py                           # send to Phoenix
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness_telemetry import (  # noqa: E402
    agent_span,
    llm_span,
    record_documents,
    record_token_usage,
    retriever_span,
    set_output,
    setup_tracing,
)

# Parameterised: user text is never spliced into the query string.
GRAPH_QUERY = "MATCH (n {name: $name})-[:DEPENDS_ON]->(d) RETURN d.id AS id, d.text AS content"


def search_graph(name: str) -> list[dict]:
    return [{"id": "component-y", "content": "Project X relies on Component Y.", "score": 0.92}]


def call_llm(prompt: str) -> tuple[str, int, int]:
    return "Based on the graph, Project X needs Component Y.", 15, 10


def run_agent(question: str, entity: str, session_id: str | None = None) -> str:
    with agent_span("Agent Reasoning Loop", input=question, session_id=session_id) as agent:
        with retriever_span(
            "Graph Search", input={"query": GRAPH_QUERY, "parameters": {"name": entity}}
        ) as retrieval:
            documents = search_graph(entity)
            record_documents(retrieval, documents)

        context = "\n".join(doc["content"] for doc in documents)
        prompt = f"Context:\n{context}\n\nQuestion: {question}"
        with llm_span("Synthesize Answer", input=prompt, model="stub-model") as llm:
            answer, prompt_tokens, completion_tokens = call_llm(prompt)
            record_token_usage(llm, prompt_tokens, completion_tokens)
            set_output(llm, answer)

        set_output(agent, answer)
        return answer


if __name__ == "__main__":
    provider = setup_tracing(project_name="harness-example")
    print(run_agent("What does Project X need?", "Project X", session_id="example"))
    if provider is not None:
        provider.force_flush()
