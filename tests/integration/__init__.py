"""Integration tests (PS-2.7 *Mechanism*): run by `scripts/test.sh full` only,
inside the one-shot `gates-it` compose service on the internal `backend`
network, against the launched stack (ADR-KE-009, architecture §2.2).

Run anywhere else (for example the network-less `gates` service), every test
fails with a message naming what it could not reach and where it must run;
none passes vacuously and none skips (no test may skip on network grounds,
ADR-KE-009)."""
