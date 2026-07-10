# WU-SEMANTIC-OWNERSHIP-01 P3-B plan review controller adjudication

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`.
- Gate: plan review controller adjudication.
- Plan: `docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`.
- Reviews:
  - `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`
- Decision: enter plan-fix gate with five merged requirements.

## Controller judgment

The plan direction is correct: one slice closes the resolver, Outbox transaction, durable/public invariants, retry, and propagation behavior without introducing an intermediate invalid contract. Review findings that merely restate current implementation gaps already named as exact plan changes are not plan defects. Findings that expose missing implementation evidence or ambiguous failure mechanics are accepted because an implementation agent must not rediscover them.

## Accepted plan fixes

### P3-B-PF-01 - correct source evidence

Correct the stale `run_transition.py:4569-4584` citation. Identify the actual Engine-origin and Host-lifecycle closeout locations in `engine_ingest.py` and the exact durable payload builder that persists `terminal_summary_ref/digest` plus canonical metadata without inline answer text.

### P3-B-PF-02 - prove ProjectionRunner atomicity

Add concrete code references showing consumer apply, Outbox insert, checkpoint advance, rollback, and separate failure recording. Make non-atomic behavior a stop condition rather than an implementation-time assumption.

### P3-B-PF-03 - prove the production smoke path

Verify the actual `FinalAnswerWorkerFactory` or replacement fixture exists and exercises the production descriptor-only closeout. Name the exact test/support file and assertions; do not let an inline-only fixture satisfy the smoke.

### P3-B-PF-04 - specify descriptor restoration and retry

Replace the vague "PayloadStore restores the same ref/digest" wording with the repository's real test mechanism. State whether recovery uses the typed payload writer or a test-only direct durable row insertion, how the same digest is preserved, and why retry observes the restored row without adding a production repair API.

### P3-B-PF-05 - close descriptor-pair and error taxonomy

Specify how the resolver distinguishes both descriptor fields absent from a one-sided malformed pair, missing descriptor row, digest mismatch, invalid JSON/object, and missing/blank/non-text `content`. Identify the check location and required behavioral assertions so projection failure rows retain actionable cause text while remaining internal diagnostics.

## Rejected with reason

- MiMo F01/F02/F03: rejected as plan findings. Sections 7 and 10 already name the exact public and durable validators, conditional invariants, blank-content rejection, and tests. These are current-code gaps the plan exists to implement.
- MiMo F05: rejected. Content source selection and final-answer metadata are distinct facts. The plan correctly keeps `filtered/degraded/finish_reason` owned by canonical `RUN_SUCCEEDED`; metadata must not switch to artifact payload based on content fallback.
- DS F01: rejected. `docs/host/design.md` explicitly authorizes inline `RUN_SUCCEEDED.final_answer` or digest-checked artifact `content`; retaining the owner policy is not undocumented compatibility code. The plan should cite this design evidence while applying PF-01.
- DS F05/F06: rejected as already specified by plan sections 7.1, 10 exact changes, and the behavior matrix.
- DS F07: informational; no forced file churn. `terminal_payload.py` remains optional only if a real docstring clarification is needed.

## Merged / covered

- MiMo F08 and DS F02 merge into PF-04.
- DS F04 is covered by PF-05.
- DS F03 is covered by PF-05.
- MiMo F06 maps to PF-02.
- MiMo F07 maps to PF-03.

## Completion

- Accepted merged plan fixes: 5.
- Rejected with reason: 7 source findings/concerns.
- Informational: 1.
- Blocking open question: none.
- Next gate: plan fix by AgentCodex, then parallel plan re-review.
