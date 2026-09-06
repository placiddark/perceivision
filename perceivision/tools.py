"""Pillar 3 — Chosen Tool Access.

Tools are held deliberately: a whitelist registry, not an open shell.
Each tool declares what it does; every call is audited (caller, tool,
args, elapsed). Nothing executes that was not chosen.
"""
from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

AUDIT_LOG = Path(__file__).resolve().parent / "state" / "tool_audit.jsonl"


class ToolRegistry:
    """Pillar 3. Whitelist registry with audit trail."""

    def __init__(self, audit_log: Optional[Path] = None) -> None:
        self.audit_log = audit_log or AUDIT_LOG
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self._tools: Dict[str, Dict[str, Any]] = {}

    # ── registration ────────────────────────────────────────────────────────
    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        danger: str = "low",
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler,
            "danger": danger,
        }

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def describe(self) -> List[Dict[str, str]]:
        return [
            {"name": t["name"], "description": t["description"], "danger": t["danger"]}
            for t in self._tools.values()
        ]

    # ── audit ────────────────────────────────────────────────────────────────
    def _audit(self, entry: Dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self.audit_log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ── execution ────────────────────────────────────────────────────────────
    def call(self, name: str, *args: str, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"tool not in whitelist: {name}", "available": self.names()}
        started = time.time()
        try:
            if ctx is not None:
                result = tool["handler"](ctx, *args)
            else:
                result = tool["handler"](*args)
            ok = not (isinstance(result, dict) and result.get("error"))
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
            ok = False
        entry = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "tool": name,
            "args": list(args),
            "ok": ok,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }
        self._audit(entry)
        return {"tool": name, "result": result, "ok": ok}


# ── default tool battery ──────────────────────────────────────────────────────
def register_default_tools(registry: ToolRegistry, memory: Any, skills: Any) -> None:
    """The chosen instruments: memory ops, skill invocation, time, echo."""

    def memory_lookup(ctx: Dict[str, Any], key: str = "") -> Dict[str, Any]:
        if not key:
            return {"facts": memory.all_facts(), "open_threads": memory.open_threads()}
        value = memory.recall_fact(key)
        return {"key": key, "value": value} if value is not None else {"key": key, "missing": True}

    def skill_invoke(ctx: Dict[str, Any], name: str = "", *args: str) -> Dict[str, Any]:
        if not name:
            return {"error": "usage: skill-invoke <name> [args]"}
        return skills.invoke(name, {"memory": memory, "skills": skills}, *args)

    def now(ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {"utc": _dt.datetime.now(_dt.timezone.utc).isoformat()}

    def echo(ctx: Dict[str, Any], *args: str) -> Dict[str, Any]:
        return {"echo": " ".join(args)}

    registry.register("memory-lookup", "Read persistent memory: facts + open threads", memory_lookup, "low")
    registry.register("skill-invoke", "Invoke a loaded skill by name", skill_invoke, "low")
    registry.register("clock", "Current UTC time", now, "low")
    registry.register("echo", "Echo arguments back (health check)", echo, "low")
