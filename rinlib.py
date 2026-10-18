"""Rin preset shared helpers.

Both tools/render.py and runtime/rin.py use this module so the persona
templates have exactly one renderer.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
PERSONA_DIR = ROOT / "persona"

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
PARTNER_BLOCK_RE = re.compile(
    r"<!--\s*if:partner\s*-->(.*?)<!--\s*/if:partner\s*-->", re.DOTALL
)
PARTNER_MARKER_RE = re.compile(r"<!--\s*/?if:partner\s*-->")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def default_config_path() -> Path:
    return ROOT / "config" / "rin.json"


def example_config_path() -> Path:
    return ROOT / "config" / "rin.example.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config, falling back to the example when config/rin.json is absent."""
    if path is None:
        path = default_config_path()
    p = Path(path)
    if not p.exists():
        p = example_config_path()
        print(f"[rin] config not found, using example: {p}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return normalize_config(cfg)


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Fill in defaults so templates can rely on every key existing."""
    cfg = dict(cfg or {})
    cfg.setdefault("character", {})
    cfg["character"].setdefault("name", "Rin")
    cfg["character"].setdefault("self_style", "本天才")
    cfg["character"].setdefault("language", "zh-CN")

    cfg.setdefault("users", {})
    owner = cfg["users"].setdefault("owner", {})
    owner.setdefault("name", "你")
    owner.setdefault("title", "你")
    owner.setdefault("mode", "sunny")
    owner.setdefault("can_read_private", True)

    partner = cfg["users"].setdefault("partner", {})
    partner.setdefault("enabled", False)
    partner.setdefault("name", "TA")
    partner.setdefault("title", "TA")
    partner.setdefault("mode", "sharp")
    partner.setdefault("can_read_private", False)

    cfg.setdefault("timezone", "Asia/Shanghai")

    cfg.setdefault("relationship", {})
    cfg["relationship"].setdefault("label", "一起生活的人")
    cfg["relationship"].setdefault("shared_notes", True)

    cfg.setdefault("privacy", {})
    cfg["privacy"].setdefault("default_visibility", "self")
    cfg["privacy"].setdefault("group_is_public", True)

    cfg.setdefault("runtime", {})
    cfg["runtime"].setdefault("base_url", "https://api.deepseek.com/v1")
    cfg["runtime"].setdefault("model", "deepseek-chat")
    cfg["runtime"].setdefault("api_key_env", "RIN_API_KEY")
    cfg["runtime"].setdefault("api_key", "")
    cfg["runtime"].setdefault("temperature", 1.0)
    cfg["runtime"].setdefault("max_tokens", 800)
    cfg["runtime"].setdefault("history_limit", 20)
    cfg["runtime"].setdefault("use_tools", True)
    cfg["runtime"].setdefault("db_path", "data/rin.db")
    return cfg


def partner_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("users", {}).get("partner", {}).get("enabled", False))


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------


def mapping(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "char": cfg["character"],
        "character": cfg["character"],
        "owner": cfg["users"]["owner"],
        "partner": cfg["users"]["partner"],
        "relationship": cfg.get("relationship", {}),
        "version": VERSION,
    }


def resolve(mapping_obj: dict[str, Any], dotted_key: str) -> Any:
    cur: Any = mapping_obj
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted_key)
        cur = cur[part]
    return cur


def render_text(text: str, values: dict[str, Any], strict: bool = True) -> str:
    """Replace {{a.b}} placeholders. Unknown placeholders raise in strict mode."""
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        try:
            value = resolve(values, key)
        except KeyError:
            if strict:
                missing.append(key)
                return match.group(0)
            return match.group(0)
        if value is None:
            return ""
        return str(value)

    out = PLACEHOLDER_RE.sub(repl, text)
    if missing:
        unique = sorted(set(missing))
        raise KeyError(f"unresolved placeholders: {', '.join(unique)}")
    return out


def apply_conditionals(text: str, cfg: dict[str, Any]) -> str:
    if partner_enabled(cfg):
        return PARTNER_MARKER_RE.sub("", text)
    return PARTNER_BLOCK_RE.sub("", text)


def read_fragment(name: str) -> str:
    return (PERSONA_DIR / name).read_text(encoding="utf-8").strip()


def build_core_text(cfg: dict[str, Any], include_examples: bool = True) -> str:
    parts = [
        read_fragment("identity.md"),
        read_fragment("modes.md"),
        read_fragment("rules.md"),
        read_fragment("tools.md"),
    ]
    if include_examples:
        examples = [read_fragment("examples.owner.md")]
        if partner_enabled(cfg):
            examples.append(read_fragment("examples.partner.md"))
        parts.append("# 语气示例\n\n" + "\n\n".join(examples))
    core = "\n\n".join(parts)
    core = apply_conditionals(core, cfg)
    return render_text(core, mapping(cfg)).strip()


# ---------------------------------------------------------------------------
# time and state formatting
# ---------------------------------------------------------------------------


def get_timezone(name: str):
    try:
        from zoneinfo import ZoneInfo  # type: ignore

        return ZoneInfo(name)
    except Exception:
        if name in {"Asia/Shanghai", "Asia/Chongqing", "PRC"}:
            return timezone(timedelta(hours=8))
        return datetime.now().astimezone().tzinfo or timezone.utc


def now_in(cfg: dict[str, Any]) -> datetime:
    tz_name = cfg.get("timezone") or "Asia/Shanghai"
    return datetime.now(get_timezone(str(tz_name)))


def format_gap(hours: float | None) -> str:
    if hours is None:
        return "第一次说话"
    if hours < 1:
        minutes = max(1, int(round(hours * 60)))
        return f"{minutes} 分钟"
    if hours < 24:
        return f"{hours:.1f} 小时"
    return f"{hours / 24:.1f} 天"


def mode_label(mode: str) -> str:
    return "晴天" if mode == "sunny" else "锐利"


def _format_notes(notes: list[dict[str, Any]] | None) -> str:
    if not notes:
        return "（暂无）"
    lines = []
    for note in notes[:5]:
        kind = note.get("kind", "笔记")
        content = str(note.get("content", "")).replace("\n", " ")
        if len(content) > 60:
            content = content[:60] + "…"
        lines.append(f"- [{kind}] {content}")
    return "\n".join(lines)


def _format_reminders(reminders: list[dict[str, Any]] | None) -> str:
    if not reminders:
        return "（暂无）"
    lines = []
    for item in reminders[:5]:
        lines.append(f"- {item.get('due_at', '')} {item.get('content', '')}")
    return "\n".join(lines)


def runtime_block(
    cfg: dict[str, Any],
    user_key: str,
    state: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
    reminders: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> str:
    user = cfg["users"][user_key]
    now = now or now_in(cfg)
    state = state or {}
    gap_hours = state.get("gap_hours")

    state_line = (
        f"心情 {float(state.get('mood', 0)):.1f}｜"
        f"精力 {float(state.get('energy', 7)):.1f}｜"
        f"亲密度 {float(state.get('affinity', 50)):.1f}｜"
        f"距上次说话 {format_gap(gap_hours)}"
    )

    return f"""# 当前对话

- 现在：{now.strftime('%Y-%m-%d %H:%M')}（{cfg.get('timezone', 'Asia/Shanghai')}）
- 对话对象：{user['name']}
- 你叫 TA：{user['title']}
- 当前模式：{mode_label(user['mode'])}
- 状态：{state_line}

## 最近笔记

{_format_notes(notes)}

## 未完成提醒

{_format_reminders(reminders)}

状态只用来微调语气，不改变事实和边界。没有工具回执就不要说「已经做了」。
"""


STATIC_INJECTION = """# 运行时注入

每次对话前，把以下内容追加到 system prompt 末尾：

- 当前时间（含时区）
- 对话对象、称呼、模式
- 心情 / 精力 / 亲密度 / 距上次说话
- 最近笔记与未完成提醒

没有这些信息时，不要假装知道对方的状态或记录。"""


def build_system_prompt(
    cfg: dict[str, Any],
    user_key: str | None = None,
    state: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
    reminders: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
    include_examples: bool = True,
    include_static_note: bool = True,
) -> str:
    """Build the full system prompt.

    user_key=None produces the static prompt used by adapters. With a user key,
    the current time / object / state / memory block is appended for a live turn.
    """
    core = build_core_text(cfg, include_examples=include_examples)
    if user_key is None:
        if not include_static_note:
            return core
        return core + "\n\n" + STATIC_INJECTION
    if user_key not in {"owner", "partner"}:
        raise ValueError(f"unknown user key: {user_key}")
    if user_key == "partner" and not partner_enabled(cfg):
        raise ValueError("partner mode is disabled in config")
    return core + "\n\n" + runtime_block(cfg, user_key, state, notes, reminders, now)
