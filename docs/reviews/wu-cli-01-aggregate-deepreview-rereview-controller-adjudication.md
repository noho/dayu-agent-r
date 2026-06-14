# WU-CLI-01 aggregate deepreview re-review controller adjudication

## Gate

- gate: aggregate deepreview re-review
- work unit: WU-CLI-01
- fix artifact: `docs/reviews/wu-cli-01-aggregate-deepreview-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/wu-cli-01-aggregate-deepreview-rereview-mimo.md`
  - `docs/reviews/wu-cli-01-aggregate-deepreview-rereview-ds.md`

## Controller decision

pass。

## Finding status

- AGG-RV-F01：已修复。
  - `_close_watcher(...)` 使用 `try/finally`，无论 `watcher.aclose()` 成功、普通异常或
    `asyncio.CancelledError`，都会 cancel 并 await 回收 `drain_task`。
  - `watcher.aclose()` 的普通异常和 cancellation 不被吞掉；内层只抑制 drain task cancel 后产生的
    `asyncio.CancelledError`。
  - 新增测试覆盖 `aclose()` 抛 `asyncio.CancelledError` 和普通异常时 drain task 仍被 cancel / awaited。

## New findings

无阻塞 finding。

DS re-review 记录的 future maintenance note（若未来 `_drain_host_events` 变更为可能抛非取消异常，`finally`
内 `await drain_task` 可能覆盖 `aclose()` 原异常）当前不可达：现有 `_drain_host_events` 把非取消异常转为
`_WatcherFailure` queue item，不向 task 外抛出。该 note 不作为当前 residual risk。

## Deferred / rejected status

- AGG-RV-F02：保持 deferred-with-owner，已登记为 `WU-CLI-01-RR-09`。
- AGG-RV-F03：保持 deferred-with-owner，已登记为 `WU-CLI-01-RR-10`。
- AGG-RV-F04：保持 rejected-with-reason。
- MiMo maintainability observations：保持 rejected-with-reason。

## Validation

Controller 复核：

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py -q`：20 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`：56 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

README trigger 复核：

- `dayu/service/README.md` 已覆盖 entrypoint runtime watcher attach、terminal observation、outbox fallback 与 watcher failure
  诊断；本 fix 是内部 cleanup hardening，不需要更新。
- `tests/README.md` 已覆盖 service entrypoint runtime 测试层级；本 fix 只是补同层细分测试，不需要更新。

## Residual risks

- Existing deferred residual risks `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-10` 均有 owner / destination。
- 无 unclassified residual risk。

## Next gate

Accepted deepreview commit。随后进入 ready-to-open-draft-PR gate。
