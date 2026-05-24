# PR 68 P12.6 Draft Review Controller Adjudication

## Gate

- Gate: P12.6 draft PR review gate
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Head: `feat/phase-12-5-conversation-memory-optimize` @ `466a639`
- Review artifacts:
  - `docs/reviews/pr-68-p12-6-draft-review-mimo-20260524.md`
  - `docs/reviews/pr-68-p12-6-draft-review-ds-20260524.md`

## Verdict

Controller verdict: PR fix gate required before `draft-PR-pass`.

The two independent reviewers both returned `PASS_WITH_FINDINGS`. DS F1 is a durable write crash and blocks
`draft-PR-pass`. Several medium findings also affect P12.6's evidence-backed memory and lifecycle governance
goals, so they are accepted into the PR fix gate rather than deferred.

## Accepted Findings

### A1: Memory diagnostic reason schema mismatch

- Source: DS F1.
- Decision: accepted, blocking.
- Reason: `MemoryDiagnosticReason` introduces `evidence_backed_fact_superseded` and
  `minimum_preserve_item_covered`, but the SQLite CHECK constraint does not allow those values. This is a direct
  durability crash path.
- Required fix: update the schema truth and add tests proving both diagnostic reasons can be persisted.

### A2: LLM compaction timeout/cancellation handling

- Source: MiMo F1 and DS F6.
- Decision: accepted.
- Reason: timeout currently leaks as raw `TimeoutError` and does not explicitly signal the Host lifecycle
  cancellation token, weakening cancellation governance and diagnostic consistency.
- Required fix: signal the request cancellation token on timeout when possible, wrap timeout as
  `LLMCompactionProposalError`, and cover with tests.

### A3: Range endpoint label must map to exactly one canonical ref

- Source: MiMo F2.
- Decision: accepted.
- Reason: silently selecting the first ref from a multi-ref label loses boundary precision for compact ranges.
- Required fix: fail proposal validation when start/end labels resolve to zero or more than one canonical source ref.

### A4: Compact material provenance must preserve locator/artifact refs

- Source: DS F2 and DS F7.
- Decision: accepted.
- Reason: second-pass compact material construction currently drops `source_locator_refs` and `artifact_refs`, which
  weakens durable provenance.
- Required fix: carry these refs through `RunInputMaterialBlock` and provenance reconstruction, with non-empty ref tests.

### A5: Dispatch lag repair failure must not leave records permanently running

- Source: MiMo F3 and DS F4.
- Decision: accepted.
- Reason: returning `skipped` after a dispatch record has moved to `DISPATCHING` can strand Run / Attempt lifecycle
  state.
- Required fix: close out or otherwise transition the worker startup failure to a terminal/retry-safe state, with a
  scheduler test proving no permanent hang.

### A6: Evidence-backed facts must not be starved by lower-value stable blocks

- Source: DS F3.
- Decision: accepted for fix if the current stable-block ordering can drop all evidence-backed facts under budget.
- Reason: evidence-backed facts are the primary stable memory output of P12.6; dropping all of them under stable budget
  pressure violates the phase objective.
- Required fix: introduce a minimal preservation rule or priority adjustment, with budget-pressure tests.

### A7: Empty evidence labels must not disable evidence-backed guard rails

- Source: MiMo F4.
- Decision: accepted for fix if evidence-backed refs can be non-empty while labels are empty.
- Reason: quality checks should fail closed when provenance labels required for verification are missing.
- Required fix: emit a diagnostic issue for non-empty evidence refs with empty labels, with tests.

### A8: Accept barrier should reject missing payload descriptors when the durable store can verify them

- Source: DS F5.
- Decision: accepted for direct-evidence investigation.
- Reason: writing `TOOL_RESULT_ACCEPTED` with a payload ref that is already missing creates a bad durable event.
- Required fix: if the accept path has access to the payload store, reject missing descriptors before writing the
  accepted event; otherwise record why this cannot be fixed without crossing layer boundaries and add a residual owner.

## Deferred Findings

- MiMo F5: intra-event memory fact tiebreaker. Deferred; deterministic enough for current phase and lower risk than
  changing payload ordering semantics during PR fix.
- MiMo F6: episode summary policy field separation. Deferred to memory policy hardening.
- MiMo F7: duplicated redaction helper. Deferred as maintainability polish.
- MiMo F8: compact material dead code. Deferred as non-behavioral cleanup.
- DS F8: overly broad `_candidate_from_final_answer` catch. Deferred as diagnostics polish.

## Next Step

Route AgentCodex for a PR fix gate covering A1-A8. The worker must produce
`docs/reviews/pr-68-p12-6-draft-fix-codex-20260524.md`, run affected tests and pyright, and stop without commit,
push, PR state changes, or moving to the next gate.
