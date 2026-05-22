# Controller Adjudication

## Scope

- PR: https://github.com/noho/dayu-agent-r/pull/68
- Gate: draft PR review
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Base: `main`
- Review artifacts:
  - `docs/reviews/pr-68-review-20260523-024713.md`
  - `docs/reviews/pr-68-review-ds-20260523.md`

## Decision

PASS. PR 68 reaches draft-PR-pass.

Both PR-level review agents passed the draft PR. The reviewed branch includes the aggregate repair that closed the earlier evidence-content and memory-lag blockers:

- accepted evidence result previews are derived from actual accepted tool outcomes and stored in the accepted evidence envelope;
- the LLM compactor prompt renders the accepted evidence envelope and preview before requesting `evidence_backed_fact_candidates`;
- dispatch handles `SNAPSHOT_LAG_OVER_THRESHOLD` through rebuild / retry without terminal Run / Attempt closeout;
- old `verified_*` contracts remain fail-closed in config, payload validation, and durable read paths.

## Non-Blocking Findings

- DS noted the LLM compactor prompt has no aggregate envelope text budget beyond the per-envelope `result_preview` limit. This is a prompt-budget hardening item, not a correctness blocker for P12.5: each preview is bounded, and the core issue that the extractor previously saw only opaque refs is fixed.
- Both reviewers kept `_NeverCancelledToken` / compaction cancellation as a residual. It is bounded by runner timeout and stale output checks.
- Large-session rebuild timeout / backoff and provider-owned summaries for deeply nested tool outputs remain follow-up hardening work.

## Validation

- Local aggregate repair validation: 260 targeted tests passed.
- Local type validation: `pyright` passed with 0 errors.
- `git diff --check` passed.
- GitHub PR state: draft, mergeable, no status checks reported.

## Verdict

draft-PR-pass.
