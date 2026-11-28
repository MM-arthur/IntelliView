# -*- coding: utf-8 -*-
"""IntelliView 核心引擎包：运行时无关的面试训练闭环。

核心逻辑在 intelliview_core.py（零 SDK 依赖），由 QwenPaw 插件 /
MCP server / CLI 三个适配器共享。
"""

from .intelliview_core import (
    DIMENSIONS,
    PERSONA,
    TOOL_DEFINITIONS,
    EngineResult,
    IntelliView,
    LocalContext,
    LocalMedia,
    LocalStorage,
)

__version__ = "0.6.0"

__all__ = [
    "DIMENSIONS",
    "PERSONA",
    "TOOL_DEFINITIONS",
    "EngineResult",
    "IntelliView",
    "LocalContext",
    "LocalMedia",
    "LocalStorage",
    "__version__",
]