# Multi-Agent 协作架构 — Design

## 架构

```
用户 query
   ↓
planner_node (LLM 拆 JSON)
   ↓ (sub-task list, e.g. 5 tasks)
   ↓
[ Send API: 并行 5 个 worker_subgraph ]
   ├─ worker_1 (LLM + Tool 调用) → task_result_1
   ├─ worker_2 (LLM + Tool 调用) → task_result_2
   ├─ worker_3 (LLM + Tool 调用) → task_result_3
   ├─ worker_4 (LLM + Tool 调用) → task_result_4
   └─ worker_5 (LLM + Tool 调用) → task_result_5
   ↓
reporter_node (LLM 聚合 5 个结果)
   ↓
final_report
```

## 关键决策

| 决策 | 选 | 理由 |
|---|---|---|
| 编排框架 | LangGraph StateGraph | 项目已在用 LangGraph，边际成本低 |
| 并行机制 | `Send` API | LangGraph 0.2+ 原生支持，可视化好 |
| LLM | `init_llm()` (Moonshot) | 用户 2026-06-10 指示用现有 |
| Tool 来源 | 原 node 改 langchain Tool | 不挂业务，等价转换 |
| 失败容忍 | `with_retry` 装饰器（已有）+ 任务转移 + Fallback | core/retry.py 已有 |
| 入口策略 | `run_multi_agent()` **共存**（不替换） `run_agent()` | 渐进迁移，旧流程保留 |

## 文件改动

| 文件 | 改/新 | 行数估算 |
|---|---|---|
| `src/core/state.py` | 改 | +5 字段 |
| `src/multi_agent.py` | 改 | +150（planner + worker_subgraph + reporter + 新主图） |
| `src/nodes/worker.py` | 新 | +50 |
| `src/nodes/tools.py` | 新 | +80（6 个原 node 改 Tool） |
| `src/agent_driver.py` | 改 | +20（run_multi_agent 入口） |
| `tests/test_multi_agent.py` | 新 | +200（回归 + Tool 等价 + 1W/5W demo） |
| `README.md` + `README_zh.md` | 改 | +30（架构图 + 5 Worker 机制） |
| **合计** | — | **~535 行** |

## 子任务重试/转移/Fallback 设计

```python
def execute_with_retry(task, llm, tools, max_retries=3):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return run_worker(task, llm, tools)
        except RetryableError as e:
            last_error = e
            time.sleep(2 ** attempt)
    # 重试 3 次失败 → 任务转移给下一个 Worker
    return transfer_to_next_worker(task, last_error)

def run_worker(task, llm, tools):
    try:
        # 调 LLM + Tool
        return {"task_id": task["id"], "status": "ok", "output": result}
    except FallbackNeeded as e:
        # 简单任务失败 → Fallback 到默认回复
        return {"task_id": task["id"], "status": "fallback", "output": default_fallback(task)}
```

## 验证路径

1. **写测试**（TDD 红）：`tests/test_multi_agent.py` 跑 1W demo，验证 planner → 1 worker → reporter 链路
2. **跑测试**（TDD 红→绿）：实现最小代码让测试过
3. **扩 5W**：测试 + 实现 worker_subgraph
4. **回归**：原 15 节点主图跑同样 query，对比新旧结果
5. **Tool 等价**：原 node 函数 vs 新 Tool 函数，同 input 验证输出 diff = ∅
