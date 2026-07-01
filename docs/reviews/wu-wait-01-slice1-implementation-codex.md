# WU-WAIT-01 Slice 1 Implementation - AgentCodex

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: implementation
- Slice: Slice 1 Host callback contract and adapter
- Accepted plan commit: `bf359ebb`

Only Slice 1 was implemented. No HTTP framework, Service mapper, durable schema migration, Engine contract change, issue-90 poller loop, issue-92 physical cancel, commit, push, PR, or control-doc update was performed.

## Changed Files

- `dayu/host/wait_callback.py`
- `dayu/host/command.py`
- `dayu/host/__init__.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `dayu/host/README.md`
- `docs/reviews/wu-wait-01-slice1-implementation-codex.md`

`docs/host/issues-implementation-control.md` already had controller gate updates in the worktree and was not modified by this implementation.

## Behavior Implemented

- Added framework-independent callback Host contract:
  - `WaitCallbackAdapterStatus`
  - `WaitCallbackAuthInput`
  - `WaitCallbackAuthAccepted`
  - `WaitCallbackAuthRejected`
  - `WaitCallbackAuthenticator`
  - `WaitCallbackCompletionEnvelope`
  - `WaitCallbackAdapterResult`
  - `CallbackWaitResolvePort`
  - `CallbackWaitResolveResult`
  - wait state read port/projection needed by the adapter
- Added `DefaultWaitCallbackAdapter.resolve_callback(...)`.
- Adapter validates typed envelope shape through dataclass construction, authenticates before durable reads, pre-reads wait state for unknown/stale/late classification, verifies digest over only `wait_id + idempotency_key + outcome`, builds `HostCallContext`, builds `ResolveWaitRequest(source=CALLBACK)`, and calls the injected command-layer resolve port.
- Adapter does not call `DefaultHostResolveWaitService` directly and does not write durable state except through the injected resolve port.
- Added `HostCommandWaitCallbackPort` in `dayu.host.command`.
  - It reads wait state as a narrow callback projection.
  - It calls the existing resolve service.
  - It returns `RunSnapshot` plus `idempotent_replay`.
  - It preserves existing dispatch wakeup semantics: non-replay resume dispatch wakes once; replay does not wake again.
- Host package root exports the stable callback contract symbols, but not the command port implementation.
- Import boundary test now asserts the callback adapter has no Service/UI/FastAPI/Flask/Starlette/Django/aiohttp dependency.

## Tests Run

```bash
source .venv/bin/activate && pytest tests/host/test_wait_callback.py -q
```

Result: `11 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
```

Result: `54 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

## README Decision

`dayu/host/README.md` was updated because Slice 1 adds stable Host public callback contracts and command-layer port semantics that belong to the Host developer interface scope defined by the README update constraints.

Root README was not updated because Slice 1 exposes no user-visible CLI/Web route, install flow, default output channel, or end-user workflow change.

## Residual Risks / Deferred Scope

- Real HTTP route, transport parsing, malformed payload mapping, and HTTP status mapping remain Slice 2 / Service-Web scope.
- Deployment-specific bearer/HMAC/secret verification remains outside Host; Slice 1 only defines the typed authenticator protocol.
- Stale classification uses current persisted `deadline_at` and optional reserved `expires_at`; no new lifecycle or schema was introduced.
- Raced late-state changes may still collapse to `INVALID_WAIT_STATE`, as approved by the plan.

## Completion Status

Slice 1 implementation is complete and validated.
