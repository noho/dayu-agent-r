# WU-CM-15 Final Closeout

## Result

WU-CM-15 is locally complete and ready for draft PR gate authorization.

The work unit stayed within the user-confirmed scope: add public smoke coverage for reactive compact and deterministic compact-failure fallback. It did not modify Host / Engine / runtime / Service production code, schemas, prompts, or public contracts.

## Delivered

- Added explicit public smoke suites:
  - `memory-reactive-compact` for deterministic provider-overflow reactive compact and recovery dispatch.
  - `memory-compact-fallback` for deterministic compact failure and fallback dispatch.
- Preserved existing `memory-compact` semantics:
  - proactive compact request required;
  - accepted compact required;
  - compact artifacts required;
  - any compact failure remains a hard failure.
- Added deterministic smoke infrastructure for ordinary worker dispatch capture and compactor accept/reject behavior.
- Added bounded compact audit / fallback diagnostics without printing full pressure blobs, compactor prompts, provider payloads, or per-delta stream logs.
- Added tests for suite parsing, reactive old-marker oracle, fallback selected / dropped / current window oracle, compact audit parsing, pressure bounds, and helper failure cases.
- Updated `tests/README.md` for the new runtime assembly coverage.
- Updated `docs/host/issues-implementation-control.md` with plan, implementation, review, aggregate review, fix, validation, residuals, and final state.

## Review History

- Accepted plan commit: `97518e93`.
- Accepted implementation slice commit: `572a88df`.
- Plan review / fix / re-review passed.
- Code review / fix / focused re-review passed.
- Aggregate deepreview passed after small closeout fixes.
- Aggregate-fix focused re-review passed from AgentMiMo and AgentDS.

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Passed: `20 passed`.
  - Warnings: existing third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors`.
- `git diff --check`
  - Passed.

## Residuals

- Real-provider `memory-compact` still requires a valid compactor provider key. This remains an environment validation residual and does not block deterministic reactive / fallback smoke coverage.
- `_patched_compactor_runner(...)` remains smoke-local monkey-patching around `dayu.host.llm_compaction._run_agent_request`; it now fails clearly if the hook changes and restores the original runner in `finally`.
- Future smoke hardening may decide whether reactive acceptance should also reject nonzero `rejected_proactive`.
- Larger smoke maintainability refactors, such as splitting deterministic infrastructure or extracting shared public Host smoke flow, are intentionally deferred.

## Next Entry

Await user authorization for draft PR gate actions: push, draft PR creation, mark-ready, reviewer requests, merge, branch deletion, or issue closure.
