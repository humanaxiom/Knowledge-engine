"""The worker service (architecture §2.4): a placeholder until PS-2.6 adds the
queue consumer. It runs the same startup refusals as the api, then idles."""

from __future__ import annotations

import signal
import time

from engine.startup import startup


def main() -> None:
    startup()
    if hasattr(signal, "pause"):
        signal.pause()
    else:  # pragma: no cover - platforms without signal.pause
        while True:
            time.sleep(3600)


if __name__ == "__main__":  # pragma: no cover
    main()
