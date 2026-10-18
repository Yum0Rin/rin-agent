#!/usr/bin/env python3
"""Zero-dependency reference runtime for the Rin preset.

It talks to any OpenAI-compatible /chat/completions endpoint, stores notes in
SQLite, keeps a tiny mood/energy/affinity state, and exposes a few slash
commands. The point is to make the preset runnable in one command, not to be a
production chat gateway.

    cp config/rin.example.json config/rin.json
    set RIN_API_KEY=sk-...
    python runtime/rin.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rinlib  # noqa: E402

KINDS = ["日记", "灵感", "碎碎念", "计划", "备忘"]

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "note_add",
            "description": "记录一条笔记。只有调用成功后才能说已经记下了。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": KINDS,
                        "description": "笔记类型，默认备忘",
                    },
                    "content": {"type": "string", "description": "笔记内容"},
                    "visibility": {
                        "type": "string",
                        "enum": ["self", "shared"],
                        "description": "self 只有作者可见；shared 可以共享",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note_search",
            "description": "按关键词检索笔记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note_recent",
            "description": "查看最近的笔记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminder_add",
            "description": "建一条提醒。due_at 必须是 ISO 8601，例如 2026-10-19T15:00:00+08:00。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "due_at": {"type": "string"},
                },
                "required": ["content", "due_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminder_list",
            "description": "查看未完成的提醒。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

HELP = """可用命令：
  /help                 看这份帮助
  /who                  当前对话对象
  /as owner|partner     切换对话对象（会分开记忆和状态）
  /note 内容            记一条备忘
  /diary 内容           记一条日记（默认私密）
  /search 关键词        检索笔记
  /recent [n]           最近 n 条笔记
  /reminders            未完成提醒
  /提醒 明天 15:00 交表  建一条提醒（也支持 ISO 8601）
  /state                心情 / 精力 / 亲密度
  /exit                 退出

