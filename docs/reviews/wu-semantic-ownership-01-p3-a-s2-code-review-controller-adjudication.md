# WU-SEMANTIC-OWNERSHIP-01 P3-A S2 code review controller adjudication

## Status

accepted

## Inputs

- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-controller-validation.md`
- AgentMiMo review: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-semantic-ownership-01-p3-a-s2-code-review-ds.md`

## Findings Merge

Both reviewers returned `pass`.

| Source | Blocking findings | Nonblocking findings | Verdict |
|---|---:|---:|---|
| AgentMiMo | 0 | 0 | pass |
| AgentDS | 0 | 0 | pass |

No accepted fix findings are required for S2.

## Controller Decision

S2 is accepted without a fix gate.

The implementation correctly moves the S2 producer-side terminal event type and Run status consumer semantics to the S1 owner helpers:

- `run_transition.py` and `engine_ingest.py` no longer own duplicate `RUN/ATTEMPT SUCCEEDED/FAILED/CANCELLED/LOST` producer constants.
- Attempt closeout event type production uses the closeout-supported helper and preserves `SUSPENDED` / `STEERED` as durable-only Attempt terminal statuses outside joint Run / Attempt closeout.
- `_TERMINAL_STATUS_PAIRS` is derived from durable terminal status owner sets and lifecycle closeout helper support.
- `admission.py`, `read_model.py`, `state.py`, and `purge.py` consume state owner predicates / serializers / SQL helpers instead of rebuilding the same semantics locally.

## Verified Residuals

The following residuals are not S2 blockers and remain owned by S3 or later sub WUs:

- worker lifecycle synthetic `EngineEvent(type=RUN_FAILED)` path
- `_late_rejection_reason` nullable terminal reference handling
- dispatch pre-worker direct cancel predicate migration
- downstream projection / memory terminal event constants outside the producer boundary
- non-terminal EventLog constants for later EventLog schema/source-of-truth hardening

## Next Gate

Commit S2 implementation and artifacts, then update the control document with the accepted S2 commit and enter P3-A S3 implementation.
