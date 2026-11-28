# IntelliView — AI Interview Coach That Remembers Your Mistakes

> An open-source interview training loop: **mock interview → error cards →
> spaced-repetition re-drills → visual report cards**. 100% local JSON data,
> zero deployment, no server — runs inside your own AI agent.

[中文文档](./README_zh.md) · [MIT License](./LICENSE)

## ✨ Why is this not "yet another AI mock-interview wrapper"?

| | Typical AI interview wrapper | IntelliView |
|---|---|---|
| Memory | Forgets after the chat | Failed questions (≤6/10) auto-become **error cards**, 1→3→7→14-day spaced repetition |
| Re-testing | Asks the same question | **Variants** — new scenario / new numbers / inverted framing (anti-memorization) |
| Pressure | None | **60-second timed** answers, one shot |
| Data | None | Session archive + user profile + recurring weaknesses + progress trend |
| Reports | A text blob | Self-contained **HTML report card**: radar chart + ability cards + trend line |
| Customization | Generic questions | Paste a JD → targeted question bank, auto-activated |
| Runtimes | One | **QwenPaw plugin / MCP** (Claude Desktop, Cursor, Codex…) |

## 🚀 Quick Start

### Option A: MCP (recommended — any MCP client)

```powershell
pip install mcp
git clone https://github.com/MM-arthur/IntelliView.git
```

Add to your Claude Desktop / Cursor / Codex MCP config:

```json
{
  "mcpServers": {
    "intelliview": {
      "command": "python",
      "args": ["<path-to-repo>/mcp_server.py", "--data-dir", "C:/intelliview-data"]
    }
  }
}
```

Then just tell your agent: *"give me a mock interview"*, *"drill my error
cards"*, or *"interview me against this JD"*. Data lives in `~/.intelliview`
by default (override with `--data-dir`).

### Option B: QwenPaw plugin

```powershell
pip install qwenpaw
qwenpaw init --defaults
qwenpaw plugin install ./intelliview-plugin
qwenpaw          # TUI, or `qwenpaw app` for the web console
```

## 🧠 The training loop

```
Mock interview (5-dim 1-10 scoring: depth / expression / logic / project / fit)
   └─ questions rated ≤6 ──→ 🃏 error card (what was wrong + model answer)
                               └─ due next day, auto-nagged every conversation
                                     └─ ⚡ 3-minute drill: variant question + 60s timer
                                           ├─ pass → interval grows 3/7/14d (3 in a row = mastered)
                                           └─ fail → retry tomorrow
Session end ──→ 💾 archive (JSON+MD) + 🧑‍💼 profile + 📊 HTML report card
```

## 📦 Architecture: one engine, many runtimes

```
intelliview-plugin/
├── intelliview_core.py            # core engine: archive/profile/cards/bank/report (zero SDK deps)
├── main.py                        # QwenPaw adapter (skills/hook/9 tools)
└── skills/intelliview/SKILL.md    # 8 interview modes + scoring anchors
mcp_server.py                      # MCP adapter (Claude / Cursor / Codex…)
```

The engine knows nothing about its host: QwenPaw and MCP each inject a
duck-typed `context` (storage / logger / media); all state is local JSON.

## 🗺 Roadmap (the high-star plan)

| Phase | Scope | Status |
|---|---|---|
| 1 | Engine extraction + MCP adapter + de-personalization | ✅ v0.4 |
| 1b | Standalone CLI (`pip install intelliview`) | ⏳ |
| 2 | README hero GIF + demo data | ⏳ |
| 3 | Open question banks (role packs + community PRs) | ⏳ |
| 4 | Launch (Show HN / V2EX / awesome lists) | ⏳ |

## 📈 The journey so far

This repo doubles as an architecture evolution case study — every
transformation was about cutting maintenance cost:

| Stage | Form | Motivation |
|---|---|---|
| v1 | LangGraph monolith (11 nodes) + FastAPI + Vue | Self-built full stack: capable, but glue-heavy |
| v2 | Multi-agent (Planner / Workers / Reporter, Send API + subgraphs) | Orchestration for scale — got more complex instead |
| v3 | **QwenPaw plugin fork** (300+ files → 3) | Drop the self-built runtime, keep only domain logic |
| v0.2 | Data foundation: archive + profile + hook injection + HTML report | Make conversations produce data |
| v0.3 | Drill loop: auto error cards + spaced repetition + due nagging | Make data drive behavior change |
| v0.4 | **Engine extraction + MCP adapter + open-sourcing** | Let any agent user run it in 5 minutes |

**The method**: the agent-era product shape = core engine (pure logic) +
thin adapters (QwenPaw / MCP / CLI) + generated artifacts (HTML report card).
The UI is the chat window; rich output is a generated artifact.

## 🤝 Contributing

- **Question banks** (opening in Phase 3): `questions/` role packs + PR template
- Good first issues will be labeled soon
- The engine/adapter boundary is clean — new runtime adapters welcome (CLI / Telegram / WeChat)

## Credits

| Agent | Joined | Contributions |
|---|---|---|
| **Arthur** (owner) | — | Product direction, keys, requirements |
| **Claude Code** | early | v1 core: 11-node graph, RAG, voice/OCR, UI |
| **Nova** (OpenClaw) | 2026.04 | SqliteSaver persistence, intent routing, Docker |
| **Vega** (Hermes Agent) | 2026.06 | Multi-agent v2, Send API, 14 parallel tools |
| **GLM** | 2026.11 | v3 plugin fork → v0.4 engine extraction + MCP |

## Milestones

- 2026.06 Multi-agent v2 shipped (Planner / Workers / Send API)
- 2026.11 QwenPaw plugin fork: LangGraph stack removed, 300+ files → 3
- 2026.11 v0.2 data foundation: archive + profile + hook + HTML report cards
- 2026.11 v0.3 drill loop: error cards + spaced repetition + due nagging
- 2026.11 v0.4 open-source ready: engine extraction + MCP adapter + MIT