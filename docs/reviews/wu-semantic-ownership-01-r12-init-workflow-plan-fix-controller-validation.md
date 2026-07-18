# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan-fix Controller validation

## 1. Gate identity and immutable target

- Active work unit remains the existing umbrella `WU-SEMANTIC-OWNERSHIP-01`.
- R12 is its final internal remediation sub-WU, not a new WU and not a reopened historical sub-WU.
- This gate validates the adjudicated plan-only fix. It does not authorize implementation, staging, commit, aggregate review,
  push, PR, or any deferred issue.
- Immutable original plan: 483 lines / 41,413 bytes / SHA-256
  `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`.
- Fixed review target: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`, 558 lines / 56,459 bytes /
  SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`.
- AgentCodex fix evidence:
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-fix-codex.md`, 137 lines / 12,700 bytes /
  SHA-256 `27c1083159181ce5c5bb9b685bd25a282bff02b9e84df10e3a753eabf6fea824`.

Controller read both final artifacts completely and matched the fixed-plan SHA after AgentCodex's final consistency edit. No
earlier intermediate SHA is accepted as the re-review target.

## 2. Protected scope and source-lock validation

The working tree contains the intentionally retained R12 control/review artifacts and the Controller-owned control edit. The
plan-fix gate added only the fixed plan content and the AgentCodex fix artifact; production, tests, README, design, workflow and
packaging files remain byte-identical to accepted R11 completion commit
`5d4deef8d37fb75b496d33fef9e2da11111a76d6`.

Protected artifacts still match their entry hashes:

| Artifact | SHA-256 |
|---|---|
| R12 plan-entry Controller validation | `678a1e424c325d8c170dee3d0375e2387149c3c3ff4c4e0440416dafa3a7a489` |
| original plan Controller validation | `693e76a36cf1aeabc02e10288035cee45dc8cb57f3c08f0b9b857475f12ea520` |
| AgentMiMo original plan review | `88714fc66d964ec54d587ae651210d4a79c62bd099de50830d9fcb0b169fdeec` |
| AgentDS corrected original plan review | `f83fc2d7058be2941637cd9c43f17ef863940fd055712ee848145b56c1699ff2` |
| original plan-review Controller adjudication | `73445f3d09c145e34f38dbf9311bd75e534f0f9318df702e127996453a33bc46` |

Controller independently rechecked the principal implementation locks. Current `commands/init.py`, `arg_parsing.py`, runtime
filelock/ConfigLoader, package models, two existing CLI test files and three README targets all match plan section 2. Every
planned new Python/test/workflow path is still absent. The bounded OLD init source still has SHA-256
`f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e`.

Mechanical checks:

- `git diff --check`: exit 0, no diagnostic.
- `git diff --cached --name-only`: empty.
- fixed plan and fix artifact no-index whitespace checks: no diagnostic; exit 1 is the expected new-file diff status.
- `.venv` full Ruff JSON: exactly 144 diagnostics and SHA-256
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`.
- No product tests or pyright were rerun because this gate changes only plan/control/review Markdown. The already validated
  current CLI baseline remains 82 passed; implementation gates retain full test, coverage and pyright requirements.

## 3. Accepted finding closure validation

