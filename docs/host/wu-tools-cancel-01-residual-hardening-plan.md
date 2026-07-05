# WU-TOOLS-CANCEL-01 Residual Hardening Plan

## Gate / Scope

- Work unit: `WU-TOOLS-CANCEL-01 residual hardening reopen`
- Gate: plan
- Branch: `phase/wu-tools-cancel-01`
- Existing draft PR: https://github.com/noho/dayu-agent-r/pull/170
- Required behavior: only produce and review this plan before implementation; do not mark PR ready, merge, close #87 directly, request reviewers, delete branch, or publish external comments without explicit authorization.

## First-Principles Goal

The reopened items are valid because WU-TOOLS-CANCEL-01 is not just about making one cancellation test pass. The user-visible promise is that Host can quickly stop waiting on blocking tool/provider work, return to an interactive state, and prevent stale tool output from contaminating a cancelled Run. That guarantee depends on three lower-level properties:

1. Process-backed tool children and their nested processes are physically bounded by an interruptible execution boundary.
2. The process-backed result envelope is a single explicit contract, not duplicated string conventions across Host and tools.
3. Cleanup wait knobs are typed runtime policy, not untracked constants that accidentally become a second business deadline.

Success signals:

- Host parses process-backed envelopes from a single `dayu.contracts` contract and preserves structured `hint` separately from `message`.
- Doc, Fins read, and Web process-backed targets build envelopes through the same contract helpers without importing Host internals.
- Runtime process cleanup can terminate synthetic nested subprocesses through shared process-group cleanup primitives on supported POSIX OSes; unsupported or unsafe process-group behavior is explicit and tested.
- Playwright cleanup smoke proves no same-process fallback and no surviving synthetic nested child process in the tested cancellation/timeout path. Real Chromium process tree cleanup is only claimed if a browser-binary-backed optional/manual smoke runs in the environment.
- Fins read process-backed coverage includes an AAPL XBRL filing fixture path, preferably copied from the already downloaded `workspace/portfolio/AAPL/filings/fil_0000320193-24-000123` 10-K if suitable.
- `tool_execution_timeout_seconds` remains the only tool-call business deadline. New grace values only bound post-cancel/post-timeout cleanup.

## Non-Goals / Boundaries

- Do not optimize Web process cold-start unless inspection proves it weakens cancellation robustness. Current evidence classifies it as performance-only.
- Do not introduce a Host tool registry or tool-name branching.
- Do not make Host import `dayu.tools`, `dayu.fins`, or concrete Web/Doc/Fins modules.
- Do not make `dayu.runtime` import Host, Engine, Service, UI, or Fins.
- Do not expose process envelope governance fields in LLM-facing tool schema.
- Do not change Engine `AgentPolicy.tool_execution_timeout_seconds` semantics.
- Do not make process cleanup diagnostics into durable Host facts beyond existing ToolRuntime outcome/diagnostic paths.

## Design Alignment

`docs/host/design.md` requires Host to own tool execution governance, cancellation, ToolRuntime accept barrier, and stale result isolation, while not carrying Fins business semantics or scanning concrete tools. This plan keeps the process-backed envelope as a Host/contracts-level execution contract and keeps concrete tool packages as contract consumers.

`docs/engine/design.md` defines `tool_execution_timeout_seconds` as the Engine wait-for-ToolExecutor handshake timeout and as the source projected into `BatchToolExecutionContext.timeout_seconds`. This plan keeps that as the only business deadline. Process terminate/kill grace values are cleanup policy after the business deadline or Host cancel has already won.

`dayu.runtime` remains layer-neutral. Runtime may provide generic process/process-group interruption primitives, but it must not know Host Run/Attempt, Engine tool loop, Fins storage, or Web/Playwright business semantics.

## Direct Code Evidence

