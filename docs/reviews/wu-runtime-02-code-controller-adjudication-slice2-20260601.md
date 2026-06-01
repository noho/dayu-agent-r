# WU-RUNTIME-02 Slice 2 Code Controller Adjudication

- **Gate**: code review / re-review adjudication
- **Work Unit**: WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification
- **Slice**: Slice 2 - 外层取消后的 shielded task 等待改为有界等待
- **Implementation artifact**: `docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md`
- **Fix artifact**: `docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md`
- **Review artifacts**:
  - `docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md`
- **Re-review artifacts**:
  - `docs/reviews/wu-runtime-02-code-rereview-slice2-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-code-rereview-slice2-ds-20260601.md`

## Controller Decision

Conclusion: **PASS**.

Slice 2 已满足 approved plan：外层取消后的 shielded task cleanup 采用有界等待，timeout 后不取消底层 task，对外保留 `asyncio.CancelledError`，tracked release / refresh 不误标 released / lost，abandoned task observer 消费 late result / exception。

## Finding Decisions

### 001-observer 只捕获 RuntimeLaneError

- **Decision**: accepted and fixed.
- **Reason**: 基于 runtime cleanup 的诊断目标，observer 不应让普通 `Exception` 从 done callback 逃逸；捕获普通 `Exception`、不捕获 `BaseException` 是当前 phase 的最小正确边界。
- **Evidence**: re-review artifacts 均确认三个 `_consume_abandoned_*_task` 已改为捕获 `Exception`，并新增普通异常日志测试。

### 002-release cancel 路径异常链丢失

- **Decision**: accepted and fixed.
- **Reason**: `CancelledError` 对外语义不变，但异常链应保留 cleanup failure 原因，便于诊断并与 claim / refresh 路径一致。
- **Evidence**: re-review artifacts 均确认 `_release_token` 与 `_release_untracked_claim` 已使用 `raise cancelled from exc`，测试覆盖 `__cause__`。

### 003-claim.acquired=False 静默消费

- **Decision**: rejected / no-action.
- **Reason**: `claim.acquired=False` 表示未持有 DB claim，不存在 TTL fallback 或 release 风险；新增日志只会降低信噪比，不服务于当前 WU 的 correctness 目标。
- **Evidence**: re-review artifacts 均确认该裁决无 correctness risk。

### DS 非 blocking 观察-observer 日志级别不一致

- **Decision**: rejected / no-action.
- **Reason**: claim / release 与 refresh 的日志级别差异不影响 cleanup correctness、取消语义或资源收口；在本 WU 中统一日志级别属于风格整理，当前不扩大 scope。

## Evidence

- `pytest tests/runtime/test_lane.py -q`: 通过，38 passed。
- `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`: 通过，41 passed。
- `python -m pyright dayu/ tests/ utils/`: 通过，0 errors。

## Residual Risk Tracking

- Cleanup timeout 不杀底层 Python thread；这是 approved plan 的设计边界。
- Abandoned successful untracked claim 依赖 TTL stale cleanup 回收容量；测试覆盖 late acquired claim observer 与手动 cleanup。
- 系统 wall clock skew 仍只影响 runtime capacity availability，不影响 Host truth / EventLog / Attempt lifecycle。

## Next Gate

创建 accepted slice2 本地提交后进入 aggregate deepreview。
