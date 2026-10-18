# Rin · 开箱即用的生活记录员 agent 预设

> 一个会记事、会翻旧记录、会读图、会提醒，也会嘴硬和邀功的聊天人格。
> 不是客服，不是心理咨询师，也不是「无所不能的 AI 助手」。

![version](https://img.shields.io/badge/version-1.0.0-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB)

[快速开始](#快速开始) · [它是什么](#它是什么) · [人设设计](#人设设计) · [配置](#配置) · [适配器](#适配器) · [隐私与边界](#隐私与边界)

---

## 它是什么

Rin 是一套**可直接落地的 agent 预设**，不是一段「你是一个温柔可爱的助手」的提示词。

它包含：

- **人设**（`persona/`）：身份、两张脸、说话硬规则、语气示例、lorebook。
- **状态机**：心情 / 精力 / 亲密度，随时间代谢，按轮次变化。
- **记忆边界**：私密默认、显式共享、按人隔离。
- **零依赖参考运行时**（`runtime/rin.py`）：SQLite + 任意 OpenAI 兼容 API，带 `/记` `/查` `/提醒` 等命令和 tool calling。
- **多端适配**：通用 system prompt、opencode、Claude Code、SillyTavern、企业微信。
- **渲染工具**（`tools/render.py`）：把配置 + 模板变成可直接用的 `system.md` / 角色卡 / lorebook。

它解决的不是「让 AI 更像人」这种玄学，而是三个具体问题：

1. **人设写了没人读**：形容词堆砌无效，示例对话 + 数值状态才有效。
2. **聊两句就变客服**：默认会给建议、会升华、会写小作文；预设用硬规则把这条路堵死。
3. **记得越多越危险**：私密内容、两个人的关系、群聊场合，必须有明确的读写边界。

## 它不是什么

- 不是一个完整的聊天平台。运行时只是参考实现，生产环境请接你自己的消息网关。
- 不是心理医生、律师、理财顾问。遇到严重问题，它会建议找真人。
- 不包含任何真实聊天记录、密钥或个人数据。仓库里的名字都是示例。

---

## 快速开始

### 方式一：先跑起来（推荐）

需要 **Python 3.10+**，不需要安装任何第三方包。

```bash
git clone https://github.com/Yum0Rin/rin-agent.git
cd rin-agent

cp config/rin.example.json config/rin.json
# 编辑 config/rin.json：改称呼、填 base_url / model

export RIN_API_KEY="sk-..."          # Windows PowerShell: $env:RIN_API_KEY="sk-..."
python runtime/rin.py
```

首次启动会创建 `data/rin.db`。试试：

```text
/记 今天终于把拖了三周的事做完了
/查 三周
/状态
/提醒 明天 15:00 交表
```

自然语言也可以：

```text
今天有点累，帮我记一下，顺便提醒我十点前洗澡
```

> 没有 API key 也能先玩命令：`python runtime/rin.py --offline`。

### 方式二：当成 system prompt 用

```bash
python tools/render.py --config config/rin.json
# 生成 build/system.md
```

把 `build/system.md` 贴到任何 agent / chatbot 的 system prompt 里。每轮对话前，按文件末尾的说明追加当前时间、对象、状态和最近笔记。

### 方式三：导入角色卡

```bash
python tools/render.py --config config/rin.json
```

- `build/card.owner.json`：默认对象（晴天模式）的 Character Card V2。
- `build/card.partner.json`：第二个人（锐利模式）的角色卡，`users.partner.enabled=true` 时才生成。
- `build/lorebook.json`：配套世界书，可单独导入 SillyTavern 等前端。

### 方式四：接到已有的 agent 工作台

| 工作台 | 用哪个文件 | 说明 |
|---|---|---|
| 任意 OpenAI 兼容 API | `build/system.md` | 作为 system message |
| opencode | `build/opencode-agent.md` | 复制到 `~/.config/opencode/agent/rin.md` 作为 subagent |
| Claude Code | `build/AGENTS.md` → `CLAUDE.md` | 放到项目根目录或 `~/.claude/` |
| SillyTavern | `build/card.owner.json` + `build/lorebook.json` | 角色卡 + 世界书 |
| 企业微信 / 其他 IM | `adapters/wecom/README.md` | 只给接口设计，不含任何私有实现 |

---

## 人设设计

### 一句话

Rin 是一个**想被看见的生活记录员**。她抢着做事、吹自己「本天才」，都是在给自己壮胆；被看穿会破功，然后赶紧找补。

这个「核心驱动」比十个形容词都有用。它让角色在「帮忙」之外有自己的小算盘，也让语气有落点。

### 两张脸

| 模式 | 对谁 | 关键词 | 禁止 |
|---|---|---|---|
| **晴天** `sunny` | 默认对象 / owner | 阳光、话多、爱表现、中二、嘴硬式关心 | 写成小作文、装人生导师 |
| **锐利** `sharp` | 第二个人 / partner（可选） | 温柔毒舌、大姐姐、先接住再补刀 | 中二、自称「本天才」、宇宙级比喻 |

两张脸是同一个 Rin，按对话对象切换。只配置一个人时，锐利模式不会启用。

### 示例 > 形容词

`persona/examples.owner.md` 和 `persona/examples.partner.md` 是预设里最重要的文件。

模型不会因为「她很温柔」就变温柔，但会因为看了 14 组「对方说 X，她回 Y」而学会节奏。改人设时，优先改示例，其次改规则，最后才改形容词。

### 状态 > 描述

`mood / energy / affinity` 不是装饰：

- 心情每小时向 0 回落。
- 精力白天回复、深夜倒扣，每轮消耗。
- 亲密度随记事和被夸增长。
- 距离上次说话超过 12 小时，第一句可以带一点「你终于来了」的怨气。

状态只微调语气，不改变事实和边界。

### 反 AI 味硬规则

`persona/rules.md` 里有一组明确的禁令：

- 不写「你已经很努力了」「允许自己」「照顾好自己」这类心理咨询模板。
- 不写「首先 / 其次 / 总之 / 换句话说」。
- 不把一件小事总结成人生道理。
- 不每条都给建议；很多时候接一句、问一句、损一句就够了。
- 不用 Markdown、不加粗、不列小标题。
- 默认 1–3 句，清单最多 8 行。

这些规则不是审美偏好，是为了让模型在长上下文里**不要滑回默认的助手腔**。

### 记忆边界

- 日记、碎碎念默认 `self`，只有作者可见。
- 只有显式 `shared` 的内容才进共享视图。
- 不把一个人的私密内容转述给另一个人。
- 群聊是公共场合：只接公共话题和已经共享的安排。
- 没有工具回执时，不说「已经记了 / 已经排了」。

---

## 配置

`config/rin.example.json` 是一份完整示例。复制成 `config/rin.json` 后修改。

| 字段 | 默认 | 作用 |
|---|---|---|
| `timezone` | `Asia/Shanghai` | 时区，用于「现在几点」和状态代谢 |
| `character.name` | `Rin` | 角色名 |
| `character.self_style` | `本天才` | 晴天模式里的自称 |
| `users.owner.name` | `小满` | 默认对象的名字（示例） |
| `users.owner.title` | `姐姐` | Rin 对 TA 的称呼；改成 `你` / `老板` / 名字都行 |
| `users.owner.mode` | `sunny` | `sunny` 或 `sharp` |
| `users.owner.can_read_private` | `true` | 是否能读私密笔记 |
| `users.partner.enabled` | `true` | 是否启用第二个人 |
| `users.partner.name` | `阿澈` | 第二个人的名字（示例） |
| `users.partner.title` | `阿澈` | 对 TA 的称呼 |
| `users.partner.mode` | `sharp` | 第二个人默认用锐利模式 |
| `relationship.label` | `一起生活的人` | 关系描述，只影响提示词 |
| `privacy.default_visibility` | `self` | 新笔记默认可见性 |
| `runtime.base_url` | `https://api.deepseek.com/v1` | OpenAI 兼容 API |
| `runtime.model` | `deepseek-chat` | 模型名 |
| `runtime.api_key_env` | `RIN_API_KEY` | 存放 key 的环境变量 |
| `runtime.use_tools` | `true` | 模型不支持 tools 时设为 `false` |
| `runtime.db_path` | `data/rin.db` | SQLite 路径 |

### 换成本地模型

以 Ollama 为例：

```json
{
  "runtime": {
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "qwen2.5:7b",
    "api_key_env": "RIN_API_KEY",
    "api_key": "ollama",
    "use_tools": false
  }
}
```

小模型不一定稳定支持 tool calling；关掉 tools 后，用 `/note` `/search` 这些确定性命令，自然语言记录会降级成「先记在对话里」。

### 只保留一个人

```json
"partner": {
  "enabled": false
}
```

渲染时会自动去掉锐利模式、partner 示例和 partner 角色卡。

### 调整语气浓度

按影响从大到小：

1. `persona/examples.*.md`：改对话示例，最有效。
2. `persona/rules.md`：改硬规则，最直接。
3. `persona/modes.md`：改两张脸的行为倾向。
4. `persona/identity.md`：改身份和核心驱动，改动最大，慎动。

改完重新渲染：

```bash
python tools/render.py --config config/rin.json --check
python tools/render.py --config config/rin.json
```

---

## 目录

```text
rin-agent/
├─ persona/                 # 人设真源
│  ├─ identity.md           # 身份 + 核心驱动
│  ├─ modes.md              # 晴天 / 锐利两张脸
│  ├─ rules.md              # 说话硬规则（反 AI 味）
│  ├─ tools.md              # 工具契约与降级规则
│  ├─ examples.owner.md     # 晴天模式示例
│  ├─ examples.partner.md   # 锐利模式示例
│  ├─ lorebook.template.json
│  ├─ card.template.json    # Character Card V2 模板
│  └─ design.md             # 人设设计说明（给人读的）
├─ config/
│  ├─ rin.example.json
│  └─ rin.schema.json
├─ runtime/
│  └─ rin.py                # 零依赖参考运行时
├─ tools/
│  └─ render.py             # 渲染 system / card / lorebook
├─ adapters/                # 各工作台接入说明
├─ docs/                    # 设计、定制、隐私、FAQ
├─ tests/
├─ rinlib.py                # 模板渲染共享逻辑
└─ README.md
```

运行期生成、已被 `.gitignore` 忽略的目录：

- `build/`：渲染产物。
- `data/`：SQLite 数据库。
- `config/rin.json`：你的私人配置。

---

## 工具契约

参考运行时会向模型暴露 5 个工具：

| 工具 | 参数 | 作用 |
|---|---|---|
| `note_add` | `kind`, `content`, `visibility` | 记一条笔记 |
| `note_search` | `query`, `limit` | 按关键词检索 |
| `note_recent` | `limit` | 最近笔记 |
| `reminder_add` | `content`, `due_at` | 建提醒（ISO 8601） |
| `reminder_list` | — | 未完成提醒 |

工具执行后，运行时会回传一条 JSON 回执。人设规定：**只有回执里出现「已记 / 已排 / 已建」，才能说已经做了**。没有工具时，按 `persona/tools.md` 的降级规则说话。

把预设接到你自己的 agent 时，可以换工具名，但要保留「执行 → 回执 → 只回执一句」的结构。这是防止模型编造「已经帮你记好了」的关键。

---

## 适配器

| 目录 | 内容 |
|---|---|
| `adapters/generic/` | 通用 system prompt 接入，含 messages 示例 |
| `adapters/opencode/` | opencode 的 AGENTS.md / subagent 接法 |
| `adapters/claude-code/` | Claude Code 的 CLAUDE.md 接法 |
| `adapters/sillytavern/` | 角色卡 + 世界书导入步骤 |
| `adapters/wecom/` | 企业微信机器人的接口设计（不含私有实现） |

详细步骤见各目录的 README。

---

## 隐私与边界

- **本地优先**：笔记、状态、对话历史都在本机 SQLite；只有你主动发给 LLM API 的内容会离开本机。
- **密钥不进仓库**：`config/rin.json`、`data/`、`.env` 都在 `.gitignore` 里。优先用环境变量。
- **私密默认**：日记、碎碎念默认 `self`；共享要显式标记。
- **按人隔离**：不同对象的笔记、状态、历史分开存；不转述私密内容。
- **群聊是公共场合**：不展开私聊历史、个人档案、情绪细节。
- **安全**：出现自伤 / 自杀表达时，人设要求立刻停止玩笑，确认安全并鼓励联系身边人或专业帮助。它不是危机干预系统，不能替代真人。
- **不做诊断**：不提供医疗、法律、投资建议。

更多见 [docs/privacy.md](docs/privacy.md)。

---

## FAQ

**为什么默认叫「姐姐」？**
这是示例配置，不是硬编码。改 `users.owner.title` 即可；填 `你` 就是直接称呼。

**能商用吗？**
MIT，可以。但人设里的语气和安全规则请按你的场景再审一遍。

**支持英文吗？**
人设目前是中文。`persona/` 是纯 Markdown，翻译后把 `config.character.language` 改掉即可；示例对话需要重写，不要机翻。

**记忆用向量库吗？**
参考运行时只用 SQLite `LIKE`，够个人规模。要上向量检索，替换 `search_notes` / `recent_notes` 即可，人设层不用动。

**为什么不用 LangChain / LlamaIndex？**
这个仓库的目标是「一个文件跑起来」和「人设可读可改」。依赖越少，越容易移植到别人的 agent 里。

**它会替代心理医生吗？**
不会。它只在日常聊天里接住情绪；严重问题会建议找真人。

---

## 设计来源

- [Character Card V2 spec](https://github.com/malfoyslastname/character-card-spec-v2)：角色卡字段规范。
- [SillyTavern](https://github.com/SillyTavern/SillyTavern)：角色卡 / 世界书生态。
- [OpenHer](https://github.com/kellyvv/OpenHer)：人格靠状态涌现，不靠形容词堆砌。
- [mem0](https://github.com/mem0ai/mem0) / [Letta](https://github.com/letta-ai/letta)：分层记忆与上下文管理思路。
- 原始 Rin 是一个私人企业微信生活记录员项目；本仓库只提取了可复用的**人设结构、状态机、记忆边界和工具契约**，不含任何私人数据或私有接入代码。

## License

MIT · 见 [LICENSE](LICENSE)。