- `dayu/host/tool_runtime.py`: `_PROCESS_ENVELOPE_*` constants define `status`, `completed`, `failed`, `value`, `error_type`, `message`, and reserved Host-governed statuses. `_tool_outcome_from_process_envelope`, `_completed_outcome_from_process_envelope`, and `_failed_outcome_from_process_envelope` parse this private Host copy.
- `dayu/tools/doc_tools.py`: `_DOC_PROCESS_*` constants duplicate the same envelope fields. `_process_failed_envelope` and `_process_failure_message` explicitly state that Host currently has no independent hint field, so hints are appended into `message`.
- `dayu/fins/tools/fins_tools.py`: `_FINS_PROCESS_*` constants duplicate the same envelope fields and also append hints into `message`.
- `dayu/tools/web/web_tools.py`: `_WEB_PROCESS_*` constants duplicate the same envelope fields. `_web_process_failed_envelope` appends `hint` into `message` because Host does not consume a separate hint field.
- `dayu/host/tool_runtime.py`: `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2` are raw Host constants used by `ProcessBackedToolExecutionCapsule.terminate` and `.kill`.
- `dayu/runtime/interruptible_process.py`: `InterruptibleProcessHandle.terminate` and `.kill` currently target only the direct `multiprocessing.Process`. They do not express process tree/process group semantics.
- `dayu/tools/web/web_playwright_backend.py`: `_run_playwright_worker_process` starts a nested `multiprocessing` worker, and `_terminate_playwright_process` terminates/kills only that direct process. Browser subprocess cleanup is not proven if the parent process is killed externally.
- `tests/host/test_toolruntime_executor.py`: existing tests cover process-backed cancel, outer task cancel, terminate-to-kill escalation, malformed/reserved envelopes, and default factory selection.
- `tests/runtime/test_interruptible_process.py`: existing tests cover direct child complete, terminate, and kill when SIGTERM is ignored; they do not cover nested child/process group cleanup.
- `tests/tools/web/test_web_tools_provider.py`: existing tests cover Web process target pickleability, process capsule success/cancel, Playwright pre-cancel, unpicklable fail-closed, and config propagation; they do not prove cleanup of nested Playwright subprocesses.
- `tests/fins/test_fins_storage_provider.py`: existing process-backed Fins tests cover list/search/table/financial-statement paths and cancellation. XBRL coverage is synthetic/fake-processor oriented and does not yet run a real AAPL XBRL filing through a spawned process target.
- `workspace/portfolio/AAPL/filings/fil_0000320193-24-000123/meta.json`: already downloaded AAPL 2024 10-K has `form_type: "10-K"`, `has_xbrl: true`, `primary_document: "aapl-20240928.htm"`, and the related `.xsd`, `_cal.xml`, `_def.xml`, `_htm.xml`, `_lab.xml`, `_pre.xml` files.

## Affected Files / Modules

Expected production files:

- `dayu/contracts/tool_execution.py`
- `dayu/contracts/__init__.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/tooling.py`
- `dayu/host/api.py`
- `dayu/runtime/interruptible_process.py`
- `dayu/runtime/config_loader.py`
- `dayu/service/host_assembly.py`
- `dayu/config/host_runtime.json`
- `dayu/tools/doc_tools.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_playwright_backend.py`

Expected tests / fixtures:

- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_public_open_host_options.py`
- `tests/runtime/test_interruptible_process.py`
- `tests/service/test_host_assembly.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- new AAPL XBRL fixture files under `tests/fins/fixtures/` if the downloaded filing is suitable after fixture minimization.

README/docs to check under AGENTS.md:

- `dayu/host/README.md`
- `dayu/fins/README.md`
- `dayu/config/README.md`
- `dayu/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`

## Contract / Schema / Runtime Policy Decisions

1. Process envelope contract ownership:
   - Define the process-backed envelope contract in `dayu.contracts.tool_execution` or a directly related contracts module exported from `dayu.contracts.__init__`.
   - Host may parse it; tools may construct it. Neither side imports concrete tool packages or Host internals.
   - The contract is not LLM-facing schema and must not be projected into `ToolSchema`.

