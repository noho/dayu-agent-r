# WU-CLI-01 / CLI-01-S2 Implementation Re-Review (AgentDS)

## Scope

- Mode: S2 fix gate re-review（只验证 accepted findings 是否关闭、fix 是否引入新问题）
- Branch: `phase/host-ui-implementation`
- Target: 当前未提交 workspace changes 的 S2 fix 后状态
- Base review artifacts:
  - `docs/reviews/wu-cli-01-s2-implementation-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`
  - `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`
  - `docs/reviews/wu-cli-01-s2-implementation-review-ds.md`
- Included scope:
  - `dayu/service/entrypoint_runtime.py`
  - `dayu/service/host_assembly.py`
  - `dayu/runtime/location.py`
  - `tests/service/test_entrypoint_runtime.py`
  - `tests/service/test_host_assembly.py`
  - `tests/runtime/test_runtime_location.py`
  - `dayu/README.md` / `dayu/service/README.md` / `tests/README.md`
  - `docs/host/ui-implementation-control.md`
- Excluded scope: S3-S7 / CLI command / Fins direct / init / Host durable internals / deferred Host watch return typing

## Accepted Findings 关闭验证

### S2-IMPL-F01 — cancel race ✅ 已关闭

**Controller 要求**:

1. initial `get_run` 已终态应跳过 `cancel_run`
2. `cancel_run` 与终态竞争失败后应继续 public terminal observation/outbox fallback

**证据**:

- `cancel_entrypoint_run_and_wait`（`entrypoint_runtime.py:448-460`）：`get_run` 后立即调用 `_is_terminal_run_status(run_snapshot.status)`；若为终态则创建空 queue 直接进入 `_wait_for_terminal`，全程不创建 watcher、不调用 `cancel_run`。
- `cancel_entrypoint_run_and_wait`（`entrypoint_runtime.py:465-478`）：`cancel_run` 抛 `HostApiError` 后 `except` 块再次 `get_run` 判断是否已终态。若已终态则保留已在 `cancel_run` 前 attach 的 watcher，继续走 `_wait_for_terminal`；若仍非终态则 `raise` 原样传播异常。
- 无论哪条路径，watcher 创建与 drain task 的清理均在 `finally`（line 488-489）中通过 `_close_watcher` 完成。

**测试覆盖**:

- `test_cancel_entrypoint_run_attaches_watcher_before_cancel_and_waits_terminal`：正常 cancel 路径（非终态 → cancel 成功 → live event terminal）。
- `test_cancel_entrypoint_run_skips_cancel_when_initial_snapshot_is_terminal`：初始 `get_run` 返回终态 → 跳过 `cancel_run`（`fake_host.cancel_requests == []`）→ 无 watcher 创建（`fake_host.watchers == []`）→ outbox fallback 返回 `OUTBOX_READ`。
- `test_cancel_entrypoint_run_continues_wait_when_cancel_loses_terminal_race`：`cancel_run` 抛 `HostApiError` → `get_run` 返回 `SUCCEEDED` → 保留 watcher 继续 → outbox fallback 返回 `OUTBOX_READ`。

**结论**：两分支均已实现且均有测试覆盖。

### S2-IMPL-F02 — watcher failure ✅ 已关闭

**Controller 要求**:

1. watcher drain failure 不能静默丢弃
2. result/error 应有 watcher failure 诊断
3. 有 watcher failure → outbox fallback 测试

**证据**:

- `_drain_available_watcher_items`（`entrypoint_runtime.py:609-611`）：遇到 `_WatcherFailure` 时调用 `_record_watcher_failure` 记录诊断，不再静默 `continue`。
- `_record_watcher_failure`（`entrypoint_runtime.py:664-680`）：记录首个 watcher failure 的诊断字符串，格式为 `"watcher drain failed: <error_type>: <message>"`。
- `EntrypointRunTerminalResult.watcher_failure_message`（`entrypoint_runtime.py:199`）在 live event 路径（line 660）、outbox 路径（`_scan_outbox_terminal_items` line 774 → `_terminal_result_from_outbox_item` line 803）以及 error 路径（`_observation_error_message` line 807-818）均被传递。
- Outbox fallback 仍正常工作：watcher failure 被记录后，`_wait_for_terminal` 继续走 `get_run` + `_read_outbox_terminal` 路径获取终态。

**测试覆盖**:

- `test_submit_entrypoint_turn_records_watcher_failure_and_uses_outbox`：注入 `RuntimeError("watch stream disconnected")` → result.source 为 `OUTBOX_READ` → result.watcher_failure_message 包含 `"RuntimeError"` 和 `"watch stream disconnected"` → outbox cursor 正常工作。

**结论**：watcher failure 不再静默丢弃；result 和 error 均携带诊断；watcher failure → outbox fallback 路径有测试。

### S2-IMPL-F03 — ensure_or_create 参数校验 ✅ 已关闭

**Controller 要求**：补 create 缺 context、create 缺 client_request_id、ensure 缺 scope、ensure 缺 slot_key 的 ValueError 测试。

**测试覆盖**（`tests/service/test_entrypoint_runtime.py`）：

- `test_ensure_or_create_entrypoint_session_rejects_create_without_context`（line 402-420）：`create_new=True, create_context=None` → `ValueError` match `"create_context"`，`fake_host.calls == []`。
- `test_ensure_or_create_entrypoint_session_rejects_create_without_request_id`（line 424-441）：`create_new=True, create_client_request_id=None` → `ValueError` match `"create_client_request_id"`，`fake_host.calls == []`。
- `test_ensure_or_create_entrypoint_session_rejects_ensure_without_scope`（line 444-460）：`create_new=False, scope=None` → `ValueError` match `"scope"`，`fake_host.calls == []`。
- `test_ensure_or_create_entrypoint_session_rejects_ensure_without_slot_key`（line 463-479）：`create_new=False, slot_key=None` → `ValueError` match `"slot_key"`，`fake_host.calls == []`。

