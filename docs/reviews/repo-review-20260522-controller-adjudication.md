# Full Repository Review Controller Adjudication

## Scope

Controller processed two parallel full-repository review artifacts:

- `docs/reviews/repo-review-20260522-070034.md`
- `docs/reviews/repo-review-20260522-070045.md`

Both reviews were produced around branch state `5ed2d88`. Current controller processing happens after Phase 12.2 commits `f570b26` and `9948792`, so every finding is judged against current `HEAD`.

## Current-Head Evidence

Controller focused validation against current `HEAD` found:

- `tests/contracts/test_tool_schema.py::test_truncate_spec_rejects_inconsistent_enabled_strategy_limits` still fails for the `(enabled=True, strategy=TEXT_CHARS, limits={})` case. This is an outdated test expectation after Phase 12.1 allowed declaration-time missing limits to be filled by runtime assembly policy defaults.
- `tests/host/test_import_boundary.py::test_fetch_more_token_stays_inside_toolruntime_owner_modules` still fails because `dayu/runtime/tools_discovery.py` owns reserved tool-name rejection for `fetch_more`, which is allowed by design but not reflected in the allowlist.
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py::test_runtime_assembly_fails_before_host_when_tools_not_discovered` passes. The smoke fail-fast finding is already fixed by Phase 12.2.

## Accepted Current Fix Items

Accepted items are limited to current-branch safe fixes that do not require reopening Engine design or moving broad Host durable contracts.

### RR-20260522-A1: Sync `ToolTruncateSpec` tests

- Source finding: `repo-review-20260522-070045.md` Finding 9.
- Decision: accepted current fix.
- Reason: focused test currently fails and contradicts accepted Phase 12.1 contract where enabled truncate declarations may omit limits for policy default fill.

### RR-20260522-A2: Add `runtime/tools_discovery.py` to `fetch_more` ownership allowlist

- Source finding: `repo-review-20260522-070045.md` Finding 10.
- Decision: accepted current fix.
- Reason: `ToolsDiscovery` is the correct layer-neutral owner for rejecting reserved framework tool names before Host construction; the boundary test must recognize this ownership.

### RR-20260522-A3: Tighten disabled `ToolTruncateSpec`

- Source finding: `repo-review-20260522-070045.md` Finding 6.
- Decision: accepted current fix.
- Reason: disabled truncate declarations carrying target or TTL fields are internally inconsistent and should fail fast. This is a local contract validation change with low blast radius.

### RR-20260522-A4: Add missing `_PublicHostHandle._closed` type annotation

- Source finding: `repo-review-20260522-070034.md` Finding 5.
- Decision: accepted current fix.
- Reason: local type-safety hardening with no behavior change.

### RR-20260522-A5: Make `MergedAgentPolicyConfig.field_sources` runtime-immutable

- Source finding: `repo-review-20260522-070034.md` Finding 6.
- Decision: accepted current fix.
- Reason: frozen dataclass should not expose a mutable dict by reference. Use a runtime-immutable mapping while preserving the public `Mapping[str, str]` type.

### RR-20260522-A6: Add selected ConfigLoader non-empty guards

- Source finding: `repo-review-20260522-070045.md` Finding 8.
- Decision: accepted current fix for `host_runtime.runtimes`, `runtime_lanes.lanes`, `execution_profiles.agent_policy_profiles`, and `tool_discovery.providers`.
- Reason: empty top-level catalogs are configuration shape errors and should fail during config load rather than later assembly.

## Already Fixed / No Current Action

### RR-20260522-R1: Smoke tool discovery fail-fast

- Source finding: `repo-review-20260522-070045.md` Finding 7.
- Decision: already fixed by Phase 12.2.
- Evidence: `tests/runtime/test_smoke_host_public_multiturn_assembly.py::test_runtime_assembly_fails_before_host_when_tools_not_discovered` passes on current `HEAD`.

## Deferred Items

### Engine findings

The following findings touch Engine behavior and should be handled in a dedicated Engine gate or after explicit user confirmation for Engine changes:

- `repo-review-20260522-070045.md` Finding 1: Engine `assert_never` diagnostics.
- `repo-review-20260522-070045.md` Finding 2: `_RunnerInterrupted` explicit agent-loop handling.
- `repo-review-20260522-070045.md` Finding 5: unknown SSE `finish_reason` handling.

Reason: current Host phase process explicitly treats Engine modifications as separate-gate work. Existing tests also document the current unknown-finish fallback-to-STOP behavior, so changing it requires a deliberate Engine contract decision.

### Broad Host / runtime refactors

The following findings are deferred because they are broad refactors or readability hardening, not current correctness blockers:

- `repo-review-20260522-070034.md` Finding 1: durable layer dependency split.
- `repo-review-20260522-070034.md` Finding 2: table-driven `merge_agent_policy_config`.
- `repo-review-20260522-070034.md` Finding 3: `LaneController.acquire` decomposition.
- `repo-review-20260522-070034.md` Finding 4: `dayu/host/api.py` module split.
- `repo-review-20260522-070045.md` Finding 3: facade-level CLOSED session error specificity.
- `repo-review-20260522-070045.md` Finding 4: PID start-token / boot-id liveness proof.
- `repo-review-20260522-070045.md` Finding 11: flaky steer test investigation.

Reason: each item needs a scoped design or hardening work unit, and none blocks the current Phase 12.2 service assembly closure.

## Next Step

Dispatch `RR-20260522-A1` through `RR-20260522-A6` to an implementation Agent via `$init-agents` routing, then run focused validation and send both review Agents a scoped re-review.
