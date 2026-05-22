# Phase 12 Slice 4 Re-Review — AgentDS

## Scope

- **Role**: AgentDS re-review
- **Gate**: Phase 12 Slice 4 narrow fix 收口验证
- **Adjudication source**: `docs/reviews/phase12-slice4-code-review-controller-adjudication-20260521.md`
- **Reviewed artifacts**:
  - `docs/reviews/phase12-slice4-code-review-controller-adjudication-20260521.md`
  - `docs/reviews/phase12-slice4-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-slice4-code-review-ds-20260521.md`
  - `docs/reviews/phase12-slice4-implementation-codex-20260521.md` (with Fix Addendum)
- **Fix scope**: `tests/runtime/test_scene_prepare.py` only
- **Non-goals verified**:
  - 未修改 production `scene_prepare.py`
  - 未修改 `PreparedSceneInputs` metadata shape
  - 未修改 duplicate fragment order 错误消息

## Accepted Findings 收口

### P12-S4-F1: optional missing fragment skip branch test — FIXED

- **Controller decision**: accepted-current-fix（test coverage only；rejected metadata shape change）
- **Fix**: `test_optional_missing_fragment_is_skipped`（test_scene_prepare.py:545）
- **验证**:
  - 声明 `required=false` 的 fragment，不创建对应文件
  - 断言 `prepare_scene` 不抛异常
  - 断言 `system_messages == ("基础提示",)`，不含 optional fragment
  - 断言 `fragment_refs` 只含 `"base"`，不含 `"optional_note"`
  - `PreparedSceneInputs` 字段列表未新增 `missing` 字段（scene_prepare.py:301-323）
- **结论**: 符合 controller 裁定

### P12-S4-F2: symlink escape containment test — FIXED

- **Controller decision**: accepted-current-fix
- **Fix**: `test_fragment_symlink_escape_prompt_asset_root_fails`（test_scene_prepare.py:510）
- **验证**:
  - 在 `prompt_root` 内创建 symlink 指向 `prompt_root` 外路径
  - 断言 `ScenePrepareError` 且错误消息匹配 `"escapes root"`
- **结论**: 符合 controller 裁定

### P12-S4-F3: inherited duplicate context slot parent-priority test — FIXED

- **Controller decision**: accepted-current-fix
- **Fix**: `test_inherited_duplicate_context_slot_keeps_parent_required_flag`（test_scene_prepare.py:566）
- **验证**:
  - 父 manifest 声明 `company` slot 且 `required=True`
  - 子 manifest 通过 extends 继承，同时声明同名的 `company` slot 且 `required=False`
  - 不提供 `company` 的 context slot value
  - 断言 `ScenePrepareError` 且错误消息匹配 `"required context slot missing: company"`
  - 证明父声明的 `required=True` 语义未被子的 `required=False` 覆盖
- **结论**: 符合 controller 裁定

### P12-S4-F4: duplicate fragment order diagnostic — DEFERRED (正确)

- **Controller decision**: deferred
- **验证**: `scene_prepare.py:1278` 错误消息仍为 `f"duplicate fragment order in {scene_id}: {fragment.order}"`，未添加父 manifest 来源信息
- **结论**: 未擅自修改，符合 controller 裁定

## New Blocker Check

- 24 tests passed（原 21 + 新增 3）
- pyright: 0 errors, 0 warnings, 0 informations
- `git diff --check`: clean
- production `scene_prepare.py` 未修改（git diff HEAD 不包含该文件）
- `PreparedSceneInputs` metadata shape 未修改（无 `missing` 字段）
- 无新发现缺陷

**无 new blocker。**

## Open Questions

无。

## Residual Risk

- P12-S4-F4 duplicate fragment order 错误消息改进已 deferred，当前错误消息不含冲突来源 manifest 引用，未来需在合适 slice 处理
- 旧 `dayu-agent` scene asset migration 仍归 Slice 5
- TOCTOU symlink race 为通用文件系统问题，当前威胁模型下可接受
- 大量 fragment / context slot 的性能边界未覆盖，第一版场景不触发

## Verdict

**PASS**

所有 accepted findings 已正确收口，无 new blocker，fix 范围严格限定于 `tests/runtime/test_scene_prepare.py`，未修改 production code、metadata shape 或 deferred 项。

## 验证命令

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q
# 24 passed

source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
# 8 passed

source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```