**结论**：四个错误路径均被参数化覆盖，每条均验证了异常类型、错误消息和 Host API 未被调用。

### S2-IMPL-F04 — caller-owned timeout contract ✅ 已关闭

**Controller 要求**：在 docstring/README 写清 Service helper 不持有 timeout。

**证据**:

- `submit_entrypoint_turn_and_wait` docstring（`entrypoint_runtime.py:390-391`）："本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。"
- `cancel_entrypoint_run_and_wait` docstring（`entrypoint_runtime.py:443-444`）：同上契约。
- `_wait_for_terminal` docstring（`entrypoint_runtime.py:564-565`）：同上契约。
- `dayu/service/README.md`（line 24-25）："`entrypoint_runtime` 的 submit / cancel wait helper 不持有内部 timeout。调用方负责通过 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。"
- `dayu/README.md` Service 边界描述（line 72）：Service 提供"可复用 entrypoint runtime helper 处理 Session ensure/create、follow-up terminal observation、cancel request 构造和 watcher failure 诊断"。

**结论**：三处 docstring + 两处 README 均已明确 caller-owned timeout 契约。

## S2 Scope 未扩大验证

- **无 CLI command 实现**：`test_entrypoint_runtime_does_not_import_engine_internals`（`test_entrypoint_runtime.py:836-850`）AST 扫描确认 `entrypoint_runtime.py` 不导入 `dayu.engine` 或 `dayu.cli`。
- **无 Fins direct**：`entrypoint_runtime.py` import 列表（line 7-56）只含 `dayu.contracts`、`dayu.host.api`、`dayu.runtime.*`、`dayu.service.host_assembly`，无 `dayu.fins` 或 Fins storage 相关 import。
- **无 init 命令**：无相关代码。
- **不读 Host durable internals**：`entrypoint_runtime.py` 所有 Host 调用均为 public API：`get_run`、`watch_session_events`、`submit_followup`、`cancel_run`、`create_session`、`ensure_session`、`read_outbox_terminal_items`。
- **不改 deferred Host watch return typing**：`_attach_watcher`（line 501）仍使用 `cast(ClosableHostEventIterator, ...)`，与 controller adjudication "deferred-with-owner" 一致。

## Fix 引入新问题检查

对 fix 改动逐路径走读，未发现引入新问题：

1. **F01 fix "already terminal" 路径**：空 queue + 直接 `_wait_for_terminal`。`_wait_for_terminal` 在 queue 为空时 `_drain_available_watcher_items` 返回 `None`，然后 `get_run` 返回终态，进入 `_read_outbox_terminal`。控制流正确，watcher 资源正确不创建（无需清理）。
2. **F01 fix "cancel loses race" 路径**：`HostApiError` catch 后 `get_run` 判断终态 → 保留已 attach watcher → `_wait_for_terminal` 先 drain live event。即使 watcher 已错过 terminal event（extreme race），`get_run` 的终态仍会触发 outbox fallback。watcher 清理在 `finally` 中正确执行。
3. **F01 fix "cancel loses race, still non-terminal" 路径**：`get_run` 仍非终态时 `raise` 原 `HostApiError`。watcher 在 `finally` 中被 `_close_watcher` 正确清理。控制流正确。
4. **F02 fix watcher failure 记录**：`_record_watcher_failure` 只在 `watcher_failure_message is None` 时写入（line 673），避免重复记录覆盖首个错误。`_drain_available_watcher_items` 在 `continue` 后回到 `queue.get_nowait()`，此时 drain task 已退出、queue 可能为空，返回 `None` 使外层走 `get_run` + outbox 路径。无死锁或无限循环风险。
5. **`_observation_error_message` 附加诊断**：在 outbox projection FAILED 或 caught-up-without-match 错误消息后追加 `"; watcher drain failed: ..."`，格式清晰、不破坏原始错误语义。

## Open Questions

无。四个 accepted finding 均有关闭的直接代码与测试证据。

## Residual Risk

- **97% 覆盖率未命中的 8 行**（`entrypoint_runtime.py:317, 478, 645, 674, 680, 769, 818, 858`）：均为边界路径（非字符串 context slot 值、cancel 竞争失败后 run 仍非终态、live event duplicate 去重、重复 watcher failure、空 error message、outbox duplicate 去重、无 watcher failure 时的 error message、非法 poll interval）。这些路径在当前生产路径中触发概率极低，但缺少显式测试。不影响 accepted findings 的关闭。
- **Deferred-with-owner**：`cast(ClosableHostEventIterator, ...)` 仍保留，按 controller adjudication 属于 Host public contract typing refinement，不阻塞 S2。
- **S2 范围外**：本次仍无真实 CLI prompt / interactive smoke 测试；只用 mocked Host public Protocol 验证 Service boundary。

## Conclusion

**pass**

四个 accepted findings 均已关闭：F01 的 cancel race 两分支均已实现并有测试；F02 的 watcher failure 诊断已进入 result/error 且 outbox fallback 路径有测试；F03 的四类参数校验错误路径测试已补齐；F04 的 caller-owned timeout 契约已在三处 docstring + 两处 README 写清。S2 scope 未扩大，fix 未引入新问题。

验证结果：
- `pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py`：**71 passed**
- `pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime`：**97% 覆盖率**
- `pyright dayu/ tests/ utils/`：**0 errors**
