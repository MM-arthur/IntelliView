# -*- coding: utf-8 -*-
"""IntelliView 核心引擎（v0.4）—— 运行时无关的数据基座 + 错题训练闭环。

本模块不依赖任何宿主 SDK：QwenPaw / MCP / CLI 适配器各自注入满足鸭子
类型的 context（storage / logger / media），全部面试数据落盘为本地 JSON。

核心思路：让对话产生数据，让数据产生资产，让资产驱动个性化。

  - 面试档案：save_interview_session 把每次面试落盘为 sessions/{id}.json + .md
  - 用户画像：profile.json / profile.md 持久化维度均分、高频弱点与进步曲线，
    并通过 PRE_DISPATCH 钩子在每轮对话自动注入
  - 维度评分：generate_interview_report 输出五维 1-10 分报告，自动对比历史
  - JD 题库：build_question_bank 持久化按 JD 生成的针对性题库并设为激活
  - 历史命令：list_interview_history 列出历次面试与趋势
  - 可视化：render_report_card 生成自包含 HTML 报告卡（雷达图 / 能力卡片 /
    弱点清单 / 历史趋势线），经 MediaStore 以文件附件返回
  - 错题闭环：低分题（≤6）自动生成错题卡（1→3→7→14 天间隔重复），
    drill_weaknesses 出变式题限时重测，update_error_card 记录结果；
    到期错题经 PRE_DISPATCH 钩子在每次对话自动催练
"""

import html as _html
import json
import math
import secrets
import string as _string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

PERSONA = (
    "你是用户的个人 AI 面试助手（IntelliView）。"
    "负责模拟面试（通用 / JD 定制 / 压力深挖）、面试复盘、职业规划与面试问答。"
    "面试相关对话开始时结合用户画像个性化提问（画像已自动注入上下文，也可调用 "
    "load_user_profile 查看详情）；每次面试结束时必须调用 save_interview_session "
    "存档，并按需调用 render_report_card 生成可视化报告。"
    "同时维护错题本：答错的题自动生成错题卡，到期时主动提醒用户"
    "进行 3 分钟错题特训（换角度出题、60 秒限时作答）。"
    "始终以专业、温和、技术深入的风格回应。"
)

DIMENSIONS = ("技术深度", "表达能力", "逻辑结构", "项目经验", "岗位匹配")
SCORE_MIN, SCORE_MAX = 1, 10

SESSIONS_DIR = "sessions"
BANKS_DIR = "question_banks"
REPORTS_DIR = "reports"
INDEX_FILE = "sessions/index.json"
BANK_INDEX_FILE = "question_banks/index.json"
PROFILE_JSON = "profile.json"
PROFILE_MD = "profile.md"
CARDS_FILE = "error_cards.json"

TYPE_LABELS = {"mock": "模拟面试", "real": "真实面试", "review": "复盘录入"}
DIFF_LABELS = {"easy": "基础", "medium": "进阶", "hard": "挑战"}
_SPARK = "▁▂▃▄▅▆▇█"

# 错题卡间隔重复：答对一次升级一档，连续答对 3 次视为掌握
INTERVAL_LADDER = (1, 3, 7, 14, 30, 60)
MASTER_STREAK = 3
AUTO_CARD_MAX_RATING = 6  # 评分 ≤ 6 的题自动进错题本

SCORE_PROPS = {
    dim: {"type": "integer", "minimum": SCORE_MIN, "maximum": SCORE_MAX}
    for dim in DIMENSIONS
}


@dataclass
class EngineResult:
    """运行时无关的工具结果：文本 + 元数据 + 可选附件。"""

    text: str = ""
    is_error: bool = False
    metadata: dict = field(default_factory=dict)
    attachment: Any = None



# ---------------------------------------------------------------------------
# 小工具函数
# ---------------------------------------------------------------------------


def _escape(text: Any) -> str:
    return _html.escape(str(text if text is not None else ""))


def _norm_scores(scores: dict) -> dict:
    result = {}
    for dim in DIMENSIONS:
        try:
            value = float(scores.get(dim, 5))
        except (TypeError, ValueError):
            value = 5.0
        result[dim] = int(round(max(SCORE_MIN, min(SCORE_MAX, value))))
    return result


def _avg(scores: dict) -> float:
    values = [float(scores.get(dim, 0)) for dim in DIMENSIONS]
    return round(sum(values) / len(values), 1)


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score / SCORE_MAX * width)))
    return "█" * filled + "░" * (width - filled)


def _sparkline(values: list) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(
        _SPARK[min(7, int(round((v - lo) / span * 7)))] for v in values
    )


def _delta(current: float, base) -> str:
    if base is None:
        return "（无历史）"
    diff = current - base
    arrow = "↑" if diff > 0.05 else ("↓" if diff < -0.05 else "→")
    return f"{arrow} {abs(diff):.1f}"


def _new_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _type_label(interview_type: str) -> str:
    return TYPE_LABELS.get(interview_type, interview_type or "模拟面试")


async def _load_json(storage, name: str, default: Any) -> Any:
    try:
        return await storage.aread_json(name, default=default)
    except Exception:
        return default


async def _load_index(storage) -> list:
    index = await _load_json(storage, INDEX_FILE, [])
    return index if isinstance(index, list) else []


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _add_days(days: int, base: str | None = None) -> str:
    start = (
        datetime.strptime(base, "%Y-%m-%d").date()
        if base
        else datetime.now().date()
    )
    return (start + timedelta(days=days)).strftime("%Y-%m-%d")


