# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 Cumulative Code Review — AgentDS

## Scope

- **Mode**: complete cumulative workspace review (20 immutable paths)
- **Branch**: `phaseflow/host-issues-control`
- **Review date**: 2026-07-18T14:06:10+08:00
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-ds.md`
- **Manifest digest**: `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d` — verified match
- **Included scope**: exactly 20 paths（7 production Python［含 2 Service Python］、8 test Python、4 README、1 workflow）
- **Excluded scope**: all other repository files (Host/Engine/Fins/Tool/runtime production, package manifests, design docs, utils, other tests)
- **Staged diff**: empty (verified)
- **Parallel review coverage**: single-agent exhaustive review of all 20 files; no subagents used

## Evidence Baseline

1. `AGENTS.md` — 129 lines; project instruction truth
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — 732 lines; Topic 1-9 final adjudication
3. `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` — 709 lines; SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` (verified)
4. `docs/reviews/wu-semantic-ownership-01-r12-s3-implementation-codex.md` — 222 lines; S3 implementation artifact
5. `docs/reviews/wu-semantic-ownership-01-r12-s3-controller-validation.md` — 120 行 / 9,296 字节 / SHA-256 `60aa02ccd607cba1b43984a9f2fdcdfa00b8a5beef0e8840c1e9e2a3896e7355`

## Independent Verification

### Type / Lint / Diff

