# Claude Code 接入

## 1. 生成并放置

```bash
python tools/render.py --config config/rin.json
cp build/AGENTS.md /path/to/your-project/CLAUDE.md
```

或者做成全局人格：

```bash
mkdir -p ~/.claude
cp build/AGENTS.md ~/.claude/CLAUDE.md
```

> 全局 `~/.claude/CLAUDE.md` 会影响你所有的 Claude Code 项目。只想给一个项目用，就放项目根目录。

## 2. 说明

- Claude Code 没有内置的「心情 / 精力 / 亲密度」状态；静态 prompt 仍然可用，只是少了状态微调。
- 如果要在每次会话前注入状态，可以用 `SessionStart` hook 往 context 里加一段：

```text
# 当前状态

心情 0.0｜精力 7.0｜亲密度 50.0｜距上次说话 第一次
```

- Claude Code 的工具名（Read / Write / Bash / TodoWrite 等）和参考运行时不同。把 `persona/tools.md` 里的工具名换成实际可用的，或者保留「没有回执不许说已做」的规则。
- 建议把 `CLAUDE.md` 控制在 4k 字以内；太长会占用上下文。可以删掉示例里不常用的场景，只留高频的 8–10 条。

## 3. 只作为 subagent

Claude Code 支持通过 `.claude/agents/*.md` 定义子 agent（frontmatter + 说明）。把 `build/AGENTS.md` 的正文放进去，在 frontmatter 里写清楚 `name` / `description` / `tools`。具体字段以你当前 Claude Code 版本的文档为准。
