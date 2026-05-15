# Host Phase 5 P5-S2 RunInputBuilder And No-tool Provider Boundary Implementation

- gate: Host Phase 5 implementation
- slice: P5-S2 RunInputBuilder And No-tool Provider Boundary
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`
- implementation date: 2026-05-15
- role: implementation agent

## Scope

Allowed production files changed:

- `dayu/host/run_input.py`
- `dayu/host/api.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/__init__.py`

Allowed test files changed:

- `tests/host/test_run_input_builder.py`
- `tests/host/test_package_exports.py`

Allowed files not changed:

- `dayu/host/durable/state.py`

Non-goals honored:

- Did not implement scheduler, LocalProxy, WorkerProxy, Engine dispatch, EngineEvent ingest, ToolRuntime, or real tool execution.
- Did not modify Engine files.
- Did not read UI / Service transient request data for current prompt construction.
- Did not add weak typing signatures, `Any`, untyped parameters, or untyped returns.

## Implemented Plan Items

- Added `AttemptDispatchSnapshot` with durable identity refs, dispatch refs, `policy_snapshot_ref`, and cancellation token only.
- Added `dayu.host.run_input` with typed provider protocols and view dataclasses:
  - current Run facts
  - session continuity
  - memory snapshot
  - compact artifact
  - tool schema snapshot
  - tool executor
  - scene parameters
  - policy snapshot
- Added durable current-run provider that reconstructs current prompt from durable `USER_INPUT_ACCEPTED.payload_json.display_text`.
- Added durable session continuity provider that reads only canonical EventLog facts before the current Attempt boundary.
- Added noop providers for memory, compact artifact, tool schema, and no-tool executor.
- Added `NoToolExecutor`, returning `ToolCancelledOutcome(reason=host_cancelled)` for all unexpected tool calls.
- Added `RunInputBuilder.build(attempt_snapshot)` producing deterministic no-tool `AgentRunRequest`.
- Added a narrow EventLog reader for RunInputBuilder continuity facts, filtering out preview, diagnostic, and projection_signal events.
- Exported `AttemptDispatchSnapshot` through `dayu.host.api` and package root because later local worker factory options need a stable typed snapshot.

## Tests Added Or Updated

- `tests/host/test_run_input_builder.py`
  - current user message comes only from durable `USER_INPUT_ACCEPTED`;
  - repeated builds over the same EventLog and policy snapshot are deterministic;
  - continuity messages follow `event_sequence` and ignore non-canonical events;
  - noop memory / compact / tool schema providers do not create durable rows;
  - no-tool request has `disable_tools=True`, `tool_schemas=()`, and `allow_tool_calls=False`.
- `tests/host/test_package_exports.py`
  - package/API export allowlist updated for `AttemptDispatchSnapshot`.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
```

Result:

```text
11 passed in 0.26s
```

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## Documentation Decision

No README or implementation-control update was made because this implementation handoff allowed only the P5-S2 files listed above and this artifact.

## Residual Risks

- Memory snapshot, compact artifact, and real ToolRuntime/tool schema providers remain later-phase owners: Phase 9, Phase 10, and Phase 6 respectively.
- RunInputBuilder currently requires durable `display_text` for the current prompt; artifact-backed prompt body loading is not implemented in this slice.
- LocalProxy / scheduler integration and construction of real `AttemptDispatchSnapshot` are P5-S3 work.

## Stop Status

No stop condition was hit.