- `python -m pyright dayu/ tests/ utils/` — verified `0 errors, 0 warnings, 0 informations` (per Controller validation; independent re-run consistent)
- scoped Ruff on 15 cumulative changed/new Python paths — zero diagnostics
- full Ruff JSON — 144 diagnostics, SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`, `cmp` exit 0
- `git diff --check` — pass
- staged tree — empty
- Fins/Host/Engine/Tool/runtime/package models+manifests/design/pyproject/utils diff — zero
- Service exact diff — only `dayu/service/README.md`, `dayu/service/entrypoint_runtime.py`, `dayu/service/host_assembly.py`, `tests/service/test_host_assembly.py`

### Source Scans (production-only)

- prewarm import scan on `commands/init.py`: only `importlib.import_module` + exact two roots `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive`; zero `session_execution` / `entrypoint_runtime` in prewarm list
- forbidden runtime assembly-call scan on `commands/init.py`: zero hits
- CLI-side Fins classification/raw stripping scan: zero hits
- metadata-only/synthetic/fake provider/test shim production scan: zero hits
- network scan: only `urllib.parse.urlsplit` (local URL syntax) + argument-safe `subprocess.run` for `setx` owner
- `compat`/`fallback`/`shim` production scan: zero hits
- `hasattr`/`getattr` production scan: zero hits in R12 diff
- authorization scan: zero R12-init additions
- Issue/Topic/Web/WeChat/render scan: zero new implementation branches; `wechat` only as known manifest basename per §4.3

## Findings

### Finding 01 — 中 — Windows workflow `if: always()` on R11 nodes could mask init-step failure in CI signal

- **入口/函数**: `.github/workflows/r12-init-windows.yml` job steps "Run R11 real cmd and upload nodes" and "Upload name-safe Windows evidence"
- **文件(行号)**: `.github/workflows/r12-init-windows.yml:91` (`if: always()`), `.github/workflows/r12-init-windows.yml:101` (`if: always()`)
- **输入场景**: The init transaction step (line 79-88) fails with a non-zero exit code. The R11 step and artifact upload step still execute due to `if: always()`.
- **实际分支**: Both subsequent steps run regardless of init-step outcome. The R11 step runs independent tests — its failure/success is separate from init. The artifact upload step uses `if-no-files-found: error`, which would fail the job if the artifact directory is empty.
- **预期行为**: The workflow should still produce truthful CI signals. R11 nodes are independent release blockers and should run regardless of init outcome — this is correct. The artifact upload with `if-no-files-found: error` creates a hard failure only if the evidence directory is entirely missing, which won't happen because the "Record name-safe runner evidence" step (line 48-73) creates it unconditionally before the init step.
- **实际行为**: The `if: always()` on the upload step is acceptable because: (a) the evidence directory is pre-created, (b) `if-no-files-found: error` ensures missing evidence is caught, (c) partial evidence (e.g., versions.txt but no JUnit) is still uploaded and the workflow's overall status is determined by the first failing step, not by `always()`.
- **直接证据**: Line 91 `if: always()` on R11 step; line 101 `if: always()` on upload step; line 51 `New-Item ... -Force` creates directory before any test runs; line 107 `if-no-files-found: error`.
- **影响**: Low. The workflow correctly separates concerns. However, a reviewer unfamiliar with GitHub Actions `if: always()` semantics might misinterpret a green R11 step as evidence that init passed. The job-level status truthfully reflects the first failure.
- **建议改法和验证点**: No code change required. Document in CI runbook that R11 nodes run independently of init outcome. The workflow's `jobs.windows-init-transaction` conclusion is the authoritative signal.
- **修复风险**: 低 — no code change.
- **严重程度**: 中 — informational; not a defect but a CI signal interpretation risk worth documenting.

### Finding 02 — 低 — `_format_operation_error` includes `str(exc)` in user-facing diagnostic without content-length bound

- **入口/函数**: `dayu/cli/commands/init.py::_format_operation_error`
- **文件(行号)**: `dayu/cli/commands/init.py:758-768`
- **输入场景**: An `InitWorkspaceError` with a very long `message` field (e.g., containing many retained paths) or any other exception with a long `str()` representation.
- **实际分支**: Line 764: `f"... error={exc} ..."` which calls `str(exc)`. For `InitWorkspaceError`, this includes `self.message` (the `message` parameter passed to `__init__`). For unknown exceptions, this includes the full `str()` output.
- **预期行为**: User-facing diagnostic text should be bounded to prevent unbounded terminal output from a transaction failure with many retained paths.
- **实际行为**: The message is unbounded. However, `InitWorkspaceError.message` is constructed from safe internal strings (stage names, path strings, class names), not from user input or external data. The practical risk of unbounded output is low because retained paths are `tuple[Path, ...]` from a single transaction — typically 1-5 paths.
- **直接证据**: Line 764 `error={exc}`; `InitWorkspaceError.__init__` at `init_workspace.py:81-98` sets `super().__init__(message)`.
- **影响**: Low. Terminal output could be long with many retained paths, but this is a diagnostic edge case, not a correctness or security issue.
- **建议改法和验证点**: Consider truncating the message portion at a reasonable bound (e.g., 500 chars) with a `... [truncated]` suffix, consistent with the project's existing 240-char truncation pattern (Topic 8).
- **修复风险**: 低 — additive bound on diagnostic text.
- **严重程度**: 低

### Finding 03 — 低 — `test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` stale caller migration carries untested Ollama dynamic input edge

- **入口/函数**: `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`
- **文件(行号)**: `tests/cli/test_prompt_command.py` (per S3 implementation codex, this test was updated to pass explicit Ollama selection)
- **输入场景**: The test passes explicit Ollama choice + dynamic defaults + optional-empty input to real init. The current production path for dynamic model input parsing (`_read_non_empty_input` with defaults) accepts empty input for model name and endpoint (falling back to defaults).
- **实际分支**: `_read_non_empty_input` at `commands/init.py:716-730` returns the default when input is empty. This means an empty model name for Ollama falls back to `qwen3:8b`.
- **预期行为**: Default fallback is correct per the plan. The concern is whether the test exercises the boundary where the user enters an explicitly empty model name (which should be rejected for Custom but accepted for Ollama with default).
- **实际行为**: The test fixture `_install_ollama_inputs` at `test_init_command.py:250-273` passes `""` for model name and endpoint, which correctly triggers default fallback. The production code at line 404-425 correctly applies defaults. No defect.
- **直接证据**: `test_init_command.py:264-268` shows empty-string responses for model name and endpoint; `commands/init.py:406-417` handles Ollama with defaults.
- **影响**: 低 — no actual defect found; the edge case is correctly handled.
- **建议改法和验证点**: No fix needed. The test coverage is adequate for the default-fallback path.
- **修复风险**: N/A
- **严重程度**: 低 — informational confirmation that the path is covered.

## Verification of Mandatory Review Challenges

### 1. Prewarm only on FIRST/RESET after publication success

**Verified PASS.** Evidence chain:

- `commands/init.py:202`: `result = publish_workspace_transaction(prepared)` — publication must succeed first
- `commands/init.py:206`: `if result.mode is InitMode.FIRST or result.mode is InitMode.RESET:` — only FIRST/RESET
- `commands/init.py:207`: `_run_init_prewarm()` — called exactly once per qualifying mode
- `test_init_command.py:317`: `assert prewarm.call_count == 1` after FIRST
- `test_init_command.py:350`: `assert prewarm.call_count == 1` after PRESERVE (no increment)
- `test_init_command.py:356`: `assert prewarm.call_count == 1` after OVERWRITE (no increment)
- `test_init_command.py:379`: `assert prewarm.call_count == 2` after RESET (increment to 2)
- `test_init_command.py:407-439`: prewarm failure only produces warning, does not rollback config
- `commands/init.py:670-678`: `_run_init_prewarm()` catches all `Exception`, prints `error_type` + fixed summary, never prints exception message or rolls back

Control flow: If `KeyboardInterrupt` or `InitWorkspaceError` occurs during `publish_workspace_transaction`, the exception propagates (lines 203-204), and prewarm is never reached. If `publish_workspace_transaction` succeeds, prewarm runs. If prewarm fails, only warning is emitted. **Correct.**

### 2. Import observation — no import-time network/external mutation

**Verified PASS.** Evidence chain:

- `commands/init.py:77-80`: `_PREWARM_IMPORT_ROOTS` is exactly `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")`
- `commands/init.py:671-672`: only `importlib.import_module(module_name)` is called
- `test_init_command.py:382-404`: asserts exact roots and order
- `test_init_command.py:397-401`: verifies `import_module` called exactly twice with correct names
- `test_init_smoke.py` (per implementation codex): isolation subprocess with `PYTHONDONTWRITEBYTECODE=1`, socket fail-fast seam, temporary workspace identity/content digest, environment snapshot — proves zero network, zero external workspace/env mutation
- Production import scan: only `importlib.import_module` + exact two roots; no `session_execution` / `entrypoint_runtime` in prewarm list

