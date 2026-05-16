# Repo Review Fix - Codex - 2026-05-16

## Scope

- 输入裁决：`docs/reviews/repo-review-controller-adjudication-20260516-2109.md`
- 输入 review artifacts：`docs/reviews/repo-review-20260516-2105.md`、`docs/reviews/repo-review-20260516-2059.md`
- 本轮只修复 Controller accepted current-fix findings DR-ALL-A1 到 DR-ALL-A5。
- 未执行 gateflow、deepreview、commit、push 或 PR 操作。

## Fixes

### DR-ALL-A1 RuntimeFileLock active token 泄漏

- `RuntimeFileLock.acquire()` 现在统一拒绝同一实例存在未释放 active token 时的重叠 acquire。
- 手动 acquire 也会登记 active token；token 已 release 后允许同一实例再次 acquire。
- 测试覆盖嵌套 `with`、context 内 manual acquire、manual acquire 后 context enter、manual release 后 reacquire。

### DR-ALL-A2 HostEventView public event_class

- 新增 public `HostEventClass`，并导出到 `dayu.host.api.__all__` 与包根 `dayu.host.__all__`。
- `HostEventView` 新增 `event_class: HostEventClass` 字段。
- `stream_run_events` 从 `EventLogRow.event_class` 映射 public `HostEventClass`。
- 测试覆盖 preview row 进入 public stream 时 caller 可区分 `PREVIEW` 与 `CANONICAL_FACT`。
- `dayu/host/README.md` 已同步 `HostEventClass` 与 `HostEventView.event_class` 字段说明。

### DR-ALL-A3 terminal_closeout terminal status 配对校验

- `_validate_terminal_input()` 增加 Attempt / Run terminal status 兼容矩阵。
- 合法配对为 succeeded/succeeded、failed/failed、cancelled/cancelled、lost/lost。
- cancelled/cancelled 通过既有 state 层 `cancel_running_attempt_row` 与 `cancel_running_run_row` CAS helper 收口，不复制 SQL。
- 测试覆盖四类合法配对与非法交叉配对。

### DR-ALL-A4 after_commit callback 全量尝试

- `_run_after_commit()` 现在会尝试全部 after-commit callbacks。
- 若存在失败，循环结束后抛出第一个失败的 `HostAfterCommitError`，保留第一个失败 `callback_index`。
- 测试覆盖第一个 callback 失败时第二个 callback 仍被调用，且错误 index 仍为 0。

### DR-ALL-A5 WaitPoller adapter 普通异常隔离

- `WaitPoller.poll_once()` 对单条 `poll_wait` / `abandon_wait` 捕获普通 `Exception`，计入 `adapter_errors` 并继续后续记录。
- 不捕获 `BaseException`。
- 测试覆盖 `abandon_wait` 抛 `ValueError` 时后续 waiting record 仍被 poll。

## Validation

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/host/test_public_event_stream.py tests/host/test_package_exports.py tests/host/test_run_attempt_transitions.py tests/host/test_durable_transaction.py tests/host/test_wait_adapter_polling.py -q
```

结果：通过，`80 passed in 0.61s`。

```bash
source .venv/bin/activate && pytest tests/host tests/runtime -q
```

结果：通过，`529 passed in 7.06s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：通过，`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

## Residual Risk

- 本轮未处理 Controller 明确 rejected 或 deferred findings。
- 未修改 schema version / DDL、Engine、Fins、Service、UI、command/admission/dispatch state machine。
- `terminal_closeout_in_transaction` 的 cancelled/cancelled 路径要求 Attempt 当前为 `RUNNING`，沿用既有 state 层取消 CAS 语义；Attempt `STARTING` 的取消仍由已有 pre-dispatch / active cancel primitive 负责。
