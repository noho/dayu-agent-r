# Re-Review: WU-CLI-SMOKE-01 Accepted Findings Verification

## Scope

- Mode: re-review (fix gate verification)
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-mimo.md
- Original review: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-mimo.md
- Fix artifact: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-fix-codex.md
- Verification scope: 2 accepted findings + regression check on changed tests/manifests

## Accepted Findings

### A-已修复-infer.json tag-only 选择保持旧暴露面

- **状态**: 已修复
- **Direct evidence**:
  - `dayu/config/prompts/manifests/infer.json` L20-25: `tool_names: []`, `tool_tags_any: ["fins-read", "fins-download", "fins-preprocess", "utils"]`
  - 不含 `web` tag → `fake_web_search` 不会被选中
  - 不含 `fins-upload` tag → `start_fins_upload` 不会被选中
  - `_fake_tool_catalog()` (test_scene_assets_migration.py:175-203) 已加入 `start_fins_upload` with tag `fins-upload` 作为真实负例
- **Validation checked**:
  - `test_infer_manifest_selects_read_download_preprocess_and_utils_without_upload` 断言:
    - `list_documents` (fins-read) ∈ selected ✓
    - `start_fins_download` (fins-download) ∈ selected ✓
    - `start_fins_preprocess` (fins-preprocess) ∈ selected ✓
    - `get_current_time` (utils) ∈ selected ✓
    - `start_fins_upload` ∉ selected ✓
    - `fake_web_search` ∉ selected ✓
  - `test_packaged_select_manifests_use_tag_only_tool_selection` 确认所有 select manifest 均为 `tool_names=[]` ✓
- **Residual risk**: 无。infer 场景旧暴露面已通过 tag-only 方式完整恢复，且有专项测试覆盖。

### B-已修复-get_current_time 非字符串 timezone 返回清晰错误消息

- **状态**: 已修复
- **Direct evidence**:
  - `dayu/tools/utils/provider.py:189-207` `_timezone_argument`:
    - 缺省值 → 返回 `DEFAULT_TIMEZONE` ("Asia/Shanghai") ✓
    - 非字符串 → 返回 `None` ✓
    - 字符串 → 返回 `.strip()` ✓
  - `dayu/tools/utils/provider.py:126-132` 调用方处理 `None`:
    - error: `"invalid_argument"` ✓
    - message: `"timezone 参数类型错误：必须是字符串，或省略以使用 Asia/Shanghai。"` ✓
    - hint: `"timezone 只能省略或填写 Asia/Shanghai；不要使用其它时区名称。"` ✓
- **Validation checked**:
  - `test_get_current_time_rejects_non_string_timezone_with_type_message` 断言:
    - `isinstance(outcome, ToolFailedOutcome)` ✓
    - `outcome.result.error == "invalid_argument"` ✓
    - `"必须是字符串" in outcome.result.message` ✓
    - `outcome.result.hint is not None` ✓
    - `DEFAULT_TIMEZONE in outcome.result.hint` ✓
  - 原有测试 `test_get_current_time_rejects_unsupported_timezone` 仍通过 ✓
  - 原有测试 `test_get_current_time_tool_returns_current_shanghai_time` 仍通过 ✓
- **Residual risk**: 无。非字符串 timezone 不再生成空白时区名错误消息，恢复提示对 LLM 可操作。

## Regression Check

- **测试回归**: 158 passed, 3 warnings (仅 edgar deprecation warnings)，无失败 ✓
- **Pyright**: 0 errors ✓
- **变更测试文件**: test_utils_tools_provider.py (新增 1 test)、test_scene_assets_migration.py (新增 1 test + fake catalog 扩展) — 均通过 ✓
- **变更 manifest**: infer.json tag-only 恢复 — 通过 scene prepare 装配测试 ✓
- **未重新开启的 rejected findings**: ZoneInfo 防御分支、格式化 noise — 未触及 ✓

## 结论

- **Status**: all accepted findings verified fixed
- **Artifact path**: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-mimo.md
- **Accepted findings status**: A 已修复, B 已修复
- **Blocking**: 无。两个 accepted findings 均已修复，有直接证据和测试覆盖，无回归。
