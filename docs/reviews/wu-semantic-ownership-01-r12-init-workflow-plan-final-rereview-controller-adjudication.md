# WU-SEMANTIC-OWNERSHIP-01 / R12 final plan re-review Controller adjudication

## 1. Gate identity

- Existing umbrella work unit: `WU-SEMANTIC-OWNERSHIP-01`.
- Internal remediation sub-WU: R12, `dayu-cli init` workflow.
- Gate: final complete dual plan re-review adjudication.
- This is not a new WU and does not itself authorize product implementation before
  the accepted-plan local commit.

## 2. Immutable review target

```text
docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md
608 lines / 71,044 bytes
SHA-256 69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2
```

The target SHA remained unchanged throughout both final reviews.

## 3. Reviewer artifacts

| Reviewer | Artifact | Metrics | Verdict | New material findings |
|---|---|---:|---|---:|
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-final-rereview-mimo.md` | 366 lines / 23,695 bytes / SHA-256 `f2a949ff626ab8a3c76932968ef58f398b3b6dee0f020bf858717a62bf264856` | PASS | 0 |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-final-rereview-ds.md` | 533 lines / 40,424 bytes / SHA-256 `fbfdd13d722c78976bc208e4f4ef8b84b83a18672e1d712e29937f4d5a8ee1b7` | PASS | 0 |

Both reviewers performed complete reviews rather than incremental spot checks. They
independently matched the target metrics and current source locks, challenged every
required boundary, and reported no design contradiction or blocker.

Controller required two artifact-only factual-hygiene corrections before acceptance:

1. AgentDS corrected the new Controller validation SHA from the adjudication SHA to
   the actual 118-line validation SHA `fda4c9d7...a73d`.
2. AgentMiMo corrected its first-round PF ledger to the actual Controller-adjudicated
   PF-01..12 groups rather than reusing second-round labels.

Neither correction changed a finding or verdict.

## 4. Final finding ledger

### 4.1 First plan-review groups

| Group | Final status |
|---|---|
| PF-01 Ruff exact baseline gate | CLOSED |
| PF-02 fresh workspace pre-lock owner | CLOSED |
| PF-03 exact OLD/CURRENT prewarm without invented lifecycle | CLOSED; runtime-assembly wording later superseded by the direct CURRENT contradiction correction |
| PF-04 publication success vs cleanup failure boundary | CLOSED |
| PF-05 static/dynamic catalog validation separation | CLOSED |
| PF-06 private same-filesystem staging without public temp protocol | CLOSED |
| PF-07 interruptible indefinite init lock | CLOSED |
| PF-08 file-granular missing prompt copy | CLOSED |
| PF-09 active Host writer residual and warning | CLOSED |
| PF-10 custom hint direct source | CLOSED |
| PF-11 absent POSIX profile private atomic `0600` creation | CLOSED |
| PF-12 `.dayu` internal owner / whole-root RESET only | CLOSED |

### 4.2 Fixed-plan re-review groups

| Group | Final status |
|---|---|
| RR-PF-01 current resolved `ModelsConfig` truth | CLOSED |
| RR-PF-02 exact 13 production / three test-owned Scene catalog boundary | CLOSED |
| RR-PF-03 deterministic observable real-lock smoke | CLOSED |
| RR-PF-04 full-batch current-process env visibility | CLOSED |
| RR-PF-04 prior selected-pair runtime-assembly prewarm | SUPERSEDED AND CLOSED by CURRENT contradiction correction |
| RR-PF-05 executable per-slice per-file coverage gates | CLOSED |
| AgentDS README-scope candidate | REJECTED/NO-FIX retained |

### 4.3 Controller direct CURRENT contradiction

`compose_open_host_options` selects compactor from the execution-profile baseline and
has no compactor override. Therefore selected-pair-only env could not support full
runtime assembly for non-DeepSeek choices. The final plan removes that unsupported
assembly and restores the OLD-aligned exact-two-root import-only behavior:

```text
dayu.cli.commands.interactive
dayu.cli.commands.prompt
```

It reads no env/secret, invokes no runtime function, creates no external state and does
not restore deleted Write/placeholder modules. Controller and both reviewers validate
this correction as closed.

### 4.4 New final-review findings

```text
AgentMiMo: 0
AgentDS:   0
Controller additional material finding: 0
```

Final accepted/open: `0`. Unclassified residual: `0`. Local plan blocker: `0`.

## 5. Boundary adjudication

The final plan is accepted because it keeps one owner for each init semantic and does
not add downstream repair or speculative framework:

- catalog owns the explicit provider/model choices, dynamic current-schema records and
  exact manifest roles;
- environment owns POSIX/Windows persistence and redacted outcomes;
- workspace transaction owns the two managed roots, containment, no-follow staging,
  publish, rollback and cleanup warnings;
- CLI orchestration owns the four-state flow, confirmations, waiting notification and
  import-only prewarm;
- existing ConfigLoader, file lock and Service discovery/Scene preparation remain the
  reused validation/runtime owners.

Issue 142/151/175/177/178, Web/WeChat/render implementation, Topic 8 changes and a
Topic 9 unified tool authorization framework remain excluded. Existing containment,
symlink, secret-handling, resource-budget and other local safety boundaries are not
removed.

## 6. Residual risks

The plan correctly classifies, without hiding or expanding, these implementation-time
risks:

- Windows `setx` has no cross-variable rollback; workspace publish remains blocked on
  partial failure and output contains names only.
- Two managed roots cannot be replaced by one syscall; recovery uses same-filesystem
  rename plus inverse rollback.
- Cleanup after the publication boundary may warn without rolling back success.
- `.dayu-init.lock` serializes init only; RESET warns the user to stop active Dayu
  writers.
- Import roots can gain future import-time side effects; current tests must prove zero
  network, secret need and external mutation, and drift stops at Controller.
- The real Windows runner, including the two R11 `.cmd` nodes, remains a release/umbrella
  aggregate gate and is not fabricated locally.

## 7. Verdict and next gate

Verdict:

```text
PASS / FINAL_R12_PLAN_ACCEPTED
```

Next gate is one exact-scope accepted-plan local commit containing only the R12 plan,
its complete plan/review/control evidence and this adjudication. After that commit,
Controller may authorize AgentCodex S1 implementation under the accepted plan. No
push, PR, aggregate closeout or Windows success claim is authorized by this verdict.
