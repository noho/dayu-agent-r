# Phase 12 Slice 5 Code Review - AgentMiMo

## Summary

- 当前 gate：Phase 12 Slice 5 code review。
- Review scope：`dayu/config/prompts/`（manifests + base + scenes）、`tests/runtime/test_scene_assets_migration.py`、`dayu/config/README.md`、`docs/host/implementation-control.md` gate 更新、`docs/reviews/phase12-slice5-implementation-codex-20260521.md`。
- 结论：**PASS**。无 blocking finding。

## Validation Run

| 检查项 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` | 28 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 8 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings |
| `git diff --check` | clean |

## Findings

### N1. Fragment 无 `{{placeholder}}` 语法（Informational）

**文件**：`dayu/config/prompts/scenes/*.md`、`dayu/config/prompts/base/*.md`

所有迁移后的 prompt fragment 文件均不包含 `{{slot_name}}` 占位符语法，但 13/14 个 manifest 声明了 `context_slots`（`fins_default_subject`、`base_user`）。`conversation_compaction` 声明空 `context_slots`，`infer` 只声明 `fins_default_subject`。

**评估**：不 blocking。设计规定 `context_slots` 声明 Service 必须提供的 typed context 名称，不要求 fragment 内部必须使用占位符。ScenePrepare 的 `{{slot_name}}` 替换机制在无占位符时为 no-op，不影响装配正确性。但后续真实 Service 接入时，若 fragment 需要动态注入 subject/user 信息，需补充占位符。当前迁移忠实反映了旧资产状态。

### N2. `allowed_names` 删除已验证无下游引用（Informational）

**文件**：14 个 manifest JSON

旧 manifest 的 `model.allowed_names` 字段已删除。Grep 验证：`dayu/` 下无任何 Python 代码引用 `allowed_names`。ScenePrepare parser 不消费该字段。删除符合设计约束"不携带 unused old bag fields"。

### N3. `runtime` raw patch 清空已验证无精确对应 hint（Informational）

**文件**：14 个 manifest JSON

旧 manifest 的 `runtime.agent.max_iterations` 与 `runtime.runner.tool_timeout_seconds` 已映射为 `runtime: {}`。`execution_profiles.json` 使用 `runner_options_profile_id` / `agent_policy_profile_id` 命名 profile，无与旧 raw patch 精确对应的 typed hint id。清空符合设计约束"不把 raw patch dict 塞进 manifest"。

## Schema Fidelity Check

| 检查项 | 结果 |
|---|---|
| 13 个必含字段全部存在 | 14/14 manifest 通过 |
| `schema_version = 1` | 14/14 通过 |
| `extends` 空数组（无继承） | 14/14 通过 |
| `capability_tags` 保守映射（仅 scene id） | 14/14 通过 |
| `conversation.mode` 映射：interactive/prompt_mt/wechat → `interactive`，其余 → `ordinary` | 14/14 通过 |
| `tool_selection.mode` 保留：audit/overview/conversation_compaction → `none`，其余 → `select` | 14/14 通过 |
| `defaults.missing_required_fragment = fail_closed` | 14/14 通过 |
| `model.default_name` 与 `temperature_profile` 保留 | 14/14 通过 |
| `runtime: {}`（raw patch 清空） | 14/14 通过 |
| `fragments` 只含 `id`/`path`/`order`/`required`（旧 `type` 已删除） | 14/14 通过 |
| `context_slots` 映射为 `{name, value_type: "string", required: true}` | 14/14 通过 |

## Migration Completeness Check

| 检查项 | 结果 |
|---|---|
| 迁移 manifest 数量 | 14 个 |
| 迁移 base fragment 数量 | 4 个（agents.md、fact_rules.md、soul.md、tools.md） |
| 迁移 scene fragment 数量 | 14 个 |
| 旧 `tasks/` 目录 | 未迁移，目录不存在 |
| 旧 `directories.md` | 未迁移，文件不存在 |
| 旧 `.contract.yaml` / `.contract.yml` | 未迁移，无匹配文件 |
| fragment 路径逃逸检查 | 测试 `_assert_fragment_paths_exist_under_prompt_root` 已覆盖 |

## Forbidden Asset Leakage Check

- 无 `tasks/` 目录。
- 无 contract 文件。
- 无 workflow 产物。
- 无未被 manifest 引用的模板。
- 无 `directories.md`。

## Tests Quality Check

- `test_all_migrated_scene_assets_prepare_successfully`：遍历全部 14 个 manifest，验证 fragment 路径存在且未逃逸，调用 `prepare_scene` 验证装配成功，检查 `system_messages`、`fragment_refs`、`capability_tags` 非空。覆盖了 `mode="none"` 和 `mode="select"` 两种工具选择路径。
- `test_migrated_prompt_assets_exclude_forbidden_legacy_files`：显式验证 forbidden 资产不存在。
- 测试使用 fake 工具目录覆盖 `fins`/`web`/`ingestion` 标签，匹配迁移 manifest 的 `tool_tags_any` 声明。

## Typing / Import Boundary Check

- `test_scene_assets_migration.py` 只 import `dayu.contracts.JsonValue` 和 `dayu.runtime.scene_prepare` 公共 API。
- 无反向依赖：测试不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`。
- pyright 0 errors 确认类型边界清洁。

## Docs Accuracy Check

- `dayu/config/README.md`：目录树新增 `prompts/` 子目录准确；职责表与实际文件结构一致；ScenePrepare 边界描述与 `design.md` 一致。
- `docs/host/implementation-control.md`：gate 状态从 "Slice 5 implementation" 更新到 "Slice 5 code review"，追加事实记录与 implementation artifact 一致。

## Residual Risks

1. Fragment 无 `{{placeholder}}`：当前迁移忠实反映旧资产，但后续 Service 接入时若需动态注入 context values，需在 fragment 中补充占位符。不阻塞当前 slice。
2. `allowed_names` 删除后无模型 allow-list 约束：若该约束仍是产品需求，需在后续 Service 层显式设计。不阻塞当前 slice。
3. `runtime` raw patch 清空后无运行预算 hint：后续 Service / execution profile work unit 需增加 typed hints。不阻塞当前 slice。

## Verdict

**PASS**。Blocking count = 0。
