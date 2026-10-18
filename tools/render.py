#!/usr/bin/env python3
"""Render the Rin preset into concrete, copy-pasteable artifacts.

Usage:
    python tools/render.py --config config/rin.json --out build
    python tools/render.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rinlib  # noqa: E402


def build_lorebook(cfg: dict) -> dict:
    raw = (rinlib.PERSONA_DIR / "lorebook.template.json").read_text(encoding="utf-8")
    rendered = rinlib.render_text(raw, rinlib.mapping(cfg))
    return json.loads(rendered)


def _card_examples(cfg: dict, mode: str) -> str:
    # 两张脸的示例池必须分开，避免「姐姐一叫我就到」串到锐利模式。
    names = ["examples.partner.md"] if mode == "partner" else ["examples.owner.md"]
    text = "\n\n".join(rinlib.read_fragment(name) for name in names)
    return rinlib.render_text(text, rinlib.mapping(cfg))


def build_card(cfg: dict, mode: str) -> dict:
    raw = (rinlib.PERSONA_DIR / "card.template.json").read_text(encoding="utf-8")
    card = json.loads(rinlib.render_text(raw, rinlib.mapping(cfg)))
    data = card["data"]

    data["system_prompt"] = rinlib.build_system_prompt(
        cfg, include_examples=False, include_static_note=False
    )
    data["mes_example"] = _card_examples(cfg, mode)
    data["character_book"] = build_lorebook(cfg)
    data["post_history_instructions"] = (
        "【当前状态】心情 0｜精力 7｜亲密度 50｜距上次说话 未知\n"
        "（宿主支持状态注入时，把这一行替换成实时值；不支持就保留默认值。"
        "状态只微调语气，不改变事实和边界。）"
    )
    data["extensions"].setdefault("rin/modes", {})
    data["extensions"]["rin/modes"]["default"] = mode

    if mode == "partner":
        data["description"] += (
            "\n\n这个角色卡默认面向第二个人：温柔毒舌，不撒娇，不索取关注。"
        )
        data["system_prompt"] += (
            f"\n\n# 当前预设\n\n本卡片默认按锐利模式运行，对象是"
            f" {cfg['users']['partner']['name']}。"
        )
    else:
        data["system_prompt"] += (
            f"\n\n# 当前预设\n\n本卡片默认按晴天模式运行，对象是"
            f" {cfg['users']['owner']['name']}。"
        )

    return card


def build_artifacts(cfg: dict) -> dict[str, str]:
    system = rinlib.build_system_prompt(cfg)
    agents = (
        "# AGENTS.md · Rin\n\n"
        "> 由 rin-agent 的 tools/render.py 生成。改 persona/*.md 后重新渲染。\n\n"
        + system
        + "\n\n## 使用说明\n\n"
        "- 把本文件放到项目根目录（或 ~/.config/opencode/AGENTS.md 的引用位置）。\n"
        "- 需要实时状态时，在每轮对话前追加当前时间、对象、心情/精力/亲密度、"
        "最近笔记与提醒；没有这些信息就不要假装知道。\n"
        "- 工具名以宿主实际提供为准；没有工具时按「没有工具时」的规则降级。\n"
    )

    opencode_agent = (
        "---\n"
        "description: Rin · 生活记录员（人设、记忆边界、语气规则）\n"
        "mode: subagent\n"
        "tools:\n"
        "  write: true\n"
        "  edit: true\n"
        "  bash: true\n"
        "---\n\n"
        + system
        + "\n"
    )

    artifacts = {
        "system.md": system + "\n",
        "AGENTS.md": agents,
        "opencode-agent.md": opencode_agent,
        "lorebook.json": json.dumps(build_lorebook(cfg), ensure_ascii=False, indent=2) + "\n",
        "card.owner.json": json.dumps(build_card(cfg, "owner"), ensure_ascii=False, indent=2) + "\n",
    }
    if rinlib.partner_enabled(cfg):
        artifacts["card.partner.json"] = (
            json.dumps(build_card(cfg, "partner"), ensure_ascii=False, indent=2) + "\n"
        )

    manifest = {
        "preset": "rin-agent",
        "version": rinlib.VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "character": cfg["character"]["name"],
        "owner": cfg["users"]["owner"]["name"],
        "partner_enabled": rinlib.partner_enabled(cfg),
        "files": sorted(artifacts),
    }
    artifacts["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return artifacts


def check_artifacts(artifacts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for name, content in artifacts.items():
        if "{{" in content or "}}" in content:
            problems.append(f"{name}: 还有未替换的占位符")
    if not artifacts.get("card.owner.json"):
        problems.append("card.owner.json 为空")
    else:
        card = json.loads(artifacts["card.owner.json"])
        if card.get("spec") != "chara_card_v2":
            problems.append("card.owner.json: spec 不是 chara_card_v2")
        if not card.get("data", {}).get("system_prompt"):
            problems.append("card.owner.json: system_prompt 为空")
    lore = json.loads(artifacts.get("lorebook.json", "{}"))
    if not lore.get("entries"):
        problems.append("lorebook.json: 没有 entries")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Rin agent preset")
    parser.add_argument("--config", default=str(ROOT / "config" / "rin.json"))
    parser.add_argument("--out", default=str(ROOT / "build"))
    parser.add_argument("--check", action="store_true", help="validate without writing")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    cfg = rinlib.load_config(args.config)
    artifacts = build_artifacts(cfg)
    problems = check_artifacts(artifacts)
    if problems:
        for problem in problems:
            print(f"[rin] {problem}", file=sys.stderr)
        return 1

    if args.check:
        if not args.quiet:
            print(f"[rin] check ok · {len(artifacts)} artifacts · v{rinlib.VERSION}")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (out / name).write_text(content, encoding="utf-8", newline="\n")

    if not args.quiet:
        print(f"[rin] rendered {len(artifacts)} files to {out}")
        for name in sorted(artifacts):
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
