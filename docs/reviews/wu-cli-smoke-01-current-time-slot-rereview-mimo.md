# Re-Review: current_time context slot — F02/F03 闭环验证

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-mimo.md`
- Review date: 2026-07-07
- Review focus: F02/F03 闭环验证、新增测试一致性、整体 intent 对齐

## Review Context

上一轮 review 产出：
- `docs/reviews/wu-cli-smoke-01-current-time-slot-review-mimo.md` — Pass
- `docs/reviews/wu-cli-smoke-01-current-time-slot-review-ds.md` — Pass（含 F01/F02/F03）

Codex fix 后额外修改：
- `dayu/config/README.md` — F02 文档补充
- `tests/runtime/test_scene_assets_migration.py` — F03 测试补充
- `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md` — fix 记录

用户最终 intent：
- prompt / interactive / wechat 同时使用 `get_current_time` 工具和 `{{current_time}}`
- 除 compact 外，其它所有 scene 都使用 `{{current_time}}`
- 只有 prompt / interactive / wechat 暴露 `get_current_time` 工具

## Findings

未发现实质性问题。

### 逐项验证

#### F02 闭环：✅ Pass

`dayu/config/README.md` 第 216 行：

> `prompt` 是单轮问答 scene，不暴露 download / preprocess / upload 这类长事务工具；需要模型在对话中触发 download / preprocess 时，使用 `interactive` 或 `wechat` scene。

该句同时覆盖两个要求：
1. prompt 是单轮问答 scene，不暴露长事务工具 — 第一个分句明确说明。
2. interactive / wechat 用于对话中触发长事务 — 第二个分句明确说明。

第 218 行补充说明 `get_current_time` 工具仅通过 `"utils"` tag 选择，且 `prompt` / `interactive` / `wechat` 三个 manifest 声明了该 tag，其它 scene 不会意外选中。

文档表述自足、语义清晰，无需模型理解内部实现即可判断工具暴露边界。F02 闭环。

#### F03 闭环：✅ Pass

`tests/runtime/test_scene_assets_migration.py` 第 383-391 行：

```python
def test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot() -> None:
    """conversation memory smoke scene 不得声明或渲染默认研究主体 slot。"""

    for scene in _CONVERSATION_MEMORY_SMOKE_SCENES:
        manifest = _load_manifest(_manifest_root() / f"{scene}.json")
        scene_content = _scene_fragment_path(manifest).read_text(encoding="utf-8")

        assert not _manifest_declares_context_slot(manifest, _FINS_DEFAULT_SUBJECT_SLOT), scene
        assert _FINS_DEFAULT_SUBJECT_PLACEHOLDER not in scene_content, scene
```

- 第 390 行：断言 manifest 不声明 `fins_default_subject` context slot。
- 第 391 行：断言 scene md 不包含 `{{fins_default_subject}}` 占位符。
- 断言失败时 `, scene` 参数会输出具体哪个 scene 违反约束。

覆盖范围：`_CONVERSATION_MEMORY_SMOKE_SCENES`（第 78-83 行）包含 `smoke_host_public_conversation_memory` 和 `smoke_host_public_conversation_memory_scenarios` 两个 scene。

F03 闭环。

#### 新增测试一致性：✅ Pass

新增测试 `test_conversation_memory_smoke_scenes_do_not_use_default_subject_slot` 与已有测试模式完全一致：

- 使用模块级 `_` 前缀私有 helper（`_load_manifest`、`_manifest_declares_context_slot`、`_scene_fragment_path`）。
- 常量使用 `typing.Final`（`_FINS_DEFAULT_SUBJECT_SLOT`、`_FINS_DEFAULT_SUBJECT_PLACEHOLDER`、`_CONVERSATION_MEMORY_SMOKE_SCENES`）。
- 断言使用 bare `assert` + trailing message，与文件中其它测试（如 `test_current_time_slot_is_rendered_by_non_compact_scenes`）风格一致。
- 无 pytest fixtures、无 mock、无过度耦合。
- 直接按 scene 名加载 manifest，路径解析复用 `_manifest_root()` / `_scene_fragment_path()`，不引入脆弱路径。

#### 整体 intent 对齐：✅ Pass

上一轮 MIMO review 已验证的七项 invariant 仍然成立：
1. 所有非 compact scene manifest 声明 required `current_time`；所有 scene md 渲染 `{{current_time}}`；prompt/interactive/wechat 暴露 `get_current_time` 工具。
2. 非 prompt/interactive/wechat scene 不暴露 `get_current_time`。
3. `current_time` 放置在 scene contract 之后、`fins_default_subject` 之前。
4. 所有 `ScenePrepare` 调用点提供 `current_time`。
5. `fins_awaiting_runtime` 修复正确。
6. README 变更符合触发规则。
7. 测试覆盖充分。

用户 intent（prompt/interactive/wechat 同时使用工具和 slot；除 compact 外所有 scene 使用 slot；只有三个 scene 暴露工具）在 manifest 和 scene md 层面已被测试覆盖。

## Open Questions

无。

## Residual Risk

上一轮 DS review 的四项 residual risk 仍然适用，此处不重复展开：

- R1：F01 相关 unstaged 变更需与本次改动一起提交。
- R2：无真实 provider 的端到端 CLI smoke 测试。
- R3：未来新增非 compact scene 需同步声明 `current_time` slot（已有迭代测试 `test_current_time_slot_is_rendered_by_non_compact_scenes` 覆盖）。
- R4：`current_time` slot 值为人类可读中文 Markdown，非机器可解析格式（`get_current_time` 工具提供结构化 `iso` 字段作为补充）。

## Conclusion

**Pass** — F02/F03 修复均已闭环，新增测试与已有模式一致，无新增阻断问题。
