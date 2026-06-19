# Aggregate Deepreview Adjudication: Compact Rejected Attempt Diagnostic Artifact

- **Gate**: aggregate deepreview adjudication
- **Work unit**: Conversation Memory compact rejected attempt diagnostics
- **Timestamp**: 20260619-144950
- **Aggregate review artifacts**:
  - `docs/reviews/code-review-20260619-144741.md`
  - `docs/reviews/code-review-20260619-144524.md`

## Decision

Current diagnostic artifact slice passed aggregate review, but the aggregate deepreview gate cannot be closed because the broader branch has a reproducible failing test outside the current slice boundary.

## Blocking Finding

### `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`

- **Review source**: `docs/reviews/code-review-20260619-144741.md`
- **Decision**: `needs-more-evidence` / scope decision required
- **Status**: `未修复`
- **Local reproduction**:

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor
```

Result: failed. Expected `fake_compactor.prompt_lengths == []`, actual `[19454]`.

## Scope Analysis

This failure is a branch-level proactive compact / fallback behavior regression. Fixing it safely requires analyzing production proactive compact decision flow, fallback caps, recovery tier behavior, or updating the public compact smoke expectation.

That exceeds the current work unit boundary:

- current work unit only adds rejected attempt diagnostic observability;
- it must not change accept/reject/fallback/tier behavior;
- it must not fix production compact root cause or production memory compact behavior.

Therefore this adjudication does not implement a fix.

## Non-Blocking / Deferred Findings

- Recovery-tier rejected attempts not written to EventLog: deferred to a later recovery-tier compact audit diagnostics work unit.
- Recovery-tier missing tests / stale-result protection / attempt numbering / operation id attribution: deferred to the same later work unit.
- Diagnostic artifact file orphan after SQL rollback: existing artifact storage lifecycle residual risk.
- Helper duplication: rejected-with-reason in code review adjudication.
- Offending block ordinal guard: accepted and fixed.

## Validation

Current slice validation remains:

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py
```

Result: `87 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

Additional branch-level failing validation:

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor
```

Result: failed.

## Gate Status

`aggregate deepreview` is blocked by a scope decision. Do not proceed to accepted deepreview commit, push, draft PR, or PR review gate until the user decides whether to:

1. expand scope to fix the branch-level proactive compact smoke regression now; or
2. split/defer that regression to a separate work unit and accept that this gate remains blocked for the full branch.
