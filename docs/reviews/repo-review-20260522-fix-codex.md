# Full Repository Review Accepted Fix - AgentCodex

## Scope

- Gate: Full-repo review accepted fix after Phase 12.2 push.
- Source adjudication: `docs/reviews/repo-review-20260522-controller-adjudication.md`.
- Implemented only accepted current fix items `RR-20260522-A1` through `RR-20260522-A6`.
- No Engine changes, no durable layer split, no broad Host/API refactor, no README dead-link fix, no `docs/host/design.md` change, no commit, no push, no PR.

## Fix Status

### RR-20260522-A1 - fixed

- Updated `tests/contracts/test_tool_schema.py`.
- Removed the outdated expectation that `enabled=True` with a strategy and empty `limits` must fail.
- Added an explicit passing test proving declaration-time empty `limits` are allowed so runtime assembly policy defaults can fill the effective spec.

### RR-20260522-A2 - fixed

- Updated `tests/host/test_import_boundary.py`.
- Added `runtime/tools_discovery.py` to the `fetch_more` ownership allowlist.
- This preserves the boundary rule while recognizing runtime tool discovery as the layer-neutral owner for reserved framework tool-name rejection.

### RR-20260522-A3 - fixed

- Updated `dayu/contracts/tool_schema.py` and `tests/contracts/test_tool_schema.py`.
- Disabled `ToolTruncateSpec` now fail-fast rejects `target_field`, `field_path`, and `ttl_seconds`, in addition to existing `strategy` and `limits` rejection.
- Added parametrized contract tests for the disabled target / TTL failure cases.

### RR-20260522-A4 - fixed

- Updated `dayu/host/open_host.py`.
- Added the missing `bool` annotation to `_PublicHostHandle._closed`.
- No runtime behavior changed.

### RR-20260522-A5 - fixed

- Updated `dayu/runtime/assembly.py` and `tests/runtime/test_assembly_helpers.py`.
- `MergedAgentPolicyConfig.field_sources` remains publicly typed as `Mapping[str, str]`, but `merge_agent_policy_config` now returns a `MappingProxyType` runtime-immutable mapping.
- Added a focused test confirming attempted mutation raises `TypeError`.

### RR-20260522-A6 - fixed

- Updated `dayu/runtime/config_loader.py` and `tests/runtime/test_config_loader.py`.
- Added non-empty guards for:
  - `host_runtime.runtimes`
  - `execution_profiles.agent_policy_profiles`
  - `tool_discovery.providers`
- `runtime_lanes.lanes` already had a production guard; added a focused regression test for it alongside the new guards.

## Validation

- `source .venv/bin/activate && pytest tests/contracts/test_tool_schema.py tests/host/test_import_boundary.py tests/runtime/test_assembly_helpers.py tests/runtime/test_config_loader.py -q`
  - Result: passed, `56 passed`.
- `source .venv/bin/activate && pytest tests/runtime -q`
  - Result: passed, `213 passed`.
- `source .venv/bin/activate && pytest tests/contracts tests/host/test_import_boundary.py -q`
  - Result: passed, `64 passed`.
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.

## Documentation Decision

- No README update was made.
- The modified tests document additional focused guards and contract edges, but no user-facing command, package responsibility, architecture boundary, or stable test-running convention changed.

## Deferred Items Not Handled

- Engine findings remain deferred to a dedicated Engine gate:
  - Engine `assert_never` diagnostics.
  - `_RunnerInterrupted` explicit agent-loop handling.
  - Unknown SSE `finish_reason` handling.
- Broad Host / runtime refactors remain deferred:
  - Durable layer dependency split.
  - Table-driven `merge_agent_policy_config` refactor.
  - `LaneController.acquire` decomposition.
  - `dayu/host/api.py` module split.
  - Facade-level CLOSED session error specificity.
  - PID start-token / boot-id liveness proof.
  - Flaky steer test investigation.
- README dead-link cleanup remains out of scope.

## Residual Risk

- The fix intentionally does not alter Engine behavior or broad Host runtime structure.
- `MappingProxyType` prevents direct mutation of the returned `field_sources` mapping; nested data is not involved because values are strings.
