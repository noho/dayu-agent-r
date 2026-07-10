# WU-SEMANTIC-OWNERSHIP-01 P3-A Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A - Host lifecycle, run status, and terminal event source of truth`
- Gate: plan fix only
- Updated plan: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md`
- Allowed changes only: plan artifact and this fix artifact

## Finding Mapping

| Finding | Status | Fixed location in plan |
|---|---|---|
| PF-01: S3 Host lifecycle closeout identity scheme must be concrete | fixed | S3 exact changes now define `_HostLifecycleCloseoutCandidate`, `event-host-lifecycle-{digest}` formula, disjoint namespace from `event-engine-`, duplicate handling, Host lifecycle ref, and routing data: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:320` |
| PF-02: S3 active-cancel race decision table | fixed | S3 exact changes include active-cancel decision table for Engine `FINAL_ANSWER`, Engine `RUN_FAILED`, Host lifecycle clean EOF, Host lifecycle lost/crash, and other Engine events: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:350` |
| PF-03: Avoid god-bag closeout candidate | fixed | S3 now requires two typed paths or an explicit tagged union, and forbids optional-field probing: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:320` |
| PF-04: Mandatory precise terminal event source scan plus residual non-terminal constants | fixed | S2 makes source scan mandatory, uses precise terminal pattern, defines no-match expectation for migrated consumers, and lists residual non-terminal constants for P3-J / future hardening: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:273` |
| PF-05: Concrete import-cycle dependency graph and validation command | fixed | Plan records import graph baseline and exact import validation command; S1/S2 validation also includes the command: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:135` |
| PF-06: SM-7 pre-implementation verification step | fixed | SM-7 section now requires pre-S1 production path search and defines found/not-found handling: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:87` |
| PF-07: SQL/query-plan or equivalent validation for status SQL helper | fixed | S1 adds SQL helper owner tests; S2 adds SQL/query-plan or equivalent durable state validation for generated `IN` clauses: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:225`, `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:298` |
| PF-08: `TERMINAL_STATUS_PAIRS` owner decision | fixed | S2 declares it a derived transition invariant, not durable row-rule truth or event mapping truth, and requires derived invariant tests: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:261` |
| PF-09: `START_BLOCKING_RUN_STATUSES` derivation assumption and test | fixed | S1 documents the “all non-terminal except `QUEUED` block start” assumption and adds exact member test expectation that fails on new non-terminal statuses: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:212`, `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:224` |
| PF-10: Executable propagation audit criteria | fixed | Propagation audit now includes concrete verification criteria for each path: source scan, owner tests, transition tests, read/projection tests, SQL validation, diagnostics, and source review: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:387` |
| PF-11: Preserve P3-B boundary; do not predesign final-answer fields | fixed | Non-goals now forbid P3-B final-answer field predesign and require preserving existing `_close_terminal` arguments/behavior only: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:176` |
| PF-12: README actual check requirement | fixed | S1/S2/S3 README decisions now require actual inspection of `dayu/host/README.md` and `tests/README.md` per trigger rules, not an “expected no update” shortcut: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:236`, `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:300`, `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:383` |
| PF-13: Concrete event type value helper strategy | fixed | S1 now chooses simple separate Run/Attempt value helpers and rejects TypeVar/overload generalization: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:210` |

## Validation

- Passed: `git diff --check -- docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md`
- Passed for untracked-file coverage: `git diff --check --no-index -- /dev/null docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md` emitted no whitespace warnings.
- Passed for untracked-file coverage: `git diff --check --no-index -- /dev/null docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md` emitted no whitespace warnings.

## Residual Risks

- No unresolved accepted plan-review findings remain in this fix artifact.
- No production code, tests, commits, pushes, re-review, or implementation gate actions were performed.

## Completion

```text
status: completed
updated plan: docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md
fix artifact: docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md
fixed findings: PF-01..PF-13
validation: git diff --check passed; no-index checks emitted no whitespace warnings for untracked changed docs
blockers: none
```
