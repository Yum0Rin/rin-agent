# opencode 接入

两种用法：项目级 `AGENTS.md`，或独立 subagent。

## 1. 项目级 AGENTS.md

```bash
python tools/render.py --config config/rin.json
cp build/AGENTS.md /path/to/your-project/AGENTS.md
```

这会让整个项目的 agent 都带上 Rin 的人设。适合「这个项目就是 Rin 的运行时」的情况。

## 2. 作为 subagent（推荐）

`tools/render.py` 会直接生成一个可用的 opencode agent 文件：

```bash
cp build/opencode-agent.md ~/.config/opencode/agent/rin.md
```

生成的文件长这样：

```markdown
---
description: Rin · 生活记录员（人设、记忆边界、语气规则）
mode: subagent
tools:
  write: true
  edit: true
  bash: true
---

（完整的 Rin system prompt）
```

要点：

- `mode: subagent` 才能被 `task` 调用；`primary` 只能 Tab 切换。
- `description` 写清楚什么时候该用它。
- `model` 按你的 opencode 配置填；没有特别要求就用便宜的小模型。
- 如果不想让它改代码，把 `write` / `edit` / `bash` 设为 `false`。

然后：

```text
@rin 帮我记一下：明天下午三点交表
```

## 3. 状态注入

opencode 本身没有「心情 / 精力 / 亲密度」状态。两种处理：

### 方案 A：不要状态

直接用 `build/AGENTS.md`。人设仍然成立，只是少了「今天不太一样」的微调。

### 方案 B：自己注入

在调用前跑一个小脚本，把下面这段拼到 prompt 末尾：

```text
# 当前状态

心情 -0.4｜精力 6.8｜亲密度 50.5｜距上次说话 2.3 小时
```

状态可以从 `runtime/rin.py` 的 SQLite 读，也可以自己维护一个 JSON。

## 4. 工具映射

opencode 的工具名和参考运行时不同。两种做法：

- **保留参考工具名**：在 opencode 里写一个 MCP / 插件，暴露 `note_add` / `note_search` / `reminder_add`。
- **改写 `persona/tools.md`**：把工具名换成 opencode 实际提供的（如 `write` / `read` / `bash`），并保留「执行 → 回执 → 只回执一句」的结构。

不要让人设里出现「我已经记好了」但实际没有工具调用。

## 5. 注意

- `AGENTS.md` 会进入每次上下文，太长会挤占 token；`build/AGENTS.md` 约 3–4k 字，按需精简。
- 不要把 `config/rin.json`、`data/` 提交到项目仓库。
- 如果项目里已经有 `AGENTS.md`，把 Rin 的段落追加进去，不要覆盖原文件。
