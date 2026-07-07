# Code Review — DS F04 闭环复查

## Scope

- Mode: targeted re-review of DS F04 fix closure
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-slot-f04-rereview-mimo.md`
- Included scope:
  - `tests/runtime/test_scene_assets_migration.py` — `_first_contract_content_line_index` 函数
- Excluded scope:
  - 生产代码（`dayu/config/`、`dayu/cli/`、`dayu/host/`、`dayu/engine/`）
  - 其它测试文件
  - 历史 review artifact
- Parallel review coverage: 无，单 reviewer 走读
- Previous review artifacts:
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-rereview-ds.md` — DS F02/F03/F04 review
  - `docs/reviews/wu-cli-smoke-01-current-time-slot-fix-codex.md` — Codex fix artifact

## Review Items

### 1. `_first_contract_content_line_index` 是否同时跳过两个占位符，docstring 是否更新

**直接证据**:

- `tests/runtime/test_scene_assets_migration.py:268`: `if stripped == _FINS_DEFAULT_SUBJECT_PLACEHOLDER: continue`
- `tests/runtime/test_scene_assets_migration.py:270`: `if stripped == _CURRENT_TIME_PLACEHOLDER: continue`
- docstring（line 258）: `首个非空、非 Markdown 标题、非 context slot 占位符的零基行号。`

两个占位符均被跳过，docstring 已从"非默认主体占位符"扩展为"非 context slot 占位符"语义。**Pass**。

### 2. 修复是否只影响测试 helper，没有改生产逻辑或 scene/config

**直接证据**:

- `git diff main -- tests/runtime/test_scene_assets_migration.py` 只涉及测试文件
- `_first_contract_content_line_index` 是 `tests/runtime/test_scene_assets_migration.py` 内的模块级私有 helper，不被任何生产代码引用
- 无 scene manifest 或 scene md 文件变更

修复范围精确限定在测试 helper。**Pass**。

### 3. 当前整体是否无新增阻断问题

**直接证据**:

- `pytest tests/runtime/test_scene_assets_migration.py -q`: 17 passed
- `pyright`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: 通过，无输出

无新增阻断问题。**Pass**。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。

## Conclusion

**Pass** — DS F04 已闭环。

- `_first_contract_content_line_index` 同时跳过 `{{fins_default_subject}}` 与 `{{current_time}}`，docstring 已更新为"非 context slot 占位符"语义。
- 修复仅影响测试 helper，未触及生产逻辑或 scene/config。
- pytest 17 passed，pyright 0 errors，git diff --check clean。
