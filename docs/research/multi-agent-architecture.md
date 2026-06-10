# LangGraph 多 Agent 协作模式选型（#2 候选）

> 作者：Vega (Hermes Agent)
> 日期：2026-06-10
> 状态：调研笔记 / 待 Nova + Arthur 拍板
> 关联：https://github.com/MM-arthur/IntelliView/issues/2

## 1. 背景

**Issue 现状**（#2 真实目标）：

- `src/multi_agent.py` 是个空架子（README 提了 Single Agent 架构 + session isolation，**多 Agent 协作没接入**）
- Nova 是 owner，半天工作量

**三种 Agent 形态要分清**：

- **单 Agent 多节点**：一个 LLM 串行/条件走多个工具节点（**当前现状**，不是 #2 目标）
- **多 Agent 协作（独立实例）**：Planner → Worker ×N → Reporter，每个 Agent 有自己的 system prompt、工具、memory
- **Multi-Agent Debate**：多 Agent 互相质疑/投票（**#2 也不是这个**）

#2 目标 = **第二种**（独立实例的多 Agent 协作）。

## 2. 三种实现方案对比

### 方案 A：LangGraph Send API + 动态 fan-out

```
intent_recognition → planner (LLM 拆任务) → [Send(rag), Send(web), Send(career)]
                                              ↓
                                          reporter (聚合)
```

- **优点**：LangGraph 原生支持，可视化好，subgraph 隔离上下文
- **缺点**：Send API 0.2+ 才稳定，老版本要手工 patch
- **调试**：LangSmith trace 清晰
- **代码量**：~120 行（multi_agent.py 内）

### 方案 B：asyncio.gather + 手动编排

```
planner → 拆任务 → asyncio.gather(*[worker(t) for t in tasks]) → reporter
```

- **优点**：纯 Python，易理解，跨框架可移植
- **缺点**：**脱离 LangGraph 状态机**——checkpoint 失效，要自己实现状态恢复
- **调试**：要自己加 log/tracing
- **代码量**：~80 行

### 方案 C：Subgraph 包 Send

```
planner_subgraph {
  planner → [Send(worker_1), Send(worker_2), Send(worker_3)] → reporter
}
main_graph → planner_subgraph
```

- **优点**：上下文隔离（worker 看不到 planner 内部 state），可复用 subgraph
- **缺点**：复杂度最高，要懂 LangGraph 嵌套
- **调试**：trace 嵌套 2 层
- **代码量**：~150 行

## 3. 推荐方案：C（Subgraph 包 Send）

**理由**：

1. **上下文隔离**是真正的多 Agent 灵魂——Worker 不该看到 Planner 的中间 prompt，只看 sub-task 输入
2. LangGraph 0.2+ 稳定支持 Send + Subgraph，**不是实验性 API**
3. 与项目现状契合：现有 `multi_agent.py` 已经是 LangGraph 编排，加 subgraph 边际成本低
4. 失败隔离：一个 Worker 挂掉不影响其他 Worker（subgraph 边界就是异常边界）

**不选 B 的核心原因**：asyncio.gather 脱离 LangGraph 状态机，**直接破坏现有的 SqliteSaver checkpoint**——这是大倒退。

**不选 A 的核心原因**：Send 在主图上跑 = Worker 共享主 state，**违背"独立 Agent"的本意**。

## 4. 工作量估算

| 步骤 | 改动 | 行数 | 时间 |
|---|---|---|---|
| 1. Planner LLM 拆任务 | 新增 `planner_node`（JSON 输出） | ~40 | 2h |
| 2. Worker ×N 模板 | 新增 `worker_node` + tool 注入 | ~30 | 2h |
| 3. Reporter 聚合 | 新增 `reporter_node` | ~30 | 1h |
| 4. Subgraph 嵌套 | StateGraph 嵌套 + Send | ~30 | 2h |
| 5. Driver 集成 | `run_multi_agent(query)` 入口 | ~20 | 1h |
| 6. 调试 + 验收测试 | 写 3+ 子任务的 demo | ~30 | 2h |
| **合计** | — | **~180 行** | **1-1.5 天** |

> 注：issue 写"半天"是低估。LLM 拆任务稳定要调 prompt，**1 天起**。

## 5. 风险点

1. **LLM 拆任务不准**（最致命）——多 Agent 协作的瓶颈在 Planner。如果 Planner 把"面试复盘"拆成"复盘 + 面试"，就复读了
   - 缓解：Few-shot examples + JSON schema 强约束
2. **Token 成本涨 N 倍**——N 个 Worker 各自调 LLM，独立 system prompt
   - 缓解：小模型（DeepSeek-V3 / Qwen2.5）做 Worker
3. **调试复杂度↑**——故障定位从 1 个 LLM 变 N+1 个
   - 缓解：LangSmith trace + 每个 node 加 print
4. **现有单 Agent 流程被替换**——`optimize_transcript` → `intent_recognition` 这条主线要不要保留？
   - 建议：**新加 `run_multi_agent()` 入口**，旧 `run_agent()` 保留，渐进迁移
5. **Subgraph checkpoint 行为**——要测 SqliteSaver 在嵌套图下是否还能正常回滚

## 6. 决策点（待 Nova 拍）

- **Q1**：用 Planner/Worker 哪个 LLM？项目现有 `custom_api_llm/` 是候选
- **Q2**：Worker 数量上限？3 个还是 5 个？
- **Q3**：失败容忍度？一个 Worker 挂是 fail-fast 还是 partial 继续？
- **Q4**：要不要保留旧 `run_agent()` 入口？还是直接替换？

## 7. 建议下一步

**短期**（今天-明天）：Nova review 这份笔记，决定：
- 接受 C 方案 → 我帮写 Planner prompt 的 few-shot examples
- 拒绝 C → 告诉我优先选 A/B 或不开干
- 不开干 → issue 转 draft / 关闭，等主流程稳了再说

**中期**（如果开干）：先跑通 1 个 Worker 的最小 demo（`planner → 1 worker → reporter`），再加 N。

## 8. 参考资料

- LangGraph Send API 文档：https://langchain-ai.github.io/langgraph/concepts/low_level/#send
- LangGraph Subgraph 文档：https://langchain-ai.github.io/langgraph/concepts/low_level/#subgraphs
- 多 Agent 协作最佳实践（Anthropic）：https://www.anthropic.com/research/building-effective-agents