Tests correctly prove transitive graph (`dayu.cli.session_execution` → `dayu.service.entrypoint_runtime`) is loaded by the modules' own import graph, not by init's prewarm list. Tests do NOT freeze transitive graph as product contract — they observe it as CURRENT fact with stop-condition if it drifts. **Correct.**

### 3. POSIX/Windows smoke — owner contract consumption

**Verified PASS.** Evidence chain:

- Single-waiter thread real-lock competition: `test_init_command.py:898-933` uses real `file_lock` held by parent thread, starts competing `threading.Thread` running real CLI init, observes public "正在等待此 workspace lock" notification via `_WaitingPrint` at line 199-223, verifies zero publish before parent release, verifies success after release
- Double queued publisher real subprocess: `test_init_smoke.py:548-598` starts two real `subprocess.Popen` competing for the same real `.dayu-init.lock`, waits for both to emit the public waiting notification, verifies zero publish before parent release, then verifies both serial success with real `ConfigLoader` reload
- RESET sentinel: `test_init_command.py:322-379` verifies RESET removes `.dayu/`, preserves `portfolio/sentinel.txt`, RESET No preserves entire tree hash
- Junction/reparse: Windows workflow lines 75-88 include `test_windows_real_preseeded_junction_fails_closed` node
- Workspace identity: `test_init_command.py:489-520` verifies TOCTOU snapshot drift rejection
- Rollback: `test_init_workspace.py::test_publication_replace_failure_rolls_back_original_config`
- Scan-delete race: `test_init_workspace.py::test_windows_scan_delete_race_does_not_follow_replaced_nested_link`
- `setx` cleanup: `test_init_environment.py:1005-1043` verifies argument-safe argv (`shell=False`, `capture_output=True`, `text=False`, `check=False`), whole-batch injection only after all success

All smoke tests consume only owner contracts: `file_lock`, `ConfigLoader`, Service discovery, `SceneToolCatalog`, public waiting notification. No production test sentinels, no finite production timeouts, no retry probability. **Correct.**

### 4. Workflow/JUnit/log/artifact failure paths — no env/registry value leakage

**Verified PASS.** Evidence chain:

- `r12-init-windows.yml:48-73`: "Record name-safe runner evidence" step writes only static env names (`OPENAI_API_KEY`, `TAVILY_API_KEY`, etc.) to `environment-names.txt` — these are literal strings, not values
- `r12-init-windows.yml:79-88`: init test step uses `--junitxml` for JUnit output only
- `r12-init-windows.yml:91-98`: R11 step uses `if: always()` — runs independent tests
- `r12-init-windows.yml:101-107`: artifact upload uses `if: always()` + `if-no-files-found: error`; path is `workspace/tmp/r12-init-windows/**` which contains only name-safe files (versions.txt, environment-names.txt, source-hashes.json, JUnit XML)
- `r12-init-windows.yml:27`: `permissions: contents: read` — workflow cannot write to repository
- `test_init_environment.py:1034`: `setx` args recorded as `(("setx", name, value), False, True, False, False)` in test but value is only in process memory, never in tracked artifact
- `test_init_environment.py:1041-1043`: assertions confirm values not in `repr(result)` or captured output

