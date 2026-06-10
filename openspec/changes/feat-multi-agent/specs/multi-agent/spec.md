## ADDED Requirements

### Requirement: Planner decomposes query into sub-tasks
The system SHALL Planner_node 调用 init_llm() 把用户 query 拆成 1~5 个 sub-task JSON 列表。

#### Scenario: Simple query yields 1 task
- **WHEN** query = "你好"
- **THEN** tasks = `[{id: "t1", description: "问候回复", tool_hint: "generate_response"}]`
- **AND** tasks.length = 1

#### Scenario: Complex query yields 5 tasks
- **WHEN** query = "介绍下你做的 LangChain 项目和 FAISS 索引机制"
- **THEN** tasks.length = 5
- **AND** tool_hint 覆盖 rag_processing / generate_response

### Requirement: Workers execute sub-tasks in parallel via Send API
The system SHALL Worker_subgraph 节点用 LangGraph Send API 并行触发 1~5 个 worker。

#### Scenario: 5 workers run concurrently
- **WHEN** tasks = 5 个
- **THEN** 5 worker 同时启动（验证 trace 时间戳重叠）
- **AND** task_results.length = 5

### Requirement: Failed worker retries 3 times then transfers then falls back
The system SHALL Worker 失败 → 重试 3 次（指数退避）→ 任务转移给下一个 worker → Fallback 默认回复。

#### Scenario: Retry succeeds
- **WHEN** worker 第 2 次调用成功
- **THEN** task_result.status = "ok"
- **AND** worker_errors 不含这次成功调用

#### Scenario: All retries fail → fallback
- **WHEN** worker 3 次都失败
- **THEN** task_result.status = "fallback"
- **AND** task_result.output = default_fallback(task)
- **AND** worker_errors.length = 4（3 retry + 1 fallback）
- **AND** fallback_used = True

### Requirement: Reporter aggregates worker results
The system SHALL Reporter_node 调 init_llm() 把 task_results 聚合成 final_report（自然语言 + 来源标注）。

#### Scenario: 5 results aggregated
- **WHEN** task_results.length = 5
- **THEN** final_report 是自然语言总结
- **AND** 包含所有 5 个 task 的核心信息
- **AND** 末尾标注数据来源

### Requirement: run_agent() and run_multi_agent() produce equivalent output for legacy queries
The system SHALL 旧主图（15 节点 run_agent）vs 新主图（3 节点 run_multi_agent）跑同样 query 输出等价。

#### Scenario: Mock interview query
- **WHEN** query = "开始模拟面试"
- **THEN** run_agent().response == run_multi_agent().response
- **AND** 仅允许时间戳等元数据差异

#### Scenario: RAG query
- **WHEN** query = "LangChain 是什么？"
- **THEN** run_agent().response == run_multi_agent().response
- **AND** rag_sources 字段一致

### Requirement: Original node functions and new Tool wrappers produce equivalent output
The system SHALL 原 6 个 node 函数（`optimize_transcript` / `intent_recognition` / `agent_router` / `rag_processing` / `web_search` / `generate_response`）vs 新 langchain Tool 包装跑同 input 输出等价。

#### Scenario: rag_processing node vs Tool
- **WHEN** state.optimized_text = "FAISS 是什么？"
- **THEN** node(state)["rag_result"] == tool.invoke(state)["rag_result"]
- **AND** rag_sources 字段值一致
