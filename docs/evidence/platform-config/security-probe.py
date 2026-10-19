import io, logging, os, socket, sys, contextlib
from unittest import mock
sys.path.insert(0, "/work")
import httpx
from engine.egress import EgressPolicy, GuardedTransport, EgressDenied, is_local_endpoint, host_of
BS = chr(92); TAB = chr(9); ZW = chr(0x200b); CYR_A = chr(0x430); NL = chr(10)
def hdr(t): print(NL + "### " + t)

hdr("1. GuardedTransport host matching (allow = allowed.example, 10.0.0.5)")
calls = []
class Rec(httpx.BaseTransport):
    def __init__(self, redirect_to=None): self.redirect_to = redirect_to
    def handle_request(self, req):
        calls.append(str(req.url))
        if self.redirect_to and req.url.host == "allowed.example" and req.url.path == "/":
            return httpx.Response(302, headers={"location": self.redirect_to})
        return httpx.Response(200)
pol = EgressPolicy(["allowed.example", "10.0.0.5"])
urls = [
 "http://allowed.example/", "http://ALLOWED.EXAMPLE./", "http://allowed.example:1/",
 "https://allowed.example:65535/x", "http://allowed.example@evil.example/",
 "http://allowed.example:pw@evil.example/", "http://evil.example" + chr(35) + "@allowed.example/",
 "http://evil.example?@allowed.example/", "http://evil.example" + BS + "@allowed.example/",
 "http://allowed.example.evil.example/", "http://evil.example/allowed.example",
 "http://2130706433/", "http://0x7f.0.0.1/", "http://0177.0.0.1/", "http://127.1/",
 "http://[::1]/", "http://[::ffff:10.0.0.5]/", "http://10.0.0.5/", "http://012.0.0.5/",
 "http://0xa.0.0.5/", "http://167772165/", "http://allowed%2eexample/",
 "http://allowed.ex" + CYR_A + "mple/", "http://allowed.example../", "http://%61llowed.example/",
]
for u in urls:
    calls.clear()
    c = httpx.Client(transport=GuardedTransport(pol, Rec()), trust_env=False)
    try:
        r = c.get(u); res = "ALLOWED -> inner saw %s" % calls
    except EgressDenied as e: res = "denied host=%r" % e.host
    except Exception as e: res = "error %s: %s" % (type(e).__name__, e)
    print("%-50r %s" % (u, res))

hdr("2. Redirects to other hosts (follow_redirects=True)")
for target in ["http://evil.example/", "http://allowed.example@evil.example/", "//evil.example/", "http://127.0.0.1/", "http://allowed.example/ok"]:
    calls.clear()
    c = httpx.Client(transport=GuardedTransport(pol, Rec(redirect_to=target)), trust_env=False, follow_redirects=True)
    try:
        r = c.get("http://allowed.example/"); res = "status %s, inner saw %s" % (r.status_code, calls)
    except EgressDenied as e: res = "denied host=%r, inner saw %s" % (e.host, calls)
    except Exception as e: res = "error %s: %s" % (type(e).__name__, e)
    print("redirect->%-40r %s" % (target, res))

hdr("3. Socket/DNS spy with real ModelClient (denied host), proxy env set")
from tests.engine_support import base_env, environ
spy = []
def gai(*a, **k): spy.append(("getaddrinfo", a[0])); raise OSError("spy")
def conn(self, addr): spy.append(("connect", addr)); raise OSError("spy")
def cc(addr, *a, **k): spy.append(("create_connection", addr)); raise OSError("spy")
env = base_env(KE_ENV="ci", KE_EGRESS_ALLOWLIST="allowed.example",
               KE_MODELS__COMPOSE__BASE_URL="http://allowed.example/v1",
               HTTP_PROXY="http://allowed.example:3128", HTTPS_PROXY="http://allowed.example:3128",
               ALL_PROXY="socks5://allowed.example:1080", NO_PROXY="*", http_proxy="http://evil.example:3128")
