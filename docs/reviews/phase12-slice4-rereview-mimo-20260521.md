# Phase 12 Slice 4 Re-Review — AgentMiMo

## Verdict: **PASS**

## Scope

- Mode: re-review (fix verification)
- Branch: `docs/phase12-design-discussion`
- Adjudication source: `docs/reviews/phase12-slice4-code-review-controller-adjudication-20260521.md`
- Implementation fix addendum: `docs/reviews/phase12-slice4-implementation-codex-20260521.md` § Fix Addendum
- Original reviews:
  - `docs/reviews/phase12-slice4-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-slice4-code-review-ds-20260521.md`
- Fix scope: `tests/runtime/test_scene_prepare.py`（新增 3 个测试）
- Production code changes: 无（`dayu/runtime/scene_prepare.py` 未修改）

## Accepted Findings 收口确认

### P12-S4-F1: optional missing fragment skip branch test — FIXED

- Controller decision: accepted-current-fix for focused test coverage; rejected-current-fix for changing `PreparedSceneInputs` metadata shape
- 实际 fix: 新增 `test_optional_missing_fragment_is_skipped`（line 545-563）
- 验证内容:
  - manifest 声明 `required=false` 的 fragment（`optional_note.md`），不创建对应文件
  - 断言 `system_messages` 只包含已加载的 base fragment
  - 断言 `fragment_refs` 只包含 base fragment id
- 评估: 测试准确覆盖了 skip 分支行为，assertions 有效证明了 optional missing fragment 不进入输出。metadata shape 未改动，符合 controller 裁决。

### P12-S4-F2: symlink escape containment test — FIXED

- Controller decision: accepted-current-fix
- 实际 fix: 新增 `test_fragment_symlink_escape_prompt_asset_root_fails`（line 510-527）
- 验证内容:
  - 在 `prompt_root` 内创建 symlink 指向 `prompt_root` 外的文件
  - 断言 `ScenePrepareError` 抛出且消息匹配 `escapes root`
- 评估: 测试覆盖了 `_resolve_contained_path` 的 symlink 解析后 containment 校验路径，补全了原 review 中 DS residual risk 1 指出的测试缺口。

### P12-S4-F3: inherited duplicate context slot parent-priority test — FIXED

- Controller decision: accepted-current-fix
- 实际 fix: 新增 `test_inherited_duplicate_context_slot_keeps_parent_required_flag`（line 566-592）
- 验证内容:
  - 父 manifest 声明 `company` slot `required=True`
  - 子 manifest 声明 `company` slot `required=False`
  - 不传入 `company` slot value
  - 断言 `ScenePrepareError` 抛出且消息匹配 `required context slot missing: company`
- 评估: 测试证明 `_dedupe_context_slots` 保留父声明的 `required` 语义，子声明不覆盖父 slot。回归保护有效。

### P12-S4-F4: duplicate fragment order error message — DEFERRED (no fix expected)

- Controller decision: deferred
- 本次未修改，符合裁决。

## New Blocker Check

未发现 new blocker。三个新增测试：
- 均为纯测试文件变更，未修改生产代码
- 测试结构与既有测试风格一致（使用 `tmp_path` fixture、helper 函数、`ScenePrepareError` match）
- 断言有效覆盖了目标行为路径

## Verification Commands

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q
# 24 passed (21 original + 3 new)

source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
# 8 passed

source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

## Residual Risk

无新增残余风险。原 review 中记录的 residual risks（TOCTOU symlink race、`SceneToolCatalog.from_tool_bundle` 无独立单测、大 fragment 性能、旧 asset migration、Service 映射链）均不属于本次 fix scope，状态不变。
