# Phase 11 Slice 1 Code Review Controller Adjudication

## Gate

Phase 11 Slice 1 code review adjudication.

## Inputs

- Implementation artifact: `docs/reviews/phase11-slice1-implementation-codex-20260519.md`
- MiMo code review: `docs/reviews/phase11-slice1-code-review-mimo-20260519.md`
- DS code review: `docs/reviews/phase11-slice1-code-review-ds-20260519.md`
- Accepted plan: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- Accepted plan commit: `9223cbf`

## Review Results

- AgentMiMo: PASS, blocking count = 0, no substantive findings.
- AgentDS: PASS, blocking count = 0, one medium and two low non-blocking findings.

## Controller Decision

Decision: accept Slice 1 without current fix pass.

基于 design_doc 的设计目标和第一性原理，Slice 1 的 correctness gate 是：Host instance liveness 不回刷、process identity 高熵且可诊断、heartbeat lifecycle 不伪造 Host truth、orphan classifier 只读且不能把 heartbeat stale 单独提升为 positive proof。两份 review 均确认这些核心不变量成立，且没有 Engine / public API / schema 变更。

## Finding Decisions

### DS 1: heartbeat close 场景下的 catch-all fatal_exit 日志

Decision: rejected-current-fix / accepted as observation.

Rationale: review 自身确认该 close race 在当前 asyncio 单线程模型下不可达，且当前实现把非 retryable heartbeat exception 作为 fatal heartbeat exit 符合 accepted plan 的 heartbeat failure mode。若当前 instance row 已进入 lifecycle conflict，heartbeat 不应继续宣称当前 Host instance live；best-effort mark own instance `STOPPING` is bounded to the current scheduler identity and does not touch other rows. 该 finding 不影响 durable truth、positive orphan proof 或 Run / Attempt 状态。

Tracking: revisit during Slice 2 if stale threshold / recovery scan introduces new lifecycle exception categories that should be diagnostic-only.

### DS 2: heartbeat interval hard-coded to 1.0 seconds

Decision: deferred to Slice 2 stale-threshold policy.

Rationale: heartbeat interval must be evaluated relative to recovery stale threshold. Slice 1 intentionally establishes heartbeat existence and identity semantics; Slice 2 owns recovery scan policy and stale threshold. Changing configurability now would either add premature policy surface or guess at threshold coupling.

Tracking: Slice 2 plan item already requires recovery stale threshold and classifier policy; implementation review must verify interval/threshold relationship.

### DS 3: `_validate_policy` timezone check redundancy

Decision: rejected-current-fix.

Rationale: `tzinfo is None or utcoffset() is None` is the conventional robust timezone-aware datetime guard. It covers naive datetimes and custom tzinfo implementations that return `None`. Removing it would reduce defensive clarity without improving correctness.

Tracking: none.

## Validation Evidence

Controller locally reran:

- `pytest tests/host/test_host_instance_liveness.py tests/host/test_recovery_orphan_classifier.py -q`: 30 passed.
- `pytest tests/host/test_dispatch_scheduler.py::test_scheduler_close_suppresses_handle_close_exception -q`: 1 passed.
- `python -m pyright dayu/host tests/host`: 0 errors.
- `git diff --check`: clean.

## Next Gate

Next gate: accepted Slice 1 local commit, then Phase 11 Slice 2 implementation.
