# Phase 12 Slice 5 Implementation - AgentCodex

## Summary

- 当前 gate：Phase 12 Slice 5 implementation。
- 任务：将旧仓库 `/Users/leo/workspace/dayu-agent` 的 legacy scene definition assets 按 Phase 12 ScenePrepare schema 迁入当前仓库。
- 结论：已迁移 14 个 scene manifest 与 18 个 manifest 直接引用的 prompt fragments；未迁移 `tasks/`、contract 文件、workflow 产物或未引用模板。

## Files Changed

- `dayu/config/prompts/manifests/*.json`
- `dayu/config/prompts/base/*.md`
- `dayu/config/prompts/scenes/*.md`
- `tests/runtime/test_scene_assets_migration.py`
- `dayu/config/README.md`
- `docs/reviews/phase12-slice5-implementation-codex-20260521.md`

## Migration Mapping Notes

- 每个旧 manifest 补齐 `schema_version: 1`，并保留 `scene`、`version`、`description`、`extends`。
- `capability_tags` 使用保守映射：每个 manifest 只写入对应 scene id，避免把旧 workflow 或工具图语义塞入 scene schema。
- `model.default_name` 与 `model.temperature_profile` 原样保留。
- `conversation.enabled=true` 的 `interactive`、`prompt_mt`、`wechat` 映射为 `conversation.mode=interactive`；其余 scene 映射为 `ordinary`。
- `tool_selection.mode`、`tool_names`、`tool_tags_any` 保留；缺失数组补为空数组，`allow_empty` 缺失时补 `false`。
- `defaults.missing_fragment_policy=error` 映射为 `defaults.missing_required_fragment=fail_closed`。
- `fragments` 删除旧 `type` 字段，只保留 `id`、`path`、`order`、`required`。
- `context_slots` 由旧字符串数组映射为 `{name, value_type: "string", required: true}`；旧 manifest 未声明时映射为空数组。
- 复制范围只包含 manifest 直接引用的 `base/agents.md`、`base/fact_rules.md`、`base/soul.md`、`base/tools.md` 与 `scenes/*.md`。

## Unmapped Old Fields

- `model.allowed_names`：ScenePrepare 当前 parser 不消费该字段，且用户 handoff 要求避免携带 unused old bag fields；已删除。后续如需模型 allow-list，应由 Service / config mapping owner 明确接入。
- `runtime.agent.max_iterations` 与 `runtime.runner.tool_timeout_seconds`：当前 `execution_profiles.json` 中没有与旧 raw patch 精确对应的 `runner_hint_id` / `agent_hint_id`。为避免把 raw patch dict 塞进 manifest，迁移为 `runtime: {}`，由后续 Service / composition root 按配置真源映射。
- 旧 manifest 没有直接表达的 workflow、task contract、artifact/parser/retry 语义未迁移，符合 ScenePrepare 不拥有 workflow 的边界。

## Tests And Validation

- `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  - 结果：28 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：8 passed。
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

## Residual Risks

- 迁移测试只证明 ScenePrepare schema 解析、fragment 读取、context slot 注入与 fake tool tag selection 可用；不验证真实 Fins storage、真实工具扫描或外部模型调用，这些明确不在本 slice 范围。
- 旧 runtime raw patch 未映射为 hint id，因为当前配置没有精确对应 hint；后续如需恢复这些运行预算，应由 Service / execution profile work unit 增加 typed hints 后再引用。
- 旧 `allowed_names` 删除后，当前 scene asset 不提供模型 allow-list 约束；如该约束仍是产品需求，需要后续在模型配置或 Service 层显式设计。

## Stop Status

Implementation、tests、README sync 与 artifact 已完成；未提交、未推送、未进入后续 gate。

## Fix Addendum - Phase 12 Slice 5

### Scope

- 当前 gate：Phase 12 Slice 5 fix。
- Fix worker：AgentCodex。
- 来源裁决：`docs/reviews/phase12-slice5-code-review-controller-adjudication-20260521.md`。
- 接受修复项：P12-S5-F1、P12-S5-F2。

### Fix Status

- P12-S5-F1：已修复。
  - `{{fins_default_subject}}` 接入 `base/agents.md`，该 fragment 被所有声明 `fins_default_subject` 的 migrated manifest 直接引用。
  - `{{base_user}}` 接入 `base/fact_rules.md`，该 fragment 被所有声明 `base_user` 的 migrated manifest 直接引用，同时避免为 `infer` 强行新增 `base_user`。
  - `tests/runtime/test_scene_assets_migration.py` 新增覆盖：每个 migrated manifest 声明的 required context slot 必须被直接装配 fragment 引用，且 `prepare_scene` 输出必须包含传入测试值。
- P12-S5-F2：已修复。
  - `base/tools.md` 删除旧 `<when_tag>` / `<when_tool>` 条件模板标记。
  - 删除 migrated manifest 未选择的 `doc` 条件段与 `get_current_time` 工具条件段；保留已被 migrated manifest 通过 tool tags 选择的 `fins`、`ingestion`、`web` 指引。
  - `tests/runtime/test_scene_assets_migration.py` 新增覆盖：`dayu/config/prompts` 下不得残留旧条件模板标记。

### Changed Files

- `dayu/config/prompts/base/agents.md`
- `dayu/config/prompts/base/fact_rules.md`
- `dayu/config/prompts/base/tools.md`
- `tests/runtime/test_scene_assets_migration.py`
- `docs/reviews/phase12-slice5-implementation-codex-20260521.md`

### Validation

- `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  - 结果：30 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：8 passed。
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

### Docs Decision

- 未更新 `dayu/config/README.md`：本次只修正 migrated prompt asset 的占位符接线与可见模板标记，不改变稳定配置入口或 prompt asset 职责说明。

### Residual Risks

- 迁移测试覆盖 ScenePrepare 对真实 migrated assets 的装配、slot 渲染与旧条件标记清理；不覆盖真实模型输出质量、真实工具发现或 Fins storage 调用，这些仍不在本 fix gate 范围。

### Stop Status

Fix scope 已完成；未提交、未推送、未进入 re-review 或后续 gate。
