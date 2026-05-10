# PR #40 Accepted Fix Re-review

## Scope

- Mode: PR fix re-review (controller-role)
- Target PR: [#40](https://github.com/noho/dayu-agent-r/pull/40)
- Source reviews: `pr-40-review-20260511-0612.md` + `pr-40-review-20260511-0613.md`
- Reviewed commits: latest on `migration/host-p8-attempt-lease-recovery`
- Review scope: 3 accepted fixes only (P8.5/P15/P16 deferred out of scope)
- Output file: `docs/reviews/pr-40-review-20260511-0612-0613-fix-rereview.md`

## Overall Verdict: PASSED

All 3 accepted fixes are correctly implemented, tests pass, pyright is clean,
smoke passes, and no new blockers are introduced.

---

## Fix 1: API surface / docstring convergence — PASSED

**Source findings:** 0612-F2 (API surface tests only negative), 0612-F5 (docstring claims P8 entries not actually exported)

**Changes reviewed:**

- `dayu/host/__init__.py` docstring rewritten: now accurately states "P8 阶段包根只导出 `dayu.host.contracts` 中的强类型契约"，explicitly notes `LocalRunHarness` / `HostToolRuntime` are internal and not package-root exports. No new `from dayu.host._durable_harness import build_durable_harness` or `from dayu.host._run_harness import LocalRunHarness` added.
- `tests/host/test_host_public_api_surface.py`:
  - Added `_EXPECTED_HOST_CONTRACT_EXPORTS` frozenset (48 symbols matching `__all__`).
  - Added `_FORBIDDEN_HOST_ROOT_EXPORTS` frozenset covering `start_run`, `stream_run_events`, `get_run_result`, `get_tool_fetch_more_handle`, `fetch_more_tool_result`, `LocalRunHarness`, `build_durable_harness`, `HostToolRuntime`.
  - Added `test_host_module_exports_exact_contract_surface()` — positive assertion: `host.__all__` exactly equals expected contracts set, length matches, each symbol hasattr.
  - Updated `test_host_module_does_not_export_legacy_helpers()` to use `_FORBIDDEN_HOST_ROOT_EXPORTS` and assert both `__all__` membership and `hasattr` absence for internal/legacy symbols.

**Verification:**
- `pytest tests/host/test_host_public_api_surface.py -q` — 5 passed
- `grep` of `dayu/host/__init__.py` confirms zero occurrences of `LocalRunHarness`, `build_durable_harness`, `HostToolRuntime`
- `__all__` contains exactly 48 contracts symbols; `_EXPECTED_HOST_CONTRACT_EXPORTS` matches

**Verdict:** Fix is complete and correct. Positive assertions exist. Negative assertions expanded. Docstring matches reality.

---

## Fix 2: `update_state_owner_aware` target state validation — PASSED

**Source findings:** 0612-F3 (no target state validation, could regress state machine)

**Changes reviewed:**

- `dayu/host/_run_state_store.py:665-669`:
  ```python
  if state not in _ATTEMPT_FINISHED_STATES:
      raise ValueError(
          "update_state_owner_aware requires finished AttemptState, "
          f"got {state}"
      )
  ```
  Rejects non-finished states (CREATED, RUNNING) at method entry, before any SQL execution.
- `dayu/host/_run_state_store.py:670`: `finished_at_iso` changed from conditional (`if state in _ATTEMPT_FINISHED_STATES else None`) to unconditional `self.clock.now().isoformat()` — correct since the guard ensures only finished states reach this line.
- Docstring updated with `:raises ValueError: state 不是诊断态 / 终态时抛出。`

**Tests added** (in `tests/host/test_phase8_attempt_lease_store.py`):
- `test_update_state_owner_aware_rejects_non_finished_states` — parameterized for `CREATED` and `RUNNING`; asserts `ValueError` raised with message "finished AttemptState"; asserts DB state, `finished_at`, `terminal_event_position`, `failure_summary` all unchanged.
- `test_update_state_owner_aware_allows_diagnostic_state` — STALE passes through CAS, `finished_at` set, `terminal_event_position` is None.
- `test_update_state_owner_aware_allows_terminal_state` — SUCCEEDED passes through CAS, `terminal_event_position` set correctly, `failure_summary` is None.

**Verification:**
- `pytest tests/host/test_phase8_attempt_lease_store.py -q` — 45 passed
- CREATED/RUNNING → ValueError, DB unchanged (confirmed by test)
- STALE/SUCCEEDED → CAS success (confirmed by test)

**Verdict:** Fix is complete, correct, and well-tested. The store layer now has its own defense against state machine regression, independent of caller discipline.

---

## Fix 3: `lease_context` create_task failure coroutine cleanup — PASSED

**Source findings:** 0612-F4 (prior code had `del self._sessions` without coroutine close, causing "was never awaited" warnings)

**Changes reviewed:**

- `dayu/host/_attempt_supervisor.py:572-583`:
  ```python
  renew_coro = self._renew_loop(session=session)
  try:
      renew_task = asyncio.create_task(
          renew_coro,
          name=f"attempt-renew:{attempt_id}",
      )
  except Exception:
      renew_coro.close()
      del self._sessions[attempt_id]
      raise
  ```
  - Coroutine object saved to `renew_coro` before `create_task` call.
  - On exception: `renew_coro.close()` called first (prevents "was never awaited" RuntimeWarning), then `_sessions` cleaned, then original exception re-raised.
  - On success: `session.renew_task = renew_task` as before.

**Test updated** (in `tests/host/test_phase8_attempt_supervisor.py`):
- No longer suppresses RuntimeWarning.
- Wraps in `warnings.catch_warnings(record=True)` + `warnings.simplefilter("always", RuntimeWarning)`.
- After `gc.collect()`, asserts no "was never awaited" in captured warnings.
- Still asserts `supervisor._sessions == {}` after cleanup.

**Verification:**
- `pytest tests/host/test_phase8_attempt_supervisor.py::test_lease_context_cleans_session_on_create_task_failure -q` — 1 passed
- No "was never awaited" warnings observed in test output
- `_sessions` cleanup confirmed

**Verdict:** Fix is complete and correct. Coroutine lifecycle is properly managed: saved → passed to create_task → closed on failure. Test verifies both session cleanup and absence of coroutine leak warnings.

---

## New Blocker Check: NONE

No new blockers introduced. The 3 fixes are scoped, well-tested, and don't interact with each other or with other components.

## Deferred Owner Accuracy: CONFIRMED

The `docs/host/migration-plan.md` Residual Risk Registry (section 6) correctly reflects:

| Item | Owner | Status |
|------|-------|--------|
| `_renew_loop` STORAGE_ERROR exception classification | P8.5 | deferred-with-owner |
| BUSY reason refinement | P8.5 | deferred-with-owner |
| `lease_context` parameter validation | P8.5 | deferred-with-owner |
| Compact diagnostic fact + terminal fact step-by-step append | P8.5 | deferred-with-owner |
| `_LeaseSession.stopped_event` dead sync primitive | P16 | deferred-with-owner |
| `_tool_outcome_name` fallback | P16 | deferred-with-owner |
| Legacy `AttemptStateStore.update_state` CAS protection | P16 | deferred-with-owner |
| Internal module `__all__` cleanup | P16 | deferred-with-owner |
| Schema bootstrap / hard-gate / watchdog | P15 | deferred-with-owner |

The newly added registry entry on line 147 correctly captures 0612/0613 low findings as P8.5 deferred.

No already-deferred P8.5/P15/P16 items were re-opened in the current changes.

## Verification Commands & Results

### 1. Targeted test run
```
$ source .venv/bin/activate && pytest tests/host/test_host_public_api_surface.py tests/host/test_phase8_attempt_lease_store.py tests/host/test_phase8_attempt_supervisor.py::test_lease_context_cleans_session_on_create_task_failure -q
31 passed in 0.21s
```

### 2. Full host test suite
```
$ source .venv/bin/activate && pytest tests/host -q
353 passed in 2.63s
```

### 3. Pyright
```
$ source .venv/bin/activate && python -m pyright dayu/host tests/host utils
0 errors, 0 warnings, 0 informations
```

### 4. P8 smoke
```
$ source .venv/bin/activate && python utils/smoke_host_p8_attempt_lease.py
[s1] owner_acquired=true renewed=True
[s2] busy=True
[s3] action=mark_lost reason=recovery_lease_expired old_state=lost
[s4] late_write=fenced reason=attempt_terminal
[s5] terminal_event_position=2 attempt_state=failed
[s6] observer_caught_up=True
[s7] checkpoint_caught_up=True snapshot_deleted=True memory_recovered=True recovery_mode=checkpoint_rebuild
```

### 5. Git diff --check
```
$ git diff --check
(no output — clean)
```

## Residual Notes

1. The `_EXPECTED_HOST_CONTRACT_EXPORTS` frozenset in the test must be kept in sync with `dayu/host/__init__.py` as contracts evolve. This is an acceptable maintenance cost per the CLAUDE.md "no compatibility code" constraint — the test is the canary for contract changes.
2. The `update_state_owner_aware` DB-unchanged assertion in the rejection test is a strong defense: it verifies not just the exception but that the transaction didn't commit partial state. The test correctly runs the invalid update inside a transaction block, and validates DB state after the transaction is rolled back (by the exception exiting the context manager).
3. The coroutine cleanup pattern (save coro → create_task → close on failure) is idiomatic and robust. The test's use of `warnings.catch_warnings` + `gc.collect()` is the correct way to assert absence of coroutine leak warnings.
