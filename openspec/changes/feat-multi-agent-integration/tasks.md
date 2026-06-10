# Implementation Tasks: feat-multi-agent-integration

> TDD 顺序：先写测试（红）→ 再写实现（绿）→ 再重构。所有测试 64/64 pass 后才算完成。

## 1. openspec 提案（本任务）

- [x] 1.1 创建 change 目录 `openspec/changes/feat-multi-agent-integration/`
- [x] 1.2 写 `proposal.md`（Why / What / Out of Scope / Acceptance / Risk）
- [x] 1.3 写 `specs/multi-agent-integration/spec.md`（5 个 Requirement + 11 个 Scenario）
- [x] 1.4 写 `tasks.md`（本文件）

## 2. TDD Red：写失败测试

- [x] 2.1 `tests/test_integration.py` — `test_register_all_tools_registers_14_tools`
- [x] 2.2 `tests/test_integration.py` — `test_register_all_tools_idempotent`
- [x] 2.3 `tests/test_integration.py` — `test_setup_v2_initializes_singleton`
- [x] 2.4 `tests/test_integration.py` — `test_setup_v2_idempotent`
- [x] 2.5 `tests/test_integration.py` — `test_is_v2_ready_false_before_setup` / `test_is_v2_ready_true_after_setup`
- [x] 2.6 `tests/test_integration.py` — `test_v2_chat_endpoint_returns_200`
- [x] 2.7 `tests/test_integration.py` — `test_v2_chat_endpoint_422_on_missing_query`
- [x] 2.8 `tests/test_integration.py` — `test_v2_health_endpoint_returns_status`
- [x] 2.9 `tests/test_integration.py` — `test_v1_endpoints_unaffected`
- [x] 2.10 跑 `pytest tests/test_integration.py -v` → 14/14 **失败**（红）✅

## 3. TDD Green：写最小实现

- [x] 3.1 `src/agents/integration.py` — `register_all_tools()`
- [x] 3.2 `src/agents/integration.py` — `setup_v2()`
- [x] 3.3 `src/agents/integration.py` — `is_v2_ready()` + 模块级状态
- [x] 3.4 `src/main.py` — startup 加 `setup_v2()` 调
- [x] 3.5 `src/routes/rest.py` — 加 `POST /api/v2/chat` + `GET /api/v2/health`
- [x] 3.6 跑 `pytest tests/test_integration.py -v` → 14/14 **通过**（绿）✅

## 4. 全量验证

- [x] 4.1 跑 `pytest tests/ -q` → **74/74 pass**（60 旧 + 14 新）✅
- [x] 4.2 E2E：TestClient(app) 跑通，POST /api/v2/chat 200，final_report 非空 ✅
- [x] 4.3 v1 不回归：/api/health 200，/api/models 200 ✅

## 5. 文档

- [x] 5.1 `README.md` — "Multi-Agent v2" 章节加"启用 / 端点 / 验证"小节
- [ ] 5.2 `README_zh.md` — 同步中文版（deferred，en 已含完整说明）

## 6. Git 流程

- [x] 6.1 `git add` 准备就绪（6 项文件）
- [ ] 6.2 `git commit`（**本地 commit，不 push**——等时间窗口 + Arthur 同意）
- [ ] 6.3 ⚠️ **不 push**（工作日 07:18 早，未到 21:00）
- [ ] 6.4 飞书群汇报进度 + 表格追加新行

## 验收红线

- 74/74 测试 pass ✓
- E2E 跑通（final_report 非空）✓
- v1 不回归 ✓
- Co-Authored-By: Nova-OpenClaw <nova@openclaw.ai> ✓