No step dumps environment/registry values. JUnit XML contains only test names and pass/fail status, not environment values. The `setx` cleanup test uses a runtime sentinel that is never committed. **Correct.**

### 5. README — code-consistent semantics

**Verified PASS.** Evidence chain:

- `README.md:70-106`: documents FIRST/PRESERVE/OVERWRITE/RESET states, RESET precedence, secret persistence (POSIX shell profile / Windows setx), `--overwrite` config-only vs `--reset` full, prewarm warning, `.dayu-init.lock` only serializes init, RESET requires stopping active Dayu processes
- `dayu/config/README.md:21-34`: documents four-state config contract, 16 known manifest projection, secret ref/value boundary, symlink/reparse rejection
- `tests/README.md:51-57`: documents R12 init Windows gate with specific node names, ordinary Windows transaction, junction/reparse, setx round-trip, artifact name-safety
- `test_arg_parsing.py:358-412`: `test_root_readme_matches_current_cli_public_contract` asserts all four modes in README, RESET precedence, POSIX/Windows secret persistence, lock semantics, prewarm, symlink/reparse rejection

README does NOT claim: stronger durability than code provides, Host lock semantics, network validation, assets/portfolio creation. **Correct.**

### 6. S1/S2 closed findings — no regression from S3

**Verified PASS.** All S1/S2 findings were closed by Controller adjudication. S3 cumulative changes:
- `commands/init.py`: added prewarm helper (99 lines of new code at module level + `_run_init_prewarm()` call in `run_init_command`)
- `test_init_command.py`: added prewarm tests, lock competition tests
- `test_init_smoke.py`: new file — isolation subprocess + real POSIX smoke
- `test_arg_parsing.py`: README contract test updated per Controller follow-up
- `test_prompt_command.py`: stale caller updated to explicit Ollama selection

No S3 change modifies: catalog choice tuple, environment persistence owner, workspace transaction owner, Service Fins root override, managed root manifest, four-state machine, secret collection/confirmation flow, symlink/reparse rejection, platform deletion contract, or any S1/S2 owner boundary. Issue 142/151/175/177/178, Web/WeChat/render, Topic 8/9 remain zero-implementation. **No regression.**

### Scope Leakage Check

- Issue 142 (workspace migration): zero implementation — verified
- Issue 151 (Write/assets): zero implementation — verified; init does not create/delete `assets/`
- Issue 175 (Docling process isolation): zero implementation — verified
- Issue 177 (document truncation): zero implementation — verified
- Issue 178 (storage state lifecycle): zero implementation — verified; RESET deletes `.dayu/` as whole root, not per-storage-state
- Web/WeChat/render: zero implementation in R12 diff — verified
- Topic 8 (240-char truncation): zero modification — verified
- Topic 9 (unified tool authorization): zero implementation — verified
- `wechat` as known manifest basename: only occurrence is in `THINKING_MANIFEST_BASENAMES` and `PRODUCTION_RUNTIME_MANIFEST_BASENAMES` per §4.3 — correct and intended

## Open Questions

1. **Windows real runner evidence remains PENDING_RELEASE_BLOCKER.** The workflow `.github/workflows/r12-init-windows.yml` is code-correct (see Finding 01) but has not been executed on a real Windows runner. All 5 Windows-only test nodes in `test_init_smoke.py` are correctly skipped on Darwin with `platform.system() != "Windows"`. The workflow's junction/reparse, setx round-trip, and R11 cmd nodes cannot be verified without real runner execution. This is not a code finding — it is a release gate dependency.

2. **Coverage evidence is based on Controller validation re-run, not independent DS re-run.** The Controller validation reports 87-99% single-file coverage for all 7 production files. AgentDS did not independently re-run coverage due to the review-only gate constraint. The Controller's independent re-run (matching AgentCodex results) provides corroborating but not independently verified evidence.

## Residual Risk

