# WU-CLI-01 / CLI-01-S2 Implementation Re-Review (AgentMiMo)

## Scope

- Mode: current changes (unstaged + untracked, relative to main)
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-01-s2-implementation-rereview-mimo.md`
- Review target: controller adjudication accepted findings S2-IMPL-F01 ~ S2-IMPL-F04 fix 后状态
- Input artifacts:
  - `docs/reviews/wu-cli-01-s2-implementation-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`
  - `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`
  - `docs/reviews/wu-cli-01-s2-implementation-review-ds.md`

## Verification

### 验证命令

```
pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q
→ 71 passed

pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q
→ 18 passed, coverage 97%

pyright dayu/service/entrypoint_runtime.py tests/service/test_entrypoint_runtime.py
→ 0 errors, 0 warnings, 0 informations
```

### S2-IMPL-F01: cancel race — 已关闭 ✅

**Fix 内容**：

1. `cancel_entrypoint_run_and_wait` 初始 `get_run(...)` 后检查 `_is_terminal_run_status(run_snapshot.status)`（line 450）。已终态时跳过 `cancel_run`、不 attach watcher，直接走 `_wait_for_terminal` → outbox fallback（lines 451-460）。
2. `cancel_run` 抛 `HostApiError` 后 catch（line 475），再 `get_run` 检查最新状态（line 476）。若已终态则不 re-raise，保留已 attach watcher 继续 `_wait_for_terminal`（lines 477-487）。若仍非终态则 re-raise 原始错误。

**证据**：

- 代码：`entrypoint_runtime.py:448-489` — 完整 cancel 函数含两个 race 防御分支。
- 测试 `test_cancel_entrypoint_run_skips_cancel_when_initial_snapshot_is_terminal`（line 771）：`run_statuses=(RunStatus.SUCCEEDED,)`，断言 `cancel_requests == []`、`watchers == []`、result 来自 `OUTBOX_READ`。确认初始终态跳过 cancel。
- 测试 `test_cancel_entrypoint_run_continues_wait_when_cancel_loses_terminal_race`（line 798）：`cancel_error=HostApiError(INVALID_STATE)` + `run_statuses=(RUNNING, SUCCEEDED)`，断言 watcher 被关闭、result 来自 `OUTBOX_READ`、call sequence 包含 `get_run` re-check。确认 cancel 失败后继续 wait。

**判定**：fix 正确覆盖了 controller adjudication 要求的两种 race 场景。初始终态检查避免了无意义的 cancel_run 调用；cancel 竞争失败后不丢弃已 attach watcher，通过 public observation 继续获取终态。

### S2-IMPL-F02: watcher failure 诊断 — 已关闭 ✅

**Fix 内容**：

1. `_TerminalObservationState` 新增 `watcher_failure_message: str | None`（line 249）。
2. 新增 `_record_watcher_failure` helper（line 664）：记录首个 watcher drain 失败的 `error_type: message` 诊断。
3. `_drain_available_watcher_items` 遇 `_WatcherFailure` 时调用 `_record_watcher_failure` 而非静默 `continue`（line 610）。
4. `EntrypointRunTerminalResult` 新增 `watcher_failure_message: str | None`（line 199），live event 和 outbox 路径均传播此字段。
5. outbox projection error / caught-up-without-match 错误消息也附带 watcher failure 诊断（`_observation_error_message`，line 807）。

**证据**：

- 代码：`entrypoint_runtime.py:249, 609-611, 660, 664-680, 773-774, 803, 807-818` — 完整诊断链路。
- 测试 `test_submit_entrypoint_turn_records_watcher_failure_and_uses_outbox`（line 568）：`submit_watcher_errors=(RuntimeError("watch stream disconnected"),)`，断言 `result.watcher_failure_message` 包含 `"RuntimeError"` 和 `"watch stream disconnected"`，且 result 来自 `OUTBOX_READ`。确认 watcher failure → outbox fallback 路径有测试覆盖。

**判定**：fix 完全满足 controller adjudication 要求——watcher failure 不再静默丢弃，诊断进入 terminal result 和 error message，且有测试覆盖 watcher failure → outbox fallback 路径。

### S2-IMPL-F03: 参数校验错误路径测试 — 已关闭 ✅

**Fix 内容**：新增 4 个测试覆盖 `ensure_or_create_entrypoint_session` 的 ValueError 路径。

**证据**：

- `test_ensure_or_create_entrypoint_session_rejects_create_without_context`（line 403）：`create_new=True, create_context=None` → `pytest.raises(ValueError, match="create_context")`。
- `test_ensure_or_create_entrypoint_session_rejects_create_without_request_id`（line 424）：`create_new=True, create_client_request_id=None` → `pytest.raises(ValueError, match="create_client_request_id")`。
- `test_ensure_or_create_entrypoint_session_rejects_ensure_without_scope`（line 445）：`create_new=False, scope=None` → `pytest.raises(ValueError, match="scope")`。
- `test_ensure_or_create_entrypoint_session_rejects_ensure_without_slot_key`（line 464）：`create_new=False, slot_key=None` → `pytest.raises(ValueError, match="slot_key")`。
- 每个测试均断言 `fake_host.calls == []`，确认校验在 Host 调用前触发。

**判定**：4 条参数校验错误路径全部有测试锁定。

### S2-IMPL-F04: caller-owned timeout contract — 已关闭 ✅

**Fix 内容**：三个 public/private helper 的 docstring 均明确 caller-owned timeout。

**证据**：

- `submit_entrypoint_turn_and_wait` docstring（line 390-391）："本 helper 不持有内部 timeout。调用方必须通过外层 task cancellation、``asyncio.wait_for(...)`` 或显式 cancel 请求控制等待生命周期。"
- `cancel_entrypoint_run_and_wait` docstring（line 443-444）：同上。
- `_wait_for_terminal` docstring（line 564-565）：同上。
- `dayu/service/README.md` diff：新增段落 "`entrypoint_runtime` 的 submit / cancel wait helper 不持有内部 timeout。调用方负责通过 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。"
- `dayu/README.md` diff：同步更新 Service 装配描述。

**判定**：contract 已在 docstring 和 README 中写清，满足 controller adjudication 的 documentation fix 要求。

### S2 Scope 未扩大确认 ✅

- 未实现 S3-S7 / CLI command / Fins direct / init。
- 未读取 Host durable internals；只使用 `Host` Protocol 的 `get_run`、`cancel_run`、`watch_session_events`、`submit_followup`、`ensure_session`、`create_session`、`read_outbox_terminal_items`。
- `_attach_watcher` 仍保留 `cast(ClosableHostEventIterator, ...)`，未改 deferred Host watch return typing。
- 未新增 S2 scope 外的 import：`entrypoint_runtime.py` 只导入 `dayu.host.api`、`dayu.runtime`、`dayu.service.host_assembly`、`dayu.contracts`。
- 测试文件只导入 S2 scope 内的符号。

### Fix 引入新问题检查 ✅

逐行走读 fix 后代码，未发现新问题：

1. **`cancel_entrypoint_run_and_wait` 终态跳过分支**（lines 450-460）：创建空 queue 直接进 `_wait_for_terminal`，`_wait_for_terminal` 首轮 drain 无 item → `get_run` 已终态 → outbox read 命中。控制流正确。
2. **`cancel_entrypoint_run_and_wait` HostApiError catch**（lines 475-478）：catch 后 re-check `get_run`，非终态 re-raise。终态时不 re-raise 继续 `_wait_for_terminal`，watcher 在 `finally` 中正确关闭。异常不会被吞掉。
3. **`_record_watcher_failure` 幂等**（lines 673-674）：只记录首个 failure，后续 failure 被忽略。这是合理设计——首个 failure 最具诊断价值。
4. **`_observation_error_message` 附加 watcher 诊断**（lines 816-818）：用 `"; "` 分隔，不影响原始错误消息可读性。
5. **`EntrypointRunTerminalResult.watcher_failure_message`**（line 199）：`str | None`，frozen dataclass，不影响现有 consumers。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Deferred-with-owner 未变**：`_attach_watcher` 仍保留 `cast(ClosableHostEventIterator, ...)`，按 controller adjudication 属于 Host public contract typing refinement，不阻塞 S2。
- **Coverage missing lines**：97% 覆盖率，8 行未覆盖均为防御性边界（`_string_context_slot_values` 类型错误、`_record_watcher_failure` 幂等早退、`_require_positive_poll_interval` 非正数、outbox 重复 dedup 等），不影响 S2 正确性。
- **S3 真实 CLI 路径未验证**：S2 只用 mocked Host public Protocol 验证 Service boundary，真实 CLI interactive path 留给 S3。

## Conclusion

**pass**

4 项 accepted findings 全部关闭，fix 正确且有测试覆盖，未引入新问题，S2 scope 未扩大。验证命令全部通过（71 tests passed, coverage 97%, pyright 0 errors）。
