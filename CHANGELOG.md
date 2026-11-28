# Changelog

本项目的所有重要变更都记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.5.0] - 2026-11-28

### Added

- **独立 CLI（`intelliview` 命令）**：不依赖任何 Agent 宿主，终端里直接用。
  - `intelliview` / `intelliview chat "练一下 Redis"` — 自由对话（function calling 驱动全部 9 个引擎工具）
  - `intelliview interview` — 一键模拟面试；`intelliview drill` — 今日错题特训
  - `intelliview profile / history / report <id> / cards` — 免 LLM 直读本地档案
  - 任意 OpenAI-compatible 端点：`INTELLIVIEW_BASE_URL` / `INTELLIVIEW_MODEL` / `INTELLIVIEW_API_KEY`（或 `OPENAI_API_KEY`）
- **PyPI 安装形态**：`pyproject.toml`（`pip install intelliview` 就绪）+ `intelliview-plugin/__init__.py` 包化。
- CLI 离线测试套件（fake OpenAI client，验证工具调用落盘闭环）。

### Changed

- **工具 schema 下沉到引擎**：`TOOL_DEFINITIONS` 成为 9 个工具的唯一定义源（name / description / input_schema / method），QwenPaw 适配器只保留注册循环，新增运行时无需改两处。
- **本地运行时上下文下沉**：`LocalStorage / LocalMedia / LocalContext` 移入引擎，MCP server 删除自带副本，改为与 CLI 共享。
- 版本统一至 0.5.0（plugin.json / pyproject / 包 `__version__`）。

## [0.4.0] - 2026-11-28

### Added

- **核心引擎抽离**：`intelliview_core.py` 零 SDK 依赖（QwenPaw / MCP / CLI 共享），含 9 个工具 handler 与 `EngineResult` 结构。
- **MCP 适配器**（`mcp_server.py`）：Claude Desktop / Cursor / Codex / Windsurf 等任何 MCP 客户端可用。
- MIT License。

### Changed

- 去个人化：persona / SKILL / 工具描述去掉个人信息，仓库公开可用。
- git 历史清洗：个人邮箱/手机号替换为 GitHub noreply 邮箱。

## [0.3.0] - 2026-11-25

### Added

- **错题闭环**：
  - 面试中评分 ≤6 的题自动生成错题卡（丢分点 + 参考答案要点）
  - 间隔重复 1→3→7→14→30→60 天；连续答对 3 次标记掌握，答错重置为次日
  - `drill_weaknesses` 变式出题重测（换场景/换数字/反着问）+ 60 秒限时
  - `update_error_card` 记录重测结果
- **到期催练**：PRE_DISPATCH 钩子每次对话自动提醒今日到期错题。

## [0.2.0] - 2026-11-25

### Added

- **数据基座**（让对话产生数据）：
  - `save_interview_session`：每次面试落盘 `sessions/`（JSON+MD）
  - `load_user_profile`：跨会话用户画像（维度均分 / 高频弱点 / 进步曲线）
  - PRE_DISPATCH 钩子自动注入画像上下文
- `generate_interview_report`：五维 1-10 评分 + 历史对比
- `build_question_bank`：粘贴 JD → 持久化针对性题库并激活
- `list_interview_history`：历次面试 + 进步趋势
- `render_report_card`：自包含 HTML 报告卡（雷达图 / 能力卡片 / 弱点清单 / 趋势线）。

## [0.1.0] - 2026-11-25

### Added

- QwenPaw 插件初版：skills / persona / 工具注册框架。

## 插件化之前（存档）

| 阶段 | 形态 | 结局 |
|---|---|---|
| v1（~2026.03） | LangGraph 单体（11 节点）+ FastAPI + Vue + RAG + 语音/OCR | 功能全但自建全栈维护成本过高 |
| v2（2026.06） | 多 Agent v2（Planner / Workers / Reporter，Send API + 14 并行工具） | 编排换扩展性失败，复杂度反升 |
| v3（2026-11） | **QwenPaw 插件 fork**：300+ 文件 → 3 个文件 | 砍掉自建运行时，只留领域逻辑 —— 项目重生为 IntelliView |

方法论沉淀：**agent 时代的产品形态 = 核心引擎（纯逻辑）+ 薄适配器（QwenPaw / MCP / CLI）+ 生成式产物（HTML 报告卡）**。UI 是聊天窗口，富输出交给生成式工件。