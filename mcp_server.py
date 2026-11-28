# -*- coding: utf-8 -*-
"""IntelliView MCP server —— 在任何 MCP 客户端（Claude Desktop / Cursor /
Codex / Windsurf…）里启用 AI 面试教练：错题闭环 + 面试档案 + 可视化报告卡。

运行时无依赖：数据全部落盘本地 JSON（默认 ~/.intelliview），不上传任何服务器。

运行（stdio）：
    python mcp_server.py [--data-dir <目录>]

Claude Desktop / Cursor 配置示例见 README。
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "intelliview-plugin"))

from intelliview_core import IntelliView  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

engine = IntelliView()
mcp = FastMCP("intelliview")

_CTX = None


class DirStorage:
    """与 QwenPaw PluginStorage 同接口的本地文件存储。"""

    def __init__(self, root: Path):
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        path = (self._root / name).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage path out of scope: {name}")
        return path

    async def aread_json(self, name, default=None):
        path = self._path(name)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    async def awrite_json(self, name, value):
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8",
        )

    async def awrite_bytes(self, name, data):
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def aread_bytes(self, name):
        return self._path(name).read_bytes()


class DirMedia:
    """本地媒体写入：HTML 报告卡落盘并返回 file:// URI。"""

    def __init__(self, storage: DirStorage):
        self._storage = storage

    async def awrite(self, name, data, *, mime_type="application/octet-stream"):
        await self._storage.awrite_bytes(name, data)
        path = self._storage._path(name)
        return SimpleNamespace(
            url=path.as_uri(),
            mime_type=mime_type,
            name=Path(name).name,
            preview_url=path.as_uri(),
        )


class EngineContext:
    def __init__(self, data_dir: Path):
        self.storage = DirStorage(data_dir)
        self.media = DirMedia(self.storage)
        self.logger = logging.getLogger("intelliview")


def _ctx() -> EngineContext:
    return _CTX


@mcp.tool()
async def save_interview_session(
    position: str,
    questions: list[dict],
    scores: dict[str, int],
    advice: str,
    company: str = "",
    interview_type: str = "mock",
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    notes: str = "",
) -> str:
    """面试结束后存档：岗位、逐题记录（question/category/answer_summary/
    rating 1-10/flaw/model_answer/follow_ups）、五维评分、亮点与弱点。
    评分 ≤6 的题自动生成错题卡（明日首次复习）。返回存档确认与历史对比。"""
    return (
        await engine.save_interview_session(
            _ctx(),
            {
                "position": position,
                "questions": questions,
                "scores": scores,
                "advice": advice,
                "company": company,
                "interview_type": interview_type,
                "strengths": strengths or [],
                "weaknesses": weaknesses or [],
                "notes": notes,
            },
        )
    ).text


@mcp.tool()
async def load_user_profile() -> str:
    """读取用户面试画像：历史维度均分、高频弱点、目标岗位、进步趋势，
    以及错题本统计（在练/已掌握/今日到期）。面试开始前调用实现个性化。"""
    return (await engine.load_user_profile(_ctx(), {})).text


@mcp.tool()
async def generate_interview_report(
    position: str,
    scores: dict[str, int],
    advice: str,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> str:
    """生成维度化评估报告：五维 1-10 打分，自动与历史均分对比（↑↓）。"""
    return (
        await engine.generate_interview_report(
            _ctx(),
            {
                "position": position,
                "scores": scores,
                "advice": advice,
                "strengths": strengths or [],
                "weaknesses": weaknesses or [],
            },
        )
    ).text


@mcp.tool()
async def build_question_bank(
    position: str,
    questions: list[dict],
    key_points: list[str] | None = None,
    jd_text: str = "",
) -> str:
    """JD 定制面试用：把按 JD 解析出的考点（key_points）与针对性题目
    （question/category/difficulty easy|medium|hard/follow_up，建议 8-12 题）
    存为持久题库并设为激活，后续模拟面试优先按此出题。"""
    return (
        await engine.build_question_bank(
            _ctx(),
            {
                "position": position,
                "questions": questions,
                "key_points": key_points or [],
                "jd_text": jd_text,
            },
        )
    ).text


@mcp.tool()
async def list_interview_history(
    limit: int = 10,
    position: str = "",
) -> str:
    """列出历次面试档案：日期、岗位、五维评分、均分变化与进步曲线，
    可按岗位过滤。复盘时必调用。"""
    return (
        await engine.list_interview_history(
            _ctx(), {"limit": limit, "position": position},
        )
    ).text


@mcp.tool()
async def render_report_card(
    session_id: str = "",
    position: str = "",
    scores: dict[str, int] | None = None,
    advice: str = "",
    questions: list[dict] | None = None,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    company: str = "",
    interview_type: str = "mock",
) -> str:
    """生成自包含 HTML 可视化报告卡（雷达图 + 能力卡片 + 弱点清单 +
    历史趋势线）。传入已存档的 session_id 重渲染，或提供完整面试数据
    （position + scores + advice）。返回本地文件路径。"""
    return (
        await engine.render_report_card(
            _ctx(),
            {
                "session_id": session_id,
                "position": position,
                "scores": scores or {},
                "advice": advice,
                "questions": questions or [],
                "strengths": strengths or [],
                "weaknesses": weaknesses or [],
                "company": company,
                "interview_type": interview_type,
            },
        )
    ).text


@mcp.tool()
async def create_error_card(
    question: str,
    category: str = "",
    flaw: str = "",
    my_answer: str = "",
    model_answer: str = "",
) -> str:
    """把一道题加入错题本：面试中答错/答差的题、用户自报的薄弱点都可入卡。
    入卡后按 1→3→7→14 天间隔重复，到期自动提醒重测。"""
    return (
        await engine.create_error_card(
            _ctx(),
            {
                "question": question,
                "category": category,
                "flaw": flaw,
                "my_answer": my_answer,
                "model_answer": model_answer,
            },
        )
    ).text


@mcp.tool()
async def drill_weaknesses(count: int = 5, category: str = "") -> str:
    """错题特训：取出当前到期的错题卡供重测，返回出题规则（换角度出题、
    60 秒限时）与每张卡的丢分点/参考要点。出题时不要展示参考要点，
    用户作答后再对照。"""
    return (
        await engine.drill_weaknesses(
            _ctx(), {"count": count, "category": category},
        )
    ).text


@mcp.tool()
async def update_error_card(
    card_id: str,
    passed: bool,
    rating: int = 0,
    note: str = "",
) -> str:
    """重测后更新错题卡结果：passed=true 时升级复习间隔
    （1→3→7→14 天，连续答对 3 次标记掌握）；passed=false 时重置为明日再测。
    必须在每次重测判定后立即调用。"""
    arguments = {"card_id": card_id, "passed": passed}
    if rating:
        arguments["rating"] = rating
    if note:
        arguments["note"] = note
    return (await engine.update_error_card(_ctx(), arguments)).text


def main() -> None:
    global _CTX  # noqa: PLW0603
    parser = argparse.ArgumentParser(description="IntelliView MCP server")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get(
            "INTELLIVIEW_HOME", str(Path.home() / ".intelliview"),
        ),
        help="数据目录（默认 ~/.intelliview）",
    )
    args = parser.parse_args()
    _CTX = EngineContext(Path(args.data_dir))
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()