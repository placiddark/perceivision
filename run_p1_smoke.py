"""P1 smoke test — exercises all four pillars, then proves persistence
across a full process restart (subprocess), then reports."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from perceivision import PerceivisionAgent  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(f"{name}{' :: ' + detail if detail else ''}")
    print(("  PASS  " if cond else "  FAIL  ") + name + (f" :: {detail}" if detail else ""))


def phase(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 50 - len(title)))


def main() -> int:
    # fresh state for a clean run
    import shutil
    state = HERE / "perceivision" / "state"
    if state.exists():
        shutil.rmtree(state)

    phase("PILLAR 1 — persistent memory (session A)")
    agent = PerceivisionAgent()
    t1 = agent.turn("remember operator = Darren Thompson, founder of Helkhem53")
    check("remember op lands durable", "[durable] remembered" in t1["reply"])
    t2 = agent.turn("open thread perceivision-p1-core")
    check("open thread lands durable", "[durable] thread opened" in t2["reply"])
    t3 = agent.turn("recall what do you know about the operator")
    check("memory context injected into model turn", "Darren Thompson" in t3["reply"] or "operator" in t3["reply"].lower())
    t4 = agent.turn("close thread perceivision-p1-core")
    check("close thread lands durable", "[durable] thread closed" in t4["reply"])

    phase("PILLAR 2 — reusable skills")
    t5 = agent.turn("run skill memory-snapshot")
    check("skill invoked via tool whitelist", '"facts": 1' in t5["reply"] or '"facts":1' in t5["reply"].replace(" ", ""), t5["reply"][:120])
    t6 = agent.turn("run skill list-skills")
    check("skill registry enumerated", "memory-snapshot" in t6["reply"] and "remember" in t6["reply"])

    phase("PILLAR 3 — chosen tool access")
    t7 = agent.turn("use tool clock")
    check("whitelisted tool called + audited", "[tool]" in t7["reply"] and "utc" in t7["reply"].lower())
    t8 = agent.turn("use tool memory-lookup operator")
    check("memory-lookup via whitelist", "Darren Thompson" in t8["reply"])
    audit = (HERE / "perceivision" / "state" / "tool_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    check("audit trail on disk", len(audit) >= 3, f"{len(audit)} audited calls")

    phase("PILLAR 4 — cross-workflow seam (turn record artifact)")
    turns = (HERE / "perceivision" / "state" / "turns.jsonl").read_text(encoding="utf-8").strip().splitlines()
    check("every turn carried to artifact", len(turns) == 8, f"{len(turns)} turn records")
    rec = json.loads(turns[-1])
    check("turn record carries trace + backend", "direct_ops" in rec and "backend" in rec)

    phase("RESTART PROOF — pillar 1 across process death")
    probe = (
        "import sys; sys.path.insert(0, r'%s');\n"
        "from perceivision import PerceivisionAgent\n"
        "a = PerceivisionAgent()\n"
        "print(a.memory.recall_fact('operator'))\n"
        "print(a.memory.recall_thread('perceivision-p1-core')['status'])\n"
    ) % str(HERE)
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=str(HERE))
    lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
    check("fact survived process death", "Darren Thompson" in out.stdout, out.stdout.strip()[:80])
    check("thread status survived death", any("closed" == l for l in lines), out.stdout.strip()[:80])

    phase("STATUS")
    print(json.dumps(agent.status(), indent=2, ensure_ascii=False))

    print(f"\n{'='*60}\nP1 SMOKE: {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
