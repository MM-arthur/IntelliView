# Multi-Agent v2 集成到生产 — Proposal

## Why

`feat-multi-agent` change（commit `c1a249e`，6/10 已 archive）完成了 v2 框架的所有 6 步实现：
- Planner / Worker / Reporter / Graph 4 个模块独立单元测试通过
- 14 个 Tool wrapper（原 node 改 Tool）
- openspec 提案 + 60/60 测试 pass
- README 更新（v1 vs v2 双架构）

**但 v2 在 prod 不可用**（E2E 实测确认）：
- Worker 拿到 task 后报 `"tool 'web_search' not registered and no fallback available"`
- 最终 `final_report: 0/1 tasks succeeded, 1 failed`
- 没有任何 route 触发 `run_multi_agent()`
- `register_tool` 只定义没调用，`TOOL_REGISTRY` 14 个 Tool 零注入 `worker._TOOL_DISPATCH`

**根因**：v2 框架是孤立模块，缺少 3 个 prod 桥接层。

## What Changes

- **`src/agents/integration.py`（新）**：
  - `register_all_tools()`：把 `TOOL_REGISTRY` 14 个 Tool 全注入 `worker._TOOL_DISPATCH`
  - `setup_v2()`：注册 + 预热 v2 singleton（一次性）
  - `is_v2_ready()`：检查 setup 是否完成（debug 端点用）
- **`src/main.py`**：`@app.on_event("startup")` 调 `setup_v2()`，与 v1 启动并行
- **`src/routes/rest.py`**：加 `POST /api/v2/chat` 端点（接 v2 graph；不动 v1 任何端点）
- **`tests/test_integration.py`（新）**：
  - 注册完整性（14 个 Tool 全部注入）
  - 幂等性（重复 setup 不爆）
  - 端点连通性（FastAPI TestClient 跑 /api/v2/chat）
  - v1 不受影响（旧 /api/* 还能用）
- **`README.md` + `README_zh.md`**：在 Multi-Agent v2 章节加"启用 / 端点 / 验证"小节
- **`src/multi_agent_v2.py`**：暴露 `is_v2_ready()` 给 routes 用

## Out of Scope

- 改造 v1 任何代码（共存不替换）
- 双平台同步 / CI / Docker
- 把 v2 设为默认入口（默认仍走 v1 `/ws/chat`）
- 前端 UI 改动（前端 v2 集成是下一 change）
- 性能调优（Send 并发数、Worker 数量现在是 5，暂不改）

## Acceptance

- **必须满足**：
  1. `tests/test_integration.py` 全过（4 个测试）
  2. 现有 60/60 测试**仍然全过**（不回归）
  3. E2E：设 `MOONSHOT_API_KEY` 后，POST `/api/v2/chat` 跑通"你好"得到含 `final_report` 的 200 响应
  4. v1 路径不受影响：原 `/ws/chat` + `/api/process_audio` + `/api/analyze_behavior` + 全部 `/api/*` 行为不变
- **不做也算完成**（不在本次范围）：
  - 前端 v2 接入
  - v2 设为默认入口
  - 性能 / 成本优化

## Risk

- **循环导入**：`integration.py` import `TOOL_REGISTRY` (tools.py) → tools.py import 14 个原 node → 触发 langgraph init。
  - 缓解：lazy import + try/except + log warning（参考 planner.py 的 init_llm 处理方式）
- **重复注册**：多次 startup（FastAPI 测试 reload）会重复注册。
  - 缓解：`register_all_tools` 用幂等检查（基于 Tool name，已存在则 skip）
- **v1 行为改变**：integration.py 不能 import 任何 v1 内部状态。
  - 缓解：仅 import `src.multi_agent_v2` 和 `src.agents.tools`，不碰 `src.multi_agent` 或 `src.core.session_manager`

## 路径

按 TDD：
1. 写 openspec 提案 + spec + tasks（本 PR）
2. 写 `tests/test_integration.py`（红）
3. 写 `src/agents/integration.py`（绿）
4. 改 `src/main.py` + `src/routes/rest.py`（绿）
5. 跑 `pytest tests/` → 60/60 + 4/4 = 64/64
6. E2E 实测（设 MOONSHOT_API_KEY）
7. 更新 README
8. commit + 等时间窗口推

## 关联

- 前置：`feat-multi-agent`（6/10 archive，c1a249e）
- 关联 GitHub：暂不开新 issue，复用 issue #4（仍开，但有 follow-up 任务）
- 关联表格：飞书任务跟踪表 `Hqakb1dkaakyYKsIZRJcu2cAnSc` 待追加 1 行