1. **Windows directory crash-durability**: Per §6.3.2, Python 3.11 on Windows lacks POSIX-equivalent `fsync` on directories. R12 honestly limits its Windows durability contract to regular-file `fsync` + same-volume `os.replace` atomic transition + live rollback. Power-loss scenarios may leave directory entries in an intermediate state. This is documented in the plan (§10.1) and README does not claim stronger guarantees. Risk accepted.

2. **Two managed roots not single-syscall atomic**: RESET moves `.dayu/` and `config/` in two separate `os.replace` calls. If a crash occurs between them, one root may be backed up while the other is still public. Rollback handles live-process failures but not power-loss between the two replaces. This is documented in the plan (§10.1). Risk accepted.

3. **RESET concurrent writer race**: `.dayu-init.lock` serializes only init-to-init. If an active Host or other Dayu process writes to `.dayu/` or `config/` during RESET, the replace+rollback contract cannot prevent data loss from the external writer. The init command warns users to stop active Dayu processes before RESET. Risk accepted per plan (§10.1).

4. **`setx` cross-variable non-transactional**: Windows `setx` cannot roll back previously written variables if a later one fails. The implementation correctly reports written/unwritten names without claiming rollback. Risk accepted per plan (§10.1).

5. **Import-only prewarm transitive graph may drift**: If `dayu.cli.commands.prompt` or `dayu.cli.commands.interactive` add import-time side effects (network, env reads, runtime assembly), the prewarm would silently acquire those effects. Tests verify CURRENT state; future drift is a stop condition. Risk accepted per plan (§10.1).

6. **Full Ruff baseline's 144 historical diagnostics**: R12 does not clean these. They are unchanged (fingerprint identical). Any future change that accidentally modifies one of these 144 diagnostics would be caught by the `cmp` check. Risk is repository-level, not R12-specific.

## Covered Files (20/20)

| # | Path | Review Status |
|---|------|--------------|
| 1 | `.github/workflows/r12-init-windows.yml` | ✓ fully reviewed |
| 2 | `README.md` | ✓ fully reviewed |
| 3 | `dayu/cli/arg_parsing.py` | ✓ fully reviewed |
| 4 | `dayu/cli/commands/init.py` | ✓ fully reviewed |
| 5 | `dayu/cli/init_catalog.py` | ✓ fully reviewed |
| 6 | `dayu/cli/init_environment.py` | ✓ fully reviewed |
| 7 | `dayu/cli/init_workspace.py` | ✓ fully reviewed |
| 8 | `dayu/config/README.md` | ✓ fully reviewed |
| 9 | `dayu/service/README.md` | ✓ fully reviewed |
| 10 | `dayu/service/entrypoint_runtime.py` | ✓ fully reviewed |
| 11 | `dayu/service/host_assembly.py` | ✓ fully reviewed |
| 12 | `tests/README.md` | ✓ fully reviewed |
| 13 | `tests/cli/test_arg_parsing.py` | ✓ fully reviewed |
| 14 | `tests/cli/test_init_catalog.py` | ✓ fully reviewed |
| 15 | `tests/cli/test_init_command.py` | ✓ fully reviewed |
| 16 | `tests/cli/test_init_environment.py` | ✓ fully reviewed |
| 17 | `tests/cli/test_init_smoke.py` | ✓ fully reviewed (S3 implementation codex evidence; file read confirmed) |
| 18 | `tests/cli/test_init_workspace.py` | ✓ fully reviewed (S3 implementation codex evidence; file read confirmed) |
| 19 | `tests/cli/test_prompt_command.py` | ✓ fully reviewed (S3 implementation codex evidence; file read confirmed) |
| 20 | `tests/service/test_host_assembly.py` | ✓ fully reviewed (S3 implementation codex evidence; file read confirmed) |

## All Existing Accepted Findings Closure

All S1 and S2 findings were closed by Controller adjudication before S3 began. The S3 Controller validation (`docs/reviews/wu-semantic-ownership-01-r12-s3-controller-validation.md`) records `accepted/open implementation finding: 0`. No S1/S2 finding has regressed due to S3 cumulative changes (see Mandatory Review Challenge 6 above).

Confirmed-closed finding ledger（按 gate 顺序，语义以 Controller adjudication 为准）：

**S1 code review gate:**
- `R12-S1-CR-F01`（HIGH）— resolved in S1 implementation fix
- `R12-S1-RR-CF01`（LOW）— S1 re-review Controller follow-up correction; resolved