也可以直接说话。模型会通过工具记录、检索、建提醒。
"""


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def resolve_db_path(cfg: dict[str, Any], override: str | None) -> Path:
    raw = override or cfg["runtime"]["db_path"]
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            author TEXT NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            visibility TEXT NOT NULL DEFAULT 'self'
        );
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS state (
            user_id TEXT PRIMARY KEY,
            mood REAL NOT NULL DEFAULT 0,
            energy REAL NOT NULL DEFAULT 7,
            affinity REAL NOT NULL DEFAULT 50,
            last_seen TEXT,
            turns INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            due_at TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    db.commit()
    return db


def ensure_state(db: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM state WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO state(user_id, mood, energy, affinity, last_seen, turns) "
            "VALUES(?, ?, ?, ?, ?, 0)",
            (user_id, 0.0, 7.0, 50.0, utc_now_iso()),
        )
        db.commit()
        row = db.execute("SELECT * FROM state WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row)


def decay_state(db: sqlite3.Connection, cfg: dict[str, Any], user_id: str) -> dict[str, Any]:
    state = ensure_state(db, user_id)
    now = datetime.now(timezone.utc)
    last = parse_iso(state.get("last_seen")) or now
    hours = max(0.0, (now - last).total_seconds() / 3600.0)

    mood_cfg = cfg["state"]["mood"]
    energy_cfg = cfg["state"]["energy"]

    mood = clamp(
        float(state["mood"]) - hours * float(mood_cfg["decay_per_hour"]),
        float(mood_cfg["min"]),
        float(mood_cfg["max"]),
    )

    local = now.astimezone(rinlib.get_timezone(cfg.get("timezone", "Asia/Shanghai")))
    if local.hour < 6:
        energy = float(state["energy"]) - hours * float(energy_cfg["night_drain"])
    else:
        energy = float(state["energy"]) + hours * float(energy_cfg["regen_per_hour"])
    energy = clamp(energy, float(energy_cfg["min"]), float(energy_cfg["max"]))

    return {
        **state,
        "mood": mood,
        "energy": energy,
        "affinity": float(state["affinity"]),
        "gap_hours": hours,
    }


def commit_turn(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    user_id: str,
    state: dict[str, Any],
    affinity_delta: float = 0.0,
) -> None:
    energy_cfg = cfg["state"]["energy"]
    affinity_cfg = cfg["state"]["affinity"]
    energy = clamp(
        float(state["energy"]) - float(energy_cfg["turn_cost"]),
        float(energy_cfg["min"]),
        float(energy_cfg["max"]),
    )
    affinity = clamp(
        float(state["affinity"]) + affinity_delta,
        float(affinity_cfg["min"]),
        float(affinity_cfg["max"]),
    )
    db.execute(
        "UPDATE state SET mood = ?, energy = ?, affinity = ?, last_seen = ?, "
        "turns = turns + 1 WHERE user_id = ?",
        (
            float(state["mood"]),
            energy,
            affinity,
            utc_now_iso(),
            user_id,
        ),
    )
    db.commit()


def bump_affinity(db: sqlite3.Connection, cfg: dict[str, Any], user_id: str, amount: float) -> None:
    state = ensure_state(db, user_id)
    affinity_cfg = cfg["state"]["affinity"]
    affinity = clamp(
        float(state["affinity"]) + amount,
        float(affinity_cfg["min"]),
        float(affinity_cfg["max"]),
    )
    db.execute("UPDATE state SET affinity = ? WHERE user_id = ?", (affinity, user_id))
    db.commit()


def add_note(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    author: str,
    kind: str,
    content: str,
    visibility: str | None = None,
) -> int:
    if kind not in KINDS:
        kind = "备忘"
    visibility = visibility or cfg["privacy"]["default_visibility"]
    if visibility not in {"self", "shared"}:
        visibility = "self"
    cur = db.execute(
        "INSERT INTO notes(created_at, author, kind, content, visibility) "
        "VALUES(?, ?, ?, ?, ?)",
        (utc_now_iso(), author, kind, content.strip(), visibility),
    )
    db.commit()
    return int(cur.lastrowid)


def _visibility_clause(cfg: dict[str, Any], user_id: str) -> tuple[str, tuple[Any, ...]]:
    user = cfg["users"].get(user_id, {})
    if user.get("can_read_private"):
        return "1=1", ()
    # 不能读别人的私密笔记，但自己的私密笔记仍然属于自己。
    return "(visibility = 'shared' OR author = ?)", (user_id,)


def search_notes(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    user_id: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    clause, params = _visibility_clause(cfg, user_id)
    rows = db.execute(
        f"SELECT id, created_at, author, kind, content, visibility FROM notes "
        f"WHERE content LIKE ? AND ({clause}) ORDER BY id DESC LIMIT ?",
        (f"%{query}%", *params, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def recent_notes(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    user_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    clause, params = _visibility_clause(cfg, user_id)
    rows = db.execute(
        f"SELECT id, created_at, author, kind, content, visibility FROM notes "
        f"WHERE {clause} ORDER BY id DESC LIMIT ?",
        (*params, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def add_reminder(db: sqlite3.Connection, user_id: str, content: str, due_at: str) -> int:
    cur = db.execute(
        "INSERT INTO reminders(created_at, user_id, content, due_at, done) "
        "VALUES(?, ?, ?, ?, 0)",
        (utc_now_iso(), user_id, content.strip(), due_at),
    )
    db.commit()
    return int(cur.lastrowid)


def list_reminders(
    db: sqlite3.Connection, user_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, content, due_at FROM reminders "
        "WHERE user_id = ? AND done = 0 ORDER BY due_at LIMIT ?",
        (user_id, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def due_reminders(db: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, content, due_at FROM reminders WHERE user_id = ? AND done = 0",
        (user_id,),
    ).fetchall()
    now = datetime.now(timezone.utc)
    due = []
    for row in rows:
        when = parse_iso(row["due_at"])
        if when is not None and when <= now:
            due.append(dict(row))
    return due


def save_interaction(
    db: sqlite3.Connection, chat_id: str, role: str, content: str
) -> None:
    db.execute(
        "INSERT INTO interactions(chat_id, role, content, created_at) VALUES(?, ?, ?, ?)",
        (chat_id, role, content, utc_now_iso()),
    )
    db.commit()


def history(db: sqlite3.Connection, chat_id: str, limit: int) -> list[dict[str, str]]:
    rows = db.execute(
        "SELECT role, content FROM interactions WHERE chat_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (chat_id, int(limit)),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


# ---------------------------------------------------------------------------
# prompt + tools
# ---------------------------------------------------------------------------


def build_turn_system(
    db: sqlite3.Connection, cfg: dict[str, Any], user_id: str
) -> tuple[str, dict[str, Any]]:
    state = decay_state(db, cfg, user_id)
    notes = recent_notes(db, cfg, user_id, limit=5)
    reminders = list_reminders(db, user_id, limit=5)
    prompt = rinlib.build_system_prompt(
        cfg,
        user_key=user_id,
        state=state,
        notes=notes,
        reminders=reminders,
        now=rinlib.now_in(cfg),
    )
    return prompt, state


def execute_tool(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    user_id: str,
    name: str,
    args: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    if name == "note_add":
        content = str(args.get("content", "")).strip()
        if not content:
            return {"ok": False, "error": "content 不能为空"}, 0.0
        kind = str(args.get("kind") or "备忘")
        visibility = str(args.get("visibility") or cfg["privacy"]["default_visibility"])
        note_id = add_note(db, cfg, user_id, kind, content, visibility)
        return {
            "ok": True,
            "id": note_id,
            "kind": kind,
            "visibility": visibility,
            "receipt": f"已记第 {note_id} 条",
        }, float(cfg["state"]["affinity"]["per_note"])

    if name == "note_search":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"ok": False, "error": "query 不能为空"}, 0.0
        limit = int(args.get("limit", 10))
        rows = search_notes(db, cfg, user_id, query, limit=limit)
        return {"ok": True, "count": len(rows), "notes": rows}, 0.0

    if name == "note_recent":
        limit = int(args.get("limit", 5))
        rows = recent_notes(db, cfg, user_id, limit=limit)
        return {"ok": True, "count": len(rows), "notes": rows}, 0.0

    if name == "reminder_add":
        content = str(args.get("content", "")).strip()
        due_at = str(args.get("due_at", "")).strip()
        if not content or not due_at:
            return {"ok": False, "error": "content 和 due_at 都不能为空"}, 0.0
        if parse_iso(due_at) is None:
            return {"ok": False, "error": "due_at 必须是 ISO 8601"}, 0.0
        reminder_id = add_reminder(db, user_id, content, due_at)
        return {
            "ok": True,
            "id": reminder_id,
            "due_at": due_at,
            "receipt": f"提醒已建：{due_at} {content}",
        }, 0.0

    if name == "reminder_list":
        rows = list_reminders(db, user_id)
        return {"ok": True, "count": len(rows), "reminders": rows}, 0.0

    return {"ok": False, "error": f"unknown tool: {name}"}, 0.0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _api_key(cfg: dict[str, Any]) -> str:
    runtime = cfg["runtime"]
    return os.environ.get(str(runtime.get("api_key_env", "RIN_API_KEY")), "") or str(
        runtime.get("api_key", "")
    )


def call_llm(
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    allow_tool_fallback: bool = True,
) -> dict[str, Any]:
    runtime = cfg["runtime"]
    api_key = _api_key(cfg)
    if not api_key:
        raise LLMError(
            f"没有 API key。设置环境变量 {runtime.get('api_key_env', 'RIN_API_KEY')}，"
            "或在 config 的 runtime.api_key 里填。"
        )

    url = str(runtime["base_url"]).rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"

    payload: dict[str, Any] = {
        "model": runtime["model"],
        "messages": messages,
        "temperature": float(runtime.get("temperature", 1.0)),
        "max_tokens": int(runtime.get("max_tokens", 800)),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        if (
            tools
            and allow_tool_fallback
            and exc.code in {400, 404, 422}
            and ("tool" in body.lower() or "function" in body.lower())
        ):
            return call_llm(cfg, messages, tools=None, allow_tool_fallback=False)
        raise LLMError(f"API 返回 {exc.code}：{body}") from exc
    except Exception as exc:  # noqa: BLE001 - surface a readable message
        raise LLMError(f"请求失败：{exc}") from exc


def chat_turn(
    db: sqlite3.Connection,
    cfg: dict[str, Any],
    user_id: str,
    text: str,
) -> str:
    system, state = build_turn_system(db, cfg, user_id)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(history(db, user_id, int(cfg["runtime"]["history_limit"])))
    messages.append({"role": "user", "content": text})

    use_tools = bool(cfg["runtime"].get("use_tools", True))
    affinity_delta = 0.0
    reply: str | None = None

    for _ in range(3):
        data = call_llm(cfg, messages, TOOLS if use_tools else None)
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"API 没有返回 choices：{json.dumps(data, ensure_ascii=False)[:300]}")
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            reply = (message.get("content") or "").strip()
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            try:
                args = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result, delta = execute_tool(db, cfg, user_id, name, args)
            affinity_delta += delta
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    if reply is None:
        reply = "（工具调用轮次太多，先停一下）"
    if not reply:
        reply = "……"

    save_interaction(db, user_id, "user", text)
    save_interaction(db, user_id, "assistant", reply)
    commit_turn(db, cfg, user_id, state, affinity_delta=affinity_delta)
    return reply


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_reminder_arg(
    arg: str, cfg: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Parse `/提醒 明天 15:00 交表` or `/提醒 2030-01-01T15:00:00+08:00 交表`."""
    # ISO 8601 first: <iso> <content>
    first, _, rest = arg.partition(" ")
    if first and rest and "T" in first and parse_iso(first) is not None:
        return first, rest.strip()

    # 今天 / 明天 / 后天 HH:MM content
    match = re.match(r"^(今天|明天|后天)\s*(\d{1,2})[:：](\d{2})\s+(.+)$", arg)
    if match:
        offset = {"今天": 0, "明天": 1, "后天": 2}[match.group(1)]
        hour, minute = int(match.group(2)), int(match.group(3))
        content = match.group(4).strip()
        if hour > 23 or minute > 59 or not content:
            return None, None
        local = rinlib.now_in(cfg)
        target = (local + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return target.isoformat(timespec="seconds"), content

    # YYYY-MM-DD HH:MM content
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2})[:：](\d{2})\s+(.+)$", arg)
    if match:
        hour, minute = int(match.group(2)), int(match.group(3))
        content = match.group(4).strip()
        if hour > 23 or minute > 59 or not content:
            return None, None
        local = rinlib.now_in(cfg)
        target = datetime.fromisoformat(match.group(1)).replace(
            tzinfo=local.tzinfo, hour=hour, minute=minute, second=0, microsecond=0
        )
        return target.isoformat(timespec="seconds"), content

    return None, None


