"""Pillar 4 — Cross-Workflow Execution.

The agent loop: one thread of execution from message to delivery,
crossing memory -> skills -> tools -> model -> artifact, with every
step carried, not dropped. The seams between workflows are where
assistants usually lose context; here the seams ARE the loop.
"""
from __future__ import annotations

import datetime as _dt
import json
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
            return None

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