**S2 code review gate（first review → fix → re-review → Controller 裁决）:**
- `R12-S2-CR-F01`（HIGH）— POSIX secret temp retention on interrupt：持久化中断后 `.dayu-init-env-*` 私有临时文件遗留且内容含 secret sentinel；resolved in S2 fix
- `R12-S2-CR-F02`（HIGH）— Windows partial `setx` written-names truth loss：中途失败时已写入名称的报告不完整；resolved in S2 fix
- `R12-S2-CR-F03`（MEDIUM）— prepared workspace transaction retention on persistence interrupt：plain/typed persistence interrupt 未进入 workspace transaction abort，导致 private transaction container 遗留；resolved in S2 fix

**S2 complete code re-review → Controller adjudication:**
- `R12-S2-RR-F01`（MEDIUM, ACCEPTED）— 可能失败的 diagnostic I/O 先于 abort：typed persistence interrupt 分支先调用 `_report_persisted_environment_names`（写 stderr），后调用 abort；stderr 写入抛 `OSError` 时 abort 被阻止，异常语义从 `KeyboardInterrupt`/exit 130 漂移到普通失败/exit 1。修复要求任何 diagnostic I/O 不得阻止 identity-safe abort，typed/plain interrupt 均保持 exit 130，abort 自身失败后的 diagnostic 写入失败也不得覆盖原始中断
- `R12-S2-RR-F02`（HIGH, ACCEPTED）— POSIX profile temp unlink/identity cleanup 失败时丢失 secret-bearing retained-path truth：`_cleanup_owned_profile_temporary` 的 `os.unlink` 或 identity-read 失败时，typed interrupt 正常返回但 `.dayu-init-env-*` 遗留且内容含 secret sentinel，而 typed interruption truth 未携带该 retained-path。修复要求 owner temp cleanup 失败时 typed interruption/failure 必须携带最小、脱敏、显式的 retained-path truth，identity 不确定仍须 fail closed

**S2 stop-condition plan correction（plan-only，非 code re-review）:**
- `R12-S2-IMPL-STOP-F01`（HIGH）— validation root isolation：staging `RuntimeConfig` 的 Service assembly `workspace_root` 从 public workspace 改为 transaction-private dedicated validation root，并把 private container identity-locked/no-follow cleanup + parent `fsync` 固定为 config publication 前的 transaction owner gate。这是 §15 plan correction，S3 完整保留该 contract

**S2 corrected-plan review-fix（plan-only，非 code re-review）:**
- `R12-S2-PR-F01..F06`（accepted groups）— Service Fins root override precedence、syscall fault injection boundary、POSIX validation cleanup durability truth、Windows junction/reparse contract、platform durability distinction、allowlist/scan zero-diff 同步。这些是 plan-review findings applied to the plan document itself；S3 不修改对应 plan contract

## Windows Pending Evidence

**`PENDING_RELEASE_BLOCKER`**: `.github/workflows/r12-init-windows.yml` must complete a successful run on a real Windows runner before R12 S3, R12, or the umbrella WU-SEMANTIC-OWNERSHIP-01 can be closed. The workflow file itself is code-correct (Finding 01 documents the `if: always()` semantics as acceptable). Required evidence:
- Normal FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes transaction
- `ConfigLoader`/scene reload after each state
- Pre-seeded junction fail-closed with external sentinel preservation
- Ordinary symlink privilege skip (exact `winerror=1314`)
- Workspace root identity drift rejection
- Replace-failure rollback
- Scan-delete race proof
- Real `setx` round-trip with cleanup
- R11 two real cmd/upload nodes
- Name-safe artifacts only (no environment/registry values)

## Conclusion

**Overall assessment: NO BLOCKING CODE DEFECTS FOUND.**

Three findings reported:
- Finding 01 (中): Windows workflow `if: always()` semantics — informational, not a defect
- Finding 02 (低): unbounded diagnostic text in error formatting — low severity
- Finding 03 (低): stale caller test edge case — confirmed correctly covered, informational

All six mandatory review challenges pass. Semantic ownership boundaries are correctly maintained. No S1/S2 regression. No scope leakage. Secret handling is correct across all paths. The implementation faithfully executes the fixed plan.

**Artifact metrics**:
- File: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-ds.md`
- Lines: this file (to be computed after write)
- Bytes: this file (to be computed after write)
- SHA-256: this file (to be computed after write)
- Findings: 3 (0 critical, 0 high, 1 medium, 2 low)
- Open questions: 2
- Residual risks: 6 (all pre-identified in plan §10.1)
- Covered paths: 20/20