2. Envelope shape:
   - Completed envelope: `{"status": "completed", "value": JsonValue}`.
   - Failed envelope: `{"status": "failed", "error_type": str, "message": str, "hint": str | null optional}`.
   - `hint` is optional. If present and non-empty, Host maps it to `ToolResultFailure.hint`; Host no longer requires tools to concatenate hint into message.
   - Reserved statuses remain Host-governed and fail closed: `awaiting`, `cancelled`, `timeout`, `host_cancelled`.
   - Provide helpers such as `process_tool_completed_envelope(...)`, `process_tool_failed_envelope(...)`, and `parse_process_tool_envelope(...)` so field names and validation are single-source.
   - Update `ProcessBackedToolTarget.__call__` docstring so the public process target protocol documents the optional `hint` field in failed envelopes.

3. Process capsule policy:
   - Add typed policy, for example `ProcessCapsuleInterruptPolicy`, with `terminate_grace_seconds` and `kill_grace_seconds`.
   - The typed dataclass is the single source of default truth. Config missing this block falls through to dataclass defaults; default literals must not be duplicated as independent truth in config loader or ToolRuntime.
   - Initial named defaults may preserve current behavior (`0.2` / `0.2`) only if S2A/S2B smoke timing validates them. S2B must measure or otherwise assert SIGTERM-to-exit behavior for the nested/Playwright smoke and adjust the named defaults upward if the current values are insufficient.
   - Validation: each field must be finite non-negative numeric, not bool. Negative values, `float("nan")`, `float("inf")`, and `float("-inf")` fail fast. The lower-level runtime `_validate_grace_seconds` path must enforce the same finite/non-bool/non-negative contract.
   - This policy is cleanup-only and must be documented as not extending `tool_execution_timeout_seconds`.

4. Runtime config mapping:
   - Add a typed host runtime config block under `host_runtime.json`, e.g. `process_capsule_interrupt_policy`.
   - Parse and validate it in `dayu.runtime.config_loader.HostRuntimeProfileConfig`.
   - Map it in `dayu.service.host_assembly.compose_open_host_options(...)` into `HostToolingOptions` / ToolRuntime build input.
   - Defaults should come from typed constructors so a missing config block remains valid.

5. Process tree/process group cleanup:
   - Because Playwright can create nested browser subprocesses, direct-child kill is not sufficient as a robustness claim.
   - Extract/share minimal process-group cleanup primitives in `dayu.runtime.interruptible_process`. `InterruptibleProcessHandle` and the Playwright raw `multiprocessing.Process` path must call the same primitives; do not duplicate process-group logic in Web code and do not force a larger full migration to `InterruptibleProcessHandle` unless implementation evidence proves the raw path cannot safely use the shared primitive.
   - POSIX signaling must avoid killing the parent process group. Signal the direct child PID first, then use process-group signaling only after confirming `os.getpgid(child_pid)` is available and differs from the current/parent process group. If pgid lookup fails, the child has exited, or the child pgid is unavailable/unchanged, fall back to direct-child cleanup and record the limitation in diagnostics/tests.
   - Unsupported OS behavior: direct process terminate/kill remains available; tests must make support status explicit and avoid claiming full tree cleanup.
   - Do not encode Web or Playwright names in runtime.

## Implementation Slices

### S1 - Process Envelope Contract And Cleanup Policy

Objective: establish single-source contract and typed cleanup policy without changing concrete tools yet.

Allowed files:

