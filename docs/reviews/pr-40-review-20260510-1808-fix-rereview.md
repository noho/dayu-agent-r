# Code Review — PR #40 Follow-up Fix Re-review

## Scope

- Mode: PR fix re-review
- Base artifact: `docs/reviews/pr-40-review-20260510-1808.md`
- Branch: migration/host-p8-attempt-lease-recovery
- Fix commit: `756f150` (committed) + workspace uncommitted changes
- Output file: docs/reviews/pr-40-review-20260510-1808-fix-rereview.md

## Verification Results

| Check | Result |
|---|---|
| `git diff --check` | clean |
| `python -m pyright dayu/host tests/host utils` | 0 errors, 0 warnings |
| `pytest tests/host -q` | 322 passed |
| `pytest -q` | 698 passed |
| `python utils/smoke_host_p8_attempt_lease.py` | 7 scenarios passed |
| `rg "event_store\.append(host_failure_draft\|...\|_build_default_harness" dayu/host` | 无命中 |
| `rg "MARK_RECOVERING_AND_CREATE_ATTEMPT\|..." dayu tests utils` | 无命中 |

## Finding-by-Finding Verdict

### F1 / F2 — compact / worker 异常路径吞 AttemptFencingError → **FIXED**

**修复内容**: `_run_harness.py` 新增 3 个 fencing 捕获点 + `_task_aware_event_stream` + `_append_overflow_acquire_failure_terminal`：

1. **Site 1** (line 845): `proxy.stream_engine_events(...)` 同步抛 `AttemptFencingError` → 优先捕获，路由到 `_handle_owner_lost`。✅
2. **Site 2** (line 903): engine event 主循环 `except Exception` 内 `_append_worker_failure_if_needed` 再抛 `AttemptFencingError` → `try/except AttemptFencingError` 捕获，路由到 `_handle_owner_lost`。✅
3. **Site 3** (line 1028): compact exception `_append_compact_exception_failure` 再抛 `AttemptFencingError` → `try/except AttemptFencingError` 捕获，路由到 `_handle_owner_lost`。✅

**`_handle_owner_lost` 路径验证** (line 1306-1342):
- CAS hit: `supervisor.append_terminal_and_close` 同事务写 `RUN_FAILED(error_code=attempt_lease_lost)` + close attempt LOST + `terminal_event_position` → `lease_exit_stack.aclose()` → 返回 `True`。✅
- CAS miss: `AttemptFencingError` 被捕获，事务 rollback，不写 stale RunEvent → `lease_exit_stack.aclose()` → 返回 `False`。✅

**`_task_aware_event_stream`** (line 729-792): 包装 subscription，与 background_task race：
- subscription 先完成 → yield event，正常路径。✅
- background_task 先完成 → 0.05s drain window 让已落库 event 有机会被拉出 → drain 后退出，避免条件变量永久挂起。✅
- `getattr(sub_iter, "aclose", None)` 模式：`subscribe` 返回类型标注为 `AsyncIterator`，运行时实际为 `AsyncGenerator`（有 `aclose`）。`getattr` 是类型标注与运行时不一致时的标准清理模式，docstring 已说明防御性质。理由成立，不违反 CLAUDE.md `getattr` 约束。✅

**`_append_overflow_acquire_failure_terminal`** (line 1550-1624): 新 attempt acquire 失败时，在旧 attempt 上写 terminal：
- `_can_atomic_terminal_close=True`: 走 `_append_terminal_and_close` 原子路径。✅
- 非 supervisor 路径: `_resolve_attempt_appender` → `PlainRunEventAppender`。✅
- **边缘场景**: 若旧 attempt 在 acquire 期间也被 fencing（compact 刚验证 owner 有效后、acquire 前极端窗口），`_append_terminal_and_close` CAS miss → `AttemptFencingError` 未被本方法捕获，向上冒泡。但 `_task_aware_event_stream` 会在 background_task 异常退出后 drain + 退出，RunStream 不会永久 hang。此窗口极窄（需旧 attempt 在 compact 验证后到 acquire 前被 fencing），且有 `get_run_result()` 补偿路径，风险可接受。✅

**未新增 compact-fence 专用测试**: 现有 fencing CAS 测试（`test_phase8_attempt_fencing.py`）已覆盖 `AttemptFencingError` 在 `append_terminal_and_close` / `scoped_appender` 的 CAS miss 行为。compact-fence 集成测试缺失但属于端到端测试范畴，当前可接受，建议 P9 补齐。

### F3 — `_diagnose_fence` owner token hash 比较未使用 timing-safe compare → **FIXED**

`_run_state_store.py` line 1146: `if not hmac.compare_digest(current_hash, expected_hash):`。`import hmac` 已在 line 16。行为无漂移，类型无变化。✅

### F4 — durable memory repair scan O(n) → **DEFERRED-WITH-OWNER: P9 / capacity**

未被误修、误删或丢失 owner。修复 commit 未触碰 `_conversation_memory_durable.py` 的 scan 逻辑（仅 `datetime.now` → `clock.now()` 的时钟注入改动）。deferred 状态确认。✅

### F5 — `RunInputContextSnapshotBuiltData` 等嵌套类型未从 `dayu.host` 导出 → **FIXED**

- `__init__.py`: 已补导入 `RunInputContextMeta`、`RunInputContextSnapshotBuiltData`、`RunInputMessageSummary`、`RunInputToolSchemaSummary`，并加入 `__all__`。✅
- `test_phase1_public_boundary.py`: `EXPECTED_EXPORTS` 已同步新增 4 个类型。✅
- `README.md` public surface 段已补充 "Run input context fact data" 条目。✅
- 确认这只是补齐已属于 `RunEventData` union 的类型，不恢复 legacy public surface。✅

