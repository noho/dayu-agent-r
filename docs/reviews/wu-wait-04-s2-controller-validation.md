# WU-WAIT-04 S2 Controller Validation

## Scope

- Slice: S2 `Public-only entrypoint awaiting E2E smoke`
- Implementation report: `docs/reviews/wu-wait-04-s2-implementation-codex.md`
- New smoke: `tests/service/test_entrypoint_runtime_awaiting_smoke.py`

## Boundary Check

- Rejected the initial S2 implementation because it imported private `dayu.engine.agent._AsyncAgent`, which violated the user hard constraint that smoke tests can only use public contracts.
- Follow-up implementation removed `dayu.engine.agent` / `_AsyncAgent`.
- Current smoke uses:
  - public Service entrypoint `submit_entrypoint_turn_and_wait`;
  - public Host opener and methods: `open_host`, `ensure_session`, `get_run`, `read_outbox_terminal_items`;
  - public construction-time contracts: `OpenHostOptions`, `HostToolingOptions`, `WaitPollAdapterRegistry`, `LocalEngineWorker`, `LocalWorkerHandle`;
  - public Engine-exported event contracts only as the `LocalWorkerHandle.events() -> AsyncIterator[EngineEvent]` payload required by the public worker protocol.
- Current smoke does not assert Engine event internals; behavioral assertions remain at Host / Service public API level.

## Controller Validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: passed, `1 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: passed, `55 passed, 3 warnings`.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- Forbidden-path guard:
  - Command: `rg -n "from dayu\.host\.durable|import dayu\.host\.durable|from dayu\.host\.tool_runtime|import dayu\.host\.tool_runtime|open_host_durable_store|read_active_wait_records_for_run|read_wait_record_by_id|ResolveWaitRequest|WaitResolutionSource\.MANUAL|resolve_wait\(|ToolRuntime|dispatch row|scheduler|dayu\.engine\.agent|_AsyncAgent" tests/service/test_entrypoint_runtime_awaiting_smoke.py`
  - Result: no matches.
- Weak typing / private bypass guard:
  - Command: `rg -n "\bAny\b|\bobject\b|type: ignore|# pyright|hasattr\(|getattr\(" tests/service/test_entrypoint_runtime_awaiting_smoke.py`
  - Result: only JSON tool schema `"type": "object"` matched, which is allowed by AGENTS tool schema exception.
- `git diff --check`
  - Result: passed.

## README Decision

- `tests/README.md` was updated because S2 adds a new `tests/service/` entrypoint runtime smoke coverage fact.
- No production code changed in S2, so no layer README or user-facing README update is required for this slice.

## Controller Decision

S2 implementation is accepted for code review dispatch. The remaining review focus should challenge whether the public worker protocol fixture faithfully exercises Host wait recovery without reintroducing private wait storage, dispatch scheduler, manual resolve, or Engine agent internals.