- `dayu/contracts/tool_execution.py`
- `dayu/contracts/__init__.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/tooling.py`
- `dayu/host/api.py`
- `dayu/runtime/config_loader.py`
- `dayu/service/host_assembly.py`
- `dayu/config/host_runtime.json`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_public_open_host_options.py`
- `tests/service/test_host_assembly.py`

Exact changes:

- Add contract constants/helpers/parser for process-backed envelopes.
- Update `ProcessBackedToolTarget.__call__` docstring to include optional `hint` in the failed envelope shape.
- Update Host parser to use the contract parser and map failed `hint` to `ToolResultFailure.hint`.
- Keep backward compatibility only for absent `hint`; do not support old aliases or duplicate status names.
- Add `ProcessCapsuleInterruptPolicy` and wire it through the exact active call path: `HostToolingOptions` -> `ToolRuntimeBuildRequest` -> `DefaultToolRuntimeFactory.create_tool_runtime(...)` -> `DeclaredToolExecutionCapsuleFactory.__init__(...)` -> `DeclaredToolExecutionCapsuleFactory.create_capsule(...)` -> `_declared_capsule_for_execution(...)` -> `ProcessBackedToolExecutionCapsule(...)`.
- Add config loader field and default config block. Service assembly must map config to Host typed options.
- Remove `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` from the active ToolRuntime code path; if named default constants remain, they must live with the typed policy default owner rather than as separate magic constants consumed directly by `ProcessBackedToolExecutionCapsule`.

Tests:

- Host envelope tests cover completed, failed with hint, failed without hint, malformed, reserved statuses, and unknown statuses.
- Host tooling/options tests cover default policy and invalid values, explicitly including `bool`, negative values, `float("nan")`, `float("inf")`, and `float("-inf")`.
- Runtime grace validation tests cover the same `bool`, negative, NaN, and infinity rejection cases for `_validate_grace_seconds` or its replacement.
- Service assembly test proves `host_runtime.json` overlay tuning reaches `HostToolingOptions`.
- Validation includes a grep/assertion that `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` are not present in the active ToolRuntime code path after migration.

Stop conditions:

- If contract helpers require `dayu.contracts` to import Host, Engine, Service, UI, or Fins, stop and mark the design invalid.
- If policy wiring would make Host import concrete tool packages, stop and mark invalid.

### S2A - Runtime Process Group Cleanup Primitive

Objective: add and test shared, layer-neutral process-group cleanup primitives without Playwright-specific behavior.

Allowed files:

- `dayu/runtime/interruptible_process.py`
- `dayu/host/tool_runtime.py` only if needed to pass new runtime options into `InterruptibleProcessHandle`
- `tests/runtime/test_interruptible_process.py`

Exact changes:

- Introduce minimal shared process-group cleanup primitives in `dayu.runtime.interruptible_process`; keep them generic and callable by both `InterruptibleProcessHandle` and Playwright's raw process path.
- `InterruptibleProcessHandle` uses those primitives for terminate/kill when process-group cleanup is supported and safe.
- POSIX behavior: start process-backed children in a separate process group/session before running the target, but signal safely: direct child PID first, then process group only after confirming the child pgid differs from the current/parent pgid.
- Unsupported, unavailable, or unsafe pgid behavior falls back to direct-child cleanup and is observable in the returned cleanup/interrupt result or test-visible diagnostic path.
- Add a deterministic smoke target that starts a nested child process which ignores direct parent termination long enough to prove process-group kill is required.

Tests:

- `tests/runtime/test_interruptible_process.py::test_interruptible_process_group_kills_nested_child_on_posix`
- `tests/runtime/test_interruptible_process.py::test_interruptible_process_group_reports_unsupported_when_not_available`
- Runtime tests explicitly cover fallback when pgid is unavailable, unchanged, or otherwise unsafe to signal as a group.

Stop conditions:

- If process tree cleanup requires OS behavior not available in Python 3.11 standard library on the current supported platform, record the OS-specific limitation and keep direct-child cleanup explicit; do not pretend nested cleanup is proven.
- If S2A cannot provide a safe shared primitive on the current OS, S2B must not claim Playwright nested cleanup; it may only validate direct-child fallback and record the OS-specific blocker.

### S2B - Playwright Cleanup Smoke

Objective: prove Web Playwright worker cleanup uses the shared runtime primitive and record the limit of synthetic versus real browser evidence.

Allowed files:

- `dayu/tools/web/web_playwright_backend.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/web/test_smoke_web_ci.py` only if adding an optional/manual live browser smoke is appropriate for the existing smoke layer.

Prerequisites:

- S2A shared primitive exists, or S2A has explicitly classified process-group cleanup as unsupported/fallback on the current OS.

Exact changes:

- Replace Playwright raw process cleanup's direct terminate/kill helper with calls to the shared runtime process-group cleanup primitive. Do not duplicate logic in Web code.
- Keep Playwright's raw `multiprocessing.Process` path unless implementation proves a full migration to `InterruptibleProcessHandle` is necessary; if such migration becomes necessary, stop and update the plan/review artifact before widening S2B.
- Add a deterministic fake picklable worker that starts a synthetic nested subprocess or long-lived child; assert cleanup returns promptly and no synthetic child PID remains on POSIX when S2A reports process-group cleanup support.
- If real Playwright browser binaries are available, add an optional/manual/live smoke or skipped test that launches a real browser path and verifies no surviving Chromium subprocesses after cleanup. If binaries are unavailable, the test must skip or the artifact must record environment-dependent residual risk honestly.
- S2B must measure or assert SIGTERM-to-exit timing for the synthetic nested worker path and use that evidence to validate or adjust `ProcessCapsuleInterruptPolicy` named defaults.

Tests:

- `tests/tools/web/test_web_tools_provider.py::test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix`
- Optional/skipped live browser smoke when browser binaries are available.
- Existing Web cancellation tests must still pass.

Stop conditions:

- If S2A process-group cleanup is unsupported or unsafe on the current OS, S2B must not claim nested Playwright cleanup. It should assert direct-child fallback behavior and record the limitation.
- If browser cold-start reveals child process group ownership instability, record it as an OS/environment boundary condition. It is not an S2B blocker unless it weakens cancellation robustness beyond the already acknowledged cold-start performance residual.

### S3 - Tool Migration And Fins AAPL XBRL Fixture Breadth

Objective: migrate concrete tools to the single-source envelope helpers and add representative Fins XBRL process-backed coverage.

Allowed files:

- `dayu/tools/doc_tools.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/tools/web/web_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- fixture files under `tests/fins/fixtures/`

