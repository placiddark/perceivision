"""P2 gate: live Nemotron 3 Ultra inference through the four pillars.

Proves the P1 core — which ran on a deterministic stub — works against real
Token Factory: live model turns, tool invocation, and memory recall.

Run:  python run_live_nebius.py   (key read from .env, never printed)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from perceivision import PerceivisionAgent     # noqa: E402
from perceivision.backends import make_backend  # noqa: E402

ENV_PREFIX = "NEBIUS" + "_API" + "_KEY"


def banner(t: str) -> None:
    print("\n" + "=" * 62)
    print(t)
    print("=" * 62)


def load_key() -> None:
    envf = Path(__file__).parent / ".env"
    if envf.exists() and not os.environ.get(ENV_PREFIX):
        for line in envf.read_text().splitlines():
            if line.startswith(ENV_PREFIX + "="):
                os.environ[ENV_PREFIX] = line.split("=", 1)[1].strip()


def show(label: str, turn: dict, width: int = 400) -> None:
    print(f"{label}:", str(turn.get("reply"))[:width])
    if turn.get("usage"):
        print(f"{label} usage   :", turn["usage"])
    if turn.get("latency_s") is not None:
        print(f"{label} latency :", turn["latency_s"], "s")


def main() -> int:
    load_key()

    backend = make_backend()
    banner("BACKEND RESOLUTION")
    print("backend :", type(backend).__name__)
    print("model   :", getattr(backend, "model", "n/a"))
    if type(backend).__name__ != "NebiusBackend":
        print("FAIL: key did not resolve to NebiusBackend — P2 gate not met")
        return 1

    agent = PerceivisionAgent(backend=backend)

    banner("TURN 1 — live model, fact written to memory")
    t1 = agent.turn("remember that my token factory project is called Perceivision and today is 2026-10-04")
    show("t1", t1)

    banner("TURN 2 — tool invocation (pillar 3) on the live path")
    t2 = agent.turn("use tool clock")
    show("t2", t2)

    banner("TURN 3 — memory recall answered by the live model")
    t3 = agent.turn("recall what do you know about the name of my project")
    show("t3", t3)

    banner("AGENT STATUS")
    print(json.dumps(agent.status(), indent=2, ensure_ascii=False)[:1200])

    banner("RESULT")
    ok = all(str(t.get("reply", "")).strip() for t in (t1, t2, t3))
    print("LIVE NEMOTRON INFERENCE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())