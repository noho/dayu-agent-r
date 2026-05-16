# Full Repository Deepreview Fix Re-Review — AgentDS — 2026-05-16 21:27

## Scope

- Mode: fix re-review（只审 Codex fix diff，不做全仓 review）
- Branch: feat/host-phase8-projection-core-event-stream
- Controller 裁决：`docs/reviews/repo-review-controller-adjudication-20260516-2109.md`
- Fix artifact：`docs/reviews/repo-review-fix-codex-20260516.md`
- 输入 review artifacts：`docs/reviews/repo-review-20260516-2105.md`、`docs/reviews/repo-review-20260516-2059.md`
- Reviewed fix scope：DR-ALL-A1 到 DR-ALL-A5，14 个文件，+620 / -40 行

## Conclusion

**PASS**

5 项 accepted fix 均完整实现，与 Controller 裁决边界一致，验证通过（529 passed, pyright 0 errors），未引入回归。

---

## Fix-by-Fix Verification

### DR-ALL-A1：RuntimeFileLock active token

- `acquire():152` — `self._active_token is not None and not self._active_token.released` 守卫正确拒绝同实例重叠 acquire。
- `acquire():171` — token 创建后登记 `self._active_token = token`，统一手动/context 两条路径。
- `__enter__():181` — 委托给 `self.acquire()`，不再重复 token 登记逻辑。
- `__exit__():200` — `if token is not None:` 守卫正确处理 acquire 失败后 context 未持有 token 的情况。

测试：`test_nested_context_manager_on_same_instance_fails_fast`、`test_manual_acquire_inside_context_fails_fast`、`test_context_enter_after_manual_acquire_fails_fast`、`test_manual_release_allows_same_instance_reacquire` — 全部通过，覆盖嵌套 context、context 内 manual acquire、manual acquire 后 context enter、manual release 后 reacquire。

### DR-ALL-A2：HostEventView public event_class

- `HostEventClass` StrEnum（`api.py:323`）四成员与 durable `EventClass` 一一对应。
- `HostEventView.event_class: HostEventClass`（`api.py:1879`），`__post_init__` 包含 `isinstance` 校验（`api.py:1897`）。
- `read_api.py:213` 映射 `HostEventClass(row.event_class.value)` — 与 durable `EventClass` value 字符串一致，不会构造失败。
- 导出链路完整：`api.py.__all__` → `__init__.py.__all__` → `__init__.py` import；`test_package_exports.py` 包含 `HostEventClass`。
- README：`stream_run_events` 描述增加 `HostEventClass` 映射说明；`HostEventView` 字段列表增加 `event_class`。

测试：`test_stream_run_events_exposes_event_class_for_preview_rows` 证明 PREVIEW row 进入 public stream 时 `event_class is HostEventClass.PREVIEW`，caller 可区分 CANONICAL_FACT 与 PREVIEW。

### DR-ALL-A3：terminal_closeout terminal status 配对

- `_TERMINAL_STATUS_PAIRS`（`run_transition.py:95`）定义 4 组合法配对。
- `_terminal_status_pair_is_compatible()`（`run_transition.py:3652`）直接检查成员关系。
- `_validate_terminal_input():3633-3637` 在个体状态校验通过后增加配对校验，不兼容组合抛 `HostDurableError("terminal Attempt and Run status pair is invalid")`。
- `_attempt_terminal_event_type` / `_run_terminal_event_type` 新增 CANCELLED 分支（`run_transition.py:3335,3350`），不再将其视为 unsupported。
- `terminal_closeout_in_transaction` 通过 `_terminal_attempt_row_for_closeout` / `_terminal_run_row_for_closeout`（`run_transition.py:1167-1241`）将 CANCELLED 终态路由到既有 CAS helper `cancel_running_attempt_row` / `cancel_running_run_row`，不复制 SQL。
- 旧 rejected test 的 parametrize 从已合法化的 `(CANCELLED, FAILED)` / `(FAILED, CANCELLED)` 更新为 `(SUCCEEDED, FAILED)` / `(SUSPENDED, SUCCEEDED)`，分别覆盖跨类型非法配对和非终态拒绝。

测试：`test_terminal_closeout_accepts_compatible_terminal_status_pairs` 参数化覆盖 4 类合法配对；CANCELLED 路径的 `mark_running` 前置正确满足 `cancel_running_attempt_row` CAS 的 RUNNING 源状态要求。

### DR-ALL-A4：after_commit callback 全量尝试

- `_run_after_commit():333-346`（`transaction.py`）— 循环内 try/except 收集首个失败，循环结束后统一抛 `HostAfterCommitError`。
- `first_error_index` 保留第一个失败 callback 的 enumerate index，语义精确。

测试：`test_after_commit_failure_still_attempts_later_callbacks` — 第一个 callback 抛 `RuntimeError`，第二个 callback 记录 `"second"`；断言 `callback_events == ["first", "second"]`，`error_info.value.callback_index == 0`，durable row 已 commit（`_count_rows(...) == 1`）。

### DR-ALL-A5：WaitPoller adapter 普通异常隔离

- `wait_adapter.py:347,352` — `except RuntimeError` → `except Exception`，覆盖 `ValueError`、`ConnectionError`、`OSError` 等普通异常。
- 不捕获 `BaseException`（`KeyboardInterrupt`、`SystemExit` 仍传播）。
- `WaitPollAdapter` Protocol docstring 从 `:raises RuntimeError:` 更新为 `:raises Exception:`（`wait_adapter.py:80,90`）。
- README：poller 描述增加单条异常隔离说明。

测试：`test_adapter_non_runtime_exception_isolated_per_wait_record` — `_AbandonValueErrorThenNotReadyAdapter.abandon_wait` 抛 `ValueError`；断言 `result.observed == 2`、`result.adapter_errors == 1`、`result.not_ready == 1`、`adapter.polled == [followup_wait_id]`，证明单条异常不阻断后续 record。

---

## Regression Surface

- 全量 Host + Runtime 测试：529 passed in 7.28s
- pyright：0 errors, 0 warnings, 0 informations
- git diff --check：无空白问题
- 修改文件全部在 Controller 允许范围内；未触碰 Engine、Fins、Service、UI、schema version / DDL

## Open Questions

无。

## Residual Risk

- CANCELLED terminal closeout 路径依赖 `cancel_running_attempt_row` CAS（要求 Attempt 当前 RUNNING）；Attempt 处于 STARTING 时的取消仍由 pre-dispatch / active cancel primitive 负责，不在本轮 fix scope。
- `HostEventClass` 与 durable `EventClass` 的 value 字符串一致性无编译期强制（两者为独立 StrEnum），若未来 durable `EventClass` 新增成员而未同步 public `HostEventClass`，`HostEventClass(row.event_class.value)` 将在运行时抛 `ValueError`。当前四个成员完全对齐，风险标记为远期维护注意项。
