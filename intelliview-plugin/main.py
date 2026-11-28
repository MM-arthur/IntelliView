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
    PERSONA,
    TOOL_DEFINITIONS,
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

    _TOOL_SHIMS = {
        "save_interview_session": "_handle_save",
        "load_user_profile": "_handle_load_profile",
        "generate_interview_report": "_handle_generate_report",
        "build_question_bank": "_handle_build_bank",
        "list_interview_history": "_handle_history",
        "render_report_card": "_handle_render_card",
        "create_error_card": "_handle_create_card",
        "drill_weaknesses": "_handle_drill",
        "update_error_card": "_handle_update_card",
    }

    _TOOL_ICONS = {
        "build_question_bank": "📚",
        "create_error_card": "🃏",
        "drill_weaknesses": "⚡",
        "generate_interview_report": "🎯",
        "list_interview_history": "🗜",
        "load_user_profile": "🧑‍💼",
        "render_report_card": "📊",
        "save_interview_session": "💾",
        "update_error_card": "✅",
    }

    def _tool_specs(self) -> list:
        return [
            ToolSpec(
                name=definition["name"],
                description=definition["description"],
                input_schema=definition["input_schema"],
                handler=getattr(self, self._TOOL_SHIMS[definition["name"]]),
                enabled=True,
                tool_type="internal",
                icon=self._TOOL_ICONS[definition["name"]],
            )
            for definition in TOOL_DEFINITIONS
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
