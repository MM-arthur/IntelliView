# -*- coding: utf-8 -*-
"""IntelliView 面试助手 —— QwenPaw 插件（二开）。

将原 LangGraph 面试助手（意图路由 + 模拟面试 + 复盘 + 职业规划）
改造成 QwenPaw 插件：
  - 打包面试技能（SKILL.md，负责意图路由与四种模式的对话流程）
  - 注入 agent 人设（system prompt）
  - 提供结构化评估报告工具（确定性渲染，替代原 generation 节点）
"""

from qwenpaw.plugins import PluginContext
from qwenpaw.plugins.prompts import PromptSpec
from qwenpaw.plugins.skills import SkillSpec
from qwenpaw.plugins.tools import ToolContext, ToolResult, ToolSpec

PERSONA = (
    "你是 Arthur 的个人 AI 面试助手（IntelliView）。"
    "负责模拟面试、面试复盘、职业规划与面试问答。"
    "优先调用 intelliview 技能判断用户意图并进入对应模式，"
    "始终以专业、温和、技术深入的风格回应。"
)

DIMENSIONS = ("技术深度", "表达能力", "项目经验", "临场反应")


def _render_report(scores: dict, advice: str) -> str:
    lines = ["## 🎯 模拟面试评估报告", ""]
    for dim in DIMENSIONS:
        s = int(scores.get(dim, 3))
        s = max(1, min(5, s))
        lines.append(f"- **{dim}**：{'⭐' * s}{'☆' * (5 - s)}（{s}/5）")
    lines.append("")
    lines.append("### 整体建议")
    lines.append(advice.strip() or "（暂无）")
    return "\n".join(lines)


class Plugin:
    def register(self, context: PluginContext) -> None:
        context.register_skills(
            SkillSpec(directory="skills"),
        )
        context.register_prompt(
            PromptSpec(name="intelliview_persona", text=PERSONA, priority=90),
        )
        context.register_tool(
            ToolSpec(
                name="generate_interview_report",
                description=(
                    "把模拟面试的维度评分与整体建议渲染成标准 Markdown 评估报告，"
                    "并持久化最近一次报告。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scores": {
                            "type": "object",
                            "description": "四个维度的 1-5 分",
                            "properties": {
                                "技术深度": {"type": "integer", "minimum": 1, "maximum": 5},
                                "表达能力": {"type": "integer", "minimum": 1, "maximum": 5},
                                "项目经验": {"type": "integer", "minimum": 1, "maximum": 5},
                                "临场反应": {"type": "integer", "minimum": 1, "maximum": 5},
                            },
                        },
                        "advice": {"type": "string", "description": "整体建议"},
                    },
                    "required": ["scores", "advice"],
                    "additionalProperties": False,
                },
                handler=self.generate_interview_report,
                enabled=True,
                tool_type="internal",
                icon="🎯",
            ),
        )

    async def generate_interview_report(
        self,
        context: ToolContext,
        arguments: dict,
    ) -> ToolResult:
        scores = arguments.get("scores", {})
        advice = arguments.get("advice", "")
        report = _render_report(scores, advice)
        await context.storage.awrite_json(
            "last_interview_report.json",
            {"scores": scores, "advice": advice},
        )
        context.logger.info("Interview report generated")
        return ToolResult.text(report)


plugin = Plugin()
