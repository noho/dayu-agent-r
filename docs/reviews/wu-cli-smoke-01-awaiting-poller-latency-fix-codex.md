# WU-CLI-SMOKE-01 awaiting poller latency / idle follow-up 修复记录

## 结论

本次问题成立，且不是 Fins 业务下载失败，也不是 resume projection / LLM-safe replay / redaction 回归。

根因是 Host production wait poller 的通用 poll path 把 `WaitPollNotReady` 当成错误重试处理，写入 30 / 60 / 120 秒指数退避；同时 supervisor 在没有可 claim wait record 时固定按 1 秒循环调用 `poll_once()`，造成真实 DB 空查和逐秒空日志。Fins completion 仍应通过 `FinsIngestionWaitPollAdapter -> WaitPoller -> resolve_wait` 进入 Host truth，本次没有让 Fins 工具绕过 Host 写 Run 终态。

## Root Cause 直接证据

- 真实日志 `workspace/tmp/wu-cli-smoke-01-manual/interactive.log`：
  - 目标 run：`run-806e7c850ae349ce9d103980202a59b5`。
  - 目标 wait：`wait-7585328c7a45f2ab1902987ed94c17e4321a47b37f573a96bb2a4fed611016ab`。
  - `18:21:35` Host accepted awaiting wait record。
  - poller 观察链路为 `18:21:36 not_ready`、`18:22:06 not_ready`、`18:23:06 not_ready`、`18:25:07 ready`。
  - Fins pipeline 在 `2026-07-08 18:23:11` 已输出：`美股下载完成: ticker=V total=35 downloaded=35 skipped=0 rejected=0 failed=0 elapsed_ms=94035`。
  - Host 直到 `18:25:07` 才 `resolve_wait`，距 Fins 完成约 116 秒；随后 `18:25:10` final answer / terminal。
  - final answer 后仍持续出现 `host.wait_poller.poll_once.claimed claimed=0` 与 `host.wait_poller.poll_once.done observed=0 ...` 空轮询摘要，至少到 `18:27` 以后。
- Host DB `workspace/.dayu/host/dayu_host.sqlite3`：
  - `host_wait_records` 目标 wait：`created_at=2026-07-08T10:21:35.868087Z`，`updated_at=terminal_at=2026-07-08T10:25:07.529258Z`，`status=resolved`，`poll_last_outcome=not_ready`，`poll_backoff_attempt=0`。
  - `host_runs` 目标 run：`terminal_at=2026-07-08T10:25:10.713757Z`，`status=succeeded`。
  - terminal 后 DB 中没有 pending poll wait，说明后续每秒日志对应的是 supervisor 空轮询查询，不是 resolved row 被错误 claim。
- 代码同源证据：
  - `FinsIngestionWaitPollAdapter.poll_wait()` 将 `PENDING / RUNNING` 映射为 `WaitPollNotReady`，terminal snapshot 映射为 `WaitPollReady`。
  - 旧 `WaitPoller.poll_once()` 对 `WaitPollNotReady` 调用 `_release_with_backoff()`，导致正常运行中的外部 job 进入错误指数退避。
  - 旧 `WaitPollerSupervisor._run_loop()` 每轮固定 `poll_interval_seconds=1.0` 后再次 `poll_once()`，即使没有 active wait，也会每秒查询和记录空摘要。

## 修改列表

- `dayu/host/wait_adapter.py`
  - 新增 `not_ready_observe_interval_seconds`，让正常 `WaitPollNotReady` 按 policy cadence 短间隔复查，且不增加 `poll_backoff_attempt`。
  - 保留 adapter error、missing adapter、resolve error、shutdown skipped 的错误 backoff。
  - `poll_once()` 空结果携带下一次 active wait due delay；supervisor 有 active wait 但未到期时睡到 next due 或 idle 上限。
  - 新增 supervisor `wakeup()`，可打断 idle / next-due sleep；wakeup 是优化，不是 correctness 唯一依赖。
  - 没有 poll 活动时不再输出逐轮 `claimed=0` / `observed=0` 摘要日志。
- `dayu/host/durable/state.py`
  - 新增 `read_next_wait_record_poll_due_at(...)`，从 durable wait records 读取下一次 `poll_next_observe_at` 或未过期 claim 的 due 时间，用于通用 scheduler sleep。
- `tests/host/test_wait_adapter_polling.py`
  - 覆盖 not-ready 不走错误 backoff。
  - 覆盖无可处理 wait 时不刷空摘要日志。
- `tests/host/test_wait_poller_runtime.py`
  - 覆盖 no active wait 后使用 idle interval，不按 1 秒短间隔持续 poll。
  - 覆盖新 wait 创建后 `wakeup()` 可打断 idle。
  - 覆盖纯 poll、无 wakeup 时也能按 not-ready policy cadence observe ready。
- 文档同步：
  - `docs/host/design.md`
  - `dayu/host/README.md`
  - `tests/README.md`

## 验证

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_open_host_runtime.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_interactive_command.py -q`
  - 结果：`151 passed`。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`。

## 真实验证建议

可复用用户已有 interactive smoke，但建议使用新的临时 workspace，避免旧 DB / WAL 干扰：

```bash
source .venv/bin/activate
dayu-cli interactive --base workspace/tmp/wu-cli-smoke-01-awaiting-poller-real --log-level debug --detail
```

预期日志信号：

- Fins `美股下载完成` 后，下一次 `host.wait_poller.observe ... outcome=ready` 应按 `not_ready_observe_interval_seconds` cadence 出现，不再等待 30 / 60 / 120 秒错误退避窗口。
- `resolve_wait.committed` 后仍通过 dispatch resume 产生 final answer。
- final answer / Run terminal 后，若没有 active poll wait，不应每秒持续打印 `claimed=0` / `observed=0` 空摘要。
- 若此时创建新的 awaiting wait，本地 `wakeup()` 可打断 idle sleep；即使没有 wakeup，纯 poll 也按 not-ready policy cadence 稳定复查。

## 残余风险

- 本次未重复真实 SEC 下载；真实网络 smoke 仍依赖 SEC / provider / 本机凭据和网络状态。
- 本次修复不改变 Fins observation terminal 写入时机，也不引入 callback completion；Fins completion 仍由 poll adapter 观察后经 `resolve_wait` 收口。
- `idle_poll_interval_seconds` 默认 5 秒；没有 wakeup 的“全新 wait 初次出现”最多可能等待 idle interval 才被首次 observe。已有 active wait 的 not-ready 复查不受该 idle 间隔拉长。
