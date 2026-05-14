# Code Re-Review: Host Phase 1 Slice 1 — D3 & D4 Fix Verification

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review Gate**: code re-review
- **Work Unit**: Host Phase 1 公共契约与 runtime 基础设施
- **Assigned Slice**: Slice 1: `dayu.host` public API typed contracts
- **Fix Artifact**: `docs/reviews/gateflow-fix-host-p1-s1-public-api-contracts-20260513.md`
- **Controller Adjudication**: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-controller-adjudication-20260513.md`
- **Review Date**: 2026-05-13

## Re-Review Scope

只复核 controller accepted findings D3 和 D4 的 fix，以及 fix 是否引入新问题。

## D3 Fix Verification: CancelRunRequest / CancelSessionRunsRequest mode 校验失败路径

**Status: PASS**

Controller 要求：在 `tests/host/test_public_contracts.py` 增加 focused test，覆盖 `CancelRunRequest` 与 `CancelSessionRunsRequest` 传入非 graceful runtime 值时抛 `ValueError`。

实际 fix：

- `test_cancel_run_rejects_non_graceful_runtime_mode` (line 316-325): 使用 `typing.cast(CancelMode, "force")` 构造非 graceful 运行时值，断言 `pytest.raises(ValueError, match="mode")`。测试覆盖了 `_require_graceful_cancel` 守卫路径。
- `test_cancel_session_runs_rejects_non_graceful_runtime_mode` (line 328-337): 同一模式覆盖 `CancelSessionRunsRequest`。
- 两个测试均使用 `typing.cast`，pyright 类型检查兼容。✓
- 未修改生产 API (`dayu/host/api.py` git diff 为空)。✓

## D4 Fix Verification: frozen / slots 测试覆盖所有 Host public dataclass

**Status: PASS**

Controller 要求：将 frozen / slots 检查改为覆盖所有 `dayu.host` public dataclass，排除 `HostApiError` 与 `HostCommandFacet` 等非 dataclass 类型。

实际 fix：

- `PUBLIC_HOST_DATACLASS_TYPES` (line 63-90): 包含全部 25 个 exported dataclass 类型的显式元组，每个元素通过 `cast(_FrozenSlotsDataclassClass, ...)` 标注。
- 排除了 `HostApiError`（plain Exception subclass，非 dataclass）和 `HostCommandFacet`（Protocol，非 dataclass）。✓
- 排除了 8 个 StrEnum 类型（`SessionStatus`, `RunStatus`, `AttemptStatus`, `FollowupBehavior`, `CancelMode`, `WaitResolutionSource`, `SourceRunRelation`, `HostApiErrorCode`）。✓
- `test_dataclasses_are_frozen_and_slots` (line 206-212): 遍历 `PUBLIC_HOST_DATACLASS_TYPES`，对每个类型断言 `is_dataclass`、`__dataclass_params__.frozen is True`、`__slots__ != ()`。✓
- 测试通过 `_FrozenSlotsDataclassClass` Protocol 定义类型安全的属性访问，无 `Any` / `object`。✓

## Production API Integrity

- `git diff dayu/host/api.py`: 无输出（未修改）。✓
- `git diff dayu/host/__init__.py`: 无输出（未修改）。✓
- fix artifact 声明的 changed files 仅包含 `tests/host/test_public_contracts.py`、docs artifacts，符合 controller approved fix scope。✓

## Fix 引入新问题检查

- 新增测试均为 focused assertion，未引入共享状态或副作用。✓
- `PUBLIC_HOST_DATACLASS_TYPES` 元组的 Protocol 定义 (`_DataclassParams`, `_FrozenSlotsDataclassClass`) 是模块级私有类型，不污染公共 API。✓
- 测试新增了 2 个 test function（从 14 → 16），test count 与 fix artifact 声明一致。✓

## Validation Re-Run

- `pytest tests/host -q`: **16 passed in 0.08s** ✓
- `python -m pyright dayu/host tests/host`: **0 errors, 0 warnings, 0 informations** ✓
- `git diff --check`: 无 whitespace errors ✓

## Finding 数量

**0**

D3 和 D4 均已正确修复，fix 未修改生产 API，未引入新问题。所有验证通过。

## Recommendation

**Controller may proceed to user confirmation.** 无 blocking finding，无 residual finding。
