# 定制指南

## 1. 改称呼和名字

编辑 `config/rin.json`：

```json
{
  "character": { "name": "Rin", "self_style": "本天才" },
  "users": {
    "owner": { "name": "小满", "title": "姐姐", "mode": "sunny" },
    "partner": { "enabled": true, "name": "阿澈", "title": "阿澈", "mode": "sharp" }
  }
}
```

- `title` 是 Rin 对 TA 的称呼。填 `你` 就是直接称呼；填 `老板`、`姐姐`、名字都可以。
- `name` 用在提示词的「对话对象」和群聊点名里。
- 改完重新渲染：

```bash
python tools/render.py --config config/rin.json
```

## 2. 只保留一个人

```json
"partner": { "enabled": false }
```

也可以直接参考 `examples/config.single.json`。

渲染时会自动去掉：

- 锐利模式段落
- `examples.partner.md`
- `build/card.partner.json`

运行时 `/as partner` 也会被拒绝。

## 3. 加第三个人

参考运行时只支持 `owner` / `partner` 两个槽位。要加第三个人，有两条路：

1. **在宿主层按 user_id 切换**：为每个人存一份 `mode` 映射，调用 `rinlib.build_system_prompt` 时传对应的 `user_key`。需要把 `rinlib.py` 里的 `user_key` 校验扩展成动态用户表。
2. **复制一份预设**：给第三个人单独一份 config + 示例池，适合关系差异很大的场景。

不建议把三个人塞进同一份示例池，容易串味。

## 4. 调语气浓度

按影响从大到小：

### 4.1 改示例（最有效）

`persona/examples.owner.md` / `persona/examples.partner.md`。

- 一个场景一条。
- 1–2 句为主。
- 不要写个人信息。
- 想让角色更毒舌，就加「被怼时怎么回」的示例；想更软，就加「对方低落时怎么接」的示例。

### 4.2 改硬规则

`persona/rules.md`。

- 想更短：把「默认 1–3 句」改成「默认 1–2 句」。
- 想少用省略号：把「一条最多一个」改成「尽量不用」。
- 想禁掉更多 AI 味：往「说人话」的禁令列表里加。

### 4.3 改两张脸

`persona/modes.md`。

- 晴天模式的关键词、动作、禁止项。
- 锐利模式的边界：不碰自卑点、身体、家人。
- 切换规则：群聊怎么点名、不确定对象时用哪张脸。

### 4.4 改核心驱动

`persona/identity.md`。

这是改动最大的一层。「想被看见」是整个语气的发动机；换掉它，示例和规则也要跟着重写。

## 5. 换模型

编辑 `config/rin.json` 的 `runtime`：

```json
{
  "runtime": {
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "RIN_API_KEY",
    "temperature": 1.0,
    "max_tokens": 800,
    "use_tools": true
  }
}
```

常见组合：

| 服务 | base_url | model | 备注 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 支持 tools |
| OpenAI | `https://api.openai.com/v1` | `gpt-4.1-mini` | 支持 tools |
| Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | 小模型建议 `use_tools: false` |
| LM Studio | `http://127.0.0.1:1234/v1` | 本地模型名 | 同上 |

## 6. 调状态参数

`config/rin.json` 的 `state`：

```json
{
  "state": {
    "mood": { "min": -5, "max": 5, "decay_per_hour": 0.2 },
    "energy": { "min": 0, "max": 10, "regen_per_hour": 0.3, "turn_cost": 0.1, "night_drain": 0.3 },
    "affinity": { "min": 0, "max": 100, "per_note": 0.5, "per_praise": 1 }
  }
}
```

- 想让状态变化更明显：调大 `decay_per_hour` / `turn_cost` / `per_note`。
- 想让状态更稳定：调小，或把 `min` / `max` 收窄。
- 状态只在运行时注入，不影响静态 `build/system.md`。

## 7. 加 lorebook 条目

编辑 `persona/lorebook.template.json`，加一条：

```json
{
  "id": 13,
  "keys": ["生日", "礼物"],
  "content": "对方提到生日时，先问日期，不要猜；记下来后提醒一次就够，不要反复提。",
  "enabled": true,
  "insertion_order": 140,
  "case_sensitive": false,
  "extensions": {}
}
```

`id` 不要重复；`insertion_order` 越大越靠后注入。

## 8. 翻译成其他语言

1. 复制 `persona/` 为 `persona.en/`。
2. 翻译 `identity.md` / `modes.md` / `rules.md` / `tools.md`。
3. **重写**示例对话，不要机翻；语气示例机翻后基本失效。
4. 改 `config.character.language`，并在 `rinlib.py` 里把 `PERSONA_DIR` 指向新目录（或加一个 `--persona-dir` 参数）。

## 9. 接到自己的消息网关

最小接入步骤：

1. 收到消息，识别发送者 → `owner` / `partner`。
2. 从 SQLite 读该用户的最近历史、最近笔记、提醒、状态。
3. 调 `rinlib.build_system_prompt(cfg, user_key, state, notes, reminders)`。
4. 调你的 LLM，带上 `note_add` / `note_search` / `reminder_add` 等工具。
5. 执行工具，把结果作为 `tool` 消息回灌。
6. 保存用户消息和助手回复，更新状态。

群聊额外规则：

- 只接公共话题和 `shared` 内容。
- 不展开私聊历史、个人档案、情绪细节。
- 两个人都在场时点名，不只叫「你 / 他」。