from engine.config import Settings, ConfigError
from engine.llm.client import ModelClient
with environ(env), mock.patch("socket.getaddrinfo", gai), mock.patch.object(socket.socket, "connect", conn), mock.patch("socket.create_connection", cc):
    s = Settings(); mc = ModelClient(s, "compose")
    print("trust_env:", mc.http_client.trust_env, "mounts:", dict(mc.http_client._mounts), "transport:", type(mc.http_client._transport).__name__)
    for u in ["http://evil.example/", "http://allowed.example@evil.example/", "http://[::2]/", "http://2130706433/"]:
        spy.clear()
        try: mc.http_client.get(u); print(u, "NO EXCEPTION")
        except EgressDenied: print("%-40s denied; socket/DNS calls before deny: %s" % (u, spy))
    spy.clear()
    try: mc.http_client.get("http://allowed.example/v1/models")
    except Exception as e: print("allowed host goes direct (no proxy): %s; calls: %s" % (type(e).__name__, spy))

hdr("4. An httpx client built without the guarded transport")
with environ(env), mock.patch("socket.getaddrinfo", gai), mock.patch.object(socket.socket, "connect", conn), mock.patch("socket.create_connection", cc):
    spy.clear()
    raw = httpx.Client()
    print("raw client mounts from env proxies:", {str(k): type(v).__name__ for k, v in raw._mounts.items()})
    try: raw.get("http://evil.example/")
    except Exception as e: print("raw client to evil.example: %s; socket calls reached: %s" % (type(e).__name__, spy))

hdr("5. is_local_endpoint (service names = defaults) via str(AnyHttpUrl) like startup")
from pydantic import AnyHttpUrl, TypeAdapter
ta = TypeAdapter(AnyHttpUrl)
names = ["gateway","api","worker","postgres","neo4j","valkey","phoenix"]
for raw in ["http://localhost:6006","http://localhost.evil.com","http://127.0.0.1.nip.io","http://0.0.0.0:6006",
            "http://[::ffff:127.0.0.1]:6006","http://[::1]:6006","http://phoenix.evil.com","http://phoenix.",
            "http://PHOENIX:6006","http://phoenix-evil","http://localhost@evil.com","http://evil.com" + BS + "@localhost",
            "http://evil.com" + chr(35) + "@localhost","http://2130706433","http://0x7f000001","http://127.1","http://[::]:6006",
            "http://127.255.255.254","http://localhost%2eevil.com","http://evil.com:80@localhost","http://localhost:6006@evil.com",
            "http://evil.com%00.localhost","http://ph%6fenix","http://localhost./","http://api.:1"]:
    try: norm = str(ta.validate_python(raw))
    except Exception as e: print("%-40r pydantic rejects (%s)" % (raw, type(e).__name__)); continue
    print("%-40r -> %-40r host=%-22r local=%s" % (raw, norm, host_of(norm), is_local_endpoint(norm, names)))
rawbs = "http://localhost" + BS + "@evil.com"
print("raw (no pydantic)", repr(rawbs), is_local_endpoint(rawbs, names), host_of(rawbs))

hdr("6. startup.check refusals")
from engine.startup import check, StartupRefused
def run(label, **ov):
    e = base_env(**ov)
    with environ(e):
        buf = io.StringIO(); h = logging.StreamHandler(buf); logging.getLogger("engine").addHandler(h)
        try:
            s = Settings(); check(s); res = "STARTS" + ((" (warn: %r)" % buf.getvalue().strip()) if buf.getvalue() else "")
        except StartupRefused as x: res = "refused: %s" % x
        except ConfigError as x: res = "ConfigError: %s" % x
        except Exception as x: res = "UNWRAPPED %s: %s" % (type(x).__name__, x)
        finally: logging.getLogger("engine").removeHandler(h)
    print("%-55s %s" % (label, res))
for v in ["false","False","FALSE","0","off","no","f","n"," false","false ",""]:
    run("ci auth=%r" % v, KE_ENV="ci", KE_AUTH__ENABLED=v)
for v in ["dev","DEV","Dev"," dev","dev ","prod","","development"]:
    run("env=%r auth=false" % v, KE_ENV=v, KE_AUTH__ENABLED="false")
for v in ["false","0","False","no"," false",""]:
    run("ci KE hide_inputs=%r" % v, KE_ENV="ci", KE_TELEMETRY__HIDE_INPUTS=v)
    run("ci OPENINFERENCE_HIDE_OUTPUTS=%r" % v, KE_ENV="ci", OPENINFERENCE_HIDE_OUTPUTS=v)