Exact changes:

- Replace `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, and `_WEB_PROCESS_*` duplicated constants with `dayu.contracts` envelope helpers/constants.
- Stop appending hint into message in tool process targets. Emit structured `hint` for failed envelopes.
- Update tests to assert structured hint where relevant and to guard against reintroduced local envelope constants.
- Create a temp Fins workspace from fixture data copied from an already downloaded AAPL filing. Preferred source: `workspace/portfolio/AAPL/filings/fil_0000320193-24-000123`.
- Keep fixture minimal but complete enough for `DefaultFinsRuntime.create(...).get_read_runtime().query_xbrl_facts(...)` through a spawned process target. Include `meta.json`, primary document if required by repository metadata, and XBRL files needed by current `xbrl_file_discovery` / processor path.
- Add a process-backed test for `query_xbrl_facts` that runs through `ProcessBackedToolExecutionCapsule` and asserts a completed outcome with at least one fact for a stable concept such as revenue or net income. The exact concept must be discovered from the fixture during implementation; do not hard-code an unverified concept in production code.

Tests:

- Doc/Web/Fins process target failed envelope tests assert `hint` remains separate from `message`.
- Fins spawned child XBRL fixture test uses `query_xbrl_facts` and the AAPL fixture.
- Add a grep-style test or assertion to prevent any local `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, or `_WEB_PROCESS_*` envelope constants from reappearing after migration, not only `*_STATUS_FIELD`.

Stop conditions:

- If the AAPL filing fixture cannot be minimized into a repository-valid test fixture, record blocker with the exact missing repository requirement and proposed fixture discovery step. Do not invent XBRL facts.
- If the XBRL processor requires network access for taxonomy resolution, stop and either select a locally self-contained fixture path or record the blocker.

### S4 - Docs, Control State, And Final Validation

