# WU-TOOLS-01-F01-02-R1 Slice 3 Code Review Controller Adjudication

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 3 `Service wiring, docs, and final focused validation`
- gate: code review
- base checkpoint: `81bc62b9`
- implementation artifact: `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`
- review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`

## Review Summary

- AgentMiMo conclusion: `pass`; one medium finding and two low findings.
- AgentDS conclusion: `pass`; one medium finding, two low findings, plus one open question about standalone Fins activation registry builder usage.
- Controller conclusion: Slice 3 wiring is correct, but should take a small code-review fix pass before accepted slice commit.

## Adjudication

### S3-CR-F01 accepted: discarded `build_fins_wait_adapter_registry(...)` call

Both reviewers independently found that `_fins_wait_activation_registry_from_provider_configs(...)` calls `build_fins_wait_adapter_registry(...)` only for validation and discards the returned registry. This is not a runtime correctness bug, but it is misleading and can hide future side effects.

Required fix:

- Remove the discarded registry construction.
- Keep equivalent validation direct and explicit.
- Do not change activation registry behavior.

### S3-CR-F02 accepted: disabled provider callable should not contain unreachable output construction

`discover_from_bindings(...)` skips disabled specs before invoking their provider callable. A full `ToolsDiscoveryProviderOutput` construction inside `_DisabledProviderCallable.__call__` is unreachable and misleading.

Required fix:

- Replace the body with a fail-fast unreachable path, or otherwise make the sentinel intent explicit.
- Preserve disabled provider reporting behavior and ordinary provider discovery behavior.

### S3-CR-F03 accepted: duplicate Fins awaiting provider collection should be centralized

The wait adapter registry and activation registry builders duplicate provider filtering, workspace root collection, and available-tool filtering. This is a low-risk maintenance issue, but it matters because both registries must stay aligned.

Required fix:

- Extract a small private helper that collects Fins awaiting tool names and the single workspace root once.
- Use it from both registry construction paths.
- Avoid a broad abstraction or platform layer.

### S3-CR-F04 accepted: `_tooling_options_from_discovery(...)` should not imply shared runtime is optional in Fins awaiting paths

The default `None` is harmless today because the only production caller passes the runtime, but it weakens the local contract.

Required fix:

- Make the function signature or local validation clearer so Fins awaiting runtime is explicit for callers.
- Keep no-Fins-awaiting behavior unchanged.

### S3-CR-F05 accepted as documentation/guardrail: standalone Fins activation registry builder runtime mismatch

`build_fins_wait_activation_registry(...)` constructs a new runtime from workspace root, while Service assembly intentionally uses a shared runtime instance. This is not a current production bug because Service bypasses the standalone builder, but future callers could misunderstand it.

Required fix:

- Add a concise docstring/comment guardrail on the standalone builder or Service assembly path explaining that production awaiting tool callables, poll adapter, and activation adapter must share the same runtime instance.
- Do not introduce a new public lifecycle platform or broad builder API unless direct code evidence proves it is required.

## Residual Risks

- Full open-host dispatch worker activation path is not fully end-to-end tested in this slice. Current focused service test verifies Service discovery -> HostToolingOptions -> shared runtime -> activation adapter behavior, while Host ToolRuntime activation hook was covered in Slice 1.
- Production poller scheduling, backoff, fencing and retry remain owned by GitHub Issue #90.
- External provider physical cancel / revoke / abandon remains owned by GitHub Issue #92.

## Next Gate

Enter Slice 3 code-review fix gate for AgentCodex. The fix must stay limited to S3-CR-F01 through S3-CR-F05, then rerun the focused Service test, the focused Host/Fins validation matrix, `pyright`, and `git diff --check`.
