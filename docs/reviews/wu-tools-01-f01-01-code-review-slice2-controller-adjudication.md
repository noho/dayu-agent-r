# WU-TOOLS-01-F01-01 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: code review
- Slice: Slice 2 - storage batch lock convergence
- Implementation artifact: `docs/reviews/wu-tools-01-f01-01-implementation-slice2-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice2-ds.md`

## Verdict

Slice 2 code review passed with one accepted clarity fix. No blocking functional issue was found.

Next gate: `fix`.

## Finding Adjudication

### A1. `_release_ticker_lock` should prefer cached token after dict pop

- Source findings: MiMo F1; DS F3.
- Decision: accepted.
- Reason: The current implementation unconditionally pops `_ticker_lock_tokens`, which satisfies the stale-reference requirement. However `effective_token = token or cached_token` gives precedence to the explicit token even when the authoritative cached token exists. Normal callers pass the same object, so behavior is correct, but `cached_token or token` better expresses ownership and avoids discarding a different cached token if future maintenance introduces such a path.
- Required fix: change `_release_ticker_lock` to prefer the popped cached token over the explicit token. Keep the unconditional pop semantics.

### R1. `_acquire_lock_token` blocking timeout docstring

- Source finding: DS F1.
- Decision: rejected-with-reason.
- Reason: `_acquire_lock_token(blocking=True)` calls `file_lock(lock_path).acquire()` with default `timeout_seconds=None`, which maps to the runtime filelock default infinite wait semantics rather than a timeout path. The helper already documents `RuntimeFileLockError`; non-blocking timeout is caught and translated to Fins `RuntimeError`. Adding `RuntimeFileLockTimeoutError` here would overstate the current public behavior.

### R2. Same-process fail-fast test versus real multiprocess

- Source finding: DS F2.
- Decision: rejected-with-reason.
- Reason: The new Fins test validates Fins public behavior through independent repository instances without depending on third-party internals. Runtime filelock owns cross-process primitive semantics and is covered separately. A Fins multiprocess test is not required for this slice.

### R3. Control doc update outside implementation allowed files

- Source finding: MiMo F2.
- Decision: rejected-with-reason.
- Reason: The control document update is phaseflow controller bookkeeping, not implementation-agent scope. It is expected for gate progression and not a slice implementation defect.

### R4. Explicit `timeout_seconds=None` in blocking acquire

- Source finding: MiMo F3.
- Decision: rejected-with-reason.
- Reason: The current call relies on `dayu.runtime.filelock` public default blocking semantics. The plan explicitly allowed this form, and adding an explicit `None` would not improve correctness.

## Residual Risks

- Storage batch filelock now depends on runtime filelock token lifecycle; covered by runtime filelock tests and Fins public behavior tests.
- `dayu/fins/_file_lock.py` deletion remains Slice 3.
- No unclassified residual risk remains for Slice 2 code review.

## Validation

- Read both code review artifacts.
- Verified both reviews reported 0 blocking findings and Slice 2 scope conformance.
- Cross-checked `_release_ticker_lock` implementation against accepted plan finding A1.
