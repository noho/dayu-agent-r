# Re-Review — WU-CLI-SMOKE-01 util time + tag-only selection (Fix Gate 后复核)

## Scope

- Mode: re-review（仅复核 fix gate 后 accepted findings，不修代码）
- Branch: `phase/host-issues-control`
- Base: `main`
- Original reviews:
  - MiMo: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-mimo.md`
  - DS: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-fix-codex.md`
- Output file: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-ds.md`
- Controller accepted findings to verify:
  1. `infer.json` 应通过 tag-only 选择保持旧暴露面：`fins-read`、`fins-download`、`fins-preprocess`、`utils`；不应加入 `web`；不应选 `start_fins_upload`。
  2. `get_current_time` 对非字符串 `timezone` 应返回清晰 `invalid_argument` message/hint，不再出现空白时区名。
- Excluded（controller rejected，不复核）: ZoneInfo 防御分支、格式化 noise。

## Accepted Finding Status

### Finding 1: infer.json tag-only 选择保持旧暴露面 — 已修复

- **直接证据**:
  - `dayu/config/prompts/manifests/infer.json:20-24` — `tool_tags_any` 为 `["fins-read", "fins-download", "fins-preprocess", "utils"]`，`tool_names` 为 `[]`（tag-only 模式）。
  - 未包含 `web` tag；`start_fins_upload` 的 tag 为 `fins-upload`（`upload_tools.py:167`），未出现在任何 manifest 的 `tool_tags_any` 中。
  - `tests/runtime/test_scene_assets_migration.py:281-301` — `test_infer_manifest_selects_read_download_preprocess_and_utils_without_upload` 通过 `prepare_scene` + fake catalog 端到端验证：
    - `list_documents`（fins-read）在 selected 中 ✅
    - `start_fins_download` 在 selected 中 ✅
    - `start_fins_preprocess` 在 selected 中 ✅
    - `get_current_time`（utils）在 selected 中 ✅
    - `start_fins_upload` 不在 selected 中 ✅
    - `fake_web_search` 不在 selected 中 ✅
- **validation checked**:
  - infer.json 的 `tool_names` 为空（tag-only）✅
  - `tool_tags_any` 精确匹配 `["fins-read", "fins-download", "fins-preprocess", "utils"]` ✅
  - `web` 不在 `tool_tags_any` 中 ✅
  - 专项测试覆盖了 infer scene 的完整 `ScenePrepare` 装配路径 ✅
  - 其他 9 个 scene manifest 的 `tool_tags_any` 保持 `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`，未受 infer 修改影响 ✅
- **residual risk**: 无。旧暴露面已完整恢复，且通过 packaged manifest 测试锁定。

### Finding 2: get_current_time 对非字符串 timezone 返回清晰错误 — 已修复

- **直接证据**:
  - `dayu/tools/utils/provider.py:189` — `_timezone_argument` 返回类型改为 `str | None`。
  - `provider.py:205-206` — 非字符串类型 `value` 返回 `None`（原返回 `""`）。
  - `provider.py:125-132` — 调用方检查 `if timezone is None` → 返回 `ToolFailedOutcome`，message 为 `"timezone 参数类型错误：必须是字符串，或省略以使用 Asia/Shanghai。"`，hint 为 `_INVALID_ARGUMENT_HINT`。
  - `tests/tools/test_utils_tools_provider.py:119-135` — `test_get_current_time_rejects_non_string_timezone_with_type_message` 验证：
    - 传入 `{"timezone": 8}`（int）→ `ToolFailedOutcome` ✅
    - `error == "invalid_argument"` ✅
    - `"必须是字符串" in message` ✅
    - `hint is not None` ✅
    - `DEFAULT_TIMEZONE in hint` ✅
- **validation checked**:
  - 非字符串输入（int）不再产生空时区名错误消息 ✅
  - 错误消息明确指示类型约束和正确用法 ✅
  - hint 保留可执行恢复指导 ✅
  - 成功路径（`timezone=None`/缺省 → 默认 `Asia/Shanghai`）未受影响 ✅
  - 不支持时区路径（合法字符串但不在 `_SUPPORTED_TIMEZONES`，如 `"UTC"`）仍产生原有精确错误消息 ✅
  - 原有 test（`test_get_current_time_tool_returns_current_shanghai_time`、`test_get_current_time_rejects_unsupported_timezone`）继续通过 ✅
- **residual risk**: 无。非字符串路径已通过 provider 单测覆盖。

## Regression Check

对 changed tests 和 manifests 的回归检查：

- **10 个 packaged scene manifest**: infer 已修复为 `["fins-read", "fins-download", "fins-preprocess", "utils"]`；其余 9 个保持 `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`，无意外变更。
- **`test_scene_assets_migration.py`**: 新增 `start_fins_upload` 到 fake catalog（L194）和 infer 专项测试（L281-301），未削弱既有断言。`test_packaged_select_manifests_use_tag_only_tool_selection` 仍对所有 select manifest 断言 `tool_names == []` 且 `tool_tags_any` 非空。
- **`test_utils_tools_provider.py`**: 新增一个非字符串 timezone 测试（L119-135），未修改既有测试逻辑。
- **其他测试文件**（`test_prompt_command.py`、`test_entrypoint_runtime_prompt_path.py`、`test_entrypoint_runtime_interactive_path.py`、`test_combined_tools_acceptance.py`、`test_fins_storage_provider.py`、`test_config_loader.py`）: diff 仅包含原 WU-CLI-SMOKE-01 的功能性改动（tag 更新、upload 排除断言），无新增回归。
- **Provider 核心逻辑**: `_timezone_argument` 签名和返回类型变更（`str → str | None`）未影响成功路径和 `_SUPPORTED_TIMEZONES` 校验路径。

## 未复核项（按 Controller 要求）

- ZoneInfoNotFoundError 防御分支（provider.py:140-148）：controller 已 rejected，不复核。
- 测试文件格式化 noise：controller 已 rejected，不复核。

## 结论

- **status**: completed
- **artifact path**: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-ds.md`
- **accepted findings status**: 2/2 已修复
- **blocking**: 无。两个 accepted findings 均已完整修复且有直接测试证据支撑，无新回归。
