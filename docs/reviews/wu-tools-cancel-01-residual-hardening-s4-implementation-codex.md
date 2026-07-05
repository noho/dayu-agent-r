# WU-TOOLS-CANCEL-01 Residual Hardening S4 Implementation

## Gate / Scope

- Work unit: `WU-TOOLS-CANCEL-01 residual hardening reopen`
- Slice: S4 - Docs, Control State, And Final Validation
- Agent: AgentCodex
- Branch: `phase/wu-tools-cancel-01`
- Scope: stable developer docs, control state, final validation artifact.
- Non-goals: no production behavior changes, no test behavior changes, no commit, no push, no PR state changes, no external comments.

## First-Principles Judgment

S4 is valid because S1 / S2A / S2B / S3 already closed the behavior-bearing residuals. The remaining risk is documentation and control-state drift: developers need to know where the process-backed envelope contract lives, how Host cleanup policy is configured, and which gate is next. Adding more production code in this slice would be scope creep unless final validation exposes a real defect.

## Changed

- Updated `dayu/README.md` to include the `dayu.contracts` process-backed envelope helpers/parser and process-backed target types in the public contract summary.
- Updated `dayu/host/README.md` to clarify that process-backed envelopes are defined in `dayu.contracts`, that failed envelope `hint` maps to structured `ToolResultFailure.hint`, and that envelope fields remain outside Engine/LLM-facing tool schema.
- Updated `dayu/fins/README.md` in `关键机制 / Read tool 结果与截断` to document that Fins process targets use `dayu.contracts` process-backed envelope helpers and keep failed-envelope `hint` as a structured field mapped by Host to `ToolResultFailure.hint`.
- Updated `docs/host/issues-implementation-control.md` from Slice S4 implementation entry to `review` / ready for aggregate or final review, using an existing status convention value and not claiming `final-closeout-pass`.

## Review Fixes

- MiMo-01 MEDIUM: fixed. `dayu/fins/README.md` now documents Fins process-backed failed envelope behavior in the existing read-tool/process-backed section.
- DS-01 LOW: fixed. `docs/host/issues-implementation-control.md` now uses `gate=review` and WU status `review`; status text still records S4 implementation completion and aggregate/final review as next entry.
- DS-02 LOW: fixed. This artifact now records direct evidence for the Fins README update and the tests README no-update decision.

## Docs Decision

- `dayu/host/README.md`: updated. `HostToolingOptions`, process-backed envelope handling, structured hint mapping, and cleanup policy are stable developer-facing Host behavior.
- `dayu/config/README.md`: checked; no new change needed because it already documents `host_runtime.json.process_capsule_interrupt_policy`, finite non-negative validation, bool/NaN/infinity rejection, and the distinction from `tool_execution_timeout_seconds`.
- `dayu/fins/README.md`: updated in `关键机制 / Read tool 结果与截断`. Direct evidence: that section already owned Fins read tool schema, Host ToolRuntime truncation, direct callable fallback, and production process-backed execution; the new sentence documents the S3 behavior at the same responsibility boundary.
- `dayu/README.md`: updated because the cross-package `dayu.contracts` process-backed envelope is now a stable public contract boundary.
- `tests/README.md`: checked; no new change needed. Direct evidence: S4 review fixes changed README/control/artifact text only, introduced no test file, no fixture category, no marker, and no test running rule. The existing tests README already documents runtime interruptible process, service host assembly, Fins read provider process-backed coverage, and common commands.

## Verified

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_tooling_options.py tests/host/test_public_open_host_options.py -q`: `89 passed`
- `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py -q`: `19 passed`
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`: `34 passed, 1 skipped`; rerun with `-rs` shows the skipped test requires `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` to run live browser cleanup smoke.
- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py -q`: `33 passed`, 3 upstream `edgar` deprecation warnings
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`: `52 passed`, 3 upstream `edgar` deprecation warnings
- `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed
- `git status --short`: only allowed S4 docs / artifact files were modified or added.

S4 review-fix validation:

- `git diff --check`: passed.
- `git status --short`: modified docs are `dayu/README.md`, `dayu/fins/README.md`, `dayu/host/README.md`, and `docs/host/issues-implementation-control.md`; untracked review/artifact files are `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-code-review-ds.md`, `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-code-review-mimo.md`, and this implementation artifact.
- pytest / pyright were not rerun for the review fix because the accepted fixes are README / control / artifact text only and do not change Python code, config schema, tests, or runtime behavior.

Additional evidence checks:

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py tests/runtime/test_import_boundary.py -q`: `25 passed`
- `source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py -q`: `10 passed`
- `rg -n "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS|_PROCESS_CAPSULE_KILL_GRACE_SECONDS" dayu/host/tool_runtime.py`: no matches.
- `rg -n "_DOC_PROCESS_|_FINS_PROCESS_|_WEB_PROCESS_" dayu/tools dayu/fins`: no matches.

## Expected Assertions Covered By Existing Tests / Validation

- No new pyright errors: `pyright` reported zero errors.
- No Host imports of concrete tool packages: covered by `tests/host/test_import_boundary.py`.
- No runtime imports of Host / Engine / Service / UI / Fins: covered by `tests/runtime/test_import_boundary.py`.
- No process-backed tool schema exposes envelope fields or cleanup policy to LLM: covered by `tests/contracts/test_tool_declaration.py`, provider tests, and README/code inspection showing execution capability and process envelope remain outside `ToolSchema`.
- No duplicated envelope field constants in Doc / Fins / Web tools: covered by provider tests and no `_DOC_PROCESS_`, `_FINS_PROCESS_`, or `_WEB_PROCESS_` source matches.
- No active ToolRuntime magic constants `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` / `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` remain: exact grep against `dayu/host/tool_runtime.py` found no matches. Typed defaults now live with `ProcessCapsuleInterruptPolicy`.
- Grace policy and runtime validation reject bool, negative, NaN, `+inf`, and `-inf`: covered by `tests/host/test_tooling_options.py::test_process_capsule_interrupt_policy_rejects_invalid_grace`, `tests/runtime/test_interruptible_process.py::test_interruptible_process_options_reject_invalid_grace`, and `tests/runtime/test_config_loader.py::test_host_runtime_process_capsule_interrupt_policy_rejects_invalid_grace`.

## Residual Risks / Blockers

- Live browser-backed Chromium process tree cleanup remains environment-dependent; S2B only claims deterministic synthetic nested-child coverage unless an optional live smoke runs in a prepared browser environment. Classification: tracked by current validation/artifact evidence; not a blocker for S4.
- Web process cold-start remains performance-only unless future evidence shows it weakens cancellation robustness. Classification: deferred with owner by prior user/controller decision; not a blocker for S4.
- No blocking open question.

## Completion Status

READY_FOR_CONTROLLER

Artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md`

Blocking open question: None
