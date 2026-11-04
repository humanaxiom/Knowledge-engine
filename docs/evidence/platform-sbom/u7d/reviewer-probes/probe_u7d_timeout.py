# Local loopback only: a TCP listener that accepts and never answers (a TLS
# handshake that hangs), then the resolver's real opener with a 2 s timeout.
import socket, threading, sys, importlib.util
spec = importlib.util.spec_from_file_location("sr", r"c:\repos\Knowledge-engine\scripts\sources_resolve.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
held = []
threading.Thread(target=lambda: held.append(srv.accept()), daemon=True).start()
try:
    mod._default_opener(f"https://127.0.0.1:{port}/x", 2)
    print("no exception")
except BaseException as e:
    print("real opener raised:", type(e).__name__, "| reason:", type(getattr(e, "reason", None)).__name__)
    r = mod._transport("127.0.0.1", "https://127.0.0.1/x", e, 2)
    print("_transport ->", type(r).__name__, "| retryable:", isinstance(r, mod._Retryable), "|", str(r))
