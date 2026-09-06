"""Pillar 1 — Persistent Memory.

JSON-backed memory that survives restarts. Two stores:
  facts   — durable knowledge (who, what, stable conventions)
  threads — open work items (task state that carries across sessions)

Thread-safety: single-process asyncio loop -> plain dict + atomic file writes.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MEM_DIR = Path(os.environ.get(
    "PERCEIVISION_MEM_DIR",
    Path(__file__).resolve().parent / "state" / "memory",
))


class PersistentMemory:
    """Pillar 1. Facts + threads, durable across process restarts."""

    def __init__(self, mem_dir: Optional[Path] = None) -> None:
        self.mem_dir = Path(mem_dir or DEFAULT_MEM_DIR)
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.facts_file = self.mem_dir / "facts.json"
        self.threads_file = self.mem_dir / "threads.json"
        self._facts: Dict[str, Any] = self._load(self.facts_file, {})
        self._threads: Dict[str, Any] = self._load(self.threads_file, {})
        # session-only recall log (not persisted; proves per-session behavior)
        self._recalled: List[str] = []

    # ── persistence ─────────────────────────────────────────────────────────
    @staticmethod
    def _load(path: Path, default: Any) -> Any:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save(self, path: Path, data: Any) -> None:
        # atomic write: temp file in same dir, then replace
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ── facts ───────────────────────────────────────────────────────────────
    def remember_fact(self, key: str, value: Any, source: str = "operator") -> Dict[str, Any]:
        entry = {
            "value": value,
            "source": source,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._facts[key] = entry
        self._save(self.facts_file, self._facts)
        return entry

    def recall_fact(self, key: str, default: Any = None) -> Any:
        entry = self._facts.get(key)
        if entry is None:
            return default
        self._recalled.append(f"fact:{key}")
        return entry["value"]

    def all_facts(self) -> Dict[str, Any]:
        return {k: v["value"] for k, v in self._facts.items()}

    # ── threads ──────────────────────────────────────────────────────────────
    def open_thread(self, name: str, note: str = "") -> Dict[str, Any]:
        thread = {
            "name": name,
            "note": note,
            "status": "open",
            "created_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "history": [],
        }
        self._threads[name] = thread
        self._save(self.threads_file, self._threads)
        return thread

    def update_thread(self, name: str, status: str, note: str = "") -> Dict[str, Any]:
        thread = self._threads.get(name)
        if thread is None:
            thread = self.open_thread(name, note)
        thread["status"] = status
        thread["updated_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        thread["history"].append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": status,
            "note": note,
        })
        self._save(self.threads_file, self._threads)
        return thread

    def recall_thread(self, name: str) -> Optional[Dict[str, Any]]:
        return self._threads.get(name)

    def open_threads(self) -> List[str]:
        return [n for n, t in self._threads.items() if t["status"] == "open"]

    # ── introspection ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        return {
            "facts": len(self._facts),
            "threads": len(self._threads),
            "open_threads": len(self.open_threads()),
            "recalled_this_session": len(self._recalled),
        }

    def wipe(self) -> None:
        """Test helper — clears both stores AND the on-disk state."""
        self._facts = {}
        self._threads = {}
        self._save(self.facts_file, self._facts)
        self._save(self.threads_file, self._threads)
