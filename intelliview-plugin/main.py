# -*- coding: utf-8 -*-
"""IntelliView 面试助手 —— QwenPaw 适配器（v0.4）。

核心引擎见 intelliview_core.py（运行时无关）；本文件只做 QwenPaw 接入：
注册 skills / persona / 画像钩子 / 9 个工具，并把引擎结果包成 ToolResult。
"""

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from intelliview_core import (  # noqa: E402
    DIMENSIONS,
    PERSONA,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_PROPS,
    EngineResult,
    IntelliView,
)
from qwenpaw.plugins import PluginContext  # noqa: E402
from qwenpaw.plugins.hooks import (  # noqa: E402
    ContextInjection,
    HookPhase,
    HookResult,
    HookSpec,
)
from qwenpaw.plugins.messages import ContentBlock  # noqa: E402
from qwenpaw.plugins.prompts import PromptSpec  # noqa: E402
from qwenpaw.plugins.skills import SkillSpec  # noqa: E402
from qwenpaw.plugins.tools import ToolResult, ToolSpec  # noqa: E402


def _wrap(result: EngineResult) -> ToolResult:
    blocks = [ContentBlock(text=result.text)]
    if result.attachment is not None:
        blocks.append(ContentBlock(type="file", attachment=result.attachment))
    return ToolResult(
        content=tuple(blocks),
        is_error=result.is_error,
        metadata=dict(result.metadata),
    )


