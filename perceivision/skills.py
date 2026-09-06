"""Pillar 2 — Reusable Skills.

Skills are procedural memory: named procedures with steps, pitfalls, and
verification. Loaded from a skills directory (JSON files), callable by name,
and extensible at runtime (new skills can be registered and persisted).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Skill:
    name: str
    description: str
    steps: List[str]
    handler: Optional[Callable[..., Any]] = None
    pitfalls: List[str] = field(default_factory=list)
    verify: Optional[str] = None


class SkillRegistry:
    """Pillar 2. Loadable, callable, extensible procedure library."""

    def __init__(self, skills_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir or SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, Skill] = {}
        self._builtin()  # seed the builtins
        self.load_dir()

    # ── builtin skills (Python handlers = real execution) ────────────────────
    def _builtin(self) -> None:
        def memory_snapshot(ctx: Dict[str, Any]) -> Dict[str, Any]:
            mem = ctx.get("memory")
            return {"stats": mem.stats()} if mem else {"error": "no memory in ctx"}

        def remember(ctx: Dict[str, Any], key: str = "", value: str = "") -> Dict[str, Any]:
            mem = ctx.get("memory")
            if not (mem and key):
                return {"error": "usage: remember <key> <value>"}
            entry = mem.remember_fact(key, value, source="skill:remember")
            return {"remembered": key, "entry": entry}

        def list_skills(ctx: Dict[str, Any]) -> Dict[str, Any]:
            return {"skills": sorted(self._skills.keys())}

        self.register(Skill(
            name="memory-snapshot",
            description="Report memory stats: facts, threads, open threads.",
            steps=["read stats from the persistent memory store"],
            handler=memory_snapshot,
            verify="returns dict with keys facts/threads/open_threads",
        ))
        self.register(Skill(
            name="remember",
            description="Persist a fact durably: remember <key> <value>",
            steps=["write key=value to persistent memory"],
            handler=remember,
            verify="fact recalled with identical value after restart",
        ))
        self.register(Skill(
            name="list-skills",
            description="List all loaded skills.",
            steps=["enumerate the skill registry"],
            handler=list_skills,
            verify="includes memory-snapshot, remember, list-skills",
        ))

    # ── registry mechanics ────────────────────────────────────────────────────
    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def load_dir(self) -> int:
        """Load every skill JSON in the skills dir. Returns count loaded."""
        count = 0
        for f in sorted(self.skills_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                self.register(Skill(
                    name=d["name"],
                    description=d.get("description", ""),
                    steps=d.get("steps", []),
                    pitfalls=d.get("pitfalls", []),
                    verify=d.get("verify"),
                ))
                count += 1
            except Exception as e:
                print(f"[skills] failed to load {f.name}: {e}")
        return count

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def names(self) -> List[str]:
        return sorted(self._skills.keys())

    # ── persistence of new skills ────────────────────────────────────────────
    def persist(self, skill: Skill) -> Path:
        """Write a skill to disk so it survives restarts (procedural memory)."""
        path = self.skills_dir / f"{skill.name}.json"
        path.write_text(json.dumps({
            "name": skill.name,
            "description": skill.description,
            "steps": skill.steps,
            "pitfalls": skill.pitfalls,
            "verify": skill.verify,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # ── execution ─────────────────────────────────────────────────────────────
    def invoke(self, name: str, ctx: Dict[str, Any], *args: str) -> Dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            return {"error": f"unknown skill: {name}", "available": self.names()}
        if skill.handler is None:
            return {
                "skill": name,
                "description": skill.description,
                "steps": skill.steps,
                "pitfalls": skill.pitfalls,
                "verify": skill.verify,
                "note": "declarative skill loaded from disk; follow its steps",
            }
        started = time.time()
        result = skill.handler(ctx, *args)
        return {
            "skill": name,
            "result": result,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }
