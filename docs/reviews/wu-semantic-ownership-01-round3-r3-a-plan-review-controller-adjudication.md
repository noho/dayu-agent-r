# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A`
- Gate: plan review controller adjudication
- Timestamp: `2026-07-12T11:50:35+0800`
- Branch: `phaseflow/host-issues-control`
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-ds.md`
- Decision: `plan-fix-required`

## Controller Summary

Both reviewers confirmed the R3-A direction is mostly valid, but the plan is not yet code-generation-ready. The shared blocking issue is S2 scope: the current S2 bundles admin opener, durable actor, public async boundary, health gate, admission lease, scheduler retry, watchdog wake, recovery batching, cancel classification, and idempotent replay into one production-high slice. That violates the control-doc slicing constraints because these concerns have different semantic owners, failure modes, validation matrices, and reviewer expertise.

MiMo also challenged S5. Direct code review confirms MiMo is correct that `LaneController.close()` does not set `_close_completed` before attempting token release. However, DR-029 remains real because `_close_completed=True` is committed even when a release failure is collected, leaving failed tokens in `_held_tokens` while later `close()` returns immediately. DR-017 also remains real: `_started` and `_closed` are committed before process start / cleanup side effects can complete, and current tests do not cover start failure, cancellation, or partial cleanup. The plan must narrow S5 so it preserves existing concurrency gating while making cleanup completion retryable and resource cleanup reliable, instead of forcing a broad five-state rewrite.

## Finding Adjudication

| Source | Finding | Decision | Required plan correction |
| --- | --- | --- | --- |
| DS | F-01 S2 over-broad slice | accepted | Split S2 into narrower implementation slices. At minimum separate admin opener + public durable actor / async boundary from scheduler health + admission lease + recovery/watchdog/cancel/idempotent replay. If recovery batching and cancel classification remain too broad, split them again. |
| DS | F-02 fatal/admission race test underspecified | accepted | Specify deterministic race test mechanics: synchronization points, fatal injection method, actor/admission lease barrier, durable assertions, and wake assertions. Sleep/probabilistic stress alone is not acceptable. |
| DS | F-03 S3 daemon observation lifecycle incomplete | accepted-as-plan-clarification | S3 must specify the late-result/result-queue shutdown gate and bounded tracking of outstanding observation threads. It may remain in S3, but cannot be left to implementation redesign. |
| DS | F-04 S1 schema feasibility unknown | accepted-as-plan-clarification | Add an S1 pre-check that reads current durable payload DDL and proves existing columns support descriptor ref/digest/size validation. If not, S1 must stop before code edits and return to plan review. |
| DS | F-05 process start ambiguity | accepted-narrowed | S5 must not rely on vague `Process.start()` semantics. Either make start failure non-retryable on the same handle, or require an explicit proof that no child process exists before allowing retry. |
| DS | F-06 Host/HostAdmin Protocol split unclear | accepted | State that `Host` and `HostAdmin` are independent protocols with no compatibility wrapper or inheritance-based admin leakage. Shared lower-level command functions are allowed only as owner implementation detail. |
| MiMo | F1 DR-017/DR-029 diagnosis mismatch / S5 overdesign | accepted-narrowed | Correct the plan text: DR-029 is release-failure-after-attempted-release, not release-before-attempt. DR-017 remains partial start/cleanup poisoning. S5 should preserve concurrency gates and focus on retryable cleanup / try-finally / shielded caller cancellation, not mandate an over-broad state-machine rewrite. |
| MiMo | F2 S2 over-broad slice | accepted | Same as DS F-01. |
| MiMo | F3 projector metadata summary shape mismatch | accepted | S1 must explicitly define the shared projector metadata descriptor shape and how all three producers populate it. Hot payload remains fixed atoms only; complete projector metadata lives in descriptor. |
| MiMo | F4 durable actor thread-safety underspecified | accepted | S2 plan fix must define actor callable typing, command handle ownership, scheduler connection creation, event-loop bridge semantics, close ordering, and busy/retry interaction. |
| MiMo | F5 wait expiry helper relation unclear | accepted-as-plan-clarification | S3 must specify `_expire_wait_in_transaction()` input/output and how it constructs the existing failed wait outcome while reusing `fail_run_from_waiting_in_transaction()` in the caller-provided transaction. |
| MiMo | F6 DR-017 queue cleanup issue | accepted-merged | Covered by the S5 narrowed correction. Add tests for partial close failure and second close cleanup. |

## Required Plan-Fix Bundle

AgentCodex must update the R3-A plan artifact only. No production code, tests, README, control doc, commit, push, or implementation work is allowed in this gate.

Required fixes:

1. Replace the current single S2 with narrower slices. Suggested structure:
   - `S2a`: admin opener, independent `HostAdmin` protocol, minimal durable actor/public async boundary, CLI list/purge routing.
   - `S2b`: scheduler health gate, admission lease covering actor commit and wake, retry exhaustion handling, idempotent replay.
   - `S2c` if needed: recovery batching, watchdog level-trigger, cancel classification race, if S2b remains too broad.
2. Update total slice count and the slice-count justification. More than five slices is acceptable only if each slice is owner-closed and reviewable; the plan must explicitly justify the extra gate cost against the optimization control.
3. Specify the deterministic fatal/admission race test mechanism.
4. Specify `_HostDurableActor` typing, connection ownership, scheduler connection source, event-loop bridge, close order, and busy/retry rules.
5. Add S1 schema feasibility pre-check and explicit projector metadata descriptor shape.
6. Clarify S3 daemon observation late-result gate and `_expire_wait_in_transaction()` contract.
7. Correct S5 diagnosis and scope. Preserve concurrency protection; make partial cleanup and release failure retryable; add tests for start failure ambiguity, close cancellation, queue cleanup, lane partial release retry, and concurrent close.
8. Keep all original R3-A accepted findings covered. Do not defer any current R3-A accepted finding except the already-adjudicated R3-D Fins wait-adapter reverse-dependency half.

## Status

- Plan review gate result: `fail`
- Next gate: AgentCodex plan fix
- Expected fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`
- After plan fix: dispatch MiMo/DS plan re-review before implementation.
