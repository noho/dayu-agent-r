# PR 68 Post-Draft Re-Review: Reactive Compaction Budget Hardening

- Reviewer: AgentMiMo
- Date: 2026-05-23
- Gate: P12.5 reactive compaction budget hardening fix
- Scope: uncommitted diff on `feat/phase-12-5-conversation-memory-optimize`
- Controller validation: pytest 177 passed; pyright 0 errors; git diff --check clean

## Verdict

**PASS**

No blocking findings.

## Review Criteria & Evidence

### 1. Proactive-only budget hard threshold reject / Reactive bypass

**Requirement:** `run_compaction_operation` must only apply compact 后 budget hard threshold reject on proactive path; reactive path must not be blocked by inaccurate estimates.

**Evidence:**

- `dayu/host/compaction_operation.py:208-219` — `_requires_budget_acceptance()` returns `True` only when `trigger_source is ContextCompactionTriggerSource.PROACTIVE`.
- `dayu/host/compaction_operation.py:164-191` — budget gate wrapped with `if _requires_budget_acceptance(request) and (...):`. Reactive requests skip the entire `>=` check.
- Test `test_run_compaction_operation_accepts_reactive_budget_estimate_overflow` (line 228-248) uses `_HardThresholdOnceCompactor` with `REACTIVE` trigger, asserts `accepted_candidate is not None` and `rejected_attempts == 0`.
- Existing test `test_run_compaction_operation_retries_hard_threshold_after_compact` (line 206-225) confirms proactive path still rejects on first attempt and retries.

**Result:** PASS. Reactive path bypasses estimate-based hard threshold gate; proactive path retains it.

### 2. Default reactive compaction limit = 2, with per-policy override

**Requirement:** Default `max_reactive_compactions_per_run` must be 2; per-policy override must still allow setting to 1.

**Evidence:**

- `dayu/host/context_policy.py:21` — `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2`.
- `dayu/host/context_policy.py:58` — `ContextBudgetPolicy.max_reactive_compactions_per_run: int` field, validated as positive int.
- `dayu/host/context_policy.py:168` — `default_context_budget_policy()` defaults `max_reactive_compactions_per_run` to `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`.
- `tests/host/test_context_policy.py:24-27` — asserts `policy.max_reactive_compactions_per_run == DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`.
- `tests/host/test_engine_ingest_mapping.py:687-688` — `_reactive_policy(max_reactive_compactions_per_run=1)` override works correctly in fail-closed test.

**Result:** PASS. Default is 2; override to 1 is supported and tested.

### 3. EngineEventIngestor reactive count gate allows 2nd request, fails closed at limit

**Requirement:** Engine ingest must allow a second reactive compact request within the limit, and fail closed when the limit is reached.

**Evidence:**

- `dayu/host/engine_ingest.py:1141` — `if compact_count >= policy.max_reactive_compactions_per_run:` triggers fail-closed. With default=2, `compact_count=1` (one existing) passes; `compact_count=2` blocks.
- `dayu/host/engine_ingest.py:1322-1344` — `_committed_reactive_compact_count()` counts `CONTEXT_COMPACTION_REQUESTED` events with `trigger_source=reactive` for the run.
- `tests/host/test_engine_ingest_mapping.py:697-730` — `test_reactive_compact_count_allows_second_operation`: seeds 1 existing reactive request, calls `ingest_async` with default policy (limit=2), asserts `ACCEPTED` and recovery attempt created.
- `tests/host/test_engine_ingest_mapping.py:652-693` — `test_reactive_compact_count_limit_fails_closed_without_second_attempt`: uses `max_reactive_compactions_per_run=1` override, seeds 1 existing request, asserts `FAILED` with `reactive_compact_limit_reached`.

**Result:** PASS. Second reactive request allowed within limit; fail-closed at limit boundary works correctly.

### 4. Test coverage for key scenarios

**Requirement:** Tests must cover reactive budget estimate overflow accepted, second reactive compact allowed, and override=1 fail-closed.

**Evidence:**

| Scenario | Test | File:Line |
|----------|------|-----------|
| Reactive budget estimate overflow accepted | `test_run_compaction_operation_accepts_reactive_budget_estimate_overflow` | `test_compaction_operation.py:228` |
| Second reactive compact allowed (default=2) | `test_reactive_compact_count_allows_second_operation` | `test_engine_ingest_mapping.py:697` |
| Override=1 fail-closed | `test_reactive_compact_count_limit_fails_closed_without_second_attempt` | `test_engine_ingest_mapping.py:652` |
| Proactive budget gate still rejects | `test_run_compaction_operation_retries_hard_threshold_after_compact` | `test_compaction_operation.py:206` |
| Default policy reactive limit assertion | `test_default_context_budget_policy_sets_compaction_attempt_budget` | `test_context_policy.py:17` |

**Result:** PASS. All five scenarios are covered by dedicated tests.

### 5. Documentation consistency with adjudication

**Requirement:** docs/README/control must align with the adjudication — no raw evidence aggregate prompt budget guard as pending item.

**Evidence:**

- `dayu/host/README.md:258` — Changed "预算硬阈值校验" to "proactive 预算硬阈值校验" and added reactive path description with `max_reactive_compactions_per_run` and fail-closed semantics.
- `docs/host/design.md:2665-2667` — Proactive path uses estimate for dispatch gating; reactive path accepts quality-passed compact and relies on real dispatch/overflow loop. Default limit 2.
- `docs/host/design.md:2771-2773` — Compact invariants updated: proactive fails on budget; reactive can retry within limit, then fail closed.
- `docs/host/design.md:2831` — Reactive path described as using real recovery dispatch loop, not estimate-based proof.
- `docs/host/implementation-control.md:224-225` — Gate description updated to reflect reactive budget hardening adjudication.
- `docs/host/implementation-control.md:134-136` — F1 residual updated from "raw evidence aggregate prompt budget guard" to "reactive recovery dispatch / Engine overflow 闭环和 `max_reactive_compactions_per_run` 上限治理".
- `docs/host/implementation-control.md:144` — Residual risks section updated: removed "raw evidence prompt hardening", replaced with "reactive overflow hardening" description.

**Result:** PASS. All documentation consistently reflects the adjudication; no stale references to raw evidence aggregate prompt budget guard as pending.

## Verified Files

| File | Lines reviewed |
|------|---------------|
| `dayu/host/compaction_operation.py` | 1-372 (full file) |
| `dayu/host/context_policy.py` | 1-307 (full file) |
| `dayu/host/engine_ingest.py` | 1124-1150, 1322-1344, 1410-1553 |
| `dayu/host/README.md` | diff hunk |
| `docs/host/design.md` | diff hunks |
| `docs/host/implementation-control.md` | diff hunks |
| `tests/host/test_compaction_operation.py` | 1-1071 (full file) |
| `tests/host/test_context_policy.py` | diff hunk |
| `tests/host/test_engine_ingest_mapping.py` | diff hunks |

## Summary

All five review criteria pass. The implementation correctly gates budget hard threshold to proactive-only path, defaults reactive limit to 2 with per-policy override support, allows second reactive compact within limit, and fails closed at boundary. Tests cover all key scenarios. Documentation is consistent with the adjudication and contains no stale pending items for raw evidence aggregate prompt budget guard.