Objective: sync stable developer docs and run the full validation matrix after implementation.

Allowed files:

- `dayu/host/README.md`
- `dayu/fins/README.md`
- `dayu/config/README.md`
- `dayu/README.md`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`
- implementation/review artifacts under `docs/reviews/`

Exact changes:

- Update `dayu/host/README.md` if `HostToolingOptions`, process-backed envelope, or cleanup policy becomes stable developer-facing Host behavior.
- Update `dayu/config/README.md` because `host_runtime.json` schema gains process capsule cleanup policy.
- Update `dayu/fins/README.md` only if Fins read tool process-backed/XBRL behavior description changes beyond tests.
- Update `dayu/README.md` only if the cross-package contract boundary text needs to mention `dayu.contracts` process-backed envelope or runtime process-group cleanup.
- Update `tests/README.md` only if a new fixture category, marker, or test running rule is added. A normal test fixture under an existing Fins/Web layer does not require a README change.
- Update `docs/host/issues-implementation-control.md` current gate/status after implementation gates, not during this plan-only task unless the controller explicitly asks.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py tests/host/test_tooling_options.py tests/host/test_public_open_host_options.py -q
pytest tests/runtime/test_interruptible_process.py -q
pytest tests/tools/web/test_web_tools_provider.py -q
pytest tests/fins/test_fins_storage_provider.py -q
pytest tests/service/test_host_assembly.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
git status --short
```

Expected validation assertions:

- No new pyright errors.
- No trailing whitespace or malformed patch output.
- No Host imports of concrete tool packages.
- No runtime imports of Host/Engine/Service/UI/Fins.
- No process-backed tool schema exposes envelope fields or cleanup policy to LLM.
- No duplicated envelope field constants in Doc/Fins/Web tools after migration.
- No `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` or `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` active ToolRuntime magic constants remain after policy migration.
- Grace policy and runtime grace validation reject `bool`, negative values, NaN, `+inf`, and `-inf`.

## Why This Is Not Over-Designed

The plan adds only two shared contracts that are already implicitly present in multiple places: a process-backed result envelope and a process cleanup policy. It does not add a registry, generalized job supervisor, new Host state machine, durable schema, or Web cold-start optimization. Process-group cleanup is included only because Playwright introduces nested subprocesses; without it, cancellation robustness would be proved only for direct children.

The slice count is five because runtime process-group cleanup and Playwright smoke have different evidence quality and stop behavior. S2A may hit OS-specific limits and should not blur S2B's Playwright claims; S2B may only claim synthetic nested-child cleanup unless a real browser smoke runs. S3 may hit fixture suitability limits and should not obscure runtime process cleanup findings. Five slices remain within the control document's 3-5 slice budget for medium cross-contract/provider work.

## Residual Risks / Open Questions

- Deterministic Playwright cleanup smoke proves synthetic nested-child cleanup only. Live Chromium cleanup remains environment-dependent unless an optional/manual browser-backed smoke runs successfully.
- Web process cold-start remains deferred as performance-only unless S2B evidence shows child process group ownership instability or survivor processes that weaken cancellation robustness.
- The AAPL 2024 10-K fixture appears suitable, but implementation must verify that the copied fixture satisfies current Fins repository and XBRL processor requirements without network access.
- POSIX process-group cleanup can be tested on the current macOS/Linux-like environment. Windows semantics must be explicitly marked unsupported/fallback unless implemented and tested.

## Completion Report Format

Implementation agent final report must use this shape:

```text
READY_FOR_CONTROLLER

Artifact: docs/host/wu-tools-cancel-01-residual-hardening-plan.md

Changed:
- ...

Verified:
- ...

Docs:
- ...

Residual risks / blockers:
- ...

Blocking open question:
- None
```

For this plan gate specifically, the controller-facing completion line is:

```text
READY_FOR_CONTROLLER
Artifact: docs/host/wu-tools-cancel-01-residual-hardening-plan.md
Blocking open question: None
```
