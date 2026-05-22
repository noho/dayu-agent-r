# Phase 12.1 Slice 3 Re-review

## Scope

- Mode: role-scoped re-review handoff
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice3-rereview-ds-20260521.md`
- Included scope: P12.1-S3-F1 fix verification only
- Excluded scope: 原 Slice 3 其他 finding（AgentMiMo 与 AgentDS 均无 blocking finding）；原 Slice 3 未覆盖的前序 dirty（`README.md`、`utils/smoke_host_public_multiturn.py`）
- Parallel review coverage: 无

## Verdict

**PASS**

## Fixed Finding Verification

### P12.1-S3-F1: `_require_scene_id` 异常类型不一致 → 已修复

**入口/函数**: `_require_scene_id`（`dayu/runtime/scene_prepare.py:1740`）

**检查项**:

1. 无效 scene id 格式分支已改为抛 `ScenePrepareError`：
   - `scene_prepare.py:1751`：`raise ScenePrepareError(f"{field_name} must be ASCII scene identifier")`
   - docstring 已同步更新（`:raises ScenePrepareError: scene id 为空或含路径字符时抛出。`）

2. 三个调用点均已通过 `_require_scene_id` 获得统一异常类型：
   - `ScenePrepareRequest.__post_init__`（line 225）：request scene id
   - `_parse_manifest`（line 702）：manifest `scene` 字段
   - `_parse_extends`（line 738）：extends parent id

3. 三条 focused tests 全部覆盖：

   | 测试 | 文件:行号 | 触发路径 |
   |---|---|---|
   | `test_request_scene_id_invalid_format_raises_scene_prepare_error` | `test_scene_prepare.py:588` | `"bad/scene"` 传入 `_request`，经 `ScenePrepareRequest.__post_init__` → `_require_scene_id` |
   | `test_manifest_scene_id_invalid_format_raises_scene_prepare_error` | `test_scene_prepare.py:600` | manifest `"scene": "bad/scene"` 经 `_parse_manifest` → `_require_scene_id` |
   | `test_extends_parent_id_invalid_format_raises_scene_prepare_error` | `test_scene_prepare.py:617` | `"extends": ["bad/parent"]` 经 `_parse_extends` → `_require_scene_id` |

   三条测试均使用 `pytest.raises(ScenePrepareError, match=...)` 精确断言异常类型与消息。

**直接证据**: `scene_prepare.py:1751` 的 `raise ScenePrepareError(...)` 替换了原 `raise ValueError(...)`；三条测试均通过，确认异常类型为 `ScenePrepareError`。

**修复验证结论**: 已完全修复。异常类型与模块错误契约一致，三个非法格式路径均有 focused test 覆盖。

## New Blockers

未发现新 blocker。

## Tests Run

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q` | 41 passed（含新增 3 条 focused tests） |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 10 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过（无输出） |

## Residual Risks

- 与原 Slice 3 一致：`utils/smoke_host_public_multiturn.py` 未接管（deferred to Slice 5）；`PreparedSceneInputs.model_hints` 为空时的 baseline 映射未实现（deferred to Slice 4/5）。这些均非本 fix 引入的新风险。
- 当前 workspace 存在前序 out-of-scope dirty（`README.md`），未纳入本次 re-review。