class Plugin:
    def __init__(self) -> None:
        self._engine = IntelliView()




    def register(self, context: PluginContext) -> None:
        context.register_skills(SkillSpec(directory="skills"))
        context.register_prompt(
            PromptSpec(name="intelliview_persona", text=PERSONA, priority=90),
        )
        context.register_hook(
            HookSpec(
                name="intelliview_profile_context",
                phase=HookPhase.PRE_DISPATCH,
                handler=self.inject_profile,
                priority=70,
            ),
        )
        for spec in self._tool_specs():
            context.register_tool(spec)

    # -- 工具声明 -----------------------------------------------------------

    def _tool_specs(self) -> list:
        return [
            ToolSpec(
                name="save_interview_session",
                description=(
                    "面试结束后调用：把岗位、逐题记录与回答摘要、五维评分（1-10）、"
                    "亮点与弱点写入持久面试档案（sessions/ JSON+MD），"
                    "并更新用户画像与进步曲线。返回存档确认与历史对比。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "position": {
                            "type": "string",
                            "description": "目标岗位，如“后端开发工程师”",
                        },
                        "company": {"type": "string", "description": "公司名（可选）"},
                        "interview_type": {
                            "type": "string",
                            "enum": ["mock", "real", "review"],
                            "description": "面试类型：模拟/真实/复盘录入",
                        },
                        "questions": {
                            "type": "array",
                            "description": "逐题记录（至少 1 题）",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "description": "题目"},
                                    "category": {"type": "string", "description": "考点分类"},
                                    "answer_summary": {
                                        "type": "string",
                                        "description": "回答摘要",
                                    },
                                    "flaw": {
                                        "type": "string",
                                        "description": "这道题错在哪 / 丢分点（自动入错题卡）",
                                    },
                                    "model_answer": {
                                        "type": "string",
                                        "description": "参考答案要点（错题卡复习用）",
                                    },
                                    "rating": {
                                        "type": "integer",
                                        "minimum": SCORE_MIN,
                                        "maximum": SCORE_MAX,
                                        "description": "该题评分 1-10",
                                    },
                                    "follow_ups": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "追问列表",
                                    },
                                },
                                "required": ["question"],
                                "additionalProperties": False,
                            },
                        },
                        "scores": {
                            "type": "object",
                            "description": "五个维度 1-10 分",
                            "properties": SCORE_PROPS,
                            "required": list(DIMENSIONS),
                            "additionalProperties": False,
                        },
                        "strengths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "本次亮点",
                        },
                        "weaknesses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "本次弱点（尽量具体，如“Redis 持久化机制混淆”）",
                        },
                        "advice": {"type": "string", "description": "整体改进建议"},
                        "notes": {"type": "string", "description": "其他备注"},
                    },
                    "required": ["position", "questions", "scores", "advice"],
                    "additionalProperties": False,
                },
                handler=self._handle_save,
                enabled=True,
                tool_type="internal",
                icon="💾",
            ),
            ToolSpec(
                name="load_user_profile",
                description=(
                    "读取用户面试画像：历史维度均分、高频弱点、目标岗位、进步趋势。"
                    "模拟面试 / 复盘 / 职业规划开始前调用，实现跨会话个性化。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                handler=self._handle_load_profile,
                enabled=True,
                tool_type="internal",
                icon="🧑‍💼",
            ),
            ToolSpec(
                name="generate_interview_report",
                description=(
                    "生成维度化评估报告（Markdown）：五维 1-10 打分，"
                    "自动与历史均分对比并给出升降幅度。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "position": {"type": "string", "description": "岗位"},
                        "scores": {
                            "type": "object",
                            "description": "五个维度 1-10 分",
                            "properties": SCORE_PROPS,
                            "required": list(DIMENSIONS),
                            "additionalProperties": False,
                        },
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "advice": {"type": "string", "description": "整体建议"},
                    },
                    "required": ["position", "scores", "advice"],
                    "additionalProperties": False,
                },
                handler=self._handle_generate_report,
                enabled=True,
                tool_type="internal",
                icon="🎯",
            ),
            ToolSpec(
                name="build_question_bank",
                description=(
                    "JD 定制面试用：把按 JD 解析出的考点与针对性题目存为持久题库，"
                    "并设为激活题库，后续模拟面试优先按此出题。"
                    "JD 解析与题目生成由你（agent）完成，本工具负责持久化与格式化。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "position": {"type": "string", "description": "岗位名称"},
                        "jd_text": {
                            "type": "string",
                            "description": "原始 JD 文本（可选，用于存档）",
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "从 JD 提取的考点",
                        },
                        "questions": {
                            "type": "array",
                            "description": "针对性题目（建议 8-12 题）",
                            "minItems": 3,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "category": {"type": "string", "description": "考点分类"},
                                    "difficulty": {
                                        "type": "string",
                                        "enum": ["easy", "medium", "hard"],
                                        "description": "难度",
                                    },
                                    "follow_up": {
                                        "type": "string",
                                        "description": "预设深挖追问",
                                    },
                                },
                                "required": ["question"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["position", "questions"],
                    "additionalProperties": False,
                },
                handler=self._handle_build_bank,
                enabled=True,
                tool_type="internal",
                icon="📚",
            ),
            ToolSpec(
                name="list_interview_history",
                description=(
                    "列出历次面试档案：日期、岗位、五维评分、均分变化与进步曲线，"
                    "可按岗位过滤。复盘时必调用。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "最多返回条数，默认 10",
                        },
                        "position": {
                            "type": "string",
                            "description": "按岗位名称过滤（子串匹配，可选）",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._handle_history,
                enabled=True,
                tool_type="internal",
                icon="📜",
            ),
            ToolSpec(
                name="render_report_card",
                description=(
                    "生成自包含 HTML 可视化报告卡（雷达图 + 能力卡片 + 弱点清单 + "
                    "历史趋势线），返回文件附件供浏览器打开。"
                    "传入已存档的 session_id 重渲染，或直接传入完整面试数据。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "已存档面试 ID（与完整数据二选一）",
                        },
                        "position": {"type": "string"},
                        "company": {"type": "string"},
                        "interview_type": {
                            "type": "string",
                            "enum": ["mock", "real", "review"],
                        },
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "category": {"type": "string"},
                                    "answer_summary": {"type": "string"},
                                    "rating": {
                                        "type": "integer",
                                        "minimum": SCORE_MIN,
                                        "maximum": SCORE_MAX,
                                    },
                                    "follow_ups": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["question"],
                                "additionalProperties": False,
                            },
                        },
                        "scores": {
                            "type": "object",
                            "description": "五个维度 1-10 分",
                            "properties": SCORE_PROPS,
                            "required": list(DIMENSIONS),
                            "additionalProperties": False,
                        },
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "advice": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                handler=self._handle_render_card,
                enabled=True,
                tool_type="internal",
                icon="📊",
            ),
            ToolSpec(
                name="create_error_card",
                description=(
                    "把一道题加入错题本（错题卡）：面试中答错/答差的题、"
                    "用户自报的薄弱点都可以入卡。入卡后按 1→3→7→14 天间隔重复，"
                    "到期时会在对话中自动提醒重测。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "题目原文"},
                        "category": {"type": "string", "description": "考点分类"},
                        "flaw": {"type": "string", "description": "错在哪 / 丢分点"},
                        "my_answer": {"type": "string", "description": "用户当时的回答摘要"},
                        "model_answer": {
                            "type": "string",
                            "description": "参考答案要点（复习时对照）",
                        },
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
                handler=self._handle_create_card,
                enabled=True,
                tool_type="internal",
                icon="🃏",
            ),
            ToolSpec(
                name="drill_weaknesses",
                description=(
                    "错题特训：取出当前到期的错题卡供重测。返回出题规则"
                    "（换角度出题、60 秒限时）与每张卡的丢分点/参考要点。"
                    "出题时不要展示参考要点，用户作答后再对照。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "本次最多抽取题数，默认 5",
                        },
                        "category": {
                            "type": "string",
                            "description": "按考点过滤（子串匹配，可选）",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._handle_drill,
                enabled=True,
                tool_type="internal",
                icon="⚡",
            ),
            ToolSpec(
                name="update_error_card",
                description=(
                    "重测后更新错题卡结果：passed=true 时升级复习间隔"
                    "（1→3→7→14 天，连续答对 3 次标记掌握）；"
                    "passed=false 时重置为明日再测。必须在每次重测判定后立即调用。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "错题卡 ID"},
                        "passed": {
                            "type": "boolean",
                            "description": "本次重测是否通过（达到 7 分水平）",
                        },
                        "rating": {
                            "type": "integer",
                            "minimum": SCORE_MIN,
                            "maximum": SCORE_MAX,
                            "description": "本次重测评分 1-10（可选）",
                        },
                        "note": {"type": "string", "description": "点评备注（可选）"},
                    },
                    "required": ["card_id", "passed"],
                    "additionalProperties": False,
                },
                handler=self._handle_update_card,
                enabled=True,
                tool_type="internal",
                icon="✅",
            ),
        ]


    # -- 适配器垫片：引擎结果 → ToolResult -------------------------------------

    async def _handle_save(self, context, arguments):
        return _wrap(await self._engine.save_interview_session(context, arguments))

    async def _handle_load_profile(self, context, arguments):
        return _wrap(await self._engine.load_user_profile(context, arguments))

    async def _handle_generate_report(self, context, arguments):
        return _wrap(await self._engine.generate_interview_report(context, arguments))

    async def _handle_build_bank(self, context, arguments):
        return _wrap(await self._engine.build_question_bank(context, arguments))

    async def _handle_history(self, context, arguments):
        return _wrap(await self._engine.list_interview_history(context, arguments))

    async def _handle_render_card(self, context, arguments):
        return _wrap(await self._engine.render_report_card(context, arguments))

    async def _handle_create_card(self, context, arguments):
        return _wrap(await self._engine.create_error_card(context, arguments))

    async def _handle_drill(self, context, arguments):
        return _wrap(await self._engine.drill_weaknesses(context, arguments))

    async def _handle_update_card(self, context, arguments):
        return _wrap(await self._engine.update_error_card(context, arguments))

    # -- 钩子 ---------------------------------------------------------------

    async def inject_profile(self, context):
        injections = await self._engine.inject_profile(context)
        if not injections:
            return HookResult()
        return HookResult(
            injections=tuple(
                ContextInjection(content=content, priority=70)
                for content in injections
            ),
        )


plugin = Plugin()
