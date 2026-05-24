# P12.6 Slice 1 Code Review Controller Adjudication

## Gate

P12.6 implementation Slice 1 code review.

## Reviewed Artifacts

- `docs/reviews/p12-6-slice1-code-review-mimo-20260524.md`
- `docs/reviews/p12-6-slice1-code-review-ds-20260524.md`
- `docs/reviews/p12-6-slice1-implementation-codex-r2-20260524.md`

## Base Correction

Slice 1 review must judge the current workspace diff against `HEAD` (`8749be9`) rather than `main`. `git diff --name-only HEAD`
does not include `dayu/host/run_input.py`, `dayu/host/memory.py`, or `tests/host/test_public_compact_smoke.py`. Those files differ
from `main` because of earlier accepted work and are not part of the current Slice 1 implementation diff.

## Rejected Findings

### Rejected M-F1: Slice 1 modified `run_input.py` and `memory.py`

Reason: needs-more-evidence finding resolved by direct command evidence. These files are not in `git diff --name-only HEAD`, so the
finding used the wrong base and does not describe the current Slice 1 diff.

### Rejected M-F2: 18 unauthorized tests were modified

Reason: same base issue. Those test files are not in the current workspace diff against `HEAD`.

## Accepted Findings

### Accepted D-F1: `CONTEXT_COMPACTED` payload writer and RunInputBuilder reader use divergent evidence ref keys

Reason: Slice 1 changed the writer in `context_events.py` to emit `canonical_evidence_refs`, while `run_input.py` still reads
`accepted_evidence_refs`. Even though `run_input.py` was not originally in Slice 1 ownership, the writer change creates a
cross-component contract mismatch. Based on Host design goals, EventLog payload writer and reader must be same-source before the slice
is accepted.

Required fix:

- Update `run_input.py` to read the new canonical evidence ref key used by `context_events.py`, or otherwise restore one shared key
  consistently without reintroducing old request-field semantics.
- Add / update focused tests for the new key.

### Accepted D-F2: `_range_tuple` can raise implicit `IndexError` for empty canonical source refs

Reason: This is a low-risk defensive correctness issue in the newly introduced prompt-local label mapping path. Errors should be
typed and explain invalid compactor output or invalid material provenance.

Required fix:

- Add explicit validation before indexing range endpoint refs, or enforce non-empty canonical source refs at the provenance entry
  boundary.

### Accepted D-F3: `context_events.py` constant names no longer match canonical evidence ref payload names

Reason: Low severity, but this is new code churn in a public governance payload validator. Clear names reduce future mistakes.

Required fix:

- Rename internal constants from accepted-evidence wording to canonical-evidence wording without changing payload behavior.

### Accepted M-F3: stale test docstring still says `accepted_evidence_envelopes`

Reason: The test body has migrated, but stale language undermines the old-field removal invariant and `rg` clarity.

Required fix:

- Rename the docstring to current evidence material / canonical evidence wording.

## Next Gate

Route targeted fix to `AgentCodex`, then run two-way re-review.
