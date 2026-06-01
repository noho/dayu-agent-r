# Fix Report

## Scope

- **Gate**: fix after code review
- **Work Unit**: WU-RUNTIME-02
- **Slice**: Slice 2 - outer cancellation bounded cleanup
- **Role**: fix specialist
- **Approved plan**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`
- **Implementation artifact**: `docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md`
- **Source review artifacts**:
  - `docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md`
- **Allowed files used**:
  - `dayu/runtime/lane.py`
  - `tests/runtime/test_lane.py`
  - `docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md`

## Controller Decisions

- **ACCEPT 001**: 修复。abandoned claim / release / refresh observer 现在消费并记录普通 `Exception`，避免非 `RuntimeLaneError` 从 done callback 逃逸。仍不捕获 `BaseException`；`CancelledError` 继续由 `task.cancelled()` 分支处理。
- **ACCEPT 002**: 修复。`_release_token` 与 `_release_untracked_claim` 的取消后 `RuntimeLaneError` 分支改为 `raise cancelled from exc`，与 claim / refresh 路径保持异常链一致。
- **REJECT 003**: 不修。`claim.acquired=False` 的 late result 不占用容量、不依赖 TTL fallback；新增日志会制造低价值噪音。按 controller 裁决仅记录。

## Per-Finding Status

### 001-已修复-低-observer 只捕获 RuntimeLaneError

- **修复文件**: `dayu/runtime/lane.py`
- **修复内容**:
  - `_consume_abandoned_claim_task` 从 `except RuntimeLaneError` 调整为 `except Exception` 并沿用原异常日志。
  - `_consume_abandoned_release_task` 从 `except RuntimeLaneError` 调整为 `except Exception` 并沿用原异常日志。
  - `_consume_abandoned_refresh_task` 从 `except RuntimeLaneError as exc` 调整为 `except Exception as exc`，保留 `error_type` 与 `exc_info=True`。
- **测试覆盖**: 新增 `test_abandoned_release_observer_logs_non_runtime_exception`，构造 abandoned release observer 收到 `ValueError`，断言写入 lane logger 且包含异常类型。

### 002-已修复-低-release cancel 路径异常链丢失

- **修复文件**: `dayu/runtime/lane.py`
- **修复内容**:
  - `_release_token` 的取消后 release `RuntimeLaneError` 分支改为 `raise cancelled from exc`。
  - `_release_untracked_claim` 的取消后 release `RuntimeLaneError` 分支改为 `raise cancelled from exc`。
- **测试覆盖**:
  - 新增 `test_release_token_failure_after_outer_cancel_preserves_cause`，断言 tracked release 取消后失败时 `CancelledError.__cause__` 是原始 `RuntimeLaneError`。
  - 更新 `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error`，断言 untracked release 同一路径的 `__cause__`。

### 003-未修复-低-claim.acquired=False 静默消费

- **处理状态**: 按 controller 裁决 rejected，不做代码修改。
- **理由**: capacity full 的 late result 未持有 claim，不存在 TTL fallback 风险；记录日志会降低信噪比。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_lane.py -q`
  - **结果**: PASS，`38 passed in 1.24s`
- `source .venv/bin/activate && pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
  - **结果**: PASS，`41 passed in 2.04s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - **结果**: PASS，`0 errors, 0 warnings, 0 informations`

## Docs Decision

- 未修改 README。此次变更仅补齐私有 runtime cleanup observer 的异常收口与测试断言，不改变测试分层、运行方式或维护规则；`tests/README.md` 无需同步。

## Residual Risks

- 无新增 residual risk。
- cleanup timeout 后底层线程仍可能继续运行，这是 approved plan 的既有设计；本 fix 仅保证 late exception 被 observer 消费并记录。
- `BaseException` 仍不会被 observer 捕获，符合 controller 裁决：`KeyboardInterrupt` / `SystemExit` 不应被 runtime logger 吞掉。

## Completion

- **Stop status**: completed for accepted findings 001 and 002.
- **No commit / push / PR**: 遵守 fix specialist handoff，未提交、未 push、未创建 PR。
- **Artifact path**: `docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md`
