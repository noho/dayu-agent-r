# Code Review

## Scope

- Mode: role-scoped code review handoff
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice3-code-review-mimo-20260521.md`
- Included scope:
  - `dayu/runtime/scene_prepare.py`
  - `dayu/config/prompts/manifests/*.json`
  - `dayu/config/prompts/scenes/*.md`
  - `tests/runtime/test_scene_prepare.py`
  - `tests/runtime/test_scene_tool_selection.py`
  - `tests/runtime/test_scene_assets_migration.py`
  - `tests/runtime/test_import_boundary.py`
  - `tests/runtime/test_weak_typing_guard.py`
  - `dayu/config/README.md`
  - `dayu/README.md`
  - `tests/README.md`
- Excluded scope: `README.md`、`utils/smoke_host_public_multiturn.py`（前序 dirty，非本 Slice 范围）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐条验证 review criteria：

1. **Scene schema matches design/plan**: `_ALLOWED_MANIFEST_FIELDS`（第 34-49 行）固定为白名单 12 个字段；`_require_exact_fields`（第 1265-1282 行）对未知字段 fail fast。`test_legacy_conversation_and_runtime_fields_fail_fast` 证明旧 `conversation` / `runtime` 出现时抛出 `ScenePrepareError("unsupported fields")`。`_ALLOWED_MODEL_FIELDS`（第 50-52 行）只含 `default_model_id` 与 `runner_option_hint_id`；`test_legacy_model_field_names_fail_fast` 证明旧 `default_name` / `temperature_profile` fail fast。所有 14 个包内 manifest 通过 `test_migrated_scene_manifest_schema_excludes_legacy_fields` 验证。`prompt_mt` manifest 与 scene 文件已删除（`test_prompt_mt_scene_asset_is_removed_and_smoke_scene_is_ordinary_asset` 第 237-238 行断言不存在）。

2. **PreparedSceneInputs output**: `PreparedSceneInputs`（第 362-383 行）字段为 `system_messages`、`tool_selection`、`model_hints`、`agent_policy_override`、`fragment_refs`、`source_refs`、`content_digest`、`capability_tags`。无 `runtime_hints` 或 `conversation_hint`。`SceneModelHints`（第 228-256 行）字段为 `default_model_id: str` 与 `runner_option_hint_id: str | None`，经 `__post_init__` 校验非空。

3. **agent_policy override**: `_ALLOWED_AGENT_POLICY_FIELDS`（第 53-64 行）为 8 个白名单字段；`_parse_agent_policy_override`（第 774-833 行）对未知字段通过 `_require_exact_fields` fail fast。`_AGENT_FALLBACK_MODES`（第 77-79 行）只含 `force_answer` / `raise_error`；`_parse_optional_fallback_mode`（第 1285-1301 行）对非法值 fail fast。测试覆盖白名单内全字段（`test_agent_policy_override_outputs_typed_view`）、未知字段（`test_agent_policy_unknown_field_fails_fast`）、非法 fallback_mode（`test_agent_policy_fallback_mode_is_closed_enum`）。

4. **ScenePrepare boundary**: `scene_prepare.py` 只 import `dayu.contracts`（`JsonValue`、`ToolBundle`）和 `dayu.runtime._digest`（`canonical_json_digest`）。无 `ConfigLoader`、`ToolsDiscovery`、`Host`、`Engine`、`Service`、`UI`、`Fins`、workspace fallback、workflow graph、lane、SQLite、artifact root、memory/context policy。`test_import_boundary.py` 的 `test_runtime_does_not_import_business_layers` 通过 AST 扫描确认。

5. **context_slots**: `_render_fragment_content`（第 1033-1068 行）对 required slot 缺失 fail fast（第 1053-1054 行）、未知 placeholder fail fast（第 1093-1096 行）、非字符串值 fail fast（第 1102-1103 行）、渲染后残留 placeholder fail fast（第 1062-1067 行）。测试覆盖全部路径。

6. **tool_selection**: `_select_tools`（第 1110-1143 行）`all` 映射 `tool_names=None`、`none` 映射空集合、`select` 支持 names/tags 并集。未知 tool_names fail fast（第 1129-1133 行）；tag 无匹配且 `allow_empty=False` fail fast（第 1135-1139 行）；最终空选择且 `allow_empty=False` fail fast（第 1141-1142 行）。结果只从 `SceneToolCatalog` 子集选取。

7. **Scene assets migration**: 14 个包内 manifest 全部通过 `test_all_migrated_scene_assets_prepare_successfully` 装配验证。`prompt_mt.json` 与 `prompt_mt.md` 已删除（物理确认 + 测试断言）。`smoke_host_public_multiturn.json` 存在且为普通资产，`ScenePrepare` 中无 special case（grep 确认模块内无 `smoke` 关键字）。`test_migrated_prompt_assets_exclude_legacy_conditional_markers` 与 `test_migrated_prompt_assets_exclude_forbidden_legacy_files` 确认无旧模板残留。

8. **Tests and README**: 测试反映当前代码，无兼容 reader/wrapper/test。`dayu/config/README.md` 已更新为新 schema（白名单字段、新 model hint 字段、typed agent_policy override）。`dayu/README.md` 已更新 `scene_prepare` 概览。`tests/README.md` 已更新 scene prepare / scene asset migration 测试覆盖事实。

9. **Project rules**: pyright 零错误零警告。`test_weak_typing_guard` 通过 AST 扫描确认无 `Any`、`object`、无类型签名或裸容器注解。所有函数和类提供中文 docstring。所有 dataclass 使用 `frozen=True, slots=True`。

## Open Questions

无。

## Residual Risk

- `PreparedSceneInputs.model_hints` 允许为 `None`；Service / composition root 需要在后续 Slice 4/5 中将空值映射到 execution profile baseline。这是 plan 中 Slice 4 的职责，非本 Slice 遗留。
- `utils/smoke_host_public_multiturn.py` 未在本 Slice 接管，后续 Slice 5 仍需将 smoke 脚本接入 dedicated ordinary scene。Implementation artifact 已记录。

## Tests Run and Results

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q` | 38 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 10 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过（无输出） |

## Verdict

**PASS**
