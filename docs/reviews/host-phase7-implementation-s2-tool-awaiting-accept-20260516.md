# P7-S2 Implementation - ToolRuntime Awaiting Accept Path

## Scope

- Phase: Phase 7 `Tool Awaiting / resolve_wait / Wait Adapter`
- Slice: P7-S2 `ToolRuntime Awaiting Accept Path`
- Branch: `feat/host-phase7-tool-awaiting-resolve-wait`
- Base commits:
  - P7-S1 accepted checkpoint: `aaa107a`
  - P7-S1 control checkpoint: `57492f5`

## Changed Files

- `dayu/host/wait_adapter.py`
- `dayu/host/waiting.py`
- `dayu/host/_event_payload.py`
- `dayu/host/durable/state.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_wait_awaiting_accept.py`
- `tests/host/test_toolruntime_executor.py`

## Implemented Behavior

- Added Host-internal wait adapter registry:
  - `WaitAdapterBinding`
  - `WaitAdapterRegistry`
  - `WaitExternalJobRefSource`
- Added awaiting accept port and durable service:
  - `ToolAwaitingAcceptCandidate`
  - `ToolAwaitingAcceptedAck`
  - `ToolAwaitingRejectedAck`
  - `ToolAwaitingAcceptTimedOut`
  - `DefaultHostToolAwaitingAcceptPort`
- Awaiting accept transaction now validates active Run / Attempt / dispatch identity, appends `TOOL_AWAITING`, `RUN_WAITING`, `ATTEMPT_SUSPENDED`, inserts one active wait record, marks Run `WAITING`, and marks Attempt `SUSPENDED`.
- Same awaiting accept idempotency key + same digest returns existing ack refs without duplicate canonical facts.
- Same awaiting accept idempotency key + different digest returns idempotency conflict rejected ack.
- ToolRuntime no longer normalizes `ToolAwaitingOutcome` into `unsupported_awaiting` when a wait adapter registry and awaiting accept port are configured.
- ToolRuntime returns `ToolAwaitingOutcome` to Engine only after `ToolAwaitingAcceptedAck`.
- Missing adapter registry / binding returns a governed tool error and does not call the ordinary tool fact accept port.
- Poll binding derives typed `ExternalJobRef` from Host binding logic rather than Engine event data.
- Awaiting accepted stops the remaining tool calls in the same batch and returns governed errors for later records without invoking business callables.
- Awaiting rejected / timeout and poll binding missing external job ref branches are covered at ToolRuntime layer.

## Explicit Non-Goals Preserved

- No public `resolve_wait` implementation.
- No WAITING cancel implementation.
- No poller / callback runtime.
- No EngineEvent ownership change.
- No Engine contract or `dayu/contracts` change.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_awaiting_accept.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py -q`
  - 24 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors
- `git diff --check`
  - clean

## Handoff Notes For Review

- Review the transaction ordering in `DefaultHostToolAwaitingAcceptPort`: events are appended before wait record / state CAS; all happen inside one write transaction, so rejected CAS rolls back appended rows.
- Review whether `ToolRuntimeExecutor` correctly bypasses ordinary `ToolFactAcceptCandidate` for awaiting outcomes and leaves completed / failed / cancelled tool behavior unchanged.
- Review whether the minimal `WaitAdapterRegistry` is sufficiently typed for S2 while not prematurely implementing poller behavior owned by P7-S4.
