# PR #40 Parallel Review Fix Re-Review

## Scope

- Branch: `migration/host-p8-attempt-lease-recovery`
- Gate: PR review fix re-review (reviewer role)
- Source findings: 1939, 1943, 1948
- Fix report: `docs/reviews/pr-40-parallel-review-fix-report-20260510.md`
- Constraint: read-only, no code modification, no commit

## Per-Finding Verdict

### 1939-F1: ToolRuntime catch-all 吞 `AttemptFencingError`

**Verdict: FIXED**

- `dayu/host/_tool_runtime.py:519-521`: `except AttemptFencingError: raise` 位于 `except Exception` catch-all 之前，fencing 信号不会被吞。
- `tests/host/test_phase8_tool_runtime_fencing.py:403-436`: regression 测试 `test_execute_tool_call_propagates_attempt_fencing_error_from_append_path()` 覆盖 append path fencing 传播，确认不返回 `ToolFailedOutcome`。

### 1943-F1: durable memory observer 非终态 checkpoint 后重启丢 pending facts

**Verdict: FIXED**

- `dayu/host/_memory_projection.py:171-181`: terminal 投影在同一 observer tx 内调用 `self.event_reader.fetch_canonical_events_for_run_in_transaction(tx=tx, ...)` 从 EventLog 重读完整 canonical events，不再依赖进程内 `_pending_by_run`。
- `dayu/host/_durable_event_store.py:693-725`: `fetch_canonical_events_for_run_in_transaction()` 按 `session_id` + `run_id` 读取，`event_position ASC` 排序，在 caller 事务内执行。
- `tests/host/test_phase8_durable_memory_recovery.py:276-340`: regression 测试 `test_terminal_projection_rereads_run_events_after_pending_checkpoint_restart()` 覆盖 checkpoint 后重启场景。

### 1943-F2: 旧 public `ToolFetchMoreHandle*` contracts

**Verdict: FIXED**

- `dayu/host/contracts.py:916-962`: `__all__` 不含任何 `ToolFetchMoreHandle*` 符号；源文件中无 `ToolFetchMoreHandle` dataclass 定义。
- `tests/host/test_phase2_tool_runtime_boundary.py:220-237`: forbidden-export 测试确认旧符号不在 `__all__` 中。
- grep 扫描确认：`dayu/` 下无 `ToolFetchMoreHandle` 残留，仅 test 阶段断言存在。

### 1948-F1: `_scope_appender()` durable fail-fast

**Verdict: FIXED**

- `dayu/host/_run_harness.py:588-615`: `_scope_appender()` 在 `is_durable=True` 且无 owner scope 时抛 `RuntimeError`；`is_durable=False` 时 fallback 到 `PlainRunEventAppender`。
- `tests/host/test_phase8_durable_invariant.py:383-416`: 两个 regression 测试覆盖 durable fail-fast 和 non-durable fallback 两条路径。

### 1939-F3: `_handle_owner_lost` 普通异常后 active attempt 未清理

**Verdict: FIXED**

- `dayu/host/_run_harness.py`: 所有 `_handle_owner_lost` 调用点（lines 855-869, 882-892, 903-916, 927-942, 1053-1066, 1107-1117）均使用 `try/finally: current_active_attempt = None` 包裹，避免 finally 对同一 attempt 重复 close。
- `tests/host/test_phase8_attempt_supervisor.py:1654-1764`: regression 测试 `test_owner_lost_handler_non_fencing_error_clears_active_attempt()` 覆盖非 fencing 异常路径。

### 1939-F4: `AttemptState.STALE` fencing 诊断未归类为 terminal

**Verdict: FIXED**

- `dayu/host/_run_state_store.py:57-66`: `_ATTEMPT_TERMINAL_STATES` 包含 `AttemptState.STALE`。
- `dayu/host/_run_state_store.py:1126-1135`: `_diagnose_fence()` 将 STALE 正确映射为 `ATTEMPT_TERMINAL`。
- `tests/host/test_phase8_attempt_lease_store.py:450-489, 584-619`: 两个 regression 测试覆盖 renew terminal 和 verify_owner 的 STALE 诊断。

### 1939-F5: durable memory snapshot `updated_at` 使用注入 clock

**Verdict: FIXED**

- `dayu/host/_conversation_memory_durable.py:150`: `clock: UtcClock = field(default_factory=_SystemUtcClock)`。
- `dayu/host/_conversation_memory_durable.py:517`: `updated_at = self.clock.now().isoformat()` 使用注入 clock。
- `dayu/host/_durable_harness.py:204-215`: `build_durable_harness()` 将同源 clock 传入 memory store 和 observer。
- `tests/host/test_phase8_durable_memory_recovery.py:344-374`: regression 测试 `test_durable_memory_snapshot_updated_at_uses_injected_clock()` 覆盖 deterministic clock。

## Deferred / Rejected Findings

### 1939-F2: recovery scan TOCTOU

**Verdict: correctly rejected-with-reason**

CAS 已正确收敛，无副作用。代码确认 recovery scan 使用 owner CAS 写入，不产生竞态问题。

### 1948-F2: 独立 `RUN_ID_MISMATCH` reason

**Verdict: correctly deferred-with-owner**

Owner 为 P9 / P16 interface freeze。当前 `_verify_run_id_matches()` 使用通用 reason，不影响功能正确性。

### durable memory repair O(N) 全 EventLog 扫描

**Verdict: correctly deferred-with-owner**

Owner 为 P9 / capacity。当前实现仅修 correctness，不优化性能。

## Validation Results

| Check | Result |
| --- | --- |
| `pytest tests/host/test_phase8_tool_runtime_fencing.py -q` | 9 passed |
| `pytest tests/host/test_phase8_durable_memory_recovery.py -q` | 13 passed |
| `pytest tests/host/test_phase8_durable_invariant.py -q` | 14 passed |
| `pytest tests/host/test_phase8_attempt_lease_store.py -q` | 21 passed |
| `pytest tests/host -q` | 332 passed |
| `python -m pyright dayu/host tests/host utils` | 0 errors, 0 warnings, 0 informations |
| `python utils/smoke_host_p8_attempt_lease.py` | all 7 scenarios passed |
| `git diff --check` | clean |
| `ToolFetchMoreHandle` residual scan | only forbidden-export test assertions remain |
| legacy default harness bypass scan | no matches |

## New Issues Found

None. All fixes are correctly implemented with proper regression test coverage. No new issues discovered during re-review.

## Conclusion

**PASSED**

All 7 accepted findings have been correctly fixed with proper regression tests. All 3 deferred/rejected findings have correct status and justification. Full test suite (332 tests), pyright, smoke script, and whitespace checks all pass clean. No new issues found.
