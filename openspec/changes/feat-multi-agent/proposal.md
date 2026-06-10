# Multi-Agent 协作架构改造 — Proposal

## Why

IntelliView 当前是单 Agent 串行流程（`multi_agent.py`：15 节点 StateGraph），处理复杂 query 时：
- 节点全串行，无并行能力
- 单 LLM 串行决策，无法拆任务
- 出错就 fail，缺少子任务级别容错

需要改成 **Planner / Worker × N / Reporter** 三层多 Agent 协作：
- 并行处理 5 个子任务
- 子任务级别重试 / 转移 / Fallback
- 原 15 node 能力保留（不挂业务）

## What Changes

- `src/multi_agent.py`：主图从 15 节点线性改 3 节点（planner → worker_subgraph → reporter）
- `src/multi_agent.py`：worker_subgraph 内部用 Send API 并行 5 个 worker
- `src/core/state.py`：加 5 字段（tasks / task_results / worker_errors / final_report / fallback_used）
- `src/nodes/worker.py`（新）：worker 模板（调 `init_llm()` + 复用原 node 改的 Tool）
- `src/nodes/tools.py`（新）：把原 6 个 LLM/Tool node（`intent_recognition` / `optimize_transcript` / `rag_processing` / `web_search` / `agent_router` / `generate_response`）改成 langchain Tool
- `src/agent_driver.py`：加 `run_multi_agent(query)` 入口（**不替换**旧 `run_agent()`，**共存**）
- `src/multi_agent.py`：旧 15 节点主图保留走 `run_agent()`，**新主图走 `run_multi_agent()`**

## Out of Scope

- 替换 LLM（**保留** `init_llm()` 即 Moonshot）
- 改造 career_intents.py 3 个节点（`mock_interview` / `interview_review` / `career_planning`）—— **保留原入口**
- 双平台同步 / CI / Docker

## Acceptance

- 1 Worker demo 跑通：planner → 1 worker → reporter → 最终回复
- 5 Worker demo 跑通：planner → 5 worker 并行 → reporter
- 回归测试：旧 15 节点主图 `run_agent()` 跑同样 3 query，结果与新主图 `run_multi_agent()` **等价**（同 input → 同 response）
- 原 node 改 Tool 后：call 原 node vs call 新 Tool，**同 input 同 output**
- 失败容忍：Worker 抛异常 → 重试 3 次 → 任务转移 → Fallback（不 crash）
- README 加架构图 + 5 Worker 机制说明

## Risk

- 业务挂：原 node 改 Tool 行为不一致 → 跑回归测试对比
- Token 成本涨 5 倍：5 Worker 并行各调 LLM
- 调试复杂：5 个并行流 + LangSmith trace