def _overdue_days(due_date: str) -> int:
    try:
        return (datetime.now().date() - datetime.strptime(due_date, "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return 0


async def _load_cards(storage) -> list:
    cards = await _load_json(storage, CARDS_FILE, [])
    return cards if isinstance(cards, list) else []


async def _save_cards(storage, cards: list) -> None:
    await storage.awrite_json(CARDS_FILE, cards)


def _normalize_question(text: Any) -> str:
    return " ".join(str(text or "").split())


def _due_cards(cards: list) -> list:
    today = _today()
    return sorted(
        (
            card
            for card in cards
            if card.get("status") == "active"
            and str(card.get("due_date", "")) <= today
        ),
        key=lambda card: str(card.get("due_date", "")),
    )


def _cards_stats(cards: list) -> dict:
    return {
        "total": len(cards),
        "active": sum(1 for c in cards if c.get("status") == "active"),
        "mastered": sum(1 for c in cards if c.get("status") == "mastered"),
        "due": len(_due_cards(cards)),
    }


def _merge_error_cards(cards: list, record: dict) -> tuple:
    """把本次面试中评分 ≤6 的题合并进错题本（同题去重，重置到期）。"""
    updates = []
    by_question = {
        _normalize_question(card.get("question")): card for card in cards
    }
    for question in record.get("questions", []):
        rating = question.get("rating")
        if rating is None or int(rating) > AUTO_CARD_MAX_RATING:
            continue
        text = str(question.get("question") or "").strip()
        if not text:
            continue
        key = _normalize_question(text)
        now_str = _now_str()
        existing = by_question.get(key)
        fields = {
            "category": str(question.get("category") or "未分类"),
            "flaw": str(question.get("flaw") or ""),
            "my_answer": str(question.get("answer_summary") or ""),
            "model_answer": str(question.get("model_answer") or ""),
            "source_session": record["id"],
            "pass_streak": 0,
            "interval_days": 1,
            "due_date": _add_days(1),
            "status": "active",
            "updated_at": now_str,
        }
        if existing:
            existing.update(fields)
            existing["fail_count"] = existing.get("fail_count", 0) + 1
            existing["last_result"] = "failed"
            updates.append(("updated", existing))
        else:
            card = {
                "id": f"card-{_new_id()}",
                "question": text,
                "created_at": now_str,
                "fail_count": 1,
                "last_reviewed": None,
                "last_result": None,
                **fields,
            }
            cards.append(card)
            by_question[key] = card
            updates.append(("new", card))
    return cards, updates


def _session_summary(record: dict) -> dict:
    return {
        "id": record["id"],
        "created_at": record["created_at"],
        "position": record.get("position", ""),
        "company": record.get("company", ""),
        "interview_type": record.get("interview_type", "mock"),
        "avg": _avg(record.get("scores", {})),
        "scores": record.get("scores", {}),
        "weaknesses": record.get("weaknesses", []),
        "question_count": len(record.get("questions", [])),
    }


def _dim_lines_md(scores: dict, base: dict | None, base_label: str = "历史") -> str:
    lines = []
    for dim in DIMENSIONS:
        value = scores[dim]
        ref = base.get(dim) if base else None
        prefix = f"{base_label} " if ref is not None else ""
        lines.append(
            f"- **{dim}**：{value}/10 ｜{_bar(value)}｜"
            f"vs{prefix}{_delta(value, ref)}",
        )
    return "\n".join(lines)


def _prev_dim_averages(index: list) -> dict | None:
    older = index[:-1] if index else []
    if not older:
        return None
    acc = {dim: [] for dim in DIMENSIONS}
    for entry in older:
        scores = entry.get("scores", {})
        for dim in DIMENSIONS:
            if dim in scores:
                acc[dim].append(float(scores[dim]))
    base = {d: round(sum(v) / len(v), 1) for d, v in acc.items() if v}
    return base or None


# ---------------------------------------------------------------------------
# 会话报告 / 画像渲染（Markdown）
# ---------------------------------------------------------------------------


def _render_session_md(record: dict) -> str:
    scores = record.get("scores", {})
    lines = [
        f"# 面试档案 · {record.get('position', '未指定岗位')}",
        "",
        f"- 档案 ID：`{record['id']}`",
        f"- 时间：{record.get('created_at', '')}",
        f"- 类型：{_type_label(record.get('interview_type', 'mock'))}"
        + (f"（公司：{record['company']}）" if record.get("company") else ""),
        f"- 题目数：{len(record.get('questions', []))}",
        "",
        f"## 维度评分（均分 {_avg(scores)}）",
        "",
        _dim_lines_md(scores, None),
        "",
    ]
    strengths = record.get("strengths") or []
    weaknesses = record.get("weaknesses") or []
    lines.append("## 亮点")
    lines += [f"- {s}" for s in strengths] or ["（未记录）"]
    lines.append("")
    lines.append("## 弱点")
    lines += [f"- {w}" for w in weaknesses] or ["（未记录）"]
    lines.append("")
    lines.append("## 整体建议")
    lines.append(str(record.get("advice") or "").strip() or "（未记录）")
    questions = record.get("questions") or []
    if questions:
        lines.append("")
        lines.append("## 逐题记录")
        for i, question in enumerate(questions, 1):
            lines.append("")
            lines.append(f"### Q{i} {question.get('question', '')}")
            if question.get("category"):
                lines.append(f"- 考点：{question['category']}")
            if question.get("rating") is not None:
                lines.append(f"- 评分：{question['rating']}/10")
            if question.get("answer_summary"):
                lines.append(f"- 回答摘要：{question['answer_summary']}")
            follow_ups = question.get("follow_ups") or []
            if follow_ups:
                lines.append("- 追问：" + "；".join(follow_ups))
    return "\n".join(lines)


def _merge_profile(profile: dict, record: dict, index: list) -> dict:
    profile = dict(profile) if isinstance(profile, dict) else {}
    position = str(record.get("position") or "").strip()
    company = str(record.get("company") or "").strip()

    profile["interview_count"] = len(index)
    positions = [p for p in profile.get("target_positions", []) if p != position]
    positions.insert(0, position)
    profile["target_positions"] = positions[:6]
    if company:
        companies = [c for c in profile.get("companies", []) if c != company]
        companies.insert(0, company)
        profile["companies"] = companies[:8]

    acc = {dim: [] for dim in DIMENSIONS}
    for entry in index:
        for dim, value in entry.get("scores", {}).items():
            if dim in acc:
                acc[dim].append(float(value))
    profile["dimension_averages"] = {
        d: round(sum(v) / len(v), 1) for d, v in acc.items() if v
    }

    freq = dict(profile.get("weakness_frequency", {}))
    for weakness in record.get("weaknesses", []):
        key = " ".join(str(weakness).split())
        if key:
            freq[key] = freq.get(key, 0) + 1
    profile["weakness_frequency"] = dict(
        sorted(freq.items(), key=lambda kv: -kv[1])[:30],
    )

    strengths = [s for s in record.get("strengths", []) if s]
    merged = strengths + [
        s for s in profile.get("strengths", []) if s not in strengths
    ]
    profile["strengths"] = merged[:15]

    history = profile.get("dimension_history", [])
    history.append(
        {
            "date": record.get("created_at", ""),
            "position": position,
            "avg": _avg(record.get("scores", {})),
            "scores": record.get("scores", {}),
        },
    )
    profile["dimension_history"] = history[-30:]
    profile["trend"] = [entry["avg"] for entry in index][-20:]
    avgs = [entry["avg"] for entry in index]
    profile["latest_session_id"] = record["id"]
    profile["latest_avg"] = avgs[-1] if avgs else None
    profile["best_avg"] = max(avgs) if avgs else None
    return profile


def _weakest_dim(profile: dict) -> tuple | None:
    averages = profile.get("dimension_averages", {})
    if not averages:
        return None
    dim = min(averages, key=averages.get)
    return dim, averages[dim]


def _top_weaknesses(profile: dict, limit: int = 5) -> list:
    freq = profile.get("weakness_frequency", {})
    return sorted(freq.items(), key=lambda kv: -kv[1])[:limit]


def _render_profile_md(profile: dict) -> str:
    if not profile or not profile.get("interview_count"):
        return "# 面试画像\n\n（暂无数据：完成第一次面试存档后自动生成）\n"
    lines = [
        "# 面试画像",
        "",
        f"更新于 {profile.get('updated_at', '')} · "
        f"累计 {profile['interview_count']} 次面试 · "
        f"最佳均分 {profile.get('best_avg', '—')} · "
        f"最近均分 {profile.get('latest_avg', '—')}",
        "",
        "## 维度均分",
        "",
    ]
    for dim, value in profile.get("dimension_averages", {}).items():
        lines.append(f"- {dim}：{value}/10 ｜{_bar(value)}｜")
    top = _top_weaknesses(profile)
    if top:
        lines += ["", "## 高频弱点", ""]
        lines += [f"- {name}（出现 {count} 次）" for name, count in top]
    positions = profile.get("target_positions", [])
    if positions:
        lines += ["", "## 目标岗位", "", f"- {'、'.join(positions)}"]
    trend = profile.get("trend", [])
    if len(trend) >= 2:
        lines += [
            "",
            "## 进步曲线",
            "",
            " → ".join(f"{v:g}" for v in trend) + f"（{_sparkline(trend)}）",
        ]
    return "\n".join(lines) + "\n"


def _render_profile_tool_text(
    profile: dict, bank_note: str = "", cards_note: str = "",
) -> str:
    if not profile or not profile.get("interview_count"):
        text = (
            "## 🧑‍💼 用户面试画像\n\n"
            "（暂无面试档案）本轮请正常进行；若完成一次面试，"
            "结束时务必调用 save_interview_session 建档。"
        )
        if bank_note:
            text += "\n\n" + bank_note
        if cards_note:
            text += "\n\n" + cards_note
        return text
    lines = [
        "## 🧑‍💼 用户面试画像",
        "",
        f"累计 {profile['interview_count']} 次面试 · "
        f"最近均分 {profile.get('latest_avg', '—')} / 10 · "
        f"最佳均分 {profile.get('best_avg', '—')} / 10",
        "",
        "### 维度均分",
        "",
    ]
    for dim, value in profile.get("dimension_averages", {}).items():
        lines.append(f"- {dim}：{value}/10 ｜{_bar(value)}｜")
    top = _top_weaknesses(profile)
    if top:
        lines += ["", "### 高频弱点 TOP", ""]
        lines += [
            f"{i}. {name}（{count} 次）" for i, (name, count) in enumerate(top, 1)
        ]
    positions = profile.get("target_positions", [])
    if positions:
        lines += ["", f"### 目标岗位：{'、'.join(positions)}"]
    trend = profile.get("trend", [])
    if len(trend) >= 2:
        lines += [
            "",
            "### 进步曲线",
            "",
            " → ".join(f"{v:g}" for v in trend) + f"（{_sparkline(trend)}）",
        ]
    if bank_note:
        lines += ["", bank_note]
    if cards_note:
        lines += ["", cards_note]
    weakest = _weakest_dim(profile)
    if weakest:
        lines += [
            "",
            "### 本轮建议",
            "",
            f"- 最弱维度是「{weakest[0]}」（{weakest[1]}/10），"
            "请优先安排相关题目并针对性追问。",
        ]
        if top:
            lines.append(f"- 复查高频弱点：{top[0][0]}。")
    return "\n".join(lines)


def _render_save_result(
    record: dict, index: list, profile: dict, card_updates: list,
) -> str:
    scores = record.get("scores", {})
    previous_avg = index[-2]["avg"] if len(index) >= 2 else None
    lines = [
        "## 💾 面试已存档",
        "",
        f"- 档案 ID：`{record['id']}`",
        f"- 岗位：{record.get('position', '未指定')}"
        + (f" · 公司：{record['company']}" if record.get("company") else ""),
        f"- 类型：{_type_label(record.get('interview_type', 'mock'))}"
        f" · 题目数：{len(record.get('questions', []))}",
        "",
        f"### 维度评分（均分 {_avg(scores)}，"
        f"vs 上一次 {_delta(_avg(scores), previous_avg)}）",
        "",
        _dim_lines_md(scores, _prev_dim_averages(index)),
    ]
    weaknesses = record.get("weaknesses") or []
    if weaknesses:
        lines += ["", "### 记录的弱点", ""]
        lines += [f"- {w}" for w in weaknesses]
    weakest = _weakest_dim(profile)
    top = _top_weaknesses(profile, limit=3)
    if weakest or top:
        lines += ["", "### 下次建议优先攻克", ""]
        if weakest:
            lines.append(f"- 维度「{weakest[0]}」当前均分仅 {weakest[1]}/10。")
        lines += [f"- {name}（已出现 {count} 次）" for name, count in top]
    lines += [
        "",
        "调用 `render_report_card`（传入 session_id）可生成 HTML 可视化报告卡。",
    ]
    if card_updates:
        lines += ["", "### 🃏 错题卡（评分 ≤6 的题已自动入卡）", ""]
        for kind, card in card_updates:
            label = "新增" if kind == "new" else "到期重置"
            lines.append(f"- {label}：{card['question']}（明日首次复习）")
        lines += ["", "之后说「**错题重测**」即可开始 3 分钟特训（换角度出题、60 秒限时）。"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML 报告卡
# ---------------------------------------------------------------------------


def _radar_svg(scores: dict, size: int = 320) -> str:
    cx = cy = size / 2
    radius = size * 0.36
    n = len(DIMENSIONS)

    def pt(i: int, r: float) -> tuple:
        ang = math.radians(-90 + i * 360 / n)
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    rings = []
    for k in (2, 4, 6, 8, 10):
        pts = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (pt(i, radius * k / 10) for i in range(n))
        )
        rings.append(
            f'<polygon points="{pts}" fill="none" stroke="#243050" stroke-width="1"/>',
        )
    axes = "".join(
        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{pt(i, radius)[0]:.1f}" '
        f'y2="{pt(i, radius)[1]:.1f}" stroke="#243050" stroke-width="1"/>'
        for i in range(n)
    )
    data = [
        pt(i, radius * max(0.0, min(10.0, float(scores.get(dim, 0)))) / 10)
        for i, dim in enumerate(DIMENSIONS)
    ]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in data)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#818cf8" '
        f'stroke="#0b1020" stroke-width="1.5"/>'
        for x, y in data
    )
    labels = []
    for i, dim in enumerate(DIMENSIONS):
        lx, ly = pt(i, radius + 26)
        anchor = "middle"
        if lx > cx + 5:
            anchor = "start"
        elif lx < cx - 5:
            anchor = "end"
        value = int(scores.get(dim, 0))
        labels.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#c7cdf0" font-size="13" '
            f'text-anchor="{anchor}" dominant-baseline="middle">'
            f'{_escape(dim)} <tspan fill="#818cf8" font-weight="700">{value}</tspan>'
            f"</text>",
        )
    return (
        f'<svg viewBox="0 0 {size} {size + 14}" width="{size}" '
        f'height="{size + 14}" role="img" aria-label="能力雷达图">'
        + "".join(rings)
        + axes
        + f'<polygon points="{poly}" fill="rgba(99,102,241,0.30)" '
        f'stroke="#6366f1" stroke-width="2.5" stroke-linejoin="round"/>'
        + dots
        + "".join(labels)
        + "</svg>"
    )


