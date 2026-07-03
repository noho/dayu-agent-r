# WU-WAIT-03 Slice 2 Code Re-review

## Scope

- Mode: current changes (workspace uncommitted changes on branch `phase/wu-wait-03-issue-92`)
- Base: `main` (Slice 1 committed at `4e661cee`; Slice 2 changes are uncommitted workspace modifications)
- Work unit: WU-WAIT-03 / GitHub Issue #92
- Slice: Fins Adapter/Runtime Mapping And Provider-focused Tests (Slice 2)
- Review target: Verify controller accepted finding from `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md` is closed
- Output file: `docs/reviews/wu-wait-03-slice2-code-rereview-ds.md`
- Included scope:
  - `dayu/fins/ingestion/wait_adapter.py` (uncommitted changes)
  - `tests/fins/test_fins_ingestion_tools.py` (uncommitted changes)
  - `tests/fins/test_fins_ingestion_runtime.py` (uncommitted changes)
  - `docs/host/issues-implementation-control.md` (uncommitted changes)
- Excluded scope:
  - Slice 1 committed changes (already reviewed and accepted)
  - Other review artifacts in `docs/reviews/`
- Reference documents:
  - `docs/host/wu-wait-03-external-job-lifecycle-plan.md` — accepted plan
  - `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md` — controller rulings
  - `docs/reviews/wu-wait-03-slice2-fix-codex.md` — fix description
- Controller pre-validated: Fins 126 passed, Host 35 passed, pyright 0 errors, `git diff --check` passed
- Parallel review coverage: 无（本 re-review 聚焦单一 accepted finding 验证，不派发 subagent）

## Accepted Finding Verification

### Controller accepted finding (唯一)

来源: `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md` Finding 行 1（AgentDS Finding 1）

> `cancel_observation(...)` non-transient error branch lacks direct test coverage
>
> Required action: Add a focused Fins adapter test using `cancel_errors` with `FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE`; assert `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`, `cancelled_handles == (handle_id,)`, and `abandoned_handles == ()`.

### 验证结论：已关闭

新增测试 `test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop`（`tests/fins/test_fins_ingestion_tools.py` 行 1754-1776）满足 controller 要求的全部五项断言：

| 要求 | 代码位置 | 状态 |
|---|---|---|
| 使用 `cancel_errors` 注入 `PERMANENT_CORRUPT_HANDLE` | 行 1762-1767 | ✅ |
| `isinstance(result, WaitExternalJobLifecycleNoop)` | 行 1773 | ✅ |
| `result.reason == "observation_error:permanent_corrupt_handle"` | 行 1774 | ✅ |
| `runtime.cancelled_handles == (handle.handle_id,)` | 行 1775 | ✅ |
| `runtime.abandoned_handles == ()` | 行 1776 | ✅ |

### 执行路径验证

逐行走读生产代码 `dayu/fins/ingestion/wait_adapter.py` `abandon_wait()` 方法（行 150-189）在 `cancel_errors` 触发场景下的实际分支：

1. **入口**：`handle = _handle_from_wait_record(wait_record)`（行 164）→ 有效 handle，非 `None`
2. **try 块**：`snapshot = _run_async_observation(self.runtime.cancel_observation(handle))`（行 170）→ `_FakeObservationRuntime.cancel_observation` 记录 `cancelled_handles += (handle.handle_id,)` 后 raise `FinsObservationPollError(PERMANENT_CORRUPT_HANDLE, ...)`
3. **except 块**（行 180-189）：
   - `TRANSIENT_UNAVAILABLE` 判断（行 181）→ **False**，不 re-raise
   - `PERMANENT_NOT_FOUND` 判断（行 183）→ **False**，不返回 `observation_missing`
   - 落入兜底分支（行 187-189）：`_observation_error_reason(PERMANENT_CORRUPT_HANDLE)` → `"observation_error:permanent_corrupt_handle"`
4. **返回值**：`WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`
5. **副作用**：cancel 已尝试（`cancelled_handles` 含 handle_id），abandon 未调用（`abandoned_handles` 为空）——与测试断言一致

生产代码路径与测试断言完全匹配，无逻辑矛盾。

### Fake 行为一致性检查

`_FakeObservationRuntime.cancel_observation()`（行 571-585）先记录 `cancelled_handles`，再检查 `cancel_errors` 并 raise。该顺序正确模拟了真实 runtime 的 best-effort 语义：adapter 已发出 cancel 请求，runtime 记录该尝试后报告无法完成的错误。测试通过 `cancelled_handles` 断言验证 adapter 确实调用了 cancel，而非静默跳过。

