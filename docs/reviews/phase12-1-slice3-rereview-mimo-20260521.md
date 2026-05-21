# Phase 12.1 Slice 3 Re-Review

## Verdict: PASS

## Scope

- Mode: role-scoped re-review
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice3-rereview-mimo-20260521.md`
- Accepted finding verified: P12.1-S3-F1
- Implementation artifact: `docs/reviews/phase12-1-slice3-implementation-codex-20260521.md`（Fix Addendum 段）

## Fixed Finding Verification

### P12.1-S3-F1: `_require_scene_id` 非法格式分支必须抛 `ScenePrepareError`

**已修复。**

- **代码变更**: `dayu/runtime/scene_prepare.py:1751` — `raise ScenePrepareError(f"{field_name} must be ASCII scene identifier")`。原为 `raise ValueError(...)`，现与同模块 `_require_context_slot_name`（行 1766）保持一致。
- **docstring 同步**: 行 1746 已标注 `:raises ScenePrepareError:`。
- **调用路径验证**:
  1. `ScenePrepareRequest.__post_init__`（行 225）调用 `_require_scene_id`，非法 request scene id 时抛 `ScenePrepareError`。
  2. `_parse_manifest`（行 702）调用 `_require_scene_id`，manifest `scene` 字段非法格式时抛 `ScenePrepareError`。
  3. `_parse_extends`（行 738）调用 `_require_scene_id`，extends parent id 非法格式时抛 `ScenePrepareError`。
- **测试覆盖**（三条 focused tests）:
  1. `test_request_scene_id_invalid_format_raises_scene_prepare_error` — request scene id `"bad/scene"` → `ScenePrepareError`
  2. `test_manifest_scene_id_invalid_format_raises_scene_prepare_error` — manifest `scene` 字段 `"bad/scene"` → `ScenePrepareError`
  3. `test_extends_parent_id_invalid_format_raises_scene_prepare_error` — extends parent id `"bad/parent"` → `ScenePrepareError`
- **一致性检查**: 模块内剩余唯一 `raise ValueError` 在 `SceneToolCatalog.__post_init__`（行 160），为工具名重复校验，与 scene id 无关，语义正确。

## New Blockers

未发现新 blocker。fix 仅改变异常类型，不改变控制流或数据流，不引入新依赖或新行为。

## Tests Run

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q` | 41 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 10 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过（无输出） |

## Residual Risks

- 本 fix 为窄范围异常类型修正，无新增 residual risk。
- 原 Slice 延后项（`utils/smoke_host_public_multiturn.py` 接入、`PreparedSceneInputs.model_hints` 空值 baseline 映射、Host / Engine 公共契约）仍归属后续 Slice 4/5，未因本 fix 变更。
