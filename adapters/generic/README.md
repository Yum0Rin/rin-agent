# 通用接入 · system prompt

适用于任何支持 system message 的 chat API。

## 1. 生成

```bash
python tools/render.py --config config/rin.json
```

产物：

- `build/system.md`：静态 system prompt。
- `build/lorebook.json`：可选的世界书 / 关键词条目。
- `build/card.*.json`：可选的角色卡。

## 2. 最小调用

```python
import json
import os
from pathlib import Path
from openai import OpenAI

system = Path("build/system.md").read_text(encoding="utf-8")

client = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=os.environ["RIN_API_KEY"],
)

messages = [
    {"role": "system", "content": system},
    {"role": "user", "content": "今天有点累"},
]

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    temperature=1.0,
    max_tokens=800,
)
print(resp.choices[0].message.content)
```

## 3. 每轮注入状态（推荐）

静态 prompt 末尾有一段「运行时注入」说明。真正跑的时候，把下面这块拼到 system prompt 后面：

```text
# 当前对话

- 现在：2026-10-18 21:03（Asia/Shanghai）
- 对话对象：小满
- 你叫 TA：姐姐
- 当前模式：晴天
- 状态：心情 -0.4｜精力 6.8｜亲密度 50.5｜距上次说话 2.3 小时

## 最近笔记

- [备忘] 今天把拖了三周的事做完了
- [计划] 周末去看海

## 未完成提醒

- 2026-10-19T15:00:00+08:00 交表
```

状态只微调语气，不改变事实和边界。没有这些信息时，不要假装知道。

## 4. 工具（可选）

如果宿主支持 function calling，暴露这 5 个工具：

```json
[
  {"name": "note_add", "arguments": {"kind": "备忘", "content": "...", "visibility": "self"}},
  {"name": "note_search", "arguments": {"query": "...", "limit": 10}},
  {"name": "note_recent", "arguments": {"limit": 5}},
  {"name": "reminder_add", "arguments": {"content": "...", "due_at": "2026-10-19T15:00:00+08:00"}},
  {"name": "reminder_list", "arguments": {}}
]
```

执行后把结果作为 `tool` 消息回灌。人设规定：只有回执里出现「已记 / 已排 / 已建」，才能说已经做了。

## 5. 没有工具时

按 `persona/tools.md` 的降级规则：

- 记录类：说「我这边现在没接记录工具，先记在对话里」。
- 日程 / 提醒：给具体时间，让对方自己确认。
- 查询类：看不到就说看不到，不编。

## 6. 常见问题

- **回复太长**：检查是不是只用了 `build/system.md`，没有把 `persona/rules.md` 的「默认 1–3 句」带进去。
- **语气变成客服**：把 `temperature` 调到 1.0 左右；检查示例是否被截断。
- **一直说「已经记了」**：没有工具回执，模型在编。加工具，或在 system prompt 末尾强调「没有回执不许说已做」。
- **私密内容串人**：检查宿主是不是把同一个 system prompt / 历史用给了所有用户；每个用户要单独组装。
