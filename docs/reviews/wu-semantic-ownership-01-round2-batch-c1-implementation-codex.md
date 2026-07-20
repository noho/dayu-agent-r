# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Implementation

## scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1`.
- Gate: `implementation/fix`.
- Implementing agent: `AgentCodex`.
- Scope boundary: Host wait expiry / supervisor / claim-release / wait EventLogStore DI.
- Explicit non-scope: dispatch, promotion, cancel predispatch, tool accept duplicate index, Engine retry, Batch C2 public-contract changes.

## changed files

- `dayu/host/wait_boundary.py`
- `dayu/host/waiting.py`
- `dayu/host/wait_adapter.py`
- `dayu/host/wait_callback.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`

## owner decisions

- Host wait durable state now owns `deadline_at` / `expires_at` parsing through `dayu.host.wait_boundary.classify_wait_time_boundary(...)`.
- `resolve_wait` rejects expired waiting records through the common owner path and fails closed on invalid stored boundary before any terminal transition.
- Wait poller checks Host-owned time boundary before calling provider adapters, so poll ready / not-ready / adapter-error observations cannot independently accept, continue, or convert an expired/corrupt Host boundary into provider `LOST`.
- Callback adapter no longer parses deadline / expires; it authenticates, validates payload digest, and delegates to `resolve_wait`.
- Fins wait adapter no longer reads Host deadline / expires in transient-unavailable handling; it reports typed provider observation only.
- `waiting.py` wait-resolution request atom validation now uses the injected `EventLogStore` instance instead of constructing temporary stores.

## fixed findings

- `144159-01` / `145711-12`: fixed. Deadline / expiry interpretation moved to Host wait owner; callback and Fins provider branch no longer own the decision.
- `150304-01`: fixed. `WaitPollerSupervisor` isolates single-round transient exceptions, records diagnostics, backs off, and continues. Self-close from the supervisor thread remains an unrecoverable programming error.
- `150304-02`: fixed. `_resolve_claimed_wait` handles read-back failure during error recovery and returns `INVALID_STATE` for the current wait instead of bubbling to the supervisor.
- `150304-22`: fixed for C1 claim-release owner. `_abandon_cancelled_wait` now attempts to release the current claim on abandon CAS loss where the current claim is still owned by this poller.
- `150304-23`: fixed for `waiting.py`. Wait resolution uses the injected `EventLogStore` for request atom and awaiting-event validation.
- `150304-11/12/13`: not modified beyond C1 owner surface. The CAS / DI / claim-release items directly overlapping this file set are covered above; broader admission / promotion semantics remain Batch C2 or separate owner scope.

## tests

- Added resolver owner tests for expired wait rejection and invalid stored deadline fail-closed behavior.
- Updated callback tests so deadline behavior is asserted at `resolve_wait` owner, not callback adapter.
- Added poller matrix covering expired wait with ready / not-ready / adapter-error observations, plus invalid boundary not becoming business `LOST`.
- Added supervisor single-round exception recovery test.
- Added `_resolve_claimed_wait` resolve-failure plus read-back-failure isolation test.
- Added cancelled abandon CAS_LOST current-claim release test.
- Added injected `EventLogStore` usage test for wait-resolution request atom validation.
- Updated Fins transient-unavailable test to prove provider adapter does not consume Host wait boundaries.

## validation

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/fins/test_fins_ingestion_tools.py -q`
  - Result: `126 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_phase7_waiting_integration.py -q`
  - Result: `8 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## README decision

- Read `dayu/host/README.md`, `dayu/fins/README.md`, and `tests/README.md` update boundaries.
- No README update required: this batch changes internal Host wait ownership and existing test coverage, without adding a public API, user workflow, test layer, Fins capability, or stable developer-facing interface beyond what the existing READMEs already describe.

## residual risk

- Expired waits now fail closed and remain `WAITING` with late diagnostic / poll backoff rather than being accepted or provider-lost. If product policy later wants expired waits to become a specific terminal status, that should be a separate Host wait policy owner decision.
- `WaitPollerDiagnosticsSnapshot.fatal_errors` is reused to count isolated round exceptions as well as fatal self-close errors. The runtime status distinguishes recoverable `RUNNING` from unrecoverable `FAILED`; a later diagnostics cleanup could rename the counter, but no behavior depends on the old label.
- Batch C2 findings for dispatch, promotion, cancel predispatch, tool accept duplicate index, and Engine retry remain untouched by this artifact.

## stop status

- Batch C1 implementation/fix is complete locally.
- No commit, push, PR, or merge was performed.
