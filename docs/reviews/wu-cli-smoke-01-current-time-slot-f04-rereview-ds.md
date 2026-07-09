# Code Review — DS F04 闭环复查

## Scope

- Mode: current changes (targeted re-review of DS F04 closure)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-slot-f04-rereview-ds.md`
- Included scope:
  - `tests/runtime/test_scene_assets_migration.py` — `_first_contract_content_line_index` 函数（F04 fix 主体）
  - `tests/runtime/test_scene_assets_migration.py` — `_placeholder_line_indexes` 函数（参数化重构）
  - 相关测试函数：`test_current_time_slot_is_rendered_by_non_compact_scenes`、`test_prepared_current_time_does_not_interrupt_scene_contract`
- Excluded scope:
  - F01/F02/F03 — 已在上一轮 DS review 确认闭环
  - `dayu/config/` 下的 manifest/scene md 变更 — 原 Codex fix 主体，非 F04 范围
  - `dayu/cli/`、`dayu/host/`、`dayu/engine/` 变更 — 非 F04 范围
- Previous review artifacts:
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-ds.md` — 上一轮 DS review（提出 F04）
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md` — Codex fix artifact（声称 F04 已修复）

## Findings

### 复查结论：F04 闭环 — Pass

- **检查项 1**: `_first_contract_content_line_index` 是否同时跳过 `{{fins_default_subject}}` 与 `{{current_time}}`，docstring 是否更新为 context slot 占位符语义。
- **直接证据**:
  - `tests/runtime/test_scene_assets_migration.py:270`: `if stripped == _FINS_DEFAULT_SUBJECT_PLACEHOLDER: continue` — 跳过 `{{fins_default_subject}}`
  - `tests/runtime/test_scene_assets_migration.py:272`: `if stripped == _CURRENT_TIME_PLACEHOLDER: continue` — 跳过 `{{current_time}}`
  - `tests/runtime/test_scene_assets_migration.py:260`: docstring `:returns: 首个非空、非 Markdown 标题、非 context slot 占位符的零基行号。` — 已从"默认主体占位符"更新为"context slot 占位符"
  - 两个 `continue` 条件对称排列，先 `_FINS_DEFAULT_SUBJECT_PLACEHOLDER` 后 `_CURRENT_TIME_PLACEHOLDER`，逻辑清晰
- **覆盖验证**: `test_current_time_slot_is_rendered_by_non_compact_scenes:419` 调用 `_first_contract_content_line_index(lines)` 断言 `current_index > first_contract_line`，直接验证 `{{current_time}}` 被跳过后的行号语义正确。`test_prepared_current_time_does_not_interrupt_scene_contract:487` 同样调用该函数取首行契约正文行号，用于真实 ScenePrepare 装配后的 system_prompt 顺序验证。
- **判定**: ✅ F04 已闭环。函数现在跳过所有已定义 context slot 占位符，docstring 语义准确。

- **检查项 2**: 修复是否只影响测试 helper，没有改生产逻辑或 scene/config。
- **直接证据**:
  - `_first_contract_content_line_index` 位于 `tests/runtime/test_scene_assets_migration.py:256`，属于测试模块
  - 函数仅被同文件内的测试函数调用：`test_fins_default_subject_slot_is_rendered_by_declaring_scenes:378`、`test_current_time_slot_is_rendered_by_non_compact_scenes:419`、`test_prepared_fins_default_subject_does_not_interrupt_scene_contract:444`、`test_prepared_current_time_does_not_interrupt_scene_contract:487`
  - `git diff -- tests/runtime/test_scene_assets_migration.py` 中与 F04 相关的改动限于 `_first_contract_content_line_index` 函数体（+2 行 continue，docstring 修改），以及 `_placeholder_line_indexes` 参数化（从硬编码 `_FINS_DEFAULT_SUBJECT_PLACEHOLDER` 改为接受 `placeholder` 参数）
  - 所有调用方同步更新为传入显式 placeholder 参数
- **判定**: ✅ 修复仅限于测试 helper，未触及生产代码、scene manifest 或 scene md。

- **检查项 3**: 当前整体是否无新增阻断问题。
- **直接证据**:
  - `pytest tests/runtime/test_scene_assets_migration.py -q`: 17 passed
  - `pyright`: 0 errors, 0 warnings, 0 informations
  - `git diff --check`: 无输出（无空白/合并标记冲突）
  - 函数逻辑为纯加法的 `continue`，不改变已有分支行为：空行跳过、`#` 标题行跳过、`{{fins_default_subject}}` 跳过三条保持不变，`{{current_time}}` 跳过新增在后
  - 不存在死分支或不可达代码：`_CURRENT_TIME_PLACEHOLDER` 常量在 line 74 定义为 `Final[str]`，在所有非 compact scene md 中均出现
- **判定**: ✅ 无新增阻断问题。

## Open Questions

无。

## Residual Risk

无。F04 修复是纯加法防御性编程改进，不改变现有测试断言语义，不引入新分支风险。

## Conclusion

**Pass** — DS F04 已闭环。

- `_first_contract_content_line_index` 同时跳过 `{{fins_default_subject}}` 与 `{{current_time}}`，docstring 更新为"context slot 占位符"语义。
- 修复局限在测试 helper 函数，未扩散到生产逻辑或 scene/config。
- 无新增阻断问题：pytest 17 passed，pyright 0 errors，git diff --check clean。
