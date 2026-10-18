# SillyTavern 接入

## 1. 生成角色卡和世界书

```bash
python tools/render.py --config config/rin.json
```

产物：

- `build/card.owner.json`：默认对象（晴天模式）。
- `build/card.partner.json`：第二个人（锐利模式，启用 partner 时才生成）。
- `build/lorebook.json`：世界书。

## 2. 导入角色卡

1. 打开 SillyTavern。
2. 角色面板 → 导入角色 → 选择 `card.owner.json`。
3. 如果也想用锐利模式，再导入 `card.partner.json` 作为另一个角色。

## 3. 导入世界书

1. 世界书面板 → 导入 → 选择 `lorebook.json`。
2. 在角色设置里把世界书绑定到 Rin。

## 4. 用户设定

角色卡里的名字是**渲染后的字面量**（例如「小满」「阿澈」），不是 `{{user}}` 宏。原因：两张脸需要区分具体对象，宏无法表达「对 A 用晴天、对 B 用锐利」。

所以要换名字，改 `config/rin.json` 后重新渲染并重新导入，而不是在 SillyTavern 里改 persona 名。

如果你只用一张脸、不介意统一用 `{{user}}`，可以手动把卡片里的名字替换成 `{{user}}`。

## 5. 状态注入

SillyTavern 不会自动算心情 / 精力 / 亲密度。`post_history_instructions` 里有一行默认值：

```text
【当前状态】心情 0｜精力 7｜亲密度 50｜距上次说话 未知
```

三种处理：

- **不管**：保留默认值，角色仍然成立。
- **手动改**：在角色设置里改这一行。
- **用扩展 / STscript**：接一个外部脚本算状态，再写回。

## 6. 工具

SillyTavern 原生不执行我们的 `note_add` / `reminder_add`。两种做法：

- 只用人设，不承诺「已经记了」；需要记录时让用户自己复制。
- 通过函数调用扩展 / 代理接入工具，保持「执行 → 回执 → 只回执一句」的结构。

## 7. 常见问题

- **角色说话太长**：检查是否启用了「快速回复」或示例被截断；`persona/rules.md` 的 1–3 句规则要完整带进去。
- **总是用「行，」开场**：这是示例污染；删掉示例里连续以「行，」开头的条目。
- **两张脸串味**：确认导入的是对应角色卡，且世界书没有把 partner 示例注入 owner 对话。
