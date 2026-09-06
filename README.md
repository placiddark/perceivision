# PERCEIVISION — Always-On Personal AI

An always-on personal AI with persistent memory, reusable skills, chosen
tool access, and cross-workflow task execution. A Helkhem53 hive project,
built for the Nebius x NVIDIA Global AI Hackathon — Personal AI track.

**Live:** https://placiddark.github.io/perceivision/

License: Apache 2.0 (see `LICENSE`, at the top of this repo).

## The Four Pillars

1. **Persistent memory** — facts + open threads, durable across process
   death. Proven: `run_p1_smoke.py` restart test.
2. **Reusable skills** — procedural memory as a loadable, callable,
   extensible skill registry (builtins + JSON skills from disk).
3. **Chosen tool access** — whitelist tool registry; every call audited
   to `state/tool_audit.jsonl`. Nothing runs that was not chosen.
4. **Cross-workflow execution** — one loop: message → memory → skills →
   tools → model → artifact. Every turn carried to `state/turns.jsonl`.

## Status

P1 CORE COMPLETE — smoke: **13 PASS / 0 FAIL** (2026-09-06), including
persistence across a full process restart. Model backend pluggable and
OpenAI-compatible: Nebius Token Factory (NVIDIA Nemotron) via
`NEBIUS_API_KEY`; deterministic local stub for development.

## Run

```
python run_p1_smoke.py
```

Requires Python 3.10+. No third-party dependencies for P1.

## Layout

- `perceivision/memory.py` — Pillar 1
- `perceivision/skills.py` — Pillar 2
- `perceivision/tools.py` — Pillar 3
- `perceivision/agent.py` — Pillar 4 (the loop)
- `perceivision/backends.py` — model backends (Token Factory / stub)
- `run_p1_smoke.py` — end-to-end pillar verification

## Hive

Part of Helkhem53 — https://placiddark.github.io/helkhem53/

⟐ 717Δ707ΔΔ
