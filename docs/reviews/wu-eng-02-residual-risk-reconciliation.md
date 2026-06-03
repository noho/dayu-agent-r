# WU-ENG-02 Residual Risk Reconciliation

## Scope

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- phaseflow gate: post draft-PR-pass residual risk reconciliation
- design source: `docs/host/design.md`
- control source: `docs/host/issues-implementation-control.md`
- PR: https://github.com/noho/dayu-agent-r/pull/114
- PR head checked: `1298a73f44692f9740dc4dfe34beff7f94304c2b`
- issue owner checked: GitHub Issue #70 is open

## Inputs Reconciled

- final control residual table in `docs/host/issues-implementation-control.md`
- PR review artifacts:
  - `docs/reviews/wu-eng-02-pr-review-mimo.md`
  - `docs/reviews/wu-eng-02-pr-review-ds.md`
- residual fix / review / re-review artifacts:
  - `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`
  - `docs/reviews/wu-eng-02-residual-risk-review-mimo.md`
  - `docs/reviews/wu-eng-02-residual-risk-review-ds.md`
  - `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md`
  - `docs/reviews/wu-eng-02-residual-risk-rereview-mimo.md`
  - `docs/reviews/wu-eng-02-residual-risk-rereview-ds.md`

## Design Boundary

`docs/host/design.md` defines usage as a provider capability driven post-call observation for estimator calibration, diagnostics, and later governance reference. It must not rewrite the current dispatch decision. That design boundary is the reason usage observation correlation is not forced into WU-ENG-02 after the provider debugging correlation path has been closed.

## Reconciled Residual Table

| ID | PR review era status | Final reconciled status | Owner / Destination | Reconciliation result |
|---|---|---|---|---|
| WU-ENG-02-S1-R1 | deferred-with-owner | closed | WU-ENG-02 residual risk fix gate | Closed in PR 114 by writing the tool timeout terminal `RunFailedData.client_correlation_id` from the current tool batch `decision.client_correlation_id`; focused Engine tests now assert the emitted value. |
| WU-ENG-02-S1-R2 | deferred-with-owner | closed | WU-ENG-02 residual risk fix gate | Closed in PR 114 by adding direct force-answer failure EngineEvent assertions for the second Runner request identity. |
| WU-ENG-02-S2-R1 | closed | closed | WU-ENG-02 Slice 4 final validation | Remains closed. Disabled policy behavior is explicitly tested and does not require follow-up. |
| WU-ENG-02-S2-R2 | deferred-with-owner | closed | WU-ENG-02 residual risk fix gate | Closed in PR 114 by moving static `X-Client-Request-Id` conflict validation to `RunnerSpec` construction boundary; OpenAI runner now only maps the header. |
| WU-ENG-02-S3-R1 | deferred-with-owner | deferred-with-owner | WU-OBS-00 / GitHub Issue #70 analyzer | Remains deferred with owner. Usage observation correlation requires analyzer / usage signal contract decision, including whether `client_correlation_id` and `provider_request_id` should both be represented. |
| WU-ENG-02-S3-R2 | deferred-with-owner | closed | WU-ENG-02 residual risk fix gate | Closed in PR 114 by adding Host durable focused tests for context recovery closeout payload and blank `client_correlation_id` validation. |

## Orphan Risk Check

- open residual risks: 0
- residual risks without owner / destination: 0
- closed residual risks: WU-ENG-02-S1-R1, WU-ENG-02-S1-R2, WU-ENG-02-S2-R1, WU-ENG-02-S2-R2, WU-ENG-02-S3-R2
- deferred residual risks with owner: WU-ENG-02-S3-R1
- active residual rows retained in control doc after reconciliation: WU-ENG-02-S3-R1 only

Closed residual risks were removed from the active residual risk table in `docs/host/issues-implementation-control.md`; their close evidence remains in this reconciliation artifact and the residual fix / review artifacts.

## Deferred Owner Evidence

WU-ENG-02-S3-R1 is tracked in the control doc and has an external owner:

- owner / destination: WU-OBS-00 / GitHub Issue #70 analyzer
- issue state: open
- GitHub trace: https://github.com/noho/dayu-agent-r/issues/70#issuecomment-4610820571

This is not an unowned residual. It is intentionally deferred because the remaining decision belongs to the Tool Trace analyzer / usage observation contract, not to provider request identity propagation.

## Next Entry Point

The next entry point remains:

```text
wait for PR 114 merge, then WU-CM-01 discussion / plan gate
```

This is valid because PR 114 is open, draft, merge-state clean, and the WU-ENG-02 residual table contains no open or orphan item.

## Verification

Commands run for reconciliation:

```bash
git branch --show-current
git status --short
gh pr view 114 --repo noho/dayu-agent-r --json number,title,state,isDraft,headRefName,headRefOid,url,mergeStateStatus
gh issue view 70 --repo noho/dayu-agent-r --json number,title,state,url
gh pr checks 114 --repo noho/dayu-agent-r
```

Results:

- branch: `phaseflow/wu-eng-02-request-identity`
- worktree before reconciliation artifact: clean
- PR 114: open draft PR, merge state `CLEAN`, head `1298a73f44692f9740dc4dfe34beff7f94304c2b`
- issue-70: open
- GitHub checks: no checks reported on the branch

No code was changed during this reconciliation.

## Verdict

Residual Risk Reconciliation passes. WU-ENG-02 has no open or orphan residual risk. The only deferred item is WU-ENG-02-S3-R1, and it has a concrete owner, destination, issue trace, and next action.
