# Host Phase 1 Slice 3 Code Review Controller Adjudication

## Scope

- Gate: Phase 1 Slice 3 code review adjudication.
- Work unit: Host Phase 1 公共契约与 runtime 基础设施。
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p1-s3-runtime-filelock-20260514.md`
- Review artifact: `docs/reviews/gateflow-code-review-host-p1-s3-runtime-filelock-mimo-20260514.md`
- Review agent: AgentMiMo only.

## Controller Decision

Slice 3 implementation is functionally aligned with the accepted plan, but one documentation sync finding is accepted for fix before accepting the slice.

## Findings Adjudication

### Finding 1: `_ensure_lock_file_marker_exists` release marker interleaving window

- Decision: not blocking; record as residual risk.
- Rationale: the plan requires a sync wrapper around third-party `filelock.FileLock`, and explicitly does not require stale takeover, force break, or deeper lock-file ownership semantics. The current wrapper does not use the lock file as Host truth, lease/fencing proof, EventLog ordering, or recovery evidence. The reported window does not break mutual exclusion correctness. The implementation artifact already records the third-party unlink behavior as a trade-off.
- Follow-up: keep as residual risk for future runtime hardening if callers ever require marker-file existence as an observable invariant. Current Phase 1 callers must not depend on marker-file existence for governance truth.

### Finding 2: same `RuntimeFileLock` instance repeated acquire ambiguity

- Decision: not accepted for this slice.
- Rationale: the accepted plan says the wrapper does not promise reentrant lock semantics and tests must not assert third-party reentrant details. Turning repeated acquire into an explicit wrapper state machine would add behavior beyond the approved Slice 3 contract. The current public contract remains: acquire returns a token, token release is idempotent, and callers must not rely on reentrant behavior.
- Follow-up: if later callers need a strict non-reentrant wrapper contract, that should be planned as an explicit API decision with tests.

### Finding 3: `dayu/runtime/__init__.py` package docstring not updated

- Decision: accepted for fix.
- Rationale: the accepted plan explicitly requires a minimal package docstring update for Phase 1 runtime lane / filelock capabilities and forbids package-root re-export. The implementation omitted this doc-only update.
- Required fix: minimally update `dayu/runtime/__init__.py` docstring to mention lane and sync filelock as current layer-neutral runtime capabilities. Do not add package-root exports.

## Required Fix Scope

Allowed fix files:

- `dayu/runtime/__init__.py`
- `docs/reviews/gateflow-implementation-host-p1-s3-runtime-filelock-20260514.md`

No production behavior changes are required.

## Required Validation After Fix

- `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime/filelock.py tests/runtime/test_filelock.py`
- `git diff --check`

## Residual Risks

- Lock marker file existence remains a best-effort wrapper-visible artifact, not a durable truth source.
- Reentrant behavior remains explicitly unsupported as a public guarantee; callers must not depend on third-party reentrant details.