run("ci hide KE=true but OI env=false (precedence)", KE_ENV="ci", KE_TELEMETRY__HIDE_INPUTS="true", OPENINFERENCE_HIDE_INPUTS="false")
for v in ["changeme-x","CHANGEME","ChangeMe-x"," changeme-x","changeme",TAB+"changeme",ZW+"changeme-x","ch"+CYR_A+"ngeme"," ","x"]:
    run("ci postgres pw=%r" % v, KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD=v)
run("ci postgres pw empty", KE_ENV="ci", KE_STORES__POSTGRES__PASSWORD="")
for t, ep in [("otlp","http://evil.example:6006"),("OTLP","http://evil.example"),("otlp","http://localhost.evil.com"),
              ("otlp","http://0.0.0.0:6006"),("console","http://evil.example"),("off","http://evil.example")]:
    run("dev tracing=%s KE endpoint=%s" % (t, ep), KE_ENV="dev", KE_AUTH__ENABLED="true", HARNESS_TRACING=t, KE_TELEMETRY__COLLECTOR_ENDPOINT=ep)
run("ci KE tracing=otlp, PHOENIX endpoint evil", KE_ENV="ci", KE_TELEMETRY__TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example")
run("ci service_names override adds evil", KE_ENV="ci", KE_STACK__SERVICE_NAMES="[\"evil.example\"]", HARNESS_TRACING="otlp", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://evil.example")
run("ci service_names non-JSON (unwrapped?)", KE_ENV="ci", KE_STACK__SERVICE_NAMES="evil.example,s3cr3t-in-msg?")
run("ci model upstream not allowlisted", KE_ENV="ci", KE_MODEL_UPSTREAM="evil.example:11434", KE_EGRESS_ALLOWLIST="allowed.example")
run("ci model upstream userinfo trick", KE_ENV="ci", KE_MODEL_UPSTREAM="allowed.example@evil.example:1", KE_EGRESS_ALLOWLIST="allowed.example")
run("ci model upstream http://allowed@evil", KE_ENV="ci", KE_MODEL_UPSTREAM="http://allowed.example@evil.example/", KE_EGRESS_ALLOWLIST="allowed.example")
run("ci model upstream garbage :::", KE_ENV="ci", KE_MODEL_UPSTREAM=":::", KE_EGRESS_ALLOWLIST="allowed.example")
run("ci model upstream [::1 (unbalanced)", KE_ENV="ci", KE_MODEL_UPSTREAM="[::1", KE_EGRESS_ALLOWLIST="allowed.example")
run("ci base_url userinfo", KE_ENV="ci", KE_MODELS__AUDIT__BASE_URL="http://allowed.example@evil.example/v1", KE_EGRESS_ALLOWLIST="allowed.example")

hdr("7. configure_tracing: settings say console, harness env decides exporter")
from opentelemetry import trace
from engine.telemetry import configure_tracing
cases = [("KE_TELEMETRY__TRACING=console, PHOENIX endpoint evil, HARNESS_TRACING unset",
          dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), True),
         ("KE_TELEMETRY__TRACING=console, KE endpoint local, PHOENIX evil, HARNESS_TRACING=otlp",
          dict(KE_ENV="ci", KE_TELEMETRY__TRACING="console", KE_TELEMETRY__COLLECTOR_ENDPOINT="http://localhost:6006",
               HARNESS_TRACING="otlp", PHOENIX_COLLECTOR_ENDPOINT="http://evil.example:4318"), False)]
for label, ov, drop in cases:
    e = base_env(**ov)
    if drop: e.pop("HARNESS_TRACING", None)
    with environ(e):
        trace._TRACER_PROVIDER = None; trace._TRACER_PROVIDER_SET_ONCE._done = False
        s = Settings()
        try: check(s); chk = "check passes"
        except StartupRefused as x: chk = "check refuses: %s" % x
        installed = configure_tracing(s)
        p = trace.get_tracer_provider()
        exps = []
        for sp in getattr(getattr(p, "_active_span_processor", None), "_span_processors", ()):
            ex = getattr(sp, "span_exporter", None)
            exps.append((type(ex).__name__, getattr(ex, "_endpoint", None)))
        print(label); print("   settings.tracing=%s endpoint=%s; %s; installed=%s; exporters=%s" % (s.telemetry.tracing, s.telemetry.collector_endpoint, chk, installed, exps))
        with contextlib.suppress(Exception): p.shutdown()