def _trend_svg(history: list, width: int = 640, height: int = 190) -> str:
    points = [
        (entry.get("created_at", ""), float(entry.get("avg", 0)))
        for entry in history
    ]
    if len(points) < 2:
        return '<p class="trend-empty">再完成 1 次面试后，这里会显示你的进步曲线。</p>'
    pad_l, pad_r, pad_t, pad_b = 48, 48, 28, 34
    values = [v for _, v in points]
    lo, hi = min(values), max(values)
    if hi - lo < 1.5:
        mid = (hi + lo) / 2
        lo, hi = mid - 1.5, mid + 1.5
    lo = max(0.0, lo - 0.4)
    hi = min(10.0, hi + 0.4)
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def xy(i: int, v: float) -> tuple:
        x = pad_l + plot_w * (i / (len(points) - 1))
        y = pad_t + plot_h * (1 - (v - lo) / (hi - lo))
        return x, y

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="历史趋势线">',
    ]
    for k in range(5):
        value = lo + (hi - lo) * k / 4
        y = pad_t + plot_h * (1 - k / 4)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="#1d2440" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" fill="#8b93b0" font-size="11" '
            f'text-anchor="end">{value:.1f}</text>',
        )
    coords = [xy(i, v) for i, (_, v) in enumerate(points)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    parts.append(
        f'<polygon points="{pad_l},{pad_t + plot_h:.1f} {line} '
        f'{pad_l + plot_w:.1f},{pad_t + plot_h:.1f}" fill="rgba(52,211,153,0.10)"/>'
        f'<polyline points="{line}" fill="none" stroke="#34d399" '
        f'stroke-width="2.5" stroke-linejoin="round"/>',
    )
    step = max(1, len(points) // 8)
    for i, ((label, value), (x, y)) in enumerate(zip(points, coords)):
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#34d399" '
            f'stroke="#0b1020" stroke-width="1.5"/>'
            f'<text x="{x:.1f}" y="{y - 10:.1f}" fill="#a7f3d0" font-size="12" '
            f'font-weight="600" text-anchor="middle">{value:.1f}</text>',
        )
        if i % step == 0 or i == len(points) - 1:
            short = label[5:10] if len(label) >= 10 else label
            anchor = "start" if i == 0 else (
                "end" if i == len(points) - 1 else "middle"
            )
            parts.append(
                f'<text x="{x:.1f}" y="{height - 10}" fill="#8b93b0" font-size="11" '
                f'text-anchor="{anchor}">{_escape(short)}</text>',
            )
    parts.append("</svg>")
    return "".join(parts)


def _dim_cards_html(scores: dict) -> str:
    cards = []
    for dim in DIMENSIONS:
        value = float(scores.get(dim, 0))
        color = "#f87171" if value < 5 else ("#fbbf24" if value < 7 else "#34d399")
        cards.append(
            f'<div class="dim"><div class="dim-head"><span>{_escape(dim)}</span>'
            f'<b style="color:{color}">{value:g}</b></div>'
            f'<div class="bar"><i style="width:{value * 10:.0f}%;'
            f'background:{color}"></i></div></div>',
        )
    return "\n".join(cards)


def _chips_html(items: list, css_class: str) -> str:
    if not items:
        return '<span class="muted">（未记录）</span>'
    return "".join(
        f'<span class="chip {css_class}">{_escape(item)}</span>' for item in items
    )


def _questions_html(questions: list) -> str:
    if not questions:
        return '<p class="muted">本次未记录逐题明细。</p>'
    blocks = []
    for i, question in enumerate(questions, 1):
        rating = question.get("rating")
        rating_html = (
            f'<span class="meta">· {rating}/10</span>'
            if rating is not None
            else ""
        )
        category = (
            f'<span class="meta">· {_escape(question["category"])}</span>'
            if question.get("category")
            else ""
        )
        summary = (
            f"<p>{_escape(question['answer_summary'])}</p>"
            if question.get("answer_summary")
            else ""
        )
        follow_ups = question.get("follow_ups") or []
        follow_html = (
            "<ul>"
            + "".join(f"<li>追问：{_escape(f)}</li>" for f in follow_ups)
            + "</ul>"
            if follow_ups
            else ""
        )
        blocks.append(
            f"<details><summary>Q{i}. {_escape(question.get('question', ''))}"
            f"{category}{rating_html}</summary>{summary}{follow_html}</details>",
        )
    return "\n".join(blocks)


_HTML_TEMPLATE = _string.Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>IntelliView 面试报告 · $title_position</title>
<style>
:root{--bg:#0b1020;--card:#141a30;--card2:#101631;--line:#243050;--text:#e8ecf8;--muted:#8b93b0;--accent:#6366f1}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(1100px 520px at 18% -8%,#1a2347 0%,var(--bg) 58%);color:var(--text);font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65;padding:36px 16px}
.wrap{max-width:900px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
h1{font-size:24px;letter-spacing:.5px}
.sub{color:var(--muted);margin-top:4px;font-size:14px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chips span{padding:3px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card2);font-size:12.5px;color:#c7cdf0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px}
.card h2{font-size:15px;color:#aab2d5;font-weight:600;margin-bottom:14px;letter-spacing:1px}
.grid{display:grid;grid-template-columns:340px 1fr;gap:18px;align-items:stretch}
@media(max-width:740px){.grid{grid-template-columns:1fr}}
.radar{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
.ring{width:118px;height:118px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.ring-in{width:90px;height:90px;border-radius:50%;background:var(--card);display:flex;flex-direction:column;align-items:center;justify-content:center}
.ring-in b{font-size:26px}
.ring-in i{font-style:normal;font-size:11px;color:var(--muted)}
.dims{display:flex;flex-direction:column;gap:13px;justify-content:center}
.dim-head{display:flex;justify-content:space-between;font-size:13.5px;margin-bottom:5px}
.bar{height:8px;border-radius:4px;background:#1d2440;overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px}
.tag-row{display:flex;flex-wrap:wrap;gap:8px}
.chip{padding:5px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card2);font-size:13px}
.chip.bad{border-color:rgba(248,113,113,.45);color:#fca5a5}
.chip.good{border-color:rgba(52,211,153,.45);color:#6ee7b7}
.muted{color:var(--muted);font-size:13px}
details{border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:10px;background:var(--card2)}
summary{cursor:pointer;font-weight:600;font-size:14px}
summary .meta{color:var(--muted);font-weight:400;font-size:12.5px;margin-left:8px}
details p{margin-top:8px;font-size:13.5px;color:#cdd4ee}
details ul{margin:6px 0 0 18px;font-size:13px;color:#aeb6d8}
.advice{white-space:pre-wrap;font-size:14px;color:#dfe5fb}
.trend-empty{color:var(--muted);font-size:13px}
footer{text-align:center;color:var(--muted);font-size:12px;padding:10px 0 18px}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>🎯 IntelliView 面试报告卡</h1>
    <div class="sub">$headline</div>
    <div class="chips">$meta_chips</div>
  </div>
  <div class="card">
    <h2>能力雷达 · 能力卡片</h2>
    <div class="grid">
      <div class="radar">$radar<div class="ring" style="background:conic-gradient(var(--accent) $ring_pct%,#1d2440 0)"><div class="ring-in"><b>$ring_avg</b><i>综合均分</i></div></div></div>
      <div class="dims">$dim_cards</div>
    </div>
  </div>
  <div class="card">
    <h2>亮点与弱点</h2>
    <p class="muted" style="margin-bottom:8px">亮点</p>
    <div class="tag-row">$strength_chips</div>
    <p class="muted" style="margin:14px 0 8px">待攻克弱点</p>
    <div class="tag-row">$weak_chips</div>
  </div>
  <div class="card">
    <h2>历史进步曲线</h2>
    $trend
  </div>
  <div class="card">
    <h2>逐题明细</h2>
    $questions
  </div>
  <div class="card">
    <h2>整体建议</h2>
    <div class="advice">$advice</div>
  </div>
  <footer>$footer</footer>
</div>
</body>
</html>
""")


def _render_html(record: dict, history: list) -> str:
    scores = record.get("scores", {})
    avg = _avg(scores)
    interview_type = record.get("interview_type", "mock")
    headline = (
        f"{record.get('position', '未指定岗位')} · {_type_label(interview_type)} · "
        f"{record.get('created_at', '')}"
    )
    chips = [record.get("created_at", ""), record.get("position", "")]
    if record.get("company"):
        chips.append(record["company"])
    chips.append(_type_label(interview_type))
    chips.append(f"{len(record.get('questions', []))} 题")
    chips.append(f"档案 {record['id']}")
    meta_chips = "".join(f"<span>{_escape(c)}</span>" for c in chips if c)
    footer = (
        f"IntelliView v0.3 · QwenPaw 插件生成 · {record['id']} · {_now_str()}"
    )
    return _HTML_TEMPLATE.substitute(
        title_position=_escape(record.get("position", "面试报告")),
        headline=_escape(headline),
        meta_chips=meta_chips,
        radar=_radar_svg(scores),
        ring_pct=f"{avg * 10:.0f}",
        ring_avg=f"{avg:g}",
        dim_cards=_dim_cards_html(scores),
        strength_chips=_chips_html(record.get("strengths") or [], "good"),
        weak_chips=_chips_html(record.get("weaknesses") or [], "bad"),
        trend=_trend_svg(history),
        questions=_questions_html(record.get("questions") or []),
        advice=_escape(str(record.get("advice") or "") or "（未记录）"),
        footer=_escape(footer),
    )




class IntelliView:
    # -- 工具实现 -----------------------------------------------------------

    async def save_interview_session(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        storage = context.storage
        sid = _new_id()
        record = {
            "id": sid,
            "created_at": _now_str(),
            "position": str(arguments.get("position") or "未指定岗位").strip(),
            "company": str(arguments.get("company") or "").strip(),
            "interview_type": arguments.get("interview_type") or "mock",
            "questions": arguments.get("questions") or [],
            "scores": _norm_scores(arguments.get("scores") or {}),
            "strengths": [str(s) for s in (arguments.get("strengths") or []) if s],
            "weaknesses": [str(w) for w in (arguments.get("weaknesses") or []) if w],
            "advice": str(arguments.get("advice") or "").strip(),
            "notes": str(arguments.get("notes") or "").strip(),
        }
        try:
            await storage.awrite_json(f"{SESSIONS_DIR}/{sid}.json", record)
            await storage.awrite_bytes(
                f"{SESSIONS_DIR}/{sid}.md",
                _render_session_md(record).encode("utf-8"),
            )
            index = await _load_index(storage)
            index.append(_session_summary(record))
            index.sort(key=lambda entry: entry.get("created_at", ""))
            await storage.awrite_json(INDEX_FILE, index)
            profile = await _load_json(storage, PROFILE_JSON, {}) or {}
            profile = _merge_profile(profile, record, index)
            profile["updated_at"] = _now_str()
            await storage.awrite_json(PROFILE_JSON, profile)
            await storage.awrite_bytes(
                PROFILE_MD,
                _render_profile_md(profile).encode("utf-8"),
            )
            cards = await _load_cards(storage)
            cards, card_updates = _merge_error_cards(cards, record)
            await _save_cards(storage, cards)
        except Exception as error:  # pragma: no cover - 存储故障兜底
            context.logger.error(f"save_interview_session failed: {error}")
            return EngineResult(text=f"存档失败：{error}", is_error=True)
        context.logger.info(f"Interview session saved: {sid}")
        return EngineResult(
            text=_render_save_result(record, index, profile, card_updates),
            metadata={"session_id": sid},
        )

    async def load_user_profile(
        self,
        context,
        _arguments: dict,
    ) -> EngineResult:
        profile = await _load_json(context.storage, PROFILE_JSON, {}) or {}
        bank_note = ""
        cards_note = ""
        active_bank_id = profile.get("active_question_bank")
        if active_bank_id:
            bank = await _load_json(
                context.storage,
                f"{BANKS_DIR}/{active_bank_id}.json",
                None,
            )
            if bank:
                bank_note = (
                    f"当前激活题库：{bank.get('position', '')}"
                    f"（{len(bank.get('questions', []))} 题，ID {active_bank_id}），"
                    "模拟面试优先按此出题。"
                )
        cards = await _load_cards(context.storage)
        stats = _cards_stats(cards)
        if stats["total"]:
            due = _due_cards(cards)
            cards_note = (
                f"### 🃏 错题本：{stats['active']} 张在练 · "
                f"{stats['mastered']} 张已掌握 · {stats['due']} 张今日到期"
            )
            if due:
                cards_note += "\n" + "\n".join(
                    f"- {card.get('question', '')}"
                    f"（逾期 {_overdue_days(str(card.get('due_date', '')))} 天）"
                    for card in due[:3]
                )
                cards_note += "\n- 说「**错题重测**」开始 3 分钟特训"
        return EngineResult(text=
            _render_profile_tool_text(profile, bank_note, cards_note),
        )

    async def generate_interview_report(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        scores = _norm_scores(arguments.get("scores") or {})
        index = await _load_index(context.storage)
        base = _prev_dim_averages(index + [{"scores": scores}])
        overall_base = (
            round(sum(entry["avg"] for entry in index) / len(index), 1)
            if index
            else None
        )
        avg = _avg(scores)
        lines = [
            "## 🎯 面试评估报告",
            "",
            f"岗位：{arguments.get('position', '未指定')} · {_now_str()}",
            "",
            "| 维度 | 得分 | vs 历史均分 |",
            "|---|---|---|",
        ]
        for dim in DIMENSIONS:
            ref = (base or {}).get(dim)
            lines.append(
                f"| {dim} | {scores[dim]}/10 {_bar(scores[dim])} "
                f"| {_delta(scores[dim], ref)} |",
            )
        lines += [
            "",
            f"**综合均分：{avg}/10**"
            + (
                f"（历史均分 {overall_base}，{_delta(avg, overall_base)}）"
                if overall_base
                else "（暂无历史）"
            ),
        ]
        strengths = arguments.get("strengths") or []
        weaknesses = arguments.get("weaknesses") or []
        if strengths:
            lines += ["", "### 亮点", ""] + [f"- {s}" for s in strengths]
        if weaknesses:
            lines += ["", "### 弱点", ""] + [f"- {w}" for w in weaknesses]
        lines += [
            "",
            "### 整体建议",
            "",
            str(arguments.get("advice") or "").strip() or "（暂无）",
        ]
        return EngineResult(text="\n".join(lines))

    async def build_question_bank(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        storage = context.storage
        bank_id = f"bank-{_new_id()}"
        questions = arguments.get("questions") or []
        record = {
            "id": bank_id,
            "created_at": _now_str(),
            "position": str(arguments.get("position") or "未指定岗位").strip(),
            "jd_text": str(arguments.get("jd_text") or "").strip()[:2000],
            "key_points": [str(k) for k in (arguments.get("key_points") or []) if k],
            "questions": questions,
        }
        try:
            await storage.awrite_json(f"{BANKS_DIR}/{bank_id}.json", record)
            banks = await _load_json(storage, BANK_INDEX_FILE, []) or []
            banks = [
                b for b in banks if isinstance(b, dict) and b.get("id") != bank_id
            ]
            banks.append(
                {
                    "id": bank_id,
                    "created_at": record["created_at"],
                    "position": record["position"],
                    "question_count": len(questions),
                },
            )
            await storage.awrite_json(BANK_INDEX_FILE, banks)
            profile = await _load_json(storage, PROFILE_JSON, {}) or {}
            profile["active_question_bank"] = bank_id
            profile["updated_at"] = _now_str()
            await storage.awrite_json(PROFILE_JSON, profile)
        except Exception as error:  # pragma: no cover
            context.logger.error(f"build_question_bank failed: {error}")
            return EngineResult(text=f"题库存档失败：{error}", is_error=True)

        lines = [
            "## 📚 题库已生成并激活",
            "",
            f"- 题库 ID：`{bank_id}`（{len(questions)} 题）",
            f"- 岗位：{record['position']}",
        ]
        if record["key_points"]:
            lines += ["", "### 考点", ""]
            lines += [f"- {k}" for k in record["key_points"]]
        lines += ["", "### 题目预览", ""]
        for i, question in enumerate(questions, 1):
            tags = []
            if question.get("category"):
                tags.append(question["category"])
            if question.get("difficulty"):
                tags.append(DIFF_LABELS.get(question["difficulty"], question["difficulty"]))
            prefix = f"[{'|'.join(tags)}] " if tags else ""
            lines.append(f"{i}. {prefix}{question.get('question', '')}")
            if question.get("follow_up"):
                lines.append(f"   追问：{question['follow_up']}")
        lines += [
            "",
            "已设为当前激活题库：模拟面试将优先按此题库出题，"
            "每题按预设追问至少深挖一层。",
        ]
        context.logger.info(f"Question bank saved: {bank_id}")
        return EngineResult(text="\n".join(lines))

    async def list_interview_history(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        index = await _load_index(context.storage)
        position = str(arguments.get("position") or "").strip()
        if position:
            index = [e for e in index if position in e.get("position", "")]
        if not index:
            return EngineResult(text=
                "## 📜 面试历史\n\n（暂无面试档案）完成一次模拟面试或复盘录入后，"
                "档案会自动出现在这里。",
            )
        limit = int(arguments.get("limit") or 10)
        shown = index[-limit:]
        lines = [
            f"## 📜 面试历史（共 {len(index)} 次"
            + (f"，按“{position}”过滤" if position else "")
            + "）",
            "",
            "| # | 时间 | 岗位 | 类型 | 均分 | vs 上次 | 弱点摘要 |",
            "|---|---|---|---|---|---|---|",
        ]
        prev = None
        start = len(index) - len(shown) + 1
        for offset, entry in enumerate(shown):
            current = float(entry.get("avg", 0))
            weakness = "、".join(entry.get("weaknesses", [])[:2]) or "—"
            lines.append(
                f"| {start + offset} | {entry.get('created_at', '')} "
                f"| {entry.get('position', '')} "
                f"| {_type_label(entry.get('interview_type', 'mock'))} "
                f"| {current:g} | {_delta(current, prev)} | {weakness} |",
            )
            prev = current
        trend = [float(entry.get("avg", 0)) for entry in index]
        lines += [
            "",
            f"**均分曲线**：{_sparkline(trend)}（最早 → 最新："
            + " → ".join(f"{v:g}" for v in trend)
            + "）",
        ]
        profile = await _load_json(context.storage, PROFILE_JSON, {}) or {}
        weakest = _weakest_dim(profile)
        if weakest:
            lines.append(
                f"**最弱维度**：{weakest[0]}（{weakest[1]}/10）"
                "——复盘建议围绕它展开。",
            )
        return EngineResult(text="\n".join(lines))

    async def render_report_card(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        storage = context.storage
        session_id = str(arguments.get("session_id") or "").strip()
        if session_id:
            record = await _load_json(
                storage,
                f"{SESSIONS_DIR}/{session_id}.json",
                None,
            )
            if not record:
                return EngineResult(text=
                    f"未找到档案 {session_id}，请先用 save_interview_session 存档。",
                    is_error=True,
                )
        else:
            if not arguments.get("scores") or not arguments.get("position"):
                return EngineResult(text=
                    "请传入已存档的 session_id，或提供完整面试数据"
                    "（position + scores + advice）。",
                    is_error=True,
                )
            record = {
                "id": _new_id(),
                "created_at": _now_str(),
                "position": arguments.get("position", ""),
                "company": arguments.get("company", ""),
                "interview_type": arguments.get("interview_type") or "mock",
                "questions": arguments.get("questions") or [],
                "scores": _norm_scores(arguments.get("scores") or {}),
                "strengths": arguments.get("strengths") or [],
                "weaknesses": arguments.get("weaknesses") or [],
                "advice": arguments.get("advice", ""),
            }
        index = await _load_index(storage)
        known = any(entry.get("id") == record["id"] for entry in index)
        history = index if known else index + [_session_summary(record)]
        history.sort(key=lambda entry: entry.get("created_at", ""))
        html_doc = _render_html(record, history)
        file_name = f"{REPORTS_DIR}/{record['id']}.html"
        try:
            attachment = await context.media.awrite(
                file_name,
                html_doc.encode("utf-8"),
                mime_type="text/html",
            )
        except Exception as error:  # pragma: no cover
            context.logger.error(f"render_report_card failed: {error}")
            return EngineResult(text=f"HTML 报告生成失败：{error}", is_error=True)
        local_path = str(storage._path(file_name))  # noqa: SLF001 - 仅用于展示
        avg = _avg(record["scores"])
        md = (
            "## 📊 可视化报告卡已生成\n\n"
            f"- 岗位：{record.get('position', '')} · 均分 {avg:g}/10\n"
            f"- 档案：`{record['id']}`\n"
            f"- 本地路径：`{local_path}`\n\n"
            "报告包含能力雷达图、五维卡片、亮点/弱点清单与历史进步曲线，"
            "已在下方以文件附件提供，可直接用浏览器打开。"
        )
        context.logger.info(f"Report card rendered: {record['id']}")
        return EngineResult(
            text=md,
            metadata={"session_id": record["id"], "html_path": local_path},
            attachment=attachment,
        )

    async def create_error_card(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        question = str(arguments.get("question") or "").strip()
        if not question:
            return EngineResult(text="question 不能为空", is_error=True)
        record = {
            "id": "manual",
            "questions": [
                {
                    "question": question,
                    "category": arguments.get("category"),
                    "flaw": arguments.get("flaw"),
                    "answer_summary": arguments.get("my_answer"),
                    "model_answer": arguments.get("model_answer"),
                    "rating": AUTO_CARD_MAX_RATING,
                },
            ],
        }
        try:
            cards = await _load_cards(context.storage)
            cards, updates = _merge_error_cards(cards, record)
            await _save_cards(context.storage, cards)
        except Exception as error:  # pragma: no cover
            context.logger.error(f"create_error_card failed: {error}")
            return EngineResult(text=f"错题卡写入失败：{error}", is_error=True)
        kind, card = updates[0]
        label = "已存在，信息已更新" if kind == "updated" else "已创建"
        md = (
            f"## 🃏 错题卡{label}\n\n"
            f"- 题目：{card['question']}\n"
            f"- 考点：{card.get('category', '未分类')}\n"
            f"- 丢分点：{card.get('flaw') or '（待补充）'}\n"
            f"- 卡片 ID：`{card['id']}`\n\n"
            "复习节奏：明日首次复习，之后按 3 / 7 / 14 天升级"
            "（答对一次升一档，连续答对 3 次标记掌握）。"
            "到期会在对话中自动提醒；说「错题重测」随时开练。"
        )
        context.logger.info(f"Error card created: {card['id']}")
        return EngineResult(text=md)

    async def drill_weaknesses(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        cards = await _load_cards(context.storage)
        due = _due_cards(cards)
        category = str(arguments.get("category") or "").strip()
        if category:
            due = [c for c in due if category in str(c.get("category", ""))]
        stats = _cards_stats(cards)
        if not due:
            upcoming = min(
                (
                    str(c.get("due_date"))
                    for c in cards
                    if c.get("status") == "active"
                ),
                default="",
            )
            md = (
                "## ⚡ 错题特训\n\n当前没有到期错题。"
                + (f"最近一张 {upcoming} 到期。" if upcoming else "")
                + f"错题本：{stats['active']} 张在练 · {stats['mastered']} 张已掌握。"
            )
            return EngineResult(text=md)
        count = int(arguments.get("count") or 5)
        picked = due[:count]
        lines = [
            "## ⚡ 错题特训（3 分钟）",
            "",
            f"错题本：{stats['active']} 张在练 · {stats['mastered']} 张已掌握 · "
            f"到期 {stats['due']} 张，本次抽取 **{len(picked)}** 张。",
            "",
            "### 出题规则（严格遵守）",
            "1. **换角度出题**：换场景 / 换数字 / 反着问，禁止原题复读（防背答案）",
            "2. **60 秒限时**：出题后要求用户立即开始作答、一次成稿，"
            "长时间斟酌视为不过关",
            "3. 用户答完先点评，再展示该卡的参考要点",
            "4. 每题判定后**立即调用 update_error_card**（card_id + passed）",
            "",
            "### 到期错题",
        ]
        for i, card in enumerate(picked, 1):
            overdue = _overdue_days(str(card.get("due_date", "")))
            lines += [
                "",
                f"**{i}. {card.get('question')}**",
                f"- 卡片 ID：`{card['id']}`",
                f"- 考点：{card.get('category', '未分类')}",
            ]
            if card.get("flaw"):
                lines.append(f"- 上次丢分：{card['flaw']}")
            if overdue > 0:
                lines.append(f"- 已逾期 {overdue} 天")
            if card.get("my_answer"):
                lines.append(
                    f"- 用户原回答（仅出题参考，勿复述）：{card['my_answer']}",
                )
            lines.append(
                f"- 参考要点（用户作答后再展示）："
                f"{card.get('model_answer') or '（未记录）'}",
            )
        return EngineResult(text="\n".join(lines))

    async def update_error_card(
        self,
        context,
        arguments: dict,
    ) -> EngineResult:
        card_id = str(arguments.get("card_id") or "").strip()
        cards = await _load_cards(context.storage)
        card = next((c for c in cards if c.get("id") == card_id), None)
        if not card:
            return EngineResult(text=
                f"未找到错题卡 {card_id}", is_error=True,
            )
        passed = bool(arguments.get("passed"))
        card["last_reviewed"] = _now_str()
        card["last_result"] = "passed" if passed else "failed"
        rating = arguments.get("rating")
        if rating is not None:
            try:
                card["last_rating"] = max(
                    SCORE_MIN, min(SCORE_MAX, int(rating)),
                )
            except (TypeError, ValueError):
                pass
        if arguments.get("note"):
            card["note"] = str(arguments["note"])
        if passed:
            streak = int(card.get("pass_streak", 0)) + 1
            card["pass_streak"] = streak
            if streak >= MASTER_STREAK:
                card["status"] = "mastered"
                card["interval_days"] = 0
                card["due_date"] = ""
            else:
                interval = INTERVAL_LADDER[streak]
                card["interval_days"] = interval
                card["due_date"] = _add_days(interval)
        else:
            card["pass_streak"] = 0
            card["fail_count"] = int(card.get("fail_count", 0)) + 1
            card["interval_days"] = 1
            card["due_date"] = _add_days(1)
        try:
            await _save_cards(context.storage, cards)
        except Exception as error:  # pragma: no cover
            context.logger.error(f"update_error_card failed: {error}")
            return EngineResult(text=f"错题卡更新失败：{error}", is_error=True)
        stats = _cards_stats(cards)
        lines = [
            "## ✅ 错题卡已更新",
            "",
            f"- 题目：{card['question']}",
        ]
        if passed:
            if card["status"] == "mastered":
                lines.append(
                    f"- 结果：🎉 连续答对 {MASTER_STREAK} 次，已掌握，退出错题循环！",
                )
            else:
                lines.append(
                    f"- 结果：通过（连续 {card['pass_streak']}/{MASTER_STREAK}）"
                    f"→ 下次复习 {card['due_date']}（{card['interval_days']} 天后）",
                )
        else:
            lines.append(
                "- 结果：未通过 → 间隔重置，明日再测（同题会换角度重出）",
            )
        lines.append(
            f"- 错题本：{stats['active']} 张在练 · {stats['mastered']} 张已掌握 · "
            f"{stats['due']} 张到期",
        )
        context.logger.info(f"Error card updated: {card_id}")
        return EngineResult(text="\n".join(lines))

    # -- 钩子 ---------------------------------------------------------------

    async def inject_profile(self, context) -> list:
        try:
            profile = await _load_json(context.storage, PROFILE_JSON, {}) or {}
            cards = await _load_cards(context.storage)
        except Exception:
            return []
        due = _due_cards(cards)
        has_profile = bool(profile and profile.get("interview_count"))
        if not has_profile and not due:
            return []
        parts = []
        if has_profile:
            weakest = _weakest_dim(profile)
            top = _top_weaknesses(profile, limit=3)
            trend = profile.get("trend", [])
            parts.append(
                "[IntelliView 用户画像] "
                f"累计面试 {profile['interview_count']} 次"
                f"（最近均分 {profile.get('latest_avg', '—')}/10，"
                f"曲线 {_sparkline(trend) if len(trend) >= 2 else '暂无'}）",
            )
            if weakest:
                parts.append(f"最弱维度：{weakest[0]}({weakest[1]}/10)")
            if top:
                parts.append("高频弱点：" + "、".join(name for name, _ in top))
            positions = profile.get("target_positions", [])
            if positions:
                parts.append("目标岗位：" + "、".join(positions[:3]))
        if due:
            sample = str(due[0].get("question", ""))
            parts.append(
                f"⏰ 错题提醒：{len(due)} 张错题卡到期"
                f"（如「{sample[:24]}」），请主动提示用户说「错题重测」"
                "开始 3 分钟特训",
            )
        parts.append(
            "请结合画像与错题本个性化提问；模拟面试结束后必须调用 "
            "save_interview_session 存档（低分题自动入错题卡）。",
        )
        return ["；".join(parts)]


# ---------------------------------------------------------------------------
# 工具定义（唯一 schema 源：QwenPaw / MCP / CLI 适配器共享）
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "save_interview_session",
        "description": (
                    "面试结束后调用：把岗位、逐题记录与回答摘要、五维评分（1-10）、"
                    "亮点与弱点写入持久面试档案（sessions/ JSON+MD），"
                    "并更新用户画像与进步曲线。返回存档确认与历史对比。"
                ),
        "input_schema": {
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
        "method": "save_interview_session",
    },
    {
        "name": "load_user_profile",
        "description": (
                    "读取用户面试画像：历史维度均分、高频弱点、目标岗位、进步趋势。"
                    "模拟面试 / 复盘 / 职业规划开始前调用，实现跨会话个性化。"
                ),
        "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
        "method": "load_user_profile",
    },
    {
        "name": "generate_interview_report",
        "description": (
                    "生成维度化评估报告（Markdown）：五维 1-10 打分，"
                    "自动与历史均分对比并给出升降幅度。"
                ),
        "input_schema": {
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
        "method": "generate_interview_report",
    },
    {
        "name": "build_question_bank",
        "description": (
                    "JD 定制面试用：把按 JD 解析出的考点与针对性题目存为持久题库，"
                    "并设为激活题库，后续模拟面试优先按此出题。"
                    "JD 解析与题目生成由你（agent）完成，本工具负责持久化与格式化。"
                ),
        "input_schema": {
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
        "method": "build_question_bank",
    },
    {
        "name": "list_interview_history",
        "description": (
                    "列出历次面试档案：日期、岗位、五维评分、均分变化与进步曲线，"
                    "可按岗位过滤。复盘时必调用。"
                ),
        "input_schema": {
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
        "method": "list_interview_history",
    },
    {
        "name": "render_report_card",
        "description": (
                    "生成自包含 HTML 可视化报告卡（雷达图 + 能力卡片 + 弱点清单 + "
                    "历史趋势线），返回文件附件供浏览器打开。"
                    "传入已存档的 session_id 重渲染，或直接传入完整面试数据。"
                ),
        "input_schema": {
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
        "method": "render_report_card",
    },
    {
        "name": "create_error_card",
        "description": (
                    "把一道题加入错题本（错题卡）：面试中答错/答差的题、"
                    "用户自报的薄弱点都可以入卡。入卡后按 1→3→7→14 天间隔重复，"
                    "到期时会在对话中自动提醒重测。"
                ),
        "input_schema": {
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
        "method": "create_error_card",
    },
    {
        "name": "drill_weaknesses",
        "description": (
                    "错题特训：取出当前到期的错题卡供重测。返回出题规则"
                    "（换角度出题、60 秒限时）与每张卡的丢分点/参考要点。"
                    "出题时不要展示参考要点，用户作答后再对照。"
                ),
        "input_schema": {
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
        "method": "drill_weaknesses",
    },
    {
        "name": "update_error_card",
        "description": (
                    "重测后更新错题卡结果：passed=true 时升级复习间隔"
                    "（1→3→7→14 天，连续答对 3 次标记掌握）；"
                    "passed=false 时重置为明日再测。必须在每次重测判定后立即调用。"
                ),
        "input_schema": {
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
        "method": "update_error_card",
    },
]


# ---------------------------------------------------------------------------
# 本地文件运行时（CLI / MCP 适配器直接使用；QwenPaw 用自己的 PluginStorage）
# ---------------------------------------------------------------------------


class LocalStorage:
    """与 QwenPaw PluginStorage 同接口的本地 JSON/字节存储。"""

    def __init__(self, root: Any):
        from pathlib import Path

        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str):
        from pathlib import Path

        path = (self._root / name).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage path out of scope: {name}")
        return path

    async def aread_json(self, name: str, default: Any = None) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    async def awrite_json(self, name: str, value: Any) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    async def awrite_bytes(self, name: str, data: bytes) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def aread_bytes(self, name: str) -> bytes:
        return self._path(name).read_bytes()


class LocalMedia:
    """本地媒体写入：HTML 报告卡落盘并返回 file:// URI 附件。"""

    def __init__(self, storage: LocalStorage):
        self._storage = storage

    async def awrite(self, name: str, data: bytes, *, mime_type: str = "application/octet-stream"):
        from types import SimpleNamespace
        from pathlib import Path

        await self._storage.awrite_bytes(name, data)
        path = self._storage._path(name)
        return SimpleNamespace(
            url=path.as_uri(),
            mime_type=mime_type,
            name=Path(name).name,
            preview_url=path.as_uri(),
        )


class LocalContext:
    """满足引擎鸭子类型的本地运行时上下文。"""

    def __init__(self, data_dir: Any):
        import logging

        self.storage = LocalStorage(data_dir)
        self.media = LocalMedia(self.storage)
        self.logger = logging.getLogger("intelliview")
