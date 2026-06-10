# Implementation Tasks

> 路径：先跑通 1 Worker demo（TDD），再扩 5 Worker，再做回归 + Tool 等价测试。

## 1. state.py 加字段（5 min）

- **文件**：`src/core/state.py`
- **加**：`tasks` / `task_results` / `worker_errors` / `final_report` / `fallback_used`
- **测试**：TypeScript-style 字段访问不报错（intellisense）

## 2. tools.py 包装原 6 node（30 min）

- **文件**：`src/nodes/tools.py`（新）
- **改**：`optimize_transcript` / `intent_recognition` / `agent_router` / `rag_processing` / `web_search` / `generate_response` → langchain Tool
- **TDD 红**：写 `test_tools_equivalence.py` —— call 原 node vs call 新 Tool，输出 diff
- **TDD 绿**：实现 Tool 包装
- **commit**：`feat(tools): wrap 6 nodes as langchain Tools`

## 3. worker.py 写 worker 模板（30 min）

- **文件**：`src/nodes/worker.py`（新）
- **做**：`execute_with_retry` 装饰器 + `run_worker` 函数 + 重试 / 转移 / Fallback 三态
- **TDD 红**：写 `test_worker.py` —— 给 3 个 mock task（成功 / 重试成功 / 重试失败转 Fallback）
- **TDD 绿**：实现
- **commit**：`feat(worker): worker template with retry/transfer/fallback`

## 4. multi_agent.py 加 3 node + 新主图（45 min）

- **文件**：`src/multi_agent.py`
- **加**：
  - `planner_node`（调 init_llm，JSON 拆 1~5 sub-task）
  - `worker_subgraph_node`（用 Send API 触发 1~5 worker）
  - `reporter_node`（调 init_llm，聚合 task_results）
  - 新主图 `create_multi_agent_v2()`：planner → worker_subgraph → reporter
- **旧主图保留**（不删）
- **TDD 红**：`test_multi_agent_1w.py` —— 跑 1 Worker demo，验证链路
- **TDD 绿**：实现
- **commit**：`feat(multi-agent): add planner + worker_subgraph + reporter + 1W demo`

## 5. 扩 5 Worker（20 min）

- **改**：`worker_subgraph_node` 支持 1~5 worker
- **TDD 红**：`test_multi_agent_5w.py` —— 跑 5 Worker demo，验证并行
- **TDD 绿**：扩
- **commit**：`feat(multi-agent): extend to 5 workers via Send API`

## 6. agent_driver.py 加 run_multi_agent 入口（15 min）

- **文件**：`src/agent_driver.py`
- **加**：`run_multi_agent(query, config)` 入口
- **保留**：`run_agent()`（旧主图）
- **commit**：`feat(driver): add run_multi_agent entry (coexist with run_agent)`

## 7. 回归测试 + Tool 等价（30 min）

- **新文件**：`tests/test_regression.py`
- **做**：
  - 跑 3 个原 query（mock interview / 行为分析 / RAG 查询）
  - 对比 `run_agent()` vs `run_multi_agent()` 输出
  - 验证输出**等价**（同 input → 同 response）
- **commit**：`test(regression): verify run_agent vs run_multi_agent equivalence`

## 8. README 更新（10 min）

- **文件**：`README.md` + `README_zh.md`
- **加**：
  - 架构图（planner → workers → reporter）
  - 功能描述（多 Agent 协作）
  - 5 Worker 机制说明
- **commit**：`docs(readme): add multi-agent architecture section`

## 9. 推 master（5 min）

- **等 21:00 窗**（你已破例一次，再等 30min 也行）
- **push**：1 个大 commit 或拆 N 个小 commit（按你偏好）
- **群里发 4 句模板** + @Nova 验
- **改任务表 #4 = 完成**

---

**总工时估算**：~3.5h（1 个工作日）

**Co-authored-by 必加**：`Co-authored-by: Vega <vega@hermes.nousresearch.com>`（Vega 身份标识）

**红线**：
- ❌ 不写 `Closes #4`（让 Nova / Arthur 显式关）
- ❌ 不替换 `run_agent()`（共存）
- ✅ TDD 红 → 绿
- ✅ 频繁 commit
- ✅ 回归测试硬指标
