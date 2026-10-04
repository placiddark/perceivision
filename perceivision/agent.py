"""Pillar 4 — Cross-Workflow Execution.

The agent loop: one thread of execution from message to delivery,
crossing memory -> skills -> tools -> model -> artifact, with every
step carried, not dropped. The seams between workflows are where
assistants usually lose context; here the seams ARE the loop.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .backends import Backend, make_backend
from .memory import PersistentMemory
from .skills import SkillRegistry
from .tools import ToolRegistry, register_default_tools

STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "You are PERCEIVISION, an always-on personal AI. You have persistent memory "
    "(facts + open threads), reusable skills, and a whitelist of tools. "
    "Be terse and precise. When the user asks to remember something, it is "
    "persisted durably before you reply."
)


class PerceivisionAgent:
    """The four pillars bound into one execution loop."""

    def __init__(self, backend: Optional[Backend] = None) -> None:
        # Pillar 1
        self.memory = PersistentMemory()
        # Pillar 2
        self.skills = SkillRegistry()
        # Pillar 3
        self.tools = ToolRegistry()
        register_default_tools(self.tools, self.memory, self.skills)
        # Model
        self.backend = backend or make_backend()
        # Conversation state (session)
        self.history: List[Dict[str, str]] = []

    # ── per-turn context assembly (memory injected into every turn) ─────────
    def _context(self) -> str:
        facts = self.memory.all_facts()
        open_threads = self.memory.open_threads()
        lines = []
        if facts:
            lines.append("Known facts: " + json.dumps(facts, ensure_ascii=False))
        if open_threads:
            lines.append("Open threads: " + ", ".join(open_threads))
        return "\n".join(lines)

    # ── the loop ─────────────────────────────────────────────────────────────
    def turn(self, user_text: str) -> Dict[str, Any]:
        trace: List[str] = []

        # 1. durable side-effects first (remember-before-reply)
        handled = self._try_direct_ops(user_text, trace)

        # 2. assemble turn context from persistent memory
        context = self._context()

        # 3. model reply (system + memory context + history + user)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context},
            *self.history[-6:],
            {"role": "user", "content": user_text},
        ]
        model_out = self.backend.chat(SYSTEM_PROMPT, messages)
        reply = model_out.get("reply", "")

        # 3b. execute model-emitted directives (Nemotron emits JSON directives
        #     like {"name": "clock", "args": {}} — honour them, never just echo)
        executed = self._execute_directive(reply, trace)
        if executed is not None:
            reply = executed

        if handled:
            # direct op already produced the ground truth; model narrates it
            reply = f"{handled}\n{reply}"

        # 4. carry the seam: history append happens even on partial failure
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply})

        # 5. artifact: the turn record (cross-workflow: memory -> model -> disk)
        turn_record = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "user": user_text,
            "reply": reply,
            "direct_ops": trace,
            "model": model_out.get("model", "?"),
            "backend": model_out.get("backend", "?"),
            "usage": model_out.get("usage", {}),
            "latency_s": model_out.get("latency_s"),
        }
        with (STATE_DIR / "turns.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn_record, ensure_ascii=False) + "\n")

        return turn_record

    # ── direct operations (deterministic, model-independent) ─────────────────
    def _try_direct_ops(self, text: str, trace: List[str]) -> Optional[str]:
        """Pattern-routed deterministic ops: remember / recall / skills / tools."""
        low = text.lower().strip()

        if low.startswith("remember "):
            body = text[9:].strip()
            if "=" in body:
                key, _, value = body.partition("=")
                key, value = key.strip(), value.strip()
                self.memory.remember_fact(key, value)
                trace.append(f"memory.remember_fact({key!r})")
                return f"[durable] remembered: {key} = {value}"
            # Natural-language form: "remember that X is Y" / "remember X is Y".
            # Written deterministically here rather than delegated to the model,
            # so a durable write never depends on the shape of model output.
            clause = re.sub(r"^that\s+", "", body).strip().rstrip(".")
            key, sep, value = clause.partition(" is ")
            if sep:
                self.memory.remember_fact(key.strip(), value.strip())
                trace.append(f"memory.remember_fact({key.strip()!r})")
                return f"[durable] remembered: {key.strip()} = {value.strip()}"
            self.memory.remember_fact("note", clause)
            trace.append("memory.remember_fact('note')")
            return f"[durable] remembered note: {clause}"

        if low.startswith("open thread "):
            name = text[12:].strip()
            self.memory.open_thread(name)
            trace.append(f"memory.open_thread({name!r})")
            return f"[durable] thread opened: {name}"

        if low.startswith("close thread "):
            name = text[13:].strip()
            self.memory.update_thread(name, "closed")
            trace.append(f"memory.close_thread({name!r})")
            return f"[durable] thread closed: {name}"

        if low.startswith("run skill "):
            parts = text[10:].split()
            name = parts[0] if parts else ""
            args = parts[1:]
            out = self.tools.call("skill-invoke", name, *args, ctx={"memory": self.memory, "skills": self.skills})
            trace.append(f"tools.skill-invoke({name!r})")
            return "[skill] " + json.dumps(out.get("result", out), ensure_ascii=False)[:400]

        if low.startswith("use tool "):
            parts = text[9:].split()
            name = parts[0] if parts else ""
            args = parts[1:]
            out = self.tools.call(name, *args, ctx={"memory": self.memory, "skills": self.skills})
            trace.append(f"tools.call({name!r})")
            return "[tool] " + json.dumps(out.get("result", out), ensure_ascii=False)[:400]

        return None

    # ── model-emitted directive execution (whitelist-gated) ─────────────────
    #: Only these directive names may be dispatched. Anything else is ignored.
    DIRECTIVE_ALLOWLIST = (
        "clock",
        "echo",
        "memory-lookup",
        "recall",
        "skill-invoke",
        "remember",
    )

    def _execute_directive(self, reply: str, trace: List[str]) -> Optional[str]:
        """If the model emitted a JSON directive, run it and return real output.

        Nemotron 3 Ultra answers tool-shaped turns with a JSON object rather
        than prose. Echoing that JSON back to the user would be a fake tool
        call, so it is parsed and executed instead. Strictly allowlisted:
        the model can only reach tools the operator already granted.
        """
        if not reply:
            return None
        # models sometimes wrap the JSON in prose or a fenced block
        start, end = reply.find("{"), reply.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            directive = json.loads(reply[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(directive, dict):
            return None

        name = directive.get("name") or directive.get("tool")

        # Shape Nemotron emits for a bare memory write: {"facts": ["..."]}
        # with no "name" key at all. Treated as a remember directive.
        if name is None and isinstance(directive.get("facts"), list):
            name = "remember"
            directive = {"name": "remember", "args": directive["facts"]}

        if name is None and isinstance(directive.get("operations"), list):
            # Alternate directive shape Nemotron emits for memory writes:
            #   {"operations": [{"op": "upsert_fact", "fact": "..."}, ...]}
            applied = []
            for operation in directive["operations"]:
                if not isinstance(operation, dict):
                    continue
                op = operation.get("op") or operation.get("name")
                fact = operation.get("fact") or operation.get("value") or operation.get("text")
                if op in ("upsert_fact", "remember", "remember_fact") and fact:
                    key, _, value = str(fact).partition(" is ")
                    key = key.strip() or "note"
                    self.memory.remember_fact(key, value.strip() or str(fact))
                    applied.append(key)
                elif op in ("open_thread", "open thread"):
                    self.memory.open_thread(str(fact))
                    applied.append(f"thread:{fact}")
                else:
                    trace.append(f"directive.op_rejected({op!r})")
            if applied:
                trace.append(f"memory.operations({applied!r})")
                return "[durable] applied: " + "; ".join(applied)
            return None

        if name not in self.DIRECTIVE_ALLOWLIST:
            trace.append(f"directive.rejected({name!r})")
            return None

        def _flatten(obj: Any) -> List[str]:
            """Deep-flatten directive args into a flat list of strings."""
            if obj is None:
                return []
            if isinstance(obj, str):
                return [obj] if obj.strip() else []
            if isinstance(obj, (int, float, bool)):
                return [str(obj)]
            if isinstance(obj, dict):
                out: List[str] = []
                for v in obj.values():
                    out.extend(_flatten(v))
                return out
            if isinstance(obj, (list, tuple)):
                out = []
                for v in obj:
                    out.extend(_flatten(v))
                return out
            return [str(obj)]

        args = _flatten(directive.get("args"))

        if name == "remember":
            written = []
            for fact in args:
                key, _, value = fact.partition(" is ")
                key = key.strip() or "note"
                self.memory.remember_fact(key, value.strip() or fact)
                written.append(key)
            trace.append(f"memory.remember_fact({written!r})")
            return "[durable] remembered: " + "; ".join(written)

        if name == "recall":
            name = "memory-lookup"

        out = self.tools.call(
            name, *args, ctx={"memory": self.memory, "skills": self.skills}
        )
        trace.append(f"tools.call({name!r})")
        if not out.get("ok", True):
            return f"[tool:{name}] failed: {out.get('error')}"
        return "[tool:" + name + "] " + json.dumps(
            out.get("result", out), ensure_ascii=False, default=str
        )[:400]

    # ── introspection ────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "pillar1_memory": self.memory.stats(),
            "pillar2_skills": self.skills.names(),
            "pillar3_tools": [t["name"] for t in self.tools.describe()],
            "pillar4_backend": getattr(self.backend, "model", "deterministic-stub")
            if hasattr(self.backend, "model") else type(self.backend).__name__,
            "turns_this_session": len(self.history) // 2,
        }
