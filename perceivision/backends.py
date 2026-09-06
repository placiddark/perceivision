"""Model backends — pluggable, OpenAI-compatible.

Token Factory (Nebius) speaks the OpenAI-compatible API natively:
  POST {base_url}/chat/completions  {model, messages, ...}

Two backends:
  NebiusBackend  — real inference via NEBIUS_API_KEY (Token Factory)
  StubBackend    — deterministic local responses for P1 development

The agent never talks to a model directly; it talks to a Backend.
Swap = one environment variable. Nemotron 3 Ultra lands here.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional

NebiusBaseURL = os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1")
NemotronModel = os.environ.get("NEBIUS_MODEL", "nvidia/nemotron-3-ultra-80b")


class Backend:
    def chat(self, system: str, messages: List[Dict[str, str]], **kw: Any) -> Dict[str, Any]:
        raise NotImplementedError


class StubBackend(Backend):
    """Deterministic dev backend — pattern-matches intents, no network."""

    def chat(self, system: str, messages: List[Dict[str, str]], **kw: Any) -> Dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        # the system prompt carries the injected memory context — use it
        sys_ctx = messages[0]["content"] if messages else ""
        facts_str = ""
        marker = "Known facts: "
        if marker in sys_ctx:
            facts_str = sys_ctx.split(marker, 1)[1].split("\n", 1)[0]
        low = last.lower()
        if "remember" in low:
            reply = "ACK: fact persisted to durable memory (stub backend)."
        elif "recall" in low or "what do you know" in low:
            reply = f"From persistent memory: {facts_str}" if facts_str else "Memory is empty."
        elif "skill" in low:
            reply = "STUB: skill invocation would load and run the named procedure."
        elif any(w in low for w in ("hello", "hi ", "status", "who are you")):
            reply = (
                "PERCEIVISION (stub). Always-on personal AI: persistent memory, "
                "reusable skills, chosen tools, cross-workflow execution."
            )
        else:
            reply = f"STUB-OK: {last[:120]}"
        return {
            "backend": "stub",
            "model": "deterministic-stub",
            "reply": reply,
            "usage": {"total_tokens": 0},
        }


class NebiusBackend(Backend):
    """Real inference through Nebius Token Factory (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = NebiusBaseURL,
        model: str = NemotronModel,
    ) -> None:
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, messages: List[Dict[str, str]], **kw: Any) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("NEBIUS_API_KEY not set — Builder Program credits pending")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            **kw,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        started = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        reply = body["choices"][0]["message"]["content"]
        return {
            "backend": "nebius",
            "model": self.model,
            "reply": reply,
            "usage": body.get("usage", {}),
            "latency_s": round(time.time() - started, 2),
        }


def make_backend() -> Backend:
    """NEBIUS_API_KEY present -> real Token Factory; else deterministic stub."""
    if os.environ.get("NEBIUS_API_KEY"):
        return NebiusBackend()
    return StubBackend()
