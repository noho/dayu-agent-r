# PR #40 Parallel Review Fix Report

## Scope

- Branch: `migration/host-p8-attempt-lease-recovery`
- Gate: PR review follow-up fix loop
- Role: parallel review fix agent; no commit, no push
- Source findings:
  - `docs/reviews/pr-40-review-20260510-1939.md`
  - `docs/reviews/pr-40-review-20260510-1943.md`
  - `docs/reviews/pr-40-review-20260510-1948.md`

## Fix Status

| Finding | Status | Fix |
| --- | --- | --- |
| 1939-F1 ToolRuntime 吞 `AttemptFencingError` | fixed | `execute_tool_call()` 在 catch-all 前透传 `AttemptFencingError`；组件测试覆盖 append path fencing 不会返回 `ToolFailedOutcome`。 |
| 1943-F1 durable memory observer 非终态 checkpoint 后重启丢 pending facts | fixed | durable observer terminal 投影在同一 observer tx 内从 EventLog 按 `session_id` + `run_id` 重读完整 canonical events，再写 snapshot + checkpoint。 |
| 1943-F2 旧 public `ToolFetchMoreHandle*` contracts | fixed | 删除 contracts dataclass / union / `__all__` 条目，清理旧术语，补 forbidden export 测试。 |
| 1948-F1 `_scope_appender()` durable fail-fast | fixed | durable + 无 owner scope 抛 `RuntimeError`；non-durable test-only fallback 保留。 |
| 1939-F3 `_handle_owner_lost` 普通异常 cleanup | fixed | owner-lost catch sites 用 `try/finally current_active_attempt = None`，避免外层 finally 对同一 attempt 重复 close。 |
| 1939-F4 STALE terminal diagnosis | fixed | `AttemptState.STALE` 纳入 attempt terminal diagnosis，renew / verify_owner CAS miss 均返回 `ATTEMPT_TERMINAL`。 |
| 1939-F5 durable memory clock injection | fixed | `DurableConversationMemoryStore` 注入 UTC clock，`build_durable_harness` 默认传同源 clock，snapshot `updated_at` 可 deterministic。 |

## Deferred / Rejected

| Finding | Decision | Owner / Reason |
| --- | --- | --- |
| 1939-F2 recovery scan TOCTOU | rejected-with-reason | CAS 已正确收敛，无副作用，不修。 |
| 1948-F2 独立 `RUN_ID_MISMATCH` reason | deferred-with-owner | P9 / P16 interface freeze；本轮不扩 enum public/internal protocol。 |
| durable memory repair O(N) | deferred-with-owner | P9 / capacity；本轮只修 correctness，不优化全表扫描性能。 |

## Validation

- `pytest tests/host/test_phase8_tool_runtime_fencing.py -q`: passed, 9 tests.
- `pytest tests/host/test_phase8_durable_memory_recovery.py -q`: passed, 13 tests.
- `pytest tests/host/test_phase8_durable_invariant.py -q`: passed, 14 tests.
- `pytest tests/host/test_phase8_attempt_lease_store.py -q`: passed, 21 tests.
- `pytest tests/host -q`: passed, 332 tests.
- `python -m pyright dayu/host tests/host utils`: passed, 0 errors.
- `python utils/smoke_host_p8_attempt_lease.py`: passed all seven smoke scenarios.
- `git diff --check`: passed.
- legacy default harness / public fetch_more bypass search: no matches.
- `ToolFetchMoreHandle` search: only forbidden-export assertions remain in tests; no production / README public old protocol remains.
