# Full Repository Deepreview Fix Re-Review Controller Adjudication - 2026-05-16 21:30

## Gate

当前 gate：Phase 8 ready-to-open-draft-PR 前追加 `/deepreview --all` fix re-review。

输入：

- `docs/reviews/repo-review-controller-adjudication-20260516-2109.md`
- `docs/reviews/repo-review-fix-codex-20260516.md`
- `docs/reviews/repo-review-fix-re-review-mimo-20260516.md`
- `docs/reviews/repo-review-fix-re-review-ds-20260516.md`

## Controller Verdict

PASS。

AgentMiMo 与 AgentDS 均确认 DR-ALL-A1 至 DR-ALL-A5 已完整修复，未发现 blocker 或 regression。当前 fix 包可以进入本地
accepted commit。

## Accepted Fixed Findings

### DR-ALL-A1 RuntimeFileLock active token overlap

状态：fixed。

证据：

- `RuntimeFileLock.acquire()` 在同一实例存在未释放 active token 时 fail fast。
- 手动 acquire 与 context manager 统一登记 active token。
- tests 覆盖 nested context、context 内 manual acquire、manual acquire 后 context enter、manual release 后 reacquire。

### DR-ALL-A2 HostEventView public event_class

状态：fixed。

证据：

- Public `HostEventClass` 已加入 API 与包根导出。
- `HostEventView.event_class` 从 durable `EventLogRow.event_class` 映射。
- stream regression 覆盖 preview row 可被 public caller 区分为 `HostEventClass.PREVIEW`。
- `dayu/host/README.md` 已同步字段说明。

### DR-ALL-A3 Terminal closeout Attempt / Run status pair

状态：fixed。

证据：

- `_TERMINAL_STATUS_PAIRS` 和 `_terminal_status_pair_is_compatible()` 阻止非法交叉配对。
- CANCELLED 合法配对复用既有 state 层 cancel CAS helper，不复制 SQL。
- tests 覆盖四类合法配对与非法配对。

### DR-ALL-A4 after_commit callbacks all attempted

状态：fixed。

证据：

- `_run_after_commit()` 现在尝试全部 callbacks。
- 若存在失败，循环后抛第一个失败的 `HostAfterCommitError` 并保留 `callback_index`。
- tests 证明第一个 callback 失败时第二个 callback 仍执行。

### DR-ALL-A5 WaitPoller adapter ordinary exception isolation

状态：fixed。

证据：

- `WaitPoller.poll_once()` 对 `poll_wait` / `abandon_wait` 捕获普通 `Exception` 并继续后续 wait record。
- 不捕获 `BaseException`。
- tests 覆盖 `ValueError` 不阻断后续 waiting record。

## Validation

Controller 已复跑：

```bash
source .venv/bin/activate
pytest tests/runtime/test_filelock.py tests/host/test_public_event_stream.py tests/host/test_package_exports.py tests/host/test_run_attempt_transitions.py tests/host/test_durable_transaction.py tests/host/test_wait_adapter_polling.py -q
pytest tests/host tests/runtime -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

结果：

- targeted tests：80 passed
- Host + runtime tests：529 passed
- pyright：0 errors, 0 warnings, 0 informations
- diff check：clean

## Deferred / Residual Risks

- Engine / OpenAI runner / parser findings 未修；修改 Engine 需单独用户确认，归 Engine hardening gate owner。
- schema CHECK 约束 hardening 未修；需要 schema version bump，归后续 schema hardening owner。
- scheduler close cancellation 后 active Run reconciliation 归 Phase 11 recovery owner。
- awaiting accepted ack 当前状态重校验归 Phase 7 / Phase 11 wait lifecycle hardening owner。
- poller LIMIT / CANCELLED abandon 退避归 Phase 15 / production polling scale owner。
- `HostEventClass` 与 durable `EventClass` 是独立 StrEnum；未来 durable event class 扩展时必须同步 public enum 和 tests。
