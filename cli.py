# -*- coding: utf-8 -*-
"""IntelliView CLI — 在终端里直接使用 AI 面试教练（无需任何 Agent 宿主）。

用法：
    intelliview                    # 自由聊天（默认命令）
    intelliview interview          # 一场模拟面试
    intelliview drill              # 今天的错题特训
    intelliview profile            # 查看用户画像（免 LLM）
    intelliview history            # 面试历史与趋势（免 LLM）
    intelliview report <id>        # 渲染 HTML 报告卡（免 LLM）
    intelliview cards              # 查看错题本（免 LLM）

配置（环境变量或参数）：
    INTELLIVIEW_API_KEY / OPENAI_API_KEY   LLM API Key
    INTELLIVIEW_BASE_URL                   OpenAI-compatible 端点
                                           （默认 https://api.openai.com/v1）
    INTELLIVIEW_MODEL                      模型（默认 gpt-4o-mini）
    INTELLIVIEW_HOME                       数据目录（默认 ~/.intelliview）

数据 100% 本地 JSON 落盘，不上传任何服务器。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

try:  # pip 安装后的形态：intelliview 包
    from intelliview.intelliview_core import (
        CARDS_FILE,
        PERSONA,
        TOOL_DEFINITIONS,
        IntelliView,
        LocalContext,
    )
except ImportError:  # 仓库源码形态：直接指向插件目录
    sys.path.insert(0, str(_HERE / "intelliview-plugin"))
    from intelliview_core import (  # noqa: E402
        CARDS_FILE,
        PERSONA,
        TOOL_DEFINITIONS,
        IntelliView,
        LocalContext,
    )

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": definition["name"],
            "description": definition["description"],
            "parameters": definition["input_schema"],
        },
    }
    for definition in TOOL_DEFINITIONS
]

TOOL_BY_NAME = {definition["name"]: definition for definition in TOOL_DEFINITIONS}

QUIT_WORDS = {"quit", "exit", "q", "/quit", "/exit", "退出"}


# ---------------------------------------------------------------------------
# LLM 聊天循环
# ---------------------------------------------------------------------------


async def _call_engine(engine: IntelliView, context, name: str, arguments: str) -> str:
    """执行一个工具调用，返回回填给 LLM 的文本。"""
    definition = TOOL_BY_NAME.get(name)
    if definition is None:
        return f"未知工具：{name}"
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return f"工具参数不是合法 JSON：{arguments}"
    try:
        result = await getattr(engine, definition["method"])(context, args)
    except Exception as exc:  # noqa: BLE001
        return f"工具执行失败：{exc}"
    return result.text


async def chat_loop(
    client,
    model: str,
    context,
    engine: IntelliView = None,
    opening_message: str = "",
    input_fn=input,
    print_fn=print,
) -> list[dict]:
    """通用对话循环：OpenAI-compatible function calling + IntelliView 引擎。

    client / input_fn / print_fn 均可注入，便于离线测试。
    返回完整 messages（便于断言工具调用是否落盘）。
    """
    if engine is None:
        engine = IntelliView()

    injections = await engine.inject_profile(context)
    system = PERSONA
    if injections:
        system += "\n\n" + "\n".join(injections)
    messages: list[dict] = [{"role": "system", "content": system}]

    pending_user = opening_message
    # follow_up = True 表示上一轮模型发起了工具调用，带着结果直接再请求，
    # 不等待用户输入
    follow_up = False
    print_fn("IntelliView CLI — 输入消息开始（quit 退出）")
    while True:
        if pending_user is not None:
            messages.append({"role": "user", "content": pending_user})
            pending_user = None
        elif not follow_up:
            try:
                line = input_fn("你: ")
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip().lower() in QUIT_WORDS:
                break
            if not line.strip():
                continue
            messages.append({"role": "user", "content": line})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                },
            )
            for call in tool_calls:
                answer = await _call_engine(
                    engine, context,
                    call.function.name, call.function.arguments,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": answer,
                    },
                )
                print_fn(f"[tool] {call.function.name}: {answer.splitlines()[0][:120]}")
            follow_up = True  # 带着工具结果继续请求，不等待用户输入
            continue

        text = message.content or ""
        print_fn(f"IntelliView: {text}")
        messages.append({"role": "assistant", "content": text})
        follow_up = False
    return messages


def _make_client(args: argparse.Namespace):
    api_key = args.api_key or os.environ.get("INTELLIVIEW_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )
    if not api_key:
        print(
            "缺少 API Key：请设置 INTELLIVIEW_API_KEY / OPENAI_API_KEY，"
            "或用 --api-key 传入。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "LLM 命令需要 openai SDK：pip install 'intelliview[cli]'",
            file=sys.stderr,
        )
        raise SystemExit(2)
    base_url = args.base_url or os.environ.get("INTELLIVIEW_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


# ---------------------------------------------------------------------------
# 免 LLM 命令：直接调引擎
# ---------------------------------------------------------------------------


async def run_profile(context) -> int:
    result = await IntelliView().load_user_profile(context, {})
    print(result.text)
    return 1 if result.is_error else 0


async def run_history(context, limit: int, position: str) -> int:
    result = await IntelliView().list_interview_history(
        context, {"limit": limit, "position": position},
    )
    print(result.text)
    return 1 if result.is_error else 0


async def run_report(context, session_id: str) -> int:
    result = await IntelliView().render_report_card(
        context, {"session_id": session_id},
    )
    print(result.text)
    return 1 if result.is_error else 0


async def run_cards(context) -> int:
    cards = await context.storage.aread_json(CARDS_FILE, [])
    if not cards:
        print("错题本是空的。模拟面试中评分 ≤6 的题会自动入卡。")
        return 0
    stats = {"active": 0, "mastered": 0}
    print(f"错题本 · 共 {len(cards)} 张\n")
    for card in cards:
        status = card.get("status", "active")
        stats[status] = stats.get(status, 0) + 1
        mark = "✅" if status == "mastered" else "🃏"
        print(
            f"{mark} [{card.get('id', '')}] {card.get('question', '')}\n"
            f"    分类: {card.get('category', '-')} | "
            f"到期: {card.get('due_date', '-')} | "
            f"连对: {card.get('pass_streak', 0)}/3\n"
            f"    丢分点: {card.get('flaw', '-')}\n"
            f"    参考: {card.get('model_answer', '-')[:100]}\n"
        )
    print(
        f"在练 {stats.get('active', 0)} 张 · 已掌握 "
        f"{stats.get('mastered', 0)} 张 · 用 `intelliview drill` 开始特训"
    )
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # 公共选项用 SUPPRESS：允许出现在命令前或命令后，且子解析器
    # 不会用默认值覆盖主解析器已解析的值
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir", default=argparse.SUPPRESS,
        help="数据目录（默认 ~/.intelliview，可用 INTELLIVIEW_HOME）",
    )
    common.add_argument(
        "--api-key", default=argparse.SUPPRESS,
        help="LLM API Key（默认取 INTELLIVIEW_API_KEY / OPENAI_API_KEY）",
    )
    common.add_argument(
        "--base-url", default=argparse.SUPPRESS,
        help="OpenAI-compatible 端点（默认 INTELLIVIEW_BASE_URL 或 "
             "https://api.openai.com/v1）",
    )
    common.add_argument(
        "--model", default=argparse.SUPPRESS,
        help="模型名（默认 INTELLIVIEW_MODEL 或 gpt-4o-mini）",
    )

    parser = argparse.ArgumentParser(
        prog="intelliview",
        description="AI 面试教练 CLI：错题闭环 + 面试档案 + 可视化报告卡（数据全本地）",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser(
        "chat", parents=[common], help="自由聊天（默认命令，可带开场消息）",
    )
    chat.add_argument("message", nargs="*", help="开场消息（可选）")
    sub.add_parser("interview", parents=[common], help="一场模拟面试")
    sub.add_parser("drill", parents=[common], help="今天的错题特训")
    sub.add_parser("profile", parents=[common], help="查看用户画像")
    history = sub.add_parser("history", parents=[common], help="面试历史与趋势")
    history.add_argument("--limit", type=int, default=10)
    history.add_argument("--position", default="")
    report = sub.add_parser("report", parents=[common], help="渲染 HTML 报告卡")
    report.add_argument("session_id", nargs="?", default="")
    sub.add_parser("cards", parents=[common], help="查看错题本")
    return parser


def _option(args, name: str, fallback: str = "") -> str:
    return getattr(args, name, None) or fallback


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"chat", "interview", "drill", "profile",
                "history", "report", "cards"}
    if not any(token in commands for token in argv):
        # `intelliview` / `intelliview --model x` / `intelliview "练一下 Redis"`
        # 都默认进入 chat；自由文本作为开场消息
        argv = ["chat"] + argv
    args = build_parser().parse_args(argv)

    data_dir = _option(
        args, "data_dir",
        os.environ.get("INTELLIVIEW_HOME", str(Path.home() / ".intelliview")),
    )
    context = LocalContext(data_dir)

    if args.command == "profile":
        return asyncio.run(run_profile(context))
    if args.command == "history":
        return asyncio.run(run_history(context, args.limit, args.position))
    if args.command == "report":
        return asyncio.run(run_report(context, args.session_id))
    if args.command == "cards":
        return asyncio.run(run_cards(context))

    model = _option(args, "model", os.environ.get("INTELLIVIEW_MODEL", DEFAULT_MODEL))
    args.api_key = _option(args, "api_key")
    args.base_url = _option(args, "base_url")
    args.model = model
    client = _make_client(args)

    openings = {
        "interview": "来一场模拟面试。",
        "drill": "开始今天的错题重测特训。",
    }
    opening = openings.get(args.command, "")
    if args.command == "chat" and getattr(args, "message", None):
        opening = " ".join(args.message)
    asyncio.run(
        chat_loop(client, model, context, opening_message=opening)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
