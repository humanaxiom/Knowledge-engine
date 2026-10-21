# Security re-audit probes, platform-config rework 1. Run in the gates image (network_mode: none).
import contextlib, io, json, logging, os, socket, sys
from unittest import mock
sys.path.insert(0, "/work")
NL = chr(10)
def hdr(t): print(NL + "### " + t)

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (SimpleSpanProcessor, BatchSpanProcessor, ConsoleSpanExporter,
                                            SpanExporter, SpanExportResult)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from tests.engine_support import base_env, environ
from engine.config import Settings, ConfigError
from engine.errors import StartupRefused
import engine.startup as st
from engine.telemetry import choose_exporter, configure_tracing

def reset():
    p = trace.get_tracer_provider()
    with contextlib.suppress(Exception): p.shutdown()
    trace._TRACER_PROVIDER = None; trace._TRACER_PROVIDER_SET_ONCE._done = False
    import harness_telemetry.tracing as _ht; _ht._tracer = trace.get_tracer("harness_telemetry")  # ProxyTracer caches the first provider

def exporters():
    p = trace.get_tracer_provider()
    out = []
    for sp in getattr(getattr(p, "_active_span_processor", None), "_span_processors", ()):
        ex = getattr(sp, "span_exporter", None) or getattr(getattr(sp, "_batch_processor", None), "_exporter", None)
        out.append((type(sp).__name__, type(ex).__name__, getattr(ex, "_endpoint", None)))
    return type(p).__name__, out

class Foreign(SpanExporter):
    """Stands in for an exporter to an unknown / non-local destination."""
    def __init__(self): self.names = []
    def export(self, spans): self.names += [s.name for s in spans]; return SpanExportResult.SUCCESS
    def shutdown(self): pass

HIDE = ("OPENINFERENCE_HIDE_INPUTS", "OPENINFERENCE_HIDE_OUTPUTS")
SECRET = "s3cr3t-VALUE-xyz"

hdr("8a. H1 console mode: exporter chosen from settings only")
for label, ov, drop in [
    ("console, PHOENIX evil, HARNESS_TRACING unset", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), True),
    ("console, PHOENIX evil, HARNESS_TRACING=otlp", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), False),
    ("HARNESS_TRACING=console, PHOENIX evil", dict(KE_ENV="ci", HARNESS_TRACING="console", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), False),
    ("console, KE endpoint local, PHOENIX evil, HARNESS otlp", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost:6006", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), False),
]:
    e = base_env(**ov)
    if drop: e.pop("HARNESS_TRACING", None)
    with environ(e):
        reset()
        s = Settings(); ce = choose_exporter(s)
        try: res = st.startup(); out = "startup OK"
        except (StartupRefused, ConfigError) as x: out = "startup refused: %s" % x
        print("%-58s choose=%s; %s; provider=%s" % (label, type(ce).__name__, out, exporters()))

hdr("8b. H1 otlp with non-local / mixed endpoints")
for label, ov in [
    ("HARNESS otlp, PHOENIX evil", dict(KE_ENV="ci", HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318")),
    ("KE tracing otlp, PHOENIX evil", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318")),
    ("KE otlp, KE endpoint local, PHOENIX evil", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost:6006", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318")),
    ("KE otlp, KE endpoint evil, PHOENIX local", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://evil.example", PHOENIX_COLLECTOR_ENDPOINT="http://localhost:6006")),
    ("dev otlp evil", dict(KE_ENV="dev", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://evil.example")),
    ("otlp localhost.evil.com", dict(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost.evil.com")),
    ("otlp localhost@evil.com", dict(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost@evil.com")),
    ("otlp phoenix (default) ok", dict(KE_ENV="ci", HARNESS_TRACING="otlp")),
]:
    with environ(base_env(**ov)):
        reset()
        try: s = Settings(); ce = choose_exporter(s); cs = "%s %s" % (type(ce).__name__, getattr(ce, "_endpoint", ""))
        except ConfigError as x: cs = "ConfigError %s" % x
        try: st.startup(); out = "startup OK"
        except (StartupRefused, ConfigError) as x: out = "startup refused: %s" % x
        print("%-45s choose=%s; %s; provider=%s" % (label, cs, out, exporters()))

hdr("8c. Provider already installed (passing env and refusing env)")
def shapes():
    yield "Simple(OTLP evil)", lambda: SimpleSpanProcessor(OTLPSpanExporter("http://evil.example:4318/v1/traces"))
    yield "Batch(OTLP evil)", lambda: BatchSpanProcessor(OTLPSpanExporter("http://evil.example:4318/v1/traces"))
    yield "Batch(OTLP localhost@evil)", lambda: BatchSpanProcessor(OTLPSpanExporter("http://localhost@evil.example/v1/traces"))
    yield "Simple(Foreign)", lambda: SimpleSpanProcessor(Foreign())
    yield "Batch(Foreign)", lambda: BatchSpanProcessor(Foreign())
    from opentelemetry.sdk.trace import ConcurrentMultiSpanProcessor
    def cm():
        m = ConcurrentMultiSpanProcessor(); m.add_span_processor(SimpleSpanProcessor(Foreign())); return m
    yield "ConcurrentMulti(Foreign)", cm
    yield "Simple(OTLP localhost)", lambda: SimpleSpanProcessor(OTLPSpanExporter("http://localhost:6006/v1/traces"))
    yield "Simple(InMemory)", lambda: SimpleSpanProcessor(InMemorySpanExporter())
for envlabel, ov in [("passing ci", dict(KE_ENV="ci")),
                     ("refusing ci (auth off)", dict(KE_ENV="ci", KE_AUTH__ENABLED="false"))]:
    for label, mk in shapes():
        with environ(base_env(**ov)):
            reset()
            spy = InMemorySpanExporter(); p = TracerProvider(); p.add_span_processor(mk()); p.add_span_processor(SimpleSpanProcessor(spy))
            trace.set_tracer_provider(p)
            try: st.startup(); out = "startup OK"
            except (StartupRefused, ConfigError) as x: out = "refused: %s" % x
            print("%-24s %-26s %s | spans the installed provider received: %s" % (envlabel, label, out, [x.name for x in spy.get_finished_spans()]))

hdr("8d. Refused startup, nothing installed: provider and hide env")
for label, ov in [("auth off ci", dict(KE_ENV="ci", KE_AUTH__ENABLED="false")),
                  ("otlp evil", dict(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://evil.example")),
                  ("console + hide false ci", dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", KE_TELEMETRY__HIDE_INPUTS="false")),
                  ("placeholder secret ci", dict(KE_ENV="ci", HARNESS_TRACING="console", KE_STORES__POSTGRES__PASSWORD="changeme-x")),
                  ("config error", dict(KE_ENV="ci", HARNESS_TRACING="console", KE_API__LISTEN_PORT="notint"))]:
    e = base_env(**ov); e["OPENINFERENCE_HIDE_INPUTS"] = "1"; e.pop("OPENINFERENCE_HIDE_OUTPUTS", None)
    with environ(e):
        reset()
        try: st.startup(); out = "startup OK"
        except (StartupRefused, ConfigError) as x: out = "refused: %s" % type(x).__name__
        print("%-26s %s; provider=%s; HIDE env=%s" % (label, out, exporters(), {k: os.environ.get(k) for k in HIDE}))

hdr("8e. Local OTLP endpoint with proxy env set: where does the exporter's socket go?")
dialed = []
def gai(host, *a, **k): dialed.append(("getaddrinfo", host)); raise OSError("spy")
def cc(addr, *a, **k): dialed.append(("create_connection", addr)); raise OSError("spy")
for label, endpoint, penv in [
    ("localhost, no proxy env", "http://localhost:6006", {}),
    ("localhost, HTTP_PROXY evil", "http://localhost:6006", {"HTTP_PROXY": "http://evil.example:3128"}),
    ("phoenix, HTTP_PROXY evil", "http://phoenix:6006", {"HTTP_PROXY": "http://evil.example:3128"}),
    ("phoenix, http_proxy evil, NO_PROXY=localhost", "http://phoenix:6006", {"http_proxy": "http://evil.example:3128", "NO_PROXY": "localhost,127.0.0.1"}),
    ("127.0.0.1, ALL_PROXY evil", "http://127.0.0.1:6006", {"ALL_PROXY": "http://evil.example:3128"}),
]:
    e = base_env(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT=endpoint, **penv)
    with environ(e), mock.patch("socket.getaddrinfo", gai), mock.patch("socket.create_connection", cc):
        reset(); dialed.clear()
        try:
            st.startup()
            with trace.get_tracer("probe").start_as_current_span("probe-span"): pass
            trace.get_tracer_provider().force_flush(3000)
            res = "startup OK"
        except Exception as x: res = "error %s: %s" % (type(x).__name__, x)
        hosts = sorted({d[1] if isinstance(d[1], str) else d[1][0] for d in dialed})
        print("%-46s %s; exporter=%s; hosts dialled: %s" % (label, res, exporters()[1], hosts))
reset()

hdr("9. L1 placeholder behind invisible / look-alike characters (ci)")
cases = {"NBSP": " ", "FEFF": "﻿", "2060": "⁠", "200B": "​", "200D": "‍", "TAB": "\t",
         "180E": "᠎", "00AD soft hyphen": "­", "2061": "⁡", "2062": "⁢", "034F": "͏",
         "3164": "ㅤ", "115F": "ᅟ", "FFA0": "ﾠ", "202E RLO": "‮", "2066": "⁦",
         "E0020 tag": "\U000e0020", "NBSP+FEFF+2060": " ﻿⁠", "3000 ideographic sp": "　"}
for name, pre in cases.items():
    with environ(base_env(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=pre + "changeme-x")):
        try: s = Settings(); st.check(s); r = "STARTS (bypass)"
        except StartupRefused as x: r = "refused"
        except ConfigError as x: r = "ConfigError"
    print("%-22s %s" % (name, r))
for label, v in [("trailing FEFF", "changeme﻿"), ("fullwidth", "ｃｈａｎｇｅｍｅ"),
                 ("inner ZW", "c​hangeme"), ("single space", " "), ("x", "x")]:
    with environ(base_env(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=v)):
        try: s = Settings(); st.check(s); r = "STARTS"
        except StartupRefused: r = "refused"
        except ConfigError: r = "ConfigError"
    print("%-22s %s" % (label, r))

hdr("10. L4 / N7 malformed values: wrapped, and no value in message")
for label, ov in [("service_names non-JSON", dict(KE_STACK__SERVICE_NAMES="evil," + SECRET)),
                  ("KE_STACK json broken", dict(KE_STACK="{" + SECRET)),
                  ("KE_STORES json broken", dict(KE_STORES="{" + SECRET)),
                  ("model upstream [::1", dict(KE_MODEL_UPSTREAM="[::1" + SECRET)),
                  ("model upstream http://[x", dict(KE_MODEL_UPSTREAM="http://[" + SECRET)),
                  ("port not int", dict(KE_API__LISTEN_PORT=SECRET)),
                  ("collector bad URL", dict(KE_TELEMETRY__COLLECTOR_ENDPOINT=SECRET)),
                  ("PHOENIX bad URL", dict(PHOENIX_COLLECTOR_ENDPOINT=SECRET)),
                  ("base_url bad", dict(KE_MODELS__COMPOSE__BASE_URL="http://[" + SECRET)),
                  ("password as JSON obj", dict(KE_STORES__POSTGRES="{\"password\": {\"a\": \"" + SECRET + "\"}}")),
                  ("extra key", dict(KE_STORES__POSTGRES__PASSWORDX=SECRET)),
                  ("nested model upstream ignored", dict(KE_MODELS__MODEL_UPSTREAM="evil.example:1")),
                  ("KE_MODELS json with upstream", dict(KE_MODELS="{\"model_upstream\": \"evil.example:1\"}")),
                  ("lowercase nested upstream", dict(ke_models__model_upstream="evil.example:1"))]:
    with environ(base_env(KE_ENV="ci", **ov)):
        try: s = Settings(); r = "loaded; model_upstream=%r" % s.models.model_upstream
        except ConfigError as x: r = "ConfigError (value leaked=%s, cause=%r): %s" % (SECRET in str(x), x.__cause__, x)
        except Exception as x: r = "UNWRAPPED %s (value leaked=%s)" % (type(x).__name__, SECRET in str(x))
    print("%-30s %s" % (label, r))
with environ(base_env(KE_ENV="ci", KE_ENV_X="1")):
    pass
for v in [SECRET]:
    with environ(base_env(KE_ENV=v)):
        try: Settings(); print("env bad: loaded")
        except ConfigError as x: print("env bad: ConfigError (value leaked=%s): %s" % (SECRET in str(x), x))

hdr("11. ModelClient.complete(): transport, span content, EgressDenied, errors")
import httpx
from engine.llm.client import ModelClient
from engine.egress import GuardedTransport, EgressDenied
def run_complete(label, env_over, handler, hide_env=None):
    mem = InMemorySpanExporter(); reset(); p = TracerProvider(); p.add_span_processor(SimpleSpanProcessor(mem)); trace.set_tracer_provider(p); import harness_telemetry.tracing as _ht; _ht._tracer = p.get_tracer("harness_telemetry")
    e = base_env(KE_ENV="ci", **env_over)
    for k in HIDE:
        if hide_env is None: e.pop(k, None)
        else: e[k] = hide_env
    with environ(e):
        s = Settings(); mc = ModelClient(s, "compose")
        t = mc.http_client._transport; assert isinstance(t, GuardedTransport), type(t)
        t._inner = httpx.MockTransport(handler)
        try: r = mc.complete([{"role": "user", "content": "PROMPT-" + SECRET}]); out = "returned keys %s" % list(r)
        except Exception as x: out = "raised %s: %s" % (type(x).__name__, x)
    print("%-34s %s" % (label, out))
    for s_ in mem.get_finished_spans():
        attrs = dict(s_.attributes)
        evs = [(ev.name, dict(ev.attributes).get("exception.message")) for ev in s_.events]
        blob = json.dumps(attrs, default=str) + json.dumps(evs, default=str)
        print("    span=%s kind=%s status=%s input.value=%r output.value=%r secret-in-span=%s pw-in-span=%s events=%s" % (
            s_.name, attrs.get("openinference.span.kind"), s_.status.status_code.name, str(attrs.get("input.value", ""))[:50],
            attrs.get("output.value"), SECRET in blob, "hunter2" in blob, evs))
def ok(req): return httpx.Response(200, json={"choices": [{"message": {"content": "ANSWER-" + SECRET}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}})
def err(req): return httpx.Response(401, text="upstream says: BODY-" + SECRET)
def redir(req):
    if req.url.host == "allowed.example": return httpx.Response(302, headers={"location": "http://evil.example/x"})
    return ok(req)
A = dict(KE_EGRESS_ALLOWLIST="allowed.example", KE_MODELS__COMPOSE__BASE_URL="http://allowed.example/v1")
run_complete("ok, hide=true", A, ok, "true")
run_complete("ok, hide=false (dev-like)", A, ok, "false")
run_complete("ok, hide env unset (no startup)", A, ok, None)
run_complete("denied base_url host", dict(KE_EGRESS_ALLOWLIST="allowed.example", KE_MODELS__COMPOSE__BASE_URL="http://evil.example/v1"), ok, "true")
run_complete("redirect to evil", A, redir, "true")
run_complete("401 with body", A, err, "true")
run_complete("userinfo in base_url, 401", dict(KE_EGRESS_ALLOWLIST="allowed.example", KE_MODELS__COMPOSE__BASE_URL="http://u:hunter2@allowed.example/v1"), err, "true")
calls = []
def gai2(host, *a, **k):
    calls.append(host); raise OSError("spy")
with mock.patch("socket.getaddrinfo", gai2), environ(base_env(KE_ENV="ci", KE_EGRESS_ALLOWLIST="allowed.example", KE_MODELS__COMPOSE__BASE_URL="http://evil.example/v1")):
    reset(); mc = ModelClient(Settings(), "compose")
    try: mc.complete([{"role": "user", "content": "x"}]); print("real transport denied host: NO EXCEPTION")
    except EgressDenied: print("real transport, denied host: EgressDenied; DNS lookups before deny: %s" % calls)
reset()
