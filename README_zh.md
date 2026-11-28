# IntelliView — AI 面试教练：答错的题，它会记仇

> 开源的面试训练闭环：**模拟面试 → 错题卡 → 间隔重复重测 → 可视化报告卡**。
> 数据 100% 本地 JSON 落盘、零部署、不上传任何服务器，跑在你自己的 Agent 里。

[English](./README.md) · [MIT License](./LICENSE)

## ✨ 与"又一个 AI 模拟面试"有何不同

| | 普通 AI 面试 wrapper | IntelliView |
|---|---|---|
| 记忆 | 聊完即散 | 答错/低分题自动进**错题卡**，1→3→7→14 天间隔重复 |
| 重测 | 原题重问 | **换场景 / 换数字 / 反着问**，防背答案 |
| 压力模拟 | 无 | **60 秒限时**一次成稿 |
| 数据 | 无 | 面试档案 + 用户画像 + 高频弱点 + 进步曲线 |
| 报告 | 一段文字 | 自包含 **HTML 报告卡**：雷达图 + 能力卡片 + 趋势线 |
| 定制 | 泛泛而问 | 粘贴 JD → 针对性题库，自动激活出题 |
| 运行时 | 单一 | **QwenPaw 插件 / MCP**（Claude Desktop、Cursor、Codex…） |

## 🚀 快速开始

### 方式 A：MCP（推荐，任何 MCP 客户端）

```powershell
pip install mcp
git clone https://github.com/MM-arthur/IntelliView.git
```

在 Claude Desktop / Cursor / Codex 的 MCP 配置中加入：

```json
{
  "mcpServers": {
    "intelliview": {
      "command": "python",
      "args": ["<你的仓库路径>/mcp_server.py", "--data-dir", "C:/intelliview-data"]
    }
  }
}
```

然后直接对 Agent 说：**"来一场模拟面试"**、**"错题重测"**、**"按这个 JD 面我"**。
面试数据默认存 `~/.intelliview`（可用 `--data-dir` 改）。

### 方式 B：QwenPaw 插件

```powershell
pip install qwenpaw
qwenpaw init --defaults
qwenpaw plugin install ./intelliview-plugin
qwenpaw          # TUI，或 qwenpaw app 走 Web 控制台
```

## 🧠 训练闭环

```
模拟面试（五维 1-10 评分：技术深度/表达/逻辑/项目/岗位匹配）
   └─ 评分 ≤6 的题 ──→ 🃏 错题卡（丢分点 + 参考答案要点）
                          └─ 次日到期，每次对话自动催练
                                └─ ⚡ 3 分钟特训：换角度出题 + 60 秒限时
                                      ├─ 通过 → 间隔升级 3/7/14 天（连续 3 次 = 掌握）
                                      └─ 失败 → 明日重测
面试结束 ──→ 💾 档案（sessions/ JSON+MD）+ 🧑‍💼 画像 + 📊 HTML 报告卡
```

## 📦 架构：一个引擎，多个运行时

```
intelliview-plugin/
├── intelliview_core.py            # 核心引擎：档案/画像/错题/题库/报告（零 SDK 依赖）
├── main.py                        # QwenPaw 适配器（注册技能/钩子/9 工具）
└── skills/intelliview/SKILL.md    # 8 种面试模式与评分锚点
mcp_server.py                      # MCP 适配器（Claude / Cursor / Codex…）
```

核心引擎不知道宿主是谁：QwenPaw 与 MCP 各自注入满足鸭子类型的
`context`（storage / logger / media），所有状态落盘本地 JSON。

## 🗺 路线图（高星计划）

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 引擎抽离 + MCP 适配器 + 去个人化 | ✅ v0.4 |
| Phase 1b | 独立 CLI（`pip install intelliview`） | ⏳ |
| Phase 2 | README 首屏 GIF demo + 演示数据 | ⏳ |
| Phase 3 | 开源题库（岗位包 + 社区 PR 流） | ⏳ |
| Phase 4 | 发布运营（Show HN / V2EX / awesome lists） | ⏳ |

## 📈 升级之路

本项目是一部"架构演化史"——每一次形态变化都是为了砍掉维护成本：

| 阶段 | 形态 | 动机 |
|---|---|---|
| v1 | LangGraph 单体（11 节点）+ FastAPI + Vue | 自建全栈，功能全但 glue 代码重 |
| v2 | 多 Agent（Planner / Workers / Reporter，Send API + Subgraph） | 想用编排换扩展性，结果更复杂 |
| v3 | **QwenPaw 插件 fork**（300+ 文件 → 3 个文件） | 砍掉自建运行时，只写领域逻辑 |
| v0.2 | 数据基座：面试档案 + 画像 + 钩子注入 + HTML 报告卡 | 让对话产生数据 |
| v0.3 | 错题闭环：低分题自动入卡 + 间隔重复 + 到期催练 | 让数据驱动行为改变 |
| v0.4 | **引擎抽离 + MCP 适配器 + 开源化** | 让任何 Agent 用户 5 分钟跑通 |

**方法论**：agent 时代的产品形态 = 核心引擎（纯逻辑）+ 薄适配器（QwenPaw /
MCP / CLI）+ 产物（HTML 报告卡）。UI 是聊天窗口，富内容由生成式工件承担。

## 🤝 贡献

- **题库贡献**（Phase 3 开放）：`questions/` 岗位包目录 + PR 模板
- good first issues 即将标注
- 引擎与适配器边界清晰，欢迎新的运行时适配器（CLI / Telegram / 微信）

## 协作记录

| Agent | 加入 | 贡献 |
|---|---|---|
| **Arthur**（仓库所有者） | — | 产品方向、密钥、需求把控 |
| **Claude Code** | 早期 | v1 核心：11 节点图、RAG、语音/OCR、UI |
| **Nova**（OpenClaw） | 2026.04 | SqliteSaver 持久化、意图路由、Docker |
| **Vega**（Hermes Agent） | 2026.06 | 多 Agent v2、Send API、14 工具并行 |
| **GLM** | 2026.11 | v3 插件化 → v0.4 引擎抽离 + MCP |

## 里程碑

- 2026.06 Multi-Agent v2 上线（Planner / Workers / Send API）
- 2026.11 QwenPaw 插件二开：删 LangGraph 栈，300+ 文件 → 3 文件
- 2026.11 v0.2 数据基座：档案 + 画像 + 钩子 + HTML 报告卡
- 2026.11 v0.3 错题闭环：错题卡 + 间隔重复 + 到期催练
- 2026.11 v0.4 开源化：引擎抽离 + MCP 适配器 + 去个人化 + MIT