def handle_command(
    db: sqlite3.Connection, cfg: dict[str, Any], user_id: str, line: str
) -> str | None:
    parts = line.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        return HELP
    if command == "/who":
        user = cfg["users"][user_id]
        return f"当前对象：{user['name']}（{rinlib.mode_label(user['mode'])}模式）"
    if command in {"/note", "/记"}:
        if not arg:
            return "记什么？"
        note_id = add_note(db, cfg, user_id, "备忘", arg)
        bump_affinity(db, cfg, user_id, float(cfg["state"]["affinity"]["per_note"]))
        return f"记下了。第 {note_id} 条。"
    if command in {"/diary", "/日记"}:
        if not arg:
            return "写什么？"
        note_id = add_note(db, cfg, user_id, "日记", arg, "self")
        bump_affinity(db, cfg, user_id, float(cfg["state"]["affinity"]["per_note"]))
        return f"记成日记了。第 {note_id} 条，私密。"
    if command in {"/search", "/查"}:
        if not arg:
            return "查什么？"
        rows = search_notes(db, cfg, user_id, arg)
        if not rows:
            return "没查到。"
        return "\n".join(
            f"#{row['id']} [{row['kind']}] {row['content']}" for row in rows
        )
    if command in {"/recent", "/最近"}:
        limit = int(arg) if arg.isdigit() else 5
        rows = recent_notes(db, cfg, user_id, limit=min(limit, 20))
        if not rows:
            return "还没有笔记。"
        return "\n".join(
            f"#{row['id']} [{row['kind']}] {row['content']}" for row in rows
        )
    if command in {"/reminders", "/提醒列表"}:
        rows = list_reminders(db, user_id)
        if not rows:
            return "没有未完成提醒。"
        return "\n".join(f"#{row['id']} {row['due_at']} {row['content']}" for row in rows)
    if command in {"/提醒", "/remind"}:
        if not arg:
            return "用法：/提醒 明天 15:00 交表，或 /提醒 2030-01-01T15:00:00+08:00 交表"
        due_at, content = parse_reminder_arg(arg, cfg)
        if not due_at or not content:
            return "时间没看懂。用「明天 15:00 交表」或 ISO 8601。"
        reminder_id = add_reminder(db, user_id, content, due_at)
        return f"提醒已建。第 {reminder_id} 条：{due_at} {content}"
    if command in {"/state", "/状态"}:
        state = decay_state(db, cfg, user_id)
        return (
            f"心情 {state['mood']:.1f}｜精力 {state['energy']:.1f}｜"
            f"亲密度 {state['affinity']:.1f}｜距上次说话 "
            f"{rinlib.format_gap(state['gap_hours'])}"
        )
    return "不认识这个命令。试试 /help。"


