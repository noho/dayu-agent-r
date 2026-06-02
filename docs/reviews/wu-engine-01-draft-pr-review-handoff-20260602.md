# WU-ENGINE-01 Draft PR Review Handoff

## Scope

- PR: https://github.com/noho/dayu-agent-r/pull/109
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: `main`
- Gate: draft PR review.
- Design source: `docs/host/design.md`.
- Control doc: `docs/host/host-core-followup-implementation-control.md`.

## Review Focus

Review the PR diff as a whole and determine whether the draft PR can pass the PR review gate.

Primary checks:

- Runner diagnostic `raw_payload` is bounded, redacted, summarized, and no longer passes raw provider JSON through stream, non-stream, or HTTP error paths.
- Stream and non-stream provider error object behavior stays consistent where the plan requires parity.
- HTTP error body handling preserves byte caps and never returns unbounded raw body content.
- Invalid UTF-8 diagnostics remain bounded and do not leak raw chunks beyond the planned prefix summary.
- Host ingest production code remains unchanged; Host only receives the same field shape.
- Engine contracts and README describe stable diagnostic semantics accurately.
- Aggregate fix for dashed sensitive keys and non-string provider error scalar fields is correct and does not introduce new leakage or type risk.
- Tests are meaningful and cover the changed behavior; no production compatibility facade or metadata bag was introduced.

## Required Reviewer Output

Write one artifact:

- AgentMiMo: `docs/reviews/wu-engine-01-draft-pr-review-mimo-20260602.md`
- AgentDS: `docs/reviews/wu-engine-01-draft-pr-review-ds-20260602.md`

The conclusion must be `PASS` or list concrete blocking/high/medium/low findings with file and line evidence. Do not modify files, commit, push, or comment on GitHub.
