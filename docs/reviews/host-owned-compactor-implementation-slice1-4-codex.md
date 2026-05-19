# Host-owned Compactor Implementation Slice 1-4

## Gate / Work Unit

- gate: implementation
- work unit: Host-owned LLM context compactor public opener contract
- accepted plan commit: cab7ad0
- approved plan: docs/host/host-owned-compactor-plan.md
- design source of truth: docs/host/design.md
- assigned scope: Slice 1 through Slice 4 as one implementation pass

## Allowed Files

- dayu/host/api.py
- dayu/host/__init__.py
- dayu/host/open_host.py
- dayu/host/context_policy.py
- dayu/host/llm_compaction.py
- dayu/host/context_events.py
- dayu/host/dispatch.py
- dayu/host/engine_ingest.py
- tests/host/test_public_open_host_options.py
- tests/host/test_package_exports.py
- tests/host/test_llm_compaction.py
- tests/host/test_open_host_runtime.py
- tests/host/test_context_policy.py
- tests/host/test_context_compact_events.py
- tests/host/test_dispatch_scheduler.py
- tests/host/test_engine_ingest_mapping.py
- docs/reviews/host-owned-compactor-implementation-slice1-4-codex.md

Additional tests/host files edited to keep impacted Host tests compiling after the `OpenHostOptions` field rename:

- tests/host/test_effective_execution_config.py
- tests/host/test_per_run_tool_selection.py
- tests/host/test_public_lifecycle_smoke.py
- tests/host/test_public_retry_replay.py
- tests/host/test_submit_followup_public_contract.py
- tests/host/test_watch_session_events.py

After controller approval for a minimal cross-slice compile fix, these Slice 5 files were edited only to remove old public API usage and restore pyright:

- tests/host/public_smoke_support.py
- tests/host/test_public_compact_smoke.py

Still explicitly not edited:

- utils/smoke_host_public_multiturn.py
- README.md
- dayu/host/README.md
- tests/README.md

## Changed Files

- dayu/host/api.py
- dayu/host/__init__.py
- dayu/host/open_host.py
- dayu/host/context_policy.py
- dayu/host/llm_compaction.py
- dayu/host/context_events.py
- dayu/host/dispatch.py
- dayu/host/engine_ingest.py
- tests/host/test_public_open_host_options.py
- tests/host/test_package_exports.py
- tests/host/test_llm_compaction.py
- tests/host/test_open_host_runtime.py
- tests/host/test_context_policy.py
- tests/host/test_context_compact_events.py
- tests/host/test_dispatch_scheduler.py
- tests/host/test_engine_ingest_mapping.py
- tests/host/test_effective_execution_config.py
- tests/host/test_per_run_tool_selection.py
- tests/host/test_public_lifecycle_smoke.py
- tests/host/test_public_retry_replay.py
- tests/host/test_submit_followup_public_contract.py
- tests/host/test_watch_session_events.py
- tests/host/public_smoke_support.py
- tests/host/test_public_compact_smoke.py
- docs/reviews/host-owned-compactor-implementation-slice1-4-codex.md

## Implemented Plan Items

- Replaced Service-facing `CompactorExecutionBaseline` with `CompactorRunnerBaseline`.
- Replaced `OpenHostOptions.compactor_baseline` with `OpenHostOptions.compactor_runner_baseline`.
- Removed package-root export of `CompactorExecutionBaseline`; package root now exports `CompactorRunnerBaseline`.
- Kept `ContextCompactor` only as Host internal / low-level test seam through `HostLocalExecutionOptions`.
- Added `dayu.host.llm_compaction.LLMContextCompactor`.
- `LLMContextCompactor` constructor accepts only `runner_spec` and `runner_options`.
- `LLMContextCompactor` builds Host-owned prompt, disables tools, calls Engine public `run_agent_and_wait`, maps only summary text from final answer, and constructs refs/evidence/budget/pinned patch in Host code.
- Added `ContextBudgetPolicy.max_compaction_attempts_per_operation` with positive-int validation and default constructor support.
- `open_host` constructs Host-owned `LLMContextCompactor` from `CompactorRunnerBaseline` and injects it into internal `HostLocalExecutionOptions.context_compactor`; baseline `None` remains fail-closed.
- Added `CONTEXT_COMPACTION_ATTEMPT_REJECTED` event type, builder, validator, and tests.
- Kept compact EventLog facts mapped through existing HostEvent `PROGRESS` projection by not adding `HostEventKind`.
- Split proactive dispatch compaction into request write, transaction-outside compactor operation, and result recheck/write.
- Split reactive ingest compaction into request/closeout write, transaction-outside compactor operation, and result recheck/write.
- Added bounded Host semantic repair attempts driven by `ContextBudgetPolicy.max_compaction_attempts_per_operation`.
- `LLMContextCompactor` does not loop for semantic repair and does not write EventLog/artifact/memory.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q`
  - passed: 14 passed
- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_llm_compaction.py tests/host/test_open_host_runtime.py tests/host/test_context_compact_events.py -q`
  - passed: 35 passed
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
  - passed: 68 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - passed: 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - passed

## Docs Decision

README files were not edited. The handoff explicitly forbids Slice 6 files in this implementation pass. Code-facing implementation artifact is this file.

## Plan Gaps / Controller Questions

- Slice 1-4 public API rename necessarily made Slice 5 smoke support fail pyright. Controller approved minimal edits in `tests/host/public_smoke_support.py` and `tests/host/test_public_compact_smoke.py` only to remove old public API usage and restore type-checking.
- Full public compact smoke behavior migration remains Slice 5. This pass did not redesign manual smoke or README behavior.

## Residual Risks / Uncovered Areas

- fixed now: public opener no longer accepts a Service-provided `ContextCompactor`.
- fixed now: Host-owned LLM compactor proposal executor exists and has no Service prompt/candidate/repair seams.
- fixed now: proactive and reactive compact calls are outside Host write transactions, covered by focused tests.
- fixed now: stale proactive compaction result does not write `CONTEXT_COMPACTED`, covered by focused test.
- fixed now: semantic proposal rejection writes `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, covered by payload tests and dispatch eventlog test.
- fixed now for compile/type-check: public compact smoke and shared smoke support no longer use package-root `CompactorExecutionBaseline` or `OpenHostOptions.compactor_baseline`.
- later slice: public compact smoke still needs full behavioral migration away from test-side real compactor helper/state assertions toward public artifact/watch evidence.
- later slice: README sync remains Slice 6.
- existing issue: real provider behavior is not covered by no-network unit tests.
- user/controller decision: whether to authorize full Slice 5 smoke behavior migration and Slice 6 README sync.

## Stop Status

Implementation pass completed within the approved Slice 1-4 scope plus controller-approved minimal Slice 5 compile fix. No commit, push, PR, review gate, or controller action was started.