| Group | Controller validation of fixed-plan contract | Status before re-review |
|---|---|---|
| `R12-PF-01` | Each cumulative changed/new Python allowlist must have zero Ruff diagnostics; full Ruff must retain exact JSON count, SHA and bytewise `cmp`; full pyright remains zero. | fixed / validated |
| `R12-PF-02` | `commands/init.py` is the sole pre-lock fresh-root bootstrap owner; RESET No precedes creation; identity, permission, ENOSPC, file and symlink races are explicit. | fixed / validated |
| `R12-PF-03` | Prewarm uses exact `prompt` and `interactive` scene IDs through one async composition boundary; current typed results have no close contract, and contract drift is a stop condition. | fixed / validated |
| `R12-PF-04` | Publication success is all required replaces plus parent durability fsync; pre-boundary failures roll back, post-boundary backup cleanup failures warn without reversing success. | fixed / validated |
| `R12-PF-05` | Static validation covers 13 paired choices plus package Ollama; absent package custom is expected and dynamic custom is validated only after staging construction. | fixed / validated |
| `R12-PF-06` | Staging/backup is unpredictable, unique, private, workspace-root-local and same-filesystem; temporary names are not public or LLM-facing protocol. | fixed / validated |
| `R12-PF-07` | Lock invocation explicitly uses `timeout_seconds=None` and `create_parent_dirs=False`; waiting is interruptible and no finite magic timeout appears. | fixed / validated |
| `R12-PF-08` | PRESERVE copies only missing ordinary prompt files and creates directories only as parents; no empty-directory or directory-merge contract exists. | fixed / validated |
| `R12-PF-09` | `.dayu-init.lock` serializes init only; RESET warns users to stop active Dayu; Host lock/discovery/kill remains forbidden and external writers remain an owned residual. | fixed / validated |
| `R12-PF-10` | Custom temperatures come from the exact OLD custom table and are explicitly projected into the current three-field hint schema; Ollama/provider-default guessing is removed. | fixed / validated |
| `R12-PF-11` | A missing supported POSIX profile is created only after confirmation by private same-parent atomic replace with final mode `0600`; existing mode and symlink rejection remain explicit. | fixed / validated |
| `R12-PF-12` | Init owns only confirmed whole-root RESET transaction; `.dayu` internal naming, creation and lifecycle stay with current Host/runtime/CLI/artifact owners. | fixed / validated |

All twelve accepted groups are closed at Controller validation level. They remain subject to two independent complete re-reviews
of the exact fixed-plan SHA. No accepted finding may be treated as closed for plan acceptance if either reviewer supplies a new
evidence-backed contradiction.

## 4. Rejected expansion remains absent

The fixed plan does not:

- clean the 144 unrelated Ruff findings or weaken full pyright;
- freeze a public temporary-name protocol;
- add a finite lock timeout, Host lock, process discovery or process kill;
- invent close/cache/FD lifecycle for preparation results without such a current contract;
- create a general migration, transaction, provider-plugin or authorization framework;
- implement Issue 142, 151, 175, 177, 178 or Web/WeChat/render tracked work;
- create compatibility, fallback, loose parsing or downstream repair semantics.

Topic 8 remains a no-code decision preserving the Engine 240-character redacted/truncated exception projection. Topic 9 remains
a no-code decision and no unified tool authorization framework is designed or implemented. Existing containment, symlink,
atomic publication, environment-secret, DNS/peer/resource-budget and other local defensive boundaries are not removed.

## 5. Residual risk and next gate

The plan classifies all remaining risks with owners: Windows `setx` cannot form a multi-variable transaction; multi-root publish
is ordered rename plus rollback rather than one syscall; post-boundary cleanup can warn; prewarm may initialize existing local
owners; init lock does not fence active Host writers; malformed shell marker blocks fail closed; repository Ruff history remains
outside R12. None is unclassified and none blocks complete plan re-review.

Current ledger before re-review:

| Category | Count | Status |
|---|---:|---|
| accepted plan-fix groups | 12 | fixed / Controller-validated |
| accepted/open finding | 0 | none before re-review |
| rejected/no-fix expansion | 5 | remains absent |
| blocker/design contradiction | 0 | none |
| unclassified residual | 0 | none |

Next and only authorized gate is concurrent complete plan re-review by AgentMiMo and AgentDS against immutable fixed-plan SHA
`37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`. Reviewers must recheck the complete plan, all twelve
closures, slice boundaries, security retention, exact tests/coverage/type/lint/smoke gates and deferred/no-code boundaries.

Implementation, accepted-plan commit, aggregate review, R11/R12 Windows workflow execution, push and PR remain unauthorized.

## 6. Verdict

`PASS / READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REREVIEW`