## Residual Checks

| 检查项 | 状态 |
|---|---|
| 无 legacy `fetch_more_tool_result` / `get_tool_fetch_more_handle` / `_default_harness_for_running_loop` / `_build_default_harness` | ✅ 无命中 |
| 无 Host-owned unscoped `event_store.append(host_failure_draft(...))` | ✅ 仅 `_append_terminal_and_close` (supervisor 原子路径) 和 `_handle_owner_lost` (CAS 路径) 使用 `host_failure_draft`，均通过 scoped appender |
| `RunStream` public dataclass 字段无变化，无新增 public close API | ✅ 仅 `handle` + `events`，无变化 |
| `MARK_RECOVERING_AND_CREATE_ATTEMPT` / `mark_recovering_and_create_attempt` / `recovery_attempt_id` / `recovery_attempt_index` 未回 source tree | ✅ 无命中 |
| `docs/host/migration-plan.md` 改动（861→174 行）为 unrelated 流程精简 | ✅ 不影响代码行为，不作 fix 证据 |

## New Findings

### N1-未修复-低-`_append_overflow_acquire_failure_terminal` 未捕获自身 `AttemptFencingError`

- **入口/函数**: `_run_to_store` line 1076 `except Exception as acquire_exc:` → `_append_overflow_acquire_failure_terminal`
- **文件(行号)**: `_run_harness.py:1076-1092`, `_run_harness.py:1609-1624`
- **输入场景**: compact 成功后，`_begin_attempt_if_durable` acquire 新 attempt 时旧 attempt 已被 fencing（极端时间窗口：compact 验证 owner 到 acquire 之间）。`_append_overflow_acquire_failure_terminal` 内 `_append_terminal_and_close` CAS miss 抛 `AttemptFencingError`。
- **实际行为**: `AttemptFencingError` 不被 `except Exception as acquire_exc:` 捕获（该 handler 在 `_append_overflow_acquire_failure_terminal` 外层），向上冒泡经 `_run_to_store` 的 `finally` 块，background task 以异常退出。`_task_aware_event_stream` 在 background_task 退出后 drain 0.05s + 退出，RunStream 不永久 hang。
- **预期行为**: 与 Site 1/2/3 一致，应捕获 `AttemptFencingError` 并路由到 `_handle_owner_lost`（或至少 log + graceful return）。
- **影响**: RunStream 不 hang（有 drain safety net），但 background task 以 uncaught exception 退出，日志中会显示为未处理错误而非 typed `attempt_lease_lost`。
- **建议改法**: 在 `_run_to_store` line 1076 增加 `except AttemptFencingError` 分支，路由到 `_handle_owner_lost` 或直接 log + return。
- **严重程度**: 低（窗口极窄，stream 不 hang，有补偿路径）

## Conclusion

**CONDITIONALLY PASSED**

F1-F5 全部 fixed 或 deferred-with-owner。验证命令全部通过。新增 `_task_aware_event_stream` 解决了 CAS miss 后 subscription 永久阻塞的根本问题，drain window 设计合理。遗留 N1（low severity）为极端窗口下的诊断准确性问题，不阻塞 merge。建议 P9 补齐 compact-fence 集成测试。

## Controller Decision / N1 Fix Status

| ID | Severity | Decision | Status | Fix Summary |
|---|---|---|---|---|
| N1 | low | accepted | fixed | `_run_harness.py` 在 context overflow retry 的 new attempt acquire-failure 分支中，将 `_append_overflow_acquire_failure_terminal(...)` 外包 `try/except AttemptFencingError`。CAS hit 时仍由旧 owner-scoped terminal close 写入 `RUN_FAILED(error_code=context_overflow_retry_acquire_failed)` 并关闭旧 attempt；CAS miss / old owner lost 时路由到 `_handle_owner_lost(..., loss_reason=FENCED, ...)`，由 `AttemptSupervisor.append_terminal_and_close` 尝试 `RUN_FAILED(error_code=attempt_lease_lost)` + LOST close，若 CAS 仍 miss 则不写 stale RunEvent，且 `_run_to_store` background task 不再裸冒泡 `AttemptFencingError`。 |

### N1 Regression Test

新增 `tests/host/test_phase4_overflow_retry.py::test_durable_overflow_acquire_failure_terminal_fencing_routes_owner_lost`:

- 模拟 context overflow compact 成功后，新 attempt acquire 抛 `AttemptFencingError`；
- 再模拟旧 attempt terminal close 的 `append_terminal_and_close` CAS miss 抛 `AttemptFencingError`；
- 断言 RunStream 在无 terminal RunEvent 的 CAS miss 路径也能结束，不 hang；
- 断言 `_handle_owner_lost` 路径再次尝试 `append_terminal_and_close`；
- 断言没有 Host-owned stale `RUN_FAILED` terminal RunEvent，也没有 `host.run.background_task_failed` 未捕获后台异常日志；
- 断言没有经 `DurableRunEventStore.append` 裸写 terminal。

### N1 Follow-up Validation

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py -q` | 17 passed |
| `source .venv/bin/activate && pytest tests/host -q` | 323 passed |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host utils` | 0 errors, 0 warnings |
| `python utils/smoke_host_p8_attempt_lease.py` | s1-s7 全绿 |
| `git diff --check` | clean |
| `rg "event_store\.append\(host_failure_draft\|fetch_more_tool_result\|get_tool_fetch_more_handle\|_default_harness_for_running_loop\|_build_default_harness" dayu/host` | no matches |
| `rg "MARK_RECOVERING_AND_CREATE_ATTEMPT\|mark_recovering_and_create_attempt\|recovery_attempt_id\|recovery_attempt_index" dayu tests utils` | no matches |
