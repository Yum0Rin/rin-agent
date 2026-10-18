# Changelog

## v1.0.0 · 2026-10-18

首个公开版本。

### 新增

- 泛化后的 Rin 人设：`persona/identity.md` / `modes.md` / `rules.md` / `tools.md`。
- 晴天 / 锐利两张脸，按对象切换；第二个人可关闭。
- 两套语气示例：`examples.owner.md` / `examples.partner.md`。
- Character Card V2 模板与 12 条 lorebook。
- `rinlib.py`：配置加载、模板渲染、状态与记忆注入。
- `tools/render.py`：生成 `build/system.md` / `AGENTS.md` / 角色卡 / 世界书。
- `runtime/rin.py`：零依赖 CLI，SQLite + OpenAI 兼容 API + 5 个工具。
- 适配器说明：generic / opencode / Claude Code / SillyTavern / 企业微信。
- 文档：设计说明、定制指南、隐私边界、FAQ。
- 10 个单元测试 + GitHub Actions。

### 设计

- 核心驱动从「被需要」改为「想被看见」，保留晴天模式的中二与邀功。
- 名字、称呼、关系全部配置化；示例重写为通用场景，不含个人信息。
- 工具回执机制：执行 → 回执 → 只回执一句。
- 私密默认、显式共享、按人隔离。
