# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan-entry Controller validation

## 1. Gate identity

- active work unit remains the existing umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- R12 is the final internal remediation sub-WU，not a new work unit、feature、issue or reopened historical sub-WU。
- user goal confirmation for this remediation continuation is already complete；no adjudicated product question is reopened。
- current gate is **R12 plan only**。Implementation、tests、README/product changes、accepted commit、aggregate
  deepreview、push and PR are not authorized by this artifact。
- entry base is R11 completion commit `5d4deef8d37fb75b496d33fef9e2da11111a76d6`，tree
  `b0879b5e6ee0369119737fd925502eda8f4c58e2`；working and staged trees were empty at entry。

## 2. Authority order and owner decision

Plan must apply the project source order already confirmed by the user，with
`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` controlling any review conflict，then
`docs/ui/design.md` and the accepted umbrella plan §19 supplying the current product contract。OLD
`/Users/leo/workspace/dayu-agent` is evidence for the user workflow only；its old schemas、migration framework、module
boundaries、compatibility behavior and unimplemented products are not portable authority。

Semantic owners for planning are fixed：

- CLI init orchestration owns interaction、typed selection、managed-root mutation and first/reset prewarm；
- a single init-owned typed catalog owns provider/model pairs、required environment refs and known-manifest roles；
- an OS-specific environment writer owns explicitly confirmed secret persistence；secret values never enter workspace JSON、
  logs、artifacts、prompts、trace or LLM-readable text；
- runtime `ConfigLoader` and current packaged JSON schemas own configuration validity；
- `dayu.runtime.filelock` owns the reusable layer-neutral lock primitive；
- one init workspace transaction owner consumes one managed-root manifest and owns containment、symlink rejection、
  same-filesystem staging/swap/rollback and reset deletion。

Do not move these semantics into argparse、README、test fixtures、display-only helpers or downstream fallback branches。

## 3. Direct CURRENT evidence

Controller inspected the R11-complete tree and found the adjudicated gap still real：

- `dayu/cli/commands/init.py` is a 470-line non-interactive filesystem copier；SHA-256
  `c33db7318476e54f81630c5e5ec8b33e94a6281dd12ecd2ddc7ee85da57b10ab`。It has no typed provider/model
  selection、API-key/optional-integration flow、environment persistence、manifest model projection、workspace lock or
  prewarm。
- ordinary existing config currently fails on every existing packaged asset unless `--overwrite`；this contradicts
  preserve-existing plus missing-prompt completion。
- `--overwrite` currently copies the existing tree into staging before overlaying packaged assets，so user extension files
  survive；the accepted contract requires a fresh current packaged tree followed only by this invocation's selected updates。
- reset currently executes without confirmation and deletes four separately derived paths
  (`config`、Host、artifact、Web storage-state) rather than consuming one managed-root manifest for whole `.dayu` and
  `config`。It does retain lexical/resolved containment、nested-symlink rejection and no-follow deletion；those protections
  must not be weakened。
- `dayu/cli/arg_parsing.py` exposes only `--reset` and `--overwrite` for init；SHA-256
  `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e`。
- `dayu/runtime/filelock.py` already provides the layer-neutral synchronous `file_lock` owner；SHA-256
  `269f30e4bacb87660713d68d192027f2e6c0c88657014871fbcab14a1f5bf2df`。
- `dayu/config/models.json` already contains most adjudicated static model records but lacks the final catalog/dynamic
  current-schema proof；SHA-256 `d817a17135a01e1e7d89ada9e6b93b107d29fa9715105340c7ff44d505cf8b68`。
- root/config/tests READMEs still describe init as a copier that refuses ordinary existing config and never persists
  secrets；documentation is therefore downstream of implementation，not current product truth。

OLD evidence is deliberately bounded：`/Users/leo/workspace/dayu-agent/dayu/cli/commands/init.py` is 1,956 lines /
SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` and contains the historical
provider/model/key/optional integration/prewarm interaction。The plan must extract the user workflow and reject its old
migration、old config names、ambient authority、duplicated catalog/role inference and any unsafe secret/path mechanics。

## 4. Mandatory plan contract

AgentCodex must produce one code-generation-ready plan at
`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，derived from direct current code and OLD workflow evidence。
The plan must have at most three cumulative slices and explicitly close：

1. typed catalog、provider/model selection、required API key、optional Tavily/Serper/FMP/HuggingFace configuration、
   known-manifest default model projection、Ollama/custom dynamic current-schema records and explicitly confirmed
   POSIX/Windows environment persistence；
2. one workspace lock and transaction for first/preserve/overwrite/reset，one managed-root manifest whose current roots
   are only whole `.dayu` and `config`，default-No reset confirmation before mutation，whole-tree atomic publish/rollback，
   containment and symlink fail-closed behavior；
3. non-network first/reset-only prewarm、real POSIX smoke、Windows CI evidence and README closure。

The plan must state exact role mapping and catalog values from umbrella §19，exact candidate production/test/document paths，
slice handoffs，immutable starting hashes，owner-level tests，per-modified-file coverage target `>=80%`，full pyright with zero
new/expanded errors，Ruff、`git diff --check`、README triggers、secret/compatibility/propagation scans and realistic
concurrency/interruption/rollback smokes。

Mandatory state semantics：

- no-overwrite existing config preserves all existing content and only adds missing packaged prompt assets before explicit
  selected model/manifest updates；
- overwrite begins from current packaged defaults and does not merge the old tree；
- reset lists exact existing managed targets and defaults to No before any mutation，never deletes `portfolio`、user-created
  `assets` or other business files，then runs the first-init path after confirmed deletion；
- the current package has no product-owned assets，so R12 neither creates nor imports `dayu/assets` and does not pre-sign
  Issue 151 ownership；
- `.dayu/web_tools_storage_states` is deleted only as a child of whole `.dayu` reset；no Issue 178 lifecycle is implemented；
- prewarm performs real assembly/config/registry loads without LLM/HTTP/network and runs once only after successful first or
  reset publication；failure is a warning after successful init，not a rollback trigger；
- environment persistence succeeds before config publication。If a later config swap fails，report only written environment
  variable names，never values；do not claim cross-resource atomicity on Windows or POSIX profiles。

## 5. Security and no-scope gates

Retain and test lexical/resolved containment、ancestor/nested symlink rejection、no-follow deletion、same-filesystem staging、
backup rollback、atomic replacement、single-publisher lock、profile symlink rejection、shell/argv-safe environment writes and
secret non-persistence。This is local defensive/correctness behavior，not a unified tool authorization framework。

Do not implement Issue 142 migrations、Issue 151 write/assets、Issue 175 process isolation、Issue 177 Doc truncation connection、
Issue 178 Web storage lifecycle、Web/WeChat/render tracker features、Topic 8 changes or Topic 9 authorization schema/policy。
Do not add old-schema compatibility、fallback/shim、ambient task/thread authority、user-manifest role guessing or hidden
profile writes without explicit confirmation。

Any direct contradiction in current schemas/design，need for an owner outside the authorized candidate boundary，or need to
persist a secret without explicit user choice is a stop condition for Controller adjudication。Otherwise proceed directly to
plan and stop at Controller plan-validation checkpoint。

## 6. Verdict

`PASS / READY_FOR_AGENTCODEX_R12_PLAN_ONLY`

Only the plan artifact named above is AgentCodex-writable in this gate。R12 implementation and all later gates remain
unauthorized。