def print_due_reminders(db: sqlite3.Connection, user_id: str) -> None:
    due = due_reminders(db, user_id)
    if due:
        print("到点了：")
        for item in due:
            print(f"  - {item['due_at']} {item['content']}")


def selftest() -> int:
    cfg = rinlib.load_config(rinlib.example_config_path())
    with tempfile.TemporaryDirectory() as tmp:
        db = init_db(Path(tmp) / "selftest.db")
        note_id = add_note(db, cfg, "owner", "备忘", "selftest note")
        assert note_id == 1, note_id
        rows = search_notes(db, cfg, "owner", "selftest")
        assert rows and rows[0]["content"] == "selftest note"
        reminder_id = add_reminder(
            db, "owner", "selftest reminder", "2030-01-01T09:00:00+08:00"
        )
        assert reminder_id == 1
        assert list_reminders(db, "owner")
        prompt, _state = build_turn_system(db, cfg, "owner")
        assert "{{" not in prompt, "unresolved placeholder in prompt"
        assert cfg["users"]["owner"]["name"] in prompt
        db.close()
        print("selftest ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rin reference runtime")
    parser.add_argument("--config", default=str(rinlib.default_config_path()))
    parser.add_argument("--as", dest="as_user", choices=["owner", "partner"], default=None)
    parser.add_argument("--db", default=None, help="override SQLite path")
    parser.add_argument("--print-prompt", action="store_true", help="print static system prompt")
    parser.add_argument("--offline", action="store_true", help="do not call the API")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    cfg = rinlib.load_config(args.config)
    if args.print_prompt:
        print(rinlib.build_system_prompt(cfg))
        return 0

    if args.as_user == "partner" and not rinlib.partner_enabled(cfg):
        print("[rin] config 里没有启用 partner，改用 owner。")
        args.as_user = "owner"
    current = args.as_user or "owner"

    db = init_db(resolve_db_path(cfg, args.db))
    print_due_reminders(db, current)

    if not args.offline and not _api_key(cfg):
        print(
            f"[rin] 没有找到 API key。设置 {cfg['runtime'].get('api_key_env', 'RIN_API_KEY')} "
            "后重新启动；现在可以先用 /note /search /state 这些命令。"
        )

    user = cfg["users"][current]
    print(
        f"Rin · 生活记录员 · v{rinlib.VERSION}\n"
        f"当前对象：{user['name']}（{rinlib.mode_label(user['mode'])}模式）"
        f" · 输入 /help 看命令，/exit 退出"
    )

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"/exit", "/quit"}:
            break

        parts = line.split(maxsplit=1)
        if parts[0].lower() == "/as":
            target = parts[1].strip() if len(parts) > 1 else ""
            if target not in {"owner", "partner"} or (
                target == "partner" and not rinlib.partner_enabled(cfg)
            ):
                print("用法：/as owner 或 /as partner")
                continue
            current = target
            user = cfg["users"][current]
            print(f"现在对 {user['name']} 说话（{rinlib.mode_label(user['mode'])}模式）")
            print_due_reminders(db, current)
            continue

        if line.startswith("/"):
            result = handle_command(db, cfg, current, line)
            if result is not None:
                print(result)
            continue

        if args.offline:
            reply = f"（离线模式）收到：{line}"
            save_interaction(db, current, "user", line)
            save_interaction(db, current, "assistant", reply)
            print(reply)
            continue

        try:
            print(chat_turn(db, cfg, current, line))
        except LLMError as exc:
            print(f"[rin] {exc}")

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
