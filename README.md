# IntelliView — AI Real-time Interview Assistant

> Never fear interviews again; AI escorts you the whole way.

**Current form**: an AI interview assistant rebuilt as a **QwenPaw plugin (fork)**, supporting mock interviews (generic / JD-based / pressure), interview review / career planning / Q&A — now with a **persistent interview archive** (v0.2 data foundation).

> This document is both a **product introduction** and a record of the project's **technical evolution** and **agent collaboration** — from a self-built LangGraph stack to a QwenPaw plugin, and which agent joined when, wrote what, and touched which models.

[中文版](./README_zh.md)

**Contributors (in joining order)**

[![Arthur with Claude Code/Codex/Trae](https://img.shields.io/badge/Arthur-MM--arthur-blue)](https://github.com/MM-arthur) · [![Nova-OpenClaw](https://img.shields.io/badge/Nova-OpenClaw-green)](https://github.com/openclaw) · [![Vega-Hermes](https://img.shields.io/badge/Vega-Hermes%20Agent-orange)](https://github.com/NousResearch/hermes-agent) · **MiniMax-M3** · **GLM5.3**

---

## 1. Capabilities

| Capability | Status | Notes |
|------|------|------|
| 🤝 Mock interview | ✅ available | multi-round, with a structured scoring report |
| 💾 Interview archive & profile | ✅ available (v0.2) | every interview saved as JSON+MD; cross-session profile with weakness memory and progress trend |
| 📚 JD-based question bank | ✅ available (v0.2) | paste a JD → targeted question bank, activated for the next mock interview |
| 🔥 Pressure / deep-dig mode | ✅ available (v0.2) | follow-up ladder (definition → boundary → comparison → failure → scale) until the knowledge boundary is exposed |
| 📊 HTML report card | ✅ available (v0.2) | self-contained page: radar chart + ability cards + weakness list + historical trend line |
| 📜 Interview history | ✅ available (v0.2) | all past sessions with per-dimension scores and a sparkline trend |
| 🃏 Error-card drills | ✅ available (v0.3) | failed questions (≤6/10) auto-become spaced-repetition cards (1→3→7→14d); due cards nagged in every conversation; drills use variant questions + 60-second timed answers |
| 📋 Interview review | ✅ available | technical / project / expression / pros-cons / suggestions |
| 🧭 Career planning | ✅ available | strengths / positioning / short-mid-long-term path |
| 💬 General Q&A | ✅ available | answer as Arthur |
| 🎤 Voice input | ⏸ previously built, deferred | Funasr / Whisper |
| 📷 Behavior analysis | ⏸ previously built, deferred | YOLOv8n |
| 📄 Multi-format parsing | ⏸ previously built, deferred | image/PDF(OCR)/Excel/Word/PPT |
| 🧠 Personal RAG | ⏸ previously built, deferred | FAISS over resume/JD/blog |
| 🔍 Live search | ⏸ previously built, deferred | Tavily |
| 💾 Session persistence | ✅ built into QwenPaw | three-layer memory |

> "⏸ previously built" capabilities belonged to the old LangGraph stack, removed in this fork; they can be reintroduced later via QwenPaw's tool/skill mechanisms.

---

## 2. Current Architecture: QwenPaw Plugin Fork

The project was rebuilt from a self-hosted LangGraph backend + Vue frontend into a **QwenPaw plugin**. The reasoning loop, model routing, three-layer memory, channels, sandbox, and scheduling are all provided by the QwenPaw runtime; the plugin contributes only the domain delta.

```
intelliview-plugin/
├── plugin.json                 # manifest (capabilities: tools/storage/logging/prompts/skills)
├── main.py                     # Plugin class: profile hook + 9 interview tools
├── skills/intelliview/SKILL.md # intent routing + 8 modes
```

The plugin registers four contributions at host startup (verified at runtime):

| Contribution | Notes |
|------|------|
| **Skill** | `SKILL.md` describes the eight-mode workflow, installed into `default` and `QwenPaw_QA_Agent_0.2` workspaces |
| **Prompt** | `intelliview_persona` (priority=90) injects the Arthur persona |
| **Hook** | `PRE_DISPATCH` auto-injects a compact user profile (weakest dimension / recurring weaknesses / target positions) **and due-card reminders** into every conversation |
| **Tools** | `save_interview_session` · `load_user_profile` · `generate_interview_report` (5-dim 1-10 scoring + history delta) · `build_question_bank` · `list_interview_history` · `render_report_card` (HTML radar + trend) · `create_error_card` · `drill_weaknesses` (variant questions + 60s drills) · `update_error_card` (spaced repetition 1→3→7→14d) |

---

## 3. Quick Start

```powershell
pip install qwenpaw
qwenpaw init --defaults

qwenpaw models add-provider moonshot -n Moonshot -u https://api.moonshot.cn/v1
qwenpaw models add-model moonshot -m moonshot-v1-8k -n "Moonshot v1 8k"
qwenpaw models config-key moonshot   # enter Moonshot key (hidden input)

qwenpaw plugin install ./intelliview-plugin

qwenpaw          # TUI chat
# or
qwenpaw app      # web console at http://127.0.0.1:8088
```

---

## 4. Technical Evolution

### Stage 1 · v1: LangGraph Singleton Agent (11 nodes)

FastAPI backend + Vue3 frontend; `AgentSingleton` compiled the LangGraph graph (11 nodes), `SessionManager` assigned a per-`session_id` SqliteSaver. Frontend/backend communicated over the **AG-UI protocol** via WebSocket.

### Stage 2 · v2: Multi-Agent (Planner / Workers / Reporter)

A second additive graph in `src/agents/`. Reused v1 nodes as **Tool wrappers**, orchestrated via a three-stage **Plan-and-Execute + Send API + Subgraph + ReAct** pipeline, with 14 tools dispatched in parallel.

| Building block | Role |
|---|---|
| Plan-and-Execute | Planner splits into 1–5 tasks once |
| Send API | fan out N Worker subgraphs in parallel |
| Subgraph | worker logic as 1 node from the main graph's view |
| ReAct (conditional edges) | observe → act → observe loop |
| Pydantic State | type-safe state + business methods |
| AG-UI protocol | standardized frontend/backend events |

Production wiring: `setup_v2()` startup hook registers 14 tools; `GET /api/v2/health` + `POST /api/v2/chat` endpoints; 74/74 tests passing.

### Stage 3 · v3: QwenPaw Plugin Fork (current)

Deleted the entire LangGraph/FastAPI stack and rebuilt as a QwenPaw plugin (see [§2](#2-current-architecture-qwenpaw-plugin-fork)). Motivation: the self-built LangGraph orchestration produced heavy glue code and dependency pain (e.g. torch `shm.dll` crashes on Windows); QwenPaw already ships the loop/memory/channels/sandbox. Result: the repo shrank from 300+ files to a single plugin directory, with the core conversation capability migrated losslessly and the model still Moonshot.

---

## 5. Agent Collaboration Record

| Agent | Joined | Wrote / owned | Models touched |
|-------|--------|---------------|----------------|
| **Arthur** (human owner) | — | product direction, keys, requirements | Moonshot, Tavily |
| **Claude Code** | early | v1 core: 11-node graph, intent routing, RAG, voice/OCR/YOLO, AG-UI, UI | Moonshot, Funasr/Whisper, YOLOv8n, PaddleOCR, FAISS |
| **MiniMax-M3** | early | model (evaluation/generation) | itself |
| **Nova** (OpenClaw) | 2026.04 | SqliteSaver persistence, intent routing, UI upgrade, Docker, v2 chat wiring, README sync | Moonshot |
| **Vega** (Hermes Agent) | 2026.06 | Multi-Agent v2 (Planner/Worker/Reporter, Send API, 14 tools), RAG wrappers, openspec, architecture survey | Moonshot |
| **This session's agent** | 2026.11 | QwenPaw plugin fork; removed 300+ legacy files; migrated core dialog to plugin | Moonshot |

---

## 6. Milestones

- **2026.04** Nova joins
- **2026.06** Vega joins
- **2026.06** Multi-Agent v2 shipped (issue #4): Planner / Workers×N / Reporter, Send API, 14 reused tools (commit `c1a249e`)
- **2026.06** v2 production wiring: `setup_v2()`, `/api/v2/chat` + `/api/v2/health`, 74/74 tests
- **2026.11** QwenPaw plugin fork: LangGraph stack removed, core dialog migrated
- **2026.11** plugin v0.2 data foundation: interview archive + profile hook + JD question banks + HTML report cards (6 tools, 8/8 local self-checks passing)
- **2026.11** plugin v0.3 drill loop: failed questions auto-become spaced-repetition error cards, due cards nag via hook, drills use variant questions + 60-second timed answers (9 tools, 11/11 local self-checks passing)

---

## 7. Tech Stack

| Category | Historical (v1/v2) | Current (v3 fork) |
|----------|--------------------|-------------------|
| Agent framework | LangGraph, LangChain | **QwenPaw plugin** (AgentScope 2.0) |
| Primary LLM | Moonshot (moonshot-v1-8k) | **Moonshot (moonshot-v1-8k)** |
| Eval/generation model | MiniMax-M3 | — |
| Speech | Funasr / Whisper | — (deferred) |
| Behavior | YOLOv8n | — (deferred) |
| OCR | PaddleOCR | — (deferred) |
| Retrieval | FAISS + Sentence Transformers | — (deferred) |
| Search | Tavily | — (deferred) |
| Frontend | Vue3 + Apple design | QwenPaw TUI / web console |
| Protocol | AG-UI | QwenPaw built-in channels |

---

*Arthur · Nova · Vega · MiniMax-M3*
