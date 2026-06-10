# Spec: Multi-Agent v2 生产集成

## ADDED Requirements

### Requirement: register_all_tools 把 14 个 Tool 全部注入 worker 派发表
系统 SHALL `register_all_tools()` 把 `src.agents.tools.TOOL_REGISTRY` 14 个 Tool 全部注册到 `src.agents.worker._TOOL_DISPATCH`，注册后 `len(_TOOL_DISPATCH) == 14` 且每个 name 都是 `TOOL_REGISTRY` 的子集。

#### Scenario: 首次注册成功
- **WHEN** 调用 `register_all_tools()`（cold start）
- **THEN** `len(worker._TOOL_DISPATCH) == 14`
- **AND** `_TOOL_DISPATCH.keys() == TOOL_REGISTRY.keys()`（超集检查）

#### Scenario: 重复注册幂等
- **WHEN** 调用 `register_all_tools()` 两次
- **THEN** 第二次不抛异常
- **AND** `_TOOL_DISPATCH` 大小不变（不会重复添加）

#### Scenario: 注册错误不抛
- **WHEN** `TOOL_REGISTRY` 里有 callable 不可调用
- **THEN** 跳过该 Tool，记 `logger.warning`，不中断整体注册
- **AND** 至少 web_search 仍能注册成功（fallback 不挂）

### Requirement: setup_v2 完整启动钩子
系统 SHALL `setup_v2()` 执行：先 `register_all_tools()`，再调 `get_singleton_multi_agent_v2()` 预热编译 langgraph graph。重复调 `setup_v2()` 幂等。

#### Scenario: 冷启动顺序正确
- **WHEN** 调 `setup_v2()`
- **THEN** 先 `len(_TOOL_DISPATCH) >= 1`（至少有 fallback）
- **AND** 再 `get_singleton_multi_agent_v2()` 返回已 compile 的 graph（不是 None）

#### Scenario: 重复 setup 幂等
- **WHEN** 调 `setup_v2()` 两次
- **THEN** `_TOOL_DISPATCH` 大小不变
- **AND** singleton 仍返回同一对象（`is` identity check 通过）

### Requirement: is_v2_ready 检查
系统 SHALL `is_v2_ready()` 返回 bool，反映 `setup_v2()` 是否完成。`/api/v2/health` 端点 SHALL 返回此状态 + 已注册 Tool 数量。

#### Scenario: 启动前
- **WHEN** `setup_v2()` 未调
- **THEN** `is_v2_ready() == False`

#### Scenario: 启动后
- **WHEN** `setup_v2()` 已调
- **THEN** `is_v2_ready() == True`
- **AND** `GET /api/v2/health` 返回 `200 {"ready": true, "tools_registered": 14}`

### Requirement: /api/v2/chat 端点连通
系统 SHALL `POST /api/v2/chat` 接受 `{"query": "...", "session_id": "..."}` 格式，调 `run_multi_agent(query)`，返回 `200 {"query", "tasks", "final_report", "task_results", "worker_errors", "fallback_used"}`。

#### Scenario: 正常查询
- **WHEN** `POST /api/v2/chat` body = `{"query": "你好", "session_id": "s1"}`
- **THEN** 返回 200
- **AND** `final_report` 是非空 string（Markdown）
- **AND** `tasks` 是 list of `{id, description, tool_hint}`

#### Scenario: 缺 query
- **WHEN** `POST /api/v2/chat` body 缺 `query`
- **THEN** 返回 422（Pydantic validation error）

#### Scenario: v2 未 setup 时调用
- **WHEN** `setup_v2()` 未调但 `POST /api/v2/chat`
- **THEN** 返回 503 `{"error": "v2 not initialized, call setup_v2() first"}`

### Requirement: v1 端点行为不变
系统 SHALL 集成过程中**不改**任何 v1 端点（`/ws/chat` / `/api/process_audio` / `/api/analyze_behavior` / `/api/upload` 等）。FastAPI TestClient 跑全部 v1 端点应仍返回与集成前等价响应。

#### Scenario: 全部 v1 路由仍可 import
- **WHEN** `from src.main import app`
- **THEN** `app.routes` 中 `/ws/chat`, `/api/process_audio`, `/api/analyze_behavior` 仍存在
- **AND** `/api/v2/chat`, `/api/v2/health` 已新增

#### Scenario: v1 TestClient 不挂
- **WHEN** `TestClient(app).get("/api/health")`
- **THEN** 返回 200（不因 v2 setup 报错）