`_FakeObservationRuntime.abandon_observation()`（行 587-598）采用相同模式：先记录 `abandoned_handles`，再检查 `abandon_errors`。对于本测试，abandon_observation 从未被调用（cancel 即抛出），因此 `abandoned_handles == ()`。

## Findings

### 1-未修复-低-`abandon_wait` 中 cancel 成功后 snapshot 为 LOST 时 abandoned_handles 仍为空但语义微妙

- **入口/函数**: `FinsIngestionWaitPollAdapter.abandon_wait`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:170-174`
- **输入场景**: cancel_observation 成功返回 LOST 状态 snapshot，但 cancel 调用本身已在 runtime 层记录了取消尝试
- **实际分支**: 行 171 `if snapshot.status is FinsObservationStatus.LOST:` → 提前返回 `WaitExternalJobLifecycleNoop(reason="observation_missing")`
- **预期行为**: cancel 已尝试并成功返回，但 snapshot 是 LOST，adapter 跳过 abandon。行为正确，但 reason `"observation_missing"` 在 cancel 成功但 snapshot LOST 的场景下不完全精确——observation 可能不是 missing，而是 cancel 后发现已 LOST
- **实际行为**: 返回 `observation_missing` noop，不调用 abandon。`test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop`（行 1710-1727）断言 `abandoned_handles == ()`、`cancelled_handles == (handle.handle_id,)`
- **直接证据**: 行 171 `snapshot.status is FinsObservationStatus.LOST` 与行 224 计划中 "Observation missing / runtime returns LOST: return WaitExternalJobLifecycleNoop(reason='observation_missing')" 一致；但实际路径是 cancel 成功 → snapshot LOST，不是 cancel 抛 PERMANENT_NOT_FOUND
- **影响**: 仅 diagnostic reason 字符串的语义精度；不影响 Host 状态机、取消正确性或 poller 行为。Host poller 对 `WaitExternalJobLifecycleNoop` 一律写 `ABANDON_NOOP` terminal marker
- **建议改法和验证点**: 可考虑将 cancel 后 LOST snapshot 路径的 reason 改为更精确的字符串（如 `"observation_lost_after_cancel"`），但当前 reason 与计划 spec 一致且不影响行为。优先级低，可作为后续 diagnostic 精度优化
- **修复风险（低）**: 仅改 reason 字符串，需同步更新 `test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop` 的断言
- **严重程度（低）**: 非阻塞；不影响 correctness、state machine 或 Host 取消正确性

## Open Questions

无。

## Residual Risk

- **已有 accepted tradeoff（不变）**: provider lifecycle cleanup 仍是 best-effort；cancel 成功但 abandon cleanup 失败时，Host cancellation correctness 不依赖 provider cleanup 完成。该风险已在 controller adjudication 中分类为 informational。
- **已有 deployment risk（不变）**: poller-disabled 部署不会执行 external lifecycle adapter actions，仍依赖 durable Host cancellation truth。
- **cancel 后 LOST snapshot reason 精度**: 见 Finding 1。当前 `observation_missing` 字符串覆盖了两种不同路径（cancel 抛 PERMANENT_NOT_FOUND 和 cancel 成功但 snapshot LOST）。不影响行为正确性，属于 diagnostic 信息精度问题。
- **测试未覆盖 `PERMANENT_NOT_FOUND` 在 abandon 阶段**: controller 已拒绝此 finding（rejected-with-reason），因为现有 missing-observation 和 LOST 测试已覆盖 missing 语义结果。

## Verdict

- **Accepted finding 关闭状态**: ✅ 已关闭
- **Blocking findings count**: 0
- **Non-blocking findings**: 1（低严重程度，diagnostic reason 精度）
- **Controller 验证复验**: 本 reviewer 独立运行 `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` 结果为 `126 passed`，与 controller 报告一致
- **生产代码越界修改**: 无。所有生产代码修改均在 Slice 2 approved files 范围内（`dayu/fins/ingestion/wait_adapter.py`）
- **README 漏更新**: 无。`dayu/fins/README.md` 检查结论：`abandon_wait` 返回类型变更属于现有"Host wait-resume typed contract"架构边界内的内部适配，不改变 README 已记录的设计意图、架构边界或公共契约
- **类型问题**: 无。pyright 0 errors
- **测试问题**: 无。新增测试正确覆盖 cancel-side 非临时错误路径，fake 行为与生产语义一致
