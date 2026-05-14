## Work Gate

code re-review

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 1: `dayu.host` public API typed contracts

## Reviewer

AgentDS (re-review)

## Re-Review Scope

仅复核 controller accepted findings D3 和 D4 的 fix，以及 fix 是否引入新问题。不重新做完整 code review。

## Source Artifacts

- Controller adjudication: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-controller-adjudication-20260513.md`
- Fix artifact: `docs/reviews/gateflow-fix-host-p1-s1-public-api-contracts-20260513.md`
- Original DS review: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`
- Original MiMo review: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-mimo-20260513.md`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- Test file: `tests/host/test_public_contracts.py`

## Per-Finding Re-Review

### D3: CancelRunRequest / CancelSessionRunsRequest mode 校验失败路径覆盖

**Fix verification**: 已修复。

- `test_cancel_run_rejects_non_graceful_runtime_mode` (test_public_contracts.py:316): 使用 `cast(CancelMode, "force")` 注入非 graceful 运行时 mode 值，断言 `ValueError` 且错误消息匹配 "mode"。
- `test_cancel_session_runs_rejects_non_graceful_runtime_mode` (test_public_contracts.py:328): 对 `CancelSessionRunsRequest` 做同等覆盖。
- 两条测试均通过 pyright 类型检查（`cast(CancelMode, ...)` 是 type-check 兼容的运行时注入方式）。
- 测试通过：pytest 16 passed。

### D4: frozen / slots 测试覆盖所有 Host public dataclass 类型

**Fix verification**: 已修复。

- `PUBLIC_HOST_DATACLASS_TYPES` (test_public_contracts.py:63) 定义完整元组，包含 26 个 public Host dataclass 类型：`OperationContext`, `AuthorizationClaim`, `HostCallContext`, `HostMetadataEntry`, `HostInput`, `SessionSlotRef`, `HostStreamCursor`, `EnsureSessionRequest`, `CreateSessionRequest`, `CloseSessionRequest`, `PurgeSessionRequest`, `StartRunRequest`, `CancelRunRequest`, `CancelSessionRunsRequest`, `SubmitFollowupRequest`, `RetryRunRequest`, `ReplayRunRequest`, `ResolveWaitRequest`, `TerminalResultSummary`, `OutboxSummary`, `SessionSnapshot`, `RunSnapshot`, `FollowupSnapshot`, `PurgeSessionResult`, `HostEventView`, `HostEventStream`。
- 正确排除了非 dataclass 符号：`HostApiError`（Exception 子类）、`HostCommandFacet`（Protocol）、全部 8 个 StrEnum 类型。
- `test_dataclasses_are_frozen_and_slots` (test_public_contracts.py:206) 遍历全部 26 个类型，断言 `is_dataclass`、`__dataclass_params__.frozen is True`、`__slots__ != ()`。
- 测试通过：pytest 16 passed。
- pyright 通过：0 errors。

## Fix Scope Compliance

- **生产 API 未修改**: `git diff --name-only HEAD -- dayu/host/api.py dayu/host/__init__.py` 无输出，确认 `dayu/host/api.py` 未被 fix 修改。
- **禁止文件未触及**: `dayu/engine/`, `dayu/fins/`, `dayu/runtime/`, `pyproject.toml` 均无变更。
- **仅允许文件被修改**: 变更范围仅包含 `tests/host/test_public_contracts.py` 和 Gateflow review artifacts，符合 controller adjudication "Required Fix Scope"。

## Validation Re-Run

| 命令 | 结果 |
|------|------|
| `pytest tests/host -q` | 16 passed in 0.05s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无空白错误 |

## New Issues or Regressions

无。Fix 仅扩展测试覆盖，未引入新问题。

- `cast(CancelMode, "force")` 的使用仅限于测试代码，不会泄漏到生产路径。
- `PUBLIC_HOST_DATACLASS_TYPES` 元组使用 `_FrozenSlotsDataclassClass` Protocol 做类型标注，类型安全性由 pyright 验证通过。
- 新增测试用例均通过，无 regressions。

## Finding Count

**Finding 数量: 0**

- Blocking: 0
- Non-blocking: 0

## Recommendation

**Proceed to user confirmation.** D3 和 D4 均已被正确修复，fix 未修改生产 API 或禁止文件，所有验证命令通过，无新问题引入。

## Artifact Path

docs/reviews/gateflow-code-re-review-host-p1-s1-public-api-contracts-ds-20260513.md
