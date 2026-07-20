# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan review Controller adjudication

## 1. Immutable review target and artifacts

- plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，483 lines / 41,413 bytes /
  SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`。
- AgentMiMo complete review：
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-review-mimo.md`，236 lines / 20,852 bytes /
  SHA-256 `88714fc66d964ec54d587ae651210d4a79c62bd099de50830d9fcb0b169fdeec`，verdict
  `pass-with-risks`，five findings plus two open questions。
- AgentDS corrected complete review：
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-review-ds.md`，365 lines / 26,496 bytes /
  SHA-256 `f83fc2d7058be2941637cd9c43f17ef863940fd055712ee848145b56c1699ff2`，verdict
  `PASS_WITH_FINDINGS`，five Controller-challenge findings plus five additional findings。
- both reviewers matched target SHA、current 82-test baseline、144-error Ruff baseline、current model/static-dynamic facts、
  no-scope boundaries and the R11 Windows nodes。The reviews did not mutate the target/control/product/tests/README and did not
  stage or commit。

## 2. Controller decision principles

Controller accepts a plan change only where direct CURRENT/design/OLD-workflow evidence shows ambiguity or an impossible gate。
It does not promote temporary path names into a public contract，invent closable resources that current public preparation seams
do not allocate，or expand R12 into repository-wide lint cleanup、Host locking、migration、assets or authorization work。

No product decision or user clarification is required。All accepted changes stay within the existing R12 plan owner and are
plan-only。

## 3. Accepted plan-fix groups

### R12-PF-01 — Ruff gate must be executable without scope expansion

Accept MiMo `FINDING-001` and DS Challenge/F-01。The immutable base has exactly144 full-tree Ruff errors。Replace the false
full-zero gate with both：

- every R12 changed/new Python path must pass scoped Ruff with zero finding；
- full `dayu/ tests/ utils/` Ruff is an immutable-baseline comparison：exact pre-existing findings may remain，but R12 must add
  zero、remove none by unrelated edits and change no existing diagnostic outside authorized paths。Record baseline/current
  fingerprints，not only a count。

Do not fix the144 unrelated findings and do not weaken full pyright zero。

### R12-PF-02 — fresh workspace root creation has an explicit owner

Accept MiMo `FINDING-002` and DS Challenge/F-02。Before the workspace-local lock can exist，`commands/init.py` must explicitly
resolve the requested path，reject an existing symlink/non-directory，and create a missing ordinary workspace root with
`mkdir(parents=True, exist_ok=True)`。This root creation is the minimal pre-lock bootstrap，not a managed-root publication；all
subsequent mutation is locked。Plan/tests must cover fresh path、concurrent creation、permission/ENOSPC and existing file/symlink。

### R12-PF-03 — prewarm invocation is exact and does not invent lifecycle work

Accept MiMo OQ-001/OQ-002 and the code-generatability portion of DS Challenge/F-03。Specify exact prompt/interactive scene IDs，
the async execution boundary for `prepare_entrypoint_runtime`，and the current preparation results as pure typed configuration /
metadata objects with no owned close contract。Keep the zero-network guard and repeated-call test。

Reject the speculative part of DS F-03 that asks R12 to create generic close/cache/FD cleanup for objects with no such current
owner contract。If current code changes before implementation and a real closable object appears，that is a stop condition，not a
plan-invented fallback。

### R12-PF-04 — publication success and cleanup failure are distinct

Accept DS Challenge/F-04 and MiMo Challenge-4 recommendation。Define publication success as the required `os.replace` sequence
plus parent-directory durability barrier。After that boundary，backup no-follow deletion/fsync failure is a typed warning /
recoverable diagnostic with the exact retained backup path；it does not roll back or report the already-published config as
failed。Failures before the boundary still roll back。Tests must cover both sides。

### R12-PF-05 — static and dynamic catalog validation are disjoint

Accept MiMo `FINDING-004` and DS Challenge/F-05。Package-default validation covers the13 non-dynamic paired choices plus
package `ollama`；`custom-openai` absence is expected and must not fail that phase。Custom is validated only after its explicit
current-schema record is built in staging and reloaded by ConfigLoader。Tests must fail closed on missing/mismatched static IDs
without making custom absence an error。

### R12-PF-06 — private staging location is precise but not public protocol

Accept MiMo `FINDING-003` only as implementation-plan precision。Say that unique private staging/backup directories are created
under the workspace root，the same parent filesystem as managed targets，and validate `st_dev`。Do not freeze exact temporary
names/prefixes or expose them as a stable user/LLM-facing contract；temporary naming remains implementation detail per design。

### R12-PF-07 — lock wait policy is explicit and interruptible

Accept MiMo `FINDING-005` narrowly。Reuse the current runtime lock default indefinite wait explicitly (`timeout_seconds=None`)
rather than inventing a deployment magic timeout。Waiting is interruptible；SIGINT must publish nothing and release any acquired
token。Document lock-wait visibility without printing secrets。

### R12-PF-08 — PRESERVE copies missing prompt files only

Accept DS `F-06`。Define packaged prompt assets at file granularity；directories are created only as parents for a missing file。
No empty-directory protocol or directory-level merge is introduced。

### R12-PF-09 — init lock does not claim active Host exclusion

Accept DS `F-07` after correcting its premise。Current Host does not consume `.dayu-init.lock`，so the lock proves init-to-init
serialization only。Plan/README/reset confirmation must tell the user to stop active Dayu processes before confirmed RESET and
record active external writers as a residual；R12 must not add Host locking、process discovery、kill or unified governance。

### R12-PF-10 — custom runtime hints have a direct source

Accept DS `F-08`。Trace every custom runtime-hint value to the exact OLD init workflow record and current-schema field mapping，
or delete any value without such evidence。The plan must name that source and keep the init catalog as the current projection
owner；do not call arbitrary copied provider defaults a product decision。

### R12-PF-11 — absent POSIX profile behavior is explicit

Accept DS `F-09`。For supported zsh/bash，an absent selected profile is created atomically with mode `0600` after explicit
persistence confirmation；existing mode is preserved，and symlink/dangling symlink remains fail closed。Add the direct test。

### R12-PF-12 — `.dayu` internal state remains Host/runtime-owned

Accept DS `F-10`。State explicitly：init owns whole-root RESET transaction only；Host/runtime/CLI/artifact owners retain all
internal `.dayu` naming、creation and lifecycle。FIRST/PRESERVE/OVERWRITE do not create、migrate or reinterpret `.dayu`。

## 4. Rejected/no-fix portions and observations

- MiMo Challenge-3 no-finding is accepted as evidence；no generic prewarm close framework is added。
- MiMo Challenge-4 no-finding is accepted only insofar as the intended semantics are already directionally correct；PF-04 still
  requires explicit success-boundary text and tests because DS showed code-generation ambiguity。
- DS OQ-01/OQ-02 are no-fix observations；post-publish warning-only prewarm and exact endpoint input remain the adjudicated
  design。
- MiMo's suggested option to fix three pre-existing CLI Ruff findings is rejected；R12 may not edit unrelated code to improve a
  baseline。
- Fixed staging prefixes、finite lock magic timeout、Host process-kill/discovery and speculative resource-close APIs are rejected。

## 5. Finding ledger and next gate

| Category | Count | Status |
|---|---:|---|
| accepted plan-fix groups | 12 | open pending AgentCodex fix |
| rejected/no-fix portions | 5 | closed with reason |
| unclassified material finding | 0 | closed |
| product question / blocker | 0 | none |

AgentCodex must fix all12 accepted groups in the same plan and produce
`docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-fix-codex.md`。Only those two paths are AgentCodex-writable in
the next gate。Production、tests、README、control、review artifacts、stage/commit remain unauthorized。

After Controller validates exact scope and content，the same fixed immutable plan must receive concurrent complete re-review by
AgentMiMo and AgentDS。No implementation or accepted-plan commit before both reviewers close every accepted group and any new
accepted finding。

## 6. Verdict

`PLAN_FIX_REQUIRED / 12 ACCEPTED GROUPS / ZERO BLOCKER`
