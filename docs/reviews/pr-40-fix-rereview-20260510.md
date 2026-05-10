# PR #40 Fix Re-Review

## Scope

- PR: #40 — `[codex] Host P8 durable attempt governance`
- Branch: `migration/host-p8-attempt-lease-recovery`
- Input review artifacts:
  - `docs/reviews/pr-40-review-20260510-1546.md`
  - `docs/reviews/pr-40-review-20260510-1558.md`
- Input fix report: PR #40 fix Agent 完成报告。
- Re-review mode: narrow fix re-review。只核验 controller-accepted findings 是否关闭，不重新发散做 base-main 全量审查。

## Conclusion

**PASSED**

F1/F2/F3/F4/F5/F7 均已修复。F6 维持 `rejected-with-reason`：同一 attempt 不允许两个有效 owner token 同时存在，1558 review 已将该 finding 复核为不适用。本次 re-review 额外发现 F5 新测试关闭 bundle 时可能与后台 terminal projection commit 竞争，已由 controller 清理为等待 `_project_terminal_run` 完成后再 close，避免测试侧 SQLite connection close 与 `to_thread(COMMIT)` 并发。

## Finding Status

| Finding | Controller decision | Re-review result | Evidence |
| --- | --- | --- | --- |
| F1 `append_in_transaction` 生产路径零测试覆盖 | accepted | **fixed** | `tests/host/test_phase8_attempt_fencing.py` 新增 4 个测试，覆盖正常外层事务 append、owner fenced 回滚、run_id mismatch、terminal draft 拒绝。 |
| F2 `update_state_owner_aware` 绕过注入 clock | accepted | **fixed** | `dayu/host/_run_state_store.py` 改为 `self.clock.now().isoformat()`；相关 lease store 测试补 fake clock 断言。 |
| F3 `AttemptStateStore` legacy clock 注入 | accepted | **fixed** | `AttemptStateStore` 新增显式 `clock: UtcClock`，`create.started_at` 与 `update_state.finished_at` 均使用注入 clock；fixtures 已迁移。 |
| F4 `acquire_new_attempt` IntegrityError 捕获过宽 | accepted | **fixed** | 新增 `_is_attempt_index_unique_violation`，仅 `(run_id, attempt_index)` UNIQUE 冲突映射 BUSY，其它 `IntegrityError` 透传；测试覆盖 BUSY 与非预期 IntegrityError。 |
| F5 context overflow retry acquire 失败无 terminal | accepted；reviewer 裸 append 方案 rejected | **fixed** | `_run_harness.py` 在新 attempt acquire 失败时调用 `_append_overflow_acquire_failure_terminal`，旧 owner 仍有效时走 `_append_terminal_and_close` 原子 owner-scoped terminal close；测试证明 RunStream 收到 `RUN_FAILED(error_code=context_overflow_retry_acquire_failed)`、旧 attempt `FAILED + terminal_event_position`、无裸 `DurableRunEventStore.append` terminal。 |
| F6 多进程 terminal close 真实 CAS 竞争 | rejected-with-reason | **accepted rejection** | 同一 attempt 模型中只有一个当前 owner token；两个有效 token 同时 close 同一 attempt 不成立。1558 review 已将该 finding 列为 prior review resolved。 |
| F7 `ToolFetchMoreHandle*` public surface / `_has_terminal_event` docstring | accepted | **fixed** | `dayu/host/__init__.py` 移除 5 个 dead handle export；public boundary 测试同步；`_has_terminal_event` docstring 收紧为 terminal-only repair 信号。 |

## Controller Cleanup

- 将 `tests/host/test_phase4_overflow_retry.py` 新增测试中的函数体 lazy imports 提升到模块顶部，避免再次引入无必要 seam。
- F5 测试原先在收到 terminal event 后立即 `bundle.close()`；重跑相关测试集合时触发 Python segfault，堆栈显示后台线程仍在 `_host_storage_transaction.py::_commit`，主线程已进入 `HostStorage.close()`。修复为 monkeypatch `_project_terminal_run` 并等待 projection 完成后再关闭 bundle。
- 该清理不改变生产语义，只让测试生命周期与后台 `_run_to_store` 完整收尾一致。

## Validation

已由 fix Agent 报告并由 controller 复核/补跑：

| Command | Result |
| --- | --- |
| `pytest tests/host/test_phase4_overflow_retry.py::test_durable_overflow_retry_acquire_failure_writes_owner_scoped_terminal -q` | `1 passed` |
| `pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_lease_store.py tests/host/test_phase4_overflow_retry.py tests/host/test_phase6_run_state_store.py -q` | `51 passed` |
| `pytest tests/host -q` | `322 passed` |
| `python -m pyright dayu/host tests/host utils` | `0 errors, 0 warnings, 0 informations` |
| `python utils/smoke_host_p8_attempt_lease.py` | 7 scenarios passed |
| `git diff --check` | clean |
| `rg "event_store\\.append\\(host_failure_draft|fetch_more_tool_result|get_tool_fetch_more_handle|_default_harness_for_running_loop|_build_default_harness" dayu/host` | no matches |
| `rg "MARK_RECOVERING_AND_CREATE_ATTEMPT|mark_recovering_and_create_attempt|recovery_attempt_id|recovery_attempt_index" dayu tests utils` | no matches |

## Residual Risks

| Risk | Owner | Status |
| --- | --- | --- |
| `recover_stale_attempts(run_id=None)` 全局扫描路径未单测 | P9 / follow-up test hardening | 不阻塞本 PR fix gate。 |
| `next_attempt_index` 未独立单测 | P9 / follow-up test hardening | 不阻塞本 PR fix gate。 |
| `HostStorage.close()` 对后台 task / to_thread commit 无生命周期保护 | P9 lifecycle | 本次通过测试等待 `_project_terminal_run` 完成避免测试竞态；生产 lifecycle close 语义仍归 P9。 |

## Gate Decision

允许进入 user confirmation + accepted PR fix commit gate。
