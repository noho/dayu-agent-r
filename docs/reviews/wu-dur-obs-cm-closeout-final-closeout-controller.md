# WU-DUR/OBS/CM Closeout Final Closeout Controller Record

## 结论

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 closeout chain
- Gate: final closeout
- PR: https://github.com/noho/dayu-agent-r/pull/118
- PR state at closeout: open draft
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- PR head checked before final closeout bookkeeping: `c57b7471feeb3ffb68afaf1cd3ac003e4464f1f6`
- Verdict: local gates complete; PR review passed; draft-PR-pass reached; final closeout record created.

## 已完成

- WU-DUR-P01 durable runner-call reconstruction atoms and residual hardening are complete.
- WU-OBS-P00 runner-call Tool Trace reconstruction signal projection is complete.
- WU-CM-01-F02 compact evidence query readability and compact instruction LLM-facing semantic rewrite are complete.
- WU-CM-01-F01 public smoke validation and production one-system-message RunInput assembly are complete.
- Residual fixes completed after draft PR creation:
  - `81402233`: runner call iteration link residual closed.
  - `454f2aa0`: compactor initial proposal trigger reason enum added.
  - `e92c4118`: compactor outcome manifest reverse refs codified.
  - `56afea6e`: usage correlation residual transferred to issue-119 under issue-70.
- PR review gate completed:
  - AgentMiMo: `docs/reviews/wu-dur-obs-cm-closeout-pr-review-mimo.md`
  - AgentDS: `docs/reviews/wu-dur-obs-cm-closeout-pr-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-dur-obs-cm-closeout-pr-review-controller-adjudication.md`
- Accepted PR review bookkeeping commit: `c57b7471feeb3ffb68afaf1cd3ac003e4464f1f6`.
- Final closeout bookkeeping is recorded in the PR branch after that accepted PR review commit.

## Final Validation

Review agents ran focused validation and reported:

- `pyright`: 0 errors
- Engine / Host focused tests: passed
- Public smoke tests: passed with the real compactor smoke skipped by environment gate
- Residual table: no `open` or ownerless items

Controller reran before accepted PR review commit:

```bash
git diff --check
# passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

GitHub state checked before creating this final closeout record:

- `gh pr view 118 --json number,url,state,isDraft,headRefName,headRefOid,baseRefName,title,mergeStateStatus,reviewDecision`
  - PR 118 open draft
  - head branch `phaseflow/wu-dur-obs-cm-closeout`
  - head commit `c57b7471feeb3ffb68afaf1cd3ac003e4464f1f6`
  - base `main`
- `gh pr checks 118`
  - no checks reported on branch `phaseflow/wu-dur-obs-cm-closeout`

## Residual Risk Reconciliation

Closed in current PR:

- `WU-DUR-P01-S2-R2`: explicit `RUNNER_CALL_INPUT_ITERATION_LINKED` correlation replaces index-zero fallback matching and fails closed on missing / ambiguous / mismatch / conflict cases.
- `WU-DUR-P01-S3-R1`: first compactor proposal uses `context_compaction_initial_proposal`; retry attempts continue using retry / repair reasons.
- `WU-DUR-P01-S3-R2`: proposal manifest remains append-only input truth; compact outcome payloads reverse-reference proposal manifest ref / digest pairs.
- `WU-CM-01-F01-S7-R1`: ordinary RunInput uses one leading system envelope while preserving user / assistant roles.

Transferred:

- `WU-ENG-02-S3-R1`: transferred to issue-119 under issue-70. Analyzer contract must decide whether `USAGE_REPORTED` needs request-level correlation; Host must not infer provider request identity from `iteration_id`.

No current closeout residual remains open without owner.

## Next Entry Point

- User / maintainer action: inspect PR 118 and decide whether to mark ready for review or merge.
- Merge, mark ready for review, request reviewers, approve, delete branch, or external issue closeout still require explicit user authorization.
- After PR 118 merge, resume phaseflow at `WU-TOOLS-01` goal confirmation unless the user selects another backlog item.
