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
    intelliview demo               # 演示数据 + 报告卡（免 LLM）
    intelliview bank list|show|use # 开源题库（岗位包）

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

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=OPENAI_TOOLS,
            )
        except Exception as exc:  # noqa: BLE001 —— 网络/鉴权/超时等给出可读提示
            print_fn(f"⚠️ 请求失败：{exc}")
            print_fn(
                "检查 INTELLIVIEW_BASE_URL / INTELLIVIEW_API_KEY / 网络"
                "（quit 退出）"
            )
            break
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
    api_key = (
        getattr(args, "api_key", "")
        or os.environ.get("INTELLIVIEW_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
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
    base_url = getattr(args, "base_url", "") or os.environ.get(
        "INTELLIVIEW_BASE_URL", DEFAULT_BASE_URL
    )
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
# 题库（岗位包）
# ---------------------------------------------------------------------------

_DIFFICULTIES = {"easy", "medium", "hard"}


def _pack_locations(data_dir: str) -> list:
    """题包搜索路径：包内（pip 安装）→ 仓库 questions/ → 用户自定义目录。"""
    locations = []
    try:
        import importlib.resources as _res

        base = _res.files("intelliview_questions")
        locations.append((Path(str(base)), "bundled"))
    except Exception:  # noqa: BLE001
        pass
    repo = _HERE / "questions"
    if repo.is_dir():
        locations.append((repo, "repo"))
    custom = Path(data_dir) / "question_packs"
    if custom.is_dir():
        locations.append((custom, "custom"))
    return locations


def _discover_packs(data_dir: str) -> list[dict]:
    packs, seen = [], set()
    for base, source in _pack_locations(data_dir):
        for path in sorted(base.glob("*.json")):
            if path.name == "question-pack.schema.json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or "questions" not in data:
                continue
            pack = dict(data)
            pack["_path"] = str(path)
            pack["_source"] = source
            pack_id = str(pack.get("id") or path.stem)
            if pack_id in seen:
                continue
            seen.add(pack_id)
            packs.append(pack)
    return packs


def validate_pack(data: dict, path: str = "<memory>") -> list[str]:
    """校验一个题包，返回错误列表（空 = 合法）。与 question-pack.schema.json 对齐。"""
    errors = []
    import re as _re

    pack_id = data.get("id")
    if not isinstance(pack_id, str) or not _re.fullmatch(
        r"[a-z0-9][a-z0-9-]{1,40}", pack_id or ""
    ):
        errors.append(f"{path}: id 必须是小写字母/数字/连字符（2-41 位）")
    if not isinstance(data.get("position"), str) or len(data.get("position", "")) < 2:
        errors.append(f"{path}: position 必须是不少于 2 字的岗位名")
    for field in ("description",):
        if field in data and not isinstance(data[field], str):
            errors.append(f"{path}: {field} 必须是字符串")
    if "version" in data and not isinstance(data["version"], int):
        errors.append(f"{path}: version 必须是整数")
    for field in ("key_points",):
        if field in data and not (
            isinstance(data[field], list)
            and all(isinstance(x, str) for x in data[field])
        ):
            errors.append(f"{path}: {field} 必须是字符串数组")
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) < 3:
        errors.append(f"{path}: questions 至少 3 题（建议 8-12 题）")
        return errors
    for idx, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            errors.append(f"{path}: 第 {idx} 题必须是对象")
            continue
        extra = set(question) - {"question", "category", "difficulty", "follow_up"}
        if extra:
            errors.append(f"{path}: 第 {idx} 题有多余字段 {sorted(extra)}")
        text = question.get("question")
        if not isinstance(text, str) or len(text.strip()) < 8:
            errors.append(f"{path}: 第 {idx} 题题干过短（至少 8 字）")
        if "category" in question and not isinstance(question["category"], str):
            errors.append(f"{path}: 第 {idx} 题 category 必须是字符串")
        if "difficulty" in question and question["difficulty"] not in _DIFFICULTIES:
            errors.append(f"{path}: 第 {idx} 题 difficulty 必须是 easy/medium/hard")
        if "follow_up" in question and not isinstance(question["follow_up"], str):
            errors.append(f"{path}: 第 {idx} 题 follow_up 必须是字符串")
    return errors


async def run_bank(context, action: str, pack_id: str, path: str) -> int:
    if action == "validate":
        targets = []
        if path:
            target = Path(path)
            targets = sorted(target.glob("*.json")) if target.is_dir() else [target]
            if not targets:
                print(f"找不到待校验文件：{path}")
                return 2
        else:
            for base, _source in _pack_locations(str(context.storage._root)):
                targets.extend(sorted(base.glob("*.json")))
            targets = [t for t in targets if t.name != "question-pack.schema.json"]
        errors = []
        for target in targets:
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{target}: 无法解析（{exc}）")
                continue
            errors.extend(validate_pack(data, str(target)))
        if errors:
            print("题包校验失败：")
            for error in errors:
                print(f"  ✗ {error}")
            return 1
        print(f"PASS：{len(targets)} 个题包全部合法")
        return 0

    packs = _discover_packs(str(context.storage._root))

    if action == "list":
        if not packs:
            print(
                "没有可用题包。bundled 包见仓库 questions/ 目录；"
                "自定义包放到 ~/.intelliview/question_packs/"
            )
            return 0
        print(f"可用题包（{len(packs)} 个）\n")
        for pack in packs:
            count = len(pack.get("questions", []))
            print(
                f"  {pack.get('id', '?'):<24} {pack.get('position', '')}"
                f"（{count} 题 · {pack['_source']}）"
            )
        print("\n用法：intelliview bank show <id> / intelliview bank use <id>")
        return 0

    if action in {"show", "use"}:
        if not pack_id:
            print("请指定题包 id，先 `intelliview bank list` 查看。")
            return 2
        pack = next((p for p in packs if str(p.get("id")) == pack_id), None)
        if pack is None:
            print(f"未找到题包 {pack_id}，用 `intelliview bank list` 查看可用列表。")
            return 1

    if action == "show":
        print(f"# {pack['id']} · {pack.get('position', '')}\n")
        if pack.get("description"):
            print(f"{pack['description']}\n")
        for point in pack.get("key_points", []):
            print(f"• 考点：{point}")
        print()
        for idx, question in enumerate(pack.get("questions", []), 1):
            mark = {"easy": "基", "medium": "进", "hard": "挑"}.get(
                question.get("difficulty", ""), "·"
            )
            print(f"{idx:>2}. [{mark}] {question['question']}")
            if question.get("category"):
                print(f"      分类：{question['category']}")
            if question.get("follow_up"):
                print(f"      追问：{question['follow_up']}")
        return 0

    # use：导入并激活
    result = await IntelliView().build_question_bank(
        context,
        {
            "position": pack.get("position", ""),
            "jd_text": pack.get("description", ""),
            "key_points": pack.get("key_points", []),
            "questions": pack.get("questions", []),
        },
    )
    print(result.text)
    return 1 if result.is_error else 0


# ---------------------------------------------------------------------------
# 演示数据（免 LLM）
# ---------------------------------------------------------------------------

_DEMO_POSITION = "Python 后端开发工程师"
_DEMO_DIMENSIONS = ("技术深度", "表达能力", "逻辑结构", "项目经验", "岗位匹配")


async def run_demo(context, with_bank: bool) -> int:
    """写入一套演示面试档案 + 错题卡 + 激活题库，并渲染报告卡。免 LLM。"""
    engine = IntelliView()
    index = await context.storage.aread_json("sessions/index.json", [])
    if index:
        print(
            "当前数据目录已有面试档案。演示数据建议用空目录：\n"
            "  intelliview demo --data-dir <新目录>"
        )
        return 0

    if with_bank:
        packs = _discover_packs(str(context.storage._root))
        pack = next(
            (p for p in packs if str(p.get("id")) == "backend-python"), None,
        )
        if pack:
            await engine.build_question_bank(
                context,
                {
                    "position": pack.get("position", ""),
                    "jd_text": pack.get("description", ""),
                    "key_points": pack.get("key_points", []),
                    "questions": pack.get("questions", []),
                },
            )

    sessions = [
        {
            "position": _DEMO_POSITION,
            "interview_type": "mock",
            "questions": [
                {
                    "question": "讲讲 Redis 的持久化机制",
                    "category": "Redis",
                    "answer_summary": "说出 RDB 与 AOF，混淆了混合持久化",
                    "flaw": "混淆混合持久化的触发时机",
                    "model_answer": "RDB 快照 + AOF 日志 + 混合持久化，各自取舍",
                    "rating": 5,
                },
                {
                    "question": "MySQL 什么情况下索引会失效？",
                    "category": "MySQL",
                    "answer_summary": "说出最左前缀与隐式转换，漏了函数包裹",
                    "flaw": "漏了函数包裹列与 OR 连接",
                    "model_answer": "最左前缀 / 隐式转换 / 函数包裹 / OR / 前导通配",
                    "rating": 6,
                },
                {
                    "question": "讲讲 GIL 对多线程的影响",
                    "category": "Python 并发",
                    "answer_summary": "解释清楚，给出 CPU/IO 密集的选择",
                    "rating": 8,
                },
            ],
            "scores": {d: 6 for d in _DEMO_DIMENSIONS},
            "strengths": ["并发模型理解到位"],
            "weaknesses": ["Redis 持久化混淆", "MySQL 索引场景不全"],
            "advice": "优先补 Redis 持久化与 MySQL 索引，然后再约一轮。",
        },
        {
            "position": _DEMO_POSITION,
            "interview_type": "mock",
            "questions": [
                {
                    "question": "Redis 持久化：RDB 期间有写入怎么办？",
                    "category": "Redis",
                    "answer_summary": "答出 fork + copy-on-write，混合持久化已理清",
                    "rating": 7,
                },
                {
                    "question": "设计一个短链接服务",
                    "category": "系统设计",
                    "answer_summary": "给出哈希 + 缓存方案，未讨论热点倾斜",
                    "flaw": "未讨论热点 key 倾斜与统计写入",
                    "model_answer": "编码方案 / 读写分离 / 热点缓存 / 异步统计",
                    "rating": 6,
                },
                {
                    "question": "消费消息怎么保证幂等？",
                    "category": "消息队列",
                    "answer_summary": "给出唯一键 + 状态机方案",
                    "rating": 8,
                },
            ],
            "scores": {d: 7 for d in _DEMO_DIMENSIONS},
            "strengths": ["Redis 明显进步", "幂等方案有工程细节"],
            "weaknesses": ["系统设计缺热点治理"],
            "advice": "进步明显；下一轮压力面重点打系统设计。",
        },
    ]
    report = None
    for payload in sessions:
        await engine.save_interview_session(context, payload)
    latest = (await context.storage.aread_json("sessions/index.json", []))[0]
    report = await engine.render_report_card(context, {"session_id": latest["id"]})

    # 演示「今日到期」：把上一轮的错题卡改为昨天到期
    cards = await context.storage.aread_json("error_cards.json", [])
    if cards:
        from datetime import datetime, timedelta

        cards[0]["due_date"] = (
            datetime.now() + timedelta(days=-1)
        ).strftime("%Y-%m-%d")
        await context.storage.awrite_json("error_cards.json", cards)

    print("演示数据已写入（2 次面试档案 + 错题卡 + 激活题库）\n")
    print(f"报告卡：{_extract_local_path(report.text)}\n")
    profile = await engine.load_user_profile(context, {})
    print("—— 用户画像 ——")
    print(profile.text)
    print("\n—— 接下来试试 ——")
    print("  intelliview drill            # 今日到期错题特训（60 秒限时）")
    print("  intelliview history          # 进步曲线")
    print("  intelliview cards            # 错题本")
    return 0


def _extract_local_path(text: str) -> str:
    for line in text.splitlines():
        if "本地路径" in line:
            return line.split("`")[1] if "`" in line else line
    return text.splitlines()[0] if text else ""


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
    bank = sub.add_parser("bank", parents=[common], help="岗位题库（list/show/use/validate）")
    bank.add_argument(
        "action", choices=["list", "show", "use", "validate"], default="list",
        nargs="?", help="动作",
    )
    bank.add_argument("pack_id", nargs="?", default="", help="题包 id（show/use）")
    bank.add_argument("path", nargs="?", default="", help="validate 的文件/目录")
    demo = sub.add_parser("demo", parents=[common], help="写入演示数据并渲染报告卡（免 LLM）")
    demo.add_argument("--no-bank", action="store_true", help="不激活示例题库")
    return parser


def _option(args, name: str, fallback: str = "") -> str:
    return getattr(args, name, None) or fallback


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"chat", "interview", "drill", "profile",
                "history", "report", "cards", "bank", "demo"}
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
    if args.command == "bank":
        return asyncio.run(run_bank(context, args.action, args.pack_id, args.path))
    if args.command == "demo":
        return asyncio.run(run_demo(context, with_bank=not args.no_bank))

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
