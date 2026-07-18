# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan Controller validation

## 1. Gate 与 immutable target

- umbrella remains the existing `WU-SEMANTIC-OWNERSHIP-01` remediation continuation；R12 is its final internal sub-WU。
- entry base：`5d4deef8d37fb75b496d33fef9e2da11111a76d6`，tree
  `b0879b5e6ee0369119737fd925502eda8f4c58e2`。
- Controller entry：
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-entry-controller-validation.md`，118 lines /
  8,731 bytes / SHA-256 `678a1e424c325d8c170dee3d0375e2387149c3c3ff4c4e0440416dafa3a7a489`。
- AgentCodex plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，483 lines /
  41,413 bytes / SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`。
  Controller已完整读取全部483行，including the untruncated §5—§7 state/transaction/prewarm contract。
- this gate authorizes review only。No implementation、test/README/product mutation、stage、commit、aggregate、push or PR。

## 2. Scope 与 source validation

Controller复核：

- AgentCodex只新增plan；既有working changes仍只有Controller-owned control和entry artifact，staged set empty。
- `git diff --check`与plan no-index whitespace check均无诊断；无placeholder/TODO/TBD。
- current init/argparse/filelock/config/test/README source hashes、R11 base/tree、OLD init hash and all 16 manifest hashes
  match the plan's exact locks。
- current package/repository have no product-owned `assets`；plan correctly keeps user `assets` and `portfolio` outside the
  only managed-root manifest。
- Controller independently ran current baseline
  `pytest -q tests/cli/test_init_command.py tests/cli/test_arg_parsing.py`：`82 passed` with three existing edgar
  deprecation warnings。This proves the current copier contract is internally covered，not that it satisfies the adjudicated product truth。
- no current code/design contradiction blocks planning；OLD remains workflow evidence only，not a schema/architecture owner。

## 3. Owner、contract 与 slice validation

Plan correctly separates：

1. `init_catalog.py` owns the typed 15-choice catalog、dynamic Ollama/custom current-schema record and exact 16-manifest role
   projection；
2. `init_environment.py` owns explicit POSIX/Windows persistence、redaction、atomic single-profile publish and Windows partial
   success disclosure；
3. `init_workspace.py` owns one `.dayu`/`config` manifest、snapshot/mode、containment/symlink/no-follow、same-filesystem
   staging、swap/rollback/reset；
4. `commands/init.py` only orchestrates interaction、ordered publication and first/reset-only non-network prewarm；
5. runtime file lock、ConfigLoader/schema and Service/Fins preparation stay at existing owners。

The three cumulative slices are implementation-sized and independently reviewable：S1 owner contracts，S2 four-state
transaction/orchestration，S3 prewarm/docs/POSIX+Windows evidence。Each has an exact candidate allowlist、tests、coverage、
pyright/Ruff/diff/scans and a review checkpoint。No intermediate slice commit or later gate is self-authorized。

The plan preserves the adjudicated behavioral truths：

- PRESERVE keeps the existing tree and fills only missing package prompt assets before explicit current selection projection；
- OVERWRITE and RESET start from package defaults，without old-tree merge or schema compatibility；
- RESET defaults No before mutation，revalidates under one external lock，deletes only whole `.dayu` and `config` and never
  deletes user assets/portfolio；
- secret values do not enter JSON/log/artifact/prompt/trace and environment mutation precedes config publication；
- prewarm is post-publish、first/reset-only、non-network and warning-only；
- Issue 142/151/175/177/178、Web/WeChat/render trackers、Topic 8 and Topic 9 remain outside implementation。

## 4. Mandatory adversarial review attention

The immutable plan is admitted to dual complete review，not yet accepted。Reviewers must independently adjudicate，at minimum，
these direct-evidence challenges；they are not pre-decided findings：

- **Ruff baseline feasibility**：the plan says full `python -m ruff check dayu/ tests/ utils/` must be zero，but Controller ran
  that exact command at the immutable base and reproduced exactly `144 errors` across unrelated historical paths。The accepted
  requirement cannot authorize a repository-wide cleanup；review must decide the exact baseline/current-delta and changed-path
  zero contract without weakening R12 quality。
- **nonexistent workspace root**：current init creates a fresh workspace root，while plan §6.3 requires an existing ordinary
  directory and does not explicitly assign creation/cleanup before the external lock。Review must prove first-init on a new path
  remains code-generatable without mutation before an applicable safety/rollback boundary。
- **prewarm resource lifecycle**：the listed Service/Fins public preparation seams may allocate local resources or owned runtime
  objects。Review must verify exact construction/close/no-network/no-business-data behavior rather than accepting “public seam”
  as sufficient cleanup evidence。
- **post-publish cleanup failure**：review must verify whether backup cleanup/fsync failure is a rollback-triggering publication
  failure or a recoverable diagnostic，and ensure the state machine never reports failed init while silently leaving a new
  published tree without the documented recovery truth。
- **static/dynamic catalog split**：`custom-openai` is absent from package defaults by design。Review must ensure static package
  validation does not require that dynamic record before it is built and that no duplicate schema/default owner is introduced。

Both reviewers must cover the full 483-line target，not only these challenges。Any accepted finding must be fixed in the plan by
AgentCodex and receive concurrent complete re-review before plan acceptance。

## 5. Security and residual validation

Retained security/correctness behavior is explicit：lexical/resolved containment、nested/dangling symlink rejection、no-follow
delete、same-filesystem staging、atomic replace/rollback、single publisher lock、POSIX profile symlink/mode/quoting、Windows
argument-safe invocation and secret non-persistence。The plan does not create a unified tool authorization framework。

Known residuals remain owned and disclosed：Windows multi-variable persistence is not cross-call atomic；multiple managed roots
are recoverable ordered renames rather than one syscall；prewarm may exercise existing local initialization but cannot take
assets/portfolio ownership。R11 real Windows execution remains `PENDING_RELEASE_BLOCKER` for umbrella aggregate acceptance and
is intentionally composed into the R12 Windows job rather than waived。

## 6. Verdict

`PASS_WITH_MANDATORY_CHALLENGES / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`

Next gate is concurrent AgentMiMo/AgentDS complete plan review of exact SHA-256
`6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`。Implementation、commit and later gates remain
unauthorized。
