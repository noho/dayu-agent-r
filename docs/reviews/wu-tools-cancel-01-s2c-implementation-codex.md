# WU-TOOLS-CANCEL-01 S2C Implementation - AgentCodex

## Gate

- Work unit: WU-TOOLS-CANCEL-01
- Slice: S2C Fins read process-backed
- Gate: implementation
- Branch: phase/wu-tools-cancel-01
- Verdict: READY_FOR_CODE_REVIEW

## Scope

Implemented the S2C migration for the nine non-WAITING Fins read tools:

- `list_documents`
- `get_document_sections`
- `read_section`
- `search_document`
- `list_tables`
- `get_table`
- `get_page_content`
- `get_financial_statement`
- `query_xbrl_facts`

No Host / Engine contract, durable schema, `dayu.runtime.interruptible_process` JSON contract, Web tools, or Fins download / preprocess / upload WAITING tool behavior was changed.

## Motivation Judgment

The motivation is valid. Before this slice, Fins read tools still captured an in-process `FinsReadRuntime` and `provider_lock` and executed synchronous read business through `asyncio.to_thread(...)`. That path cannot provide production-grade non-cooperative interrupt semantics for #87, and it risks accepting stale blocking results after Host cancellation. The root cause is the Fins read provider execution boundary, not Engine cancellation, Host durable state, or storage schema.

## Changed Files

- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `dayu/fins/README.md`
- `tests/README.md`

## Implementation Summary

- Added module-level `_FinsReadProcessTargetFactory` and `_FinsReadProcessTarget`.
- Changed `build_fins_read_tool_definitions(...)` to receive an explicit `workspace_root: Path`.
- Declared `ProcessBackedToolExecutionCapability` for all nine Fins read `ToolDefinition`s.
- Moved direct callable and process target execution through shared synchronous routing:
  - argument validation remains schema-driven through `validate_and_project_arguments(...)`;
  - success output shape remains the existing read runtime payload;
  - failure codes and recovery hints are preserved, with process-backed hint text folded into the failed envelope message because the Host process envelope has no separate hint field.
- In the child process, the target reconstructs `DefaultFinsRuntime.create(workspace_root=Path(...))` and calls `get_read_runtime(processor_cache_max_entries=...)`.
- The process target only stores serializable values: workspace root string, tool name, JSON argument copy, `FinsToolLimits`, and timeout scalar.
- Direct callable fallback remains available for direct tests and non-production fallback only; it is no longer the production default.

## Storage / Process Boundary

The process-backed path does not serialize or capture:

- `FinsReadRuntime`
- repository objects
- processor cache instances
- provider locks
- `CancellationToken`
- session/run objects
- Host internals

All Fins file access still goes through `DefaultFinsRuntime` and `dayu.fins.storage` repositories.

## Tests Added / Updated

Updated `tests/fins/test_fins_storage_provider.py` to cover:

- all nine read definitions declare process-backed execution;
- process target factory and target pickle round-trip;
- process target does not carry obvious runtime / repository / Host-governance payload fragments;
- fast path through `list_documents`;
- processor path through `search_document`;
- table path through `list_tables`;
- parameter failure returns a `failed` process JSON envelope, not awaiting / cancelled / timeout / host_cancelled;
- spawned-child pre-check using `ProcessBackedToolExecutionCapsule` and a real temporary Fins workspace;
- ToolRuntime cancellation of a real Fins process-backed target drops the late result.

Existing direct callable cancellation tests remain as fallback coverage.

## Documentation Sync

- `dayu/fins/README.md` updated to describe read tool process-backed production execution, explicit `workspace_root` passing, and child-process `DefaultFinsRuntime` reconstruction.
- `tests/README.md` updated to record the new Fins process-backed read coverage.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py -q
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q
source .venv/bin/activate && pyright
git diff --check
```

Observed results:

- `tests/fins/test_fins_storage_provider.py`: 30 passed, 3 third-party deprecation warnings from `edgar`.
- `tests/fins/test_fins_ingestion_tools.py`: 56 passed, 3 third-party deprecation warnings from `edgar`.
- `tests/host/test_toolruntime_executor.py`: 55 passed.
- `pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.

## Stop Conditions

No stop condition was hit:

- did not bypass `dayu.fins.storage`;
- did not serialize runtime, repository, processor cache, provider lock, cancellation token, or Host internals across process boundary;
- did not require parent-process provider lock in the child;
- did not modify Engine / Host contracts or durable schema;
- did not change `dayu.runtime.interruptible_process` away from `JsonValue`;
- did not change Fins download / preprocess / upload WAITING behavior.

## Residual Risks

- Fixed in current slice: the process envelope still has no dedicated hint field, so failed-envelope hints are appended to the message. This follows the existing Doc process-backed pattern and avoids changing the Host process envelope contract.
- Fixed in current slice: the direct callable fallback still uses the provider lock and `asyncio.to_thread(...)` for direct tests and non-production fallback, but production default is process-backed and tests assert the declared execution mode.
- Tracked by existing coverage: cancellation coverage uses a real spawned Fins process target and Host ToolRuntime cancellation. The focused Fins test gives S2C integration evidence; deterministic non-cooperative process kill behavior remains covered by `tests/host/test_toolruntime_executor.py`.

## Next Gate

Implementation is ready for code review. Per user instruction, this pass did not enter review gate and did not commit, push, or open a PR.
