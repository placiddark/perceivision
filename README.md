# PERCEIVISION — Always-On Personal AI

An always-on personal AI with persistent memory, reusable skills, chosen
tool access, and cross-workflow task execution. A Helkhem53 hive project,
built for the Nebius x NVIDIA Global AI Hackathon — Personal AI track.

**Live demo:** https://placiddark.github.io/perceivision/demo/
**Project page:** https://placiddark.github.io/perceivision/

License: **Apache 2.0** (see `LICENSE`, at the top of this repo).

---

## The Four Pillars

1. **Persistent memory** — facts + open threads, durable across process
   death. Proven by a restart test: a fresh process with zero session
   history answers a question using only what is on disk.
2. **Reusable skills** — procedural memory as a loadable, callable,
   extensible skill registry (builtins + JSON skills from disk).
3. **Chosen tool access** — whitelist tool registry; every call audited
   to `state/tool_audit.jsonl`. Nothing runs that was not chosen.
4. **Cross-workflow execution** — one loop: message → memory → skills →
   tools → model → artifact. Every turn carried to `state/turns.jsonl`.

---

## NVIDIA model usage

The model layer is **NVIDIA Nemotron 3 Ultra**, served through **Nebius
Token Factory**:

| | |
|---|---|
| Model | `nvidia/Nemotron-3-Ultra-550b-a55b` |
| Endpoint | `https://api.tokenfactory.us-central1.nebius.com/v1` (OpenAI-compatible) |
| Auth | `NEBIUS_API_KEY` |
| Measured latency | **1.03 – 1.51 s** per turn |
| Measured tokens | **250 – 381** per turn |
| Reasoning tokens | 31 – 139 per turn (surfaced in `usage`) |

Two Nemotron-specific behaviours the integration handles, both found by
running against the real endpoint rather than a mock:

- **Reasoning-saturated turns.** Nemotron 3 Ultra intermittently spends
  an entire turn in reasoning and returns `content: null`. The backend
  retries up to 3× with a nudge before falling back, so a null completion
  is never silently replaced by prose scraped from the reasoning trace.
- **Directive-style output.** For tool-shaped turns the model answers with
  a JSON directive (`{"name": "clock", ...}`, `{"facts": [...]}`, or
  `{"operations": [{"op": "upsert_fact", ...}]}`) rather than prose. Those
  directives are parsed and **executed**, not echoed — a whitelist gates
  dispatch, so the model can only reach tools the operator already granted.

The backend is a one-line swap. With no `NEBIUS_API_KEY` set, the agent
falls back to a deterministic local stub, which is what the smoke suite
runs against.

### Where Token Factory accelerated the workflow

- **Zero-infrastructure inference.** OpenAI-compatible API, so the whole
  agent needed no serving layer, no GPU, no container — the model call is
  three fields (`model`, `messages`, `max_tokens`).
- **Nemotron 3 Ultra is purpose-built for long-running autonomous agents**,
  which is exactly this track's shape. Its reasoning budget is visible in
  the `usage` payload, so agent turns can be cost- and latency-audited.
- **One env var to swap backends**, which made it possible to develop the
  entire four-pillar core against the stub and validate it against the live
  model in the same afternoon.

---

## Status

| Phase | State | Evidence |
|---|---|---|
| P0 · gates | CLOSED | Builders form submitted; Token Factory key live |
| P1 · core | DONE | `run_p1_smoke.py` — **13 PASS / 0 FAIL** |
| P1b · live | DONE | Real Nemotron 3 Ultra inference; **restart proof PASS** |
| P2 · surface | DONE | Hosted live demo |
| P3 · repo | DONE | This repo, Apache-2.0, setup + NVIDIA notes |
| P4 · video | IN FLIGHT | ≤3-min demo + Devpost submission |

**Restart proof (the claim that matters).** Turn 1 writes a fact to disk.
A second, separate process starts with zero conversation history and is
asked what the project is called. It answers from `state/memory/facts.json`:

```
in-session history turns: 0
reply  : Perceivision
backend: nebius | tokens: 242 | lat: 1.14
```

Memory written by one process, recalled by another. That is the difference
between persistent memory and a chat log.

---

## Run

Deterministic smoke suite (no key needed):

```bash
python run_p1_smoke.py
# P1 SMOKE: 13 PASS / 0 FAIL
```

Live model:

```bash
export NEBIUS_API_KEY=...        # Token Factory key
python run_live_nebius.py
# LIVE NEMOTRON INFERENCE: PASS
```

Requires Python 3.10+. No third-party dependencies — standard library only.

## Layout

- `perceivision/memory.py` — Pillar 1
- `perceivision/skills.py` — Pillar 2
- `perceivision/tools.py` — Pillar 3
- `perceivision/agent.py` — Pillar 4 (the loop)
- `perceivision/backends.py` — model backends (Token Factory / stub)
- `run_p1_smoke.py` — deterministic end-to-end verification (13 checks)
- `run_live_nebius.py` — live Nemotron 3 Ultra run
- `docs/` — GitHub Pages site + browser demo

## Known limits

Stated plainly, because a demo that overclaims loses to one that doesn't:

- The browser demo is an **interactive simulation of the loop**, not a live
  model call. Live Nemotron inference runs in the CLI runner, not in the page.
- No auth or multi-user isolation — this is a single-operator personal agent.
- Skills are JSON-defined; there is no skill-authoring UI yet.

---

## Hive

Part of Helkhem53 — https://placiddark.github.io/helkhem53/

⟐ 717Δ707ΔΔ