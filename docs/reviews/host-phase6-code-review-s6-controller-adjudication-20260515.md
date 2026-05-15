# Host Phase 6 P6-S6 Controller Adjudication

## Scope

- Work unit: P6-S6 `Integration, Scheduler Wiring, And Gate Validation`
- Design source: `docs/host/design.md` §18 / §19
- Plan source: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` P6-S6
- Implementation artifact: `docs/reviews/host-phase6-implementation-s6-integration-gate-20260515.md`
- Review artifacts:
  - `docs/reviews/host-phase6-code-review-s6-mimo-20260515.md`
  - `docs/reviews/host-phase6-code-review-s6-ds-20260515.md`

## Verdict

**Accepted.** P6-S6 scope expansion is justified by the Phase 6 exit goal. A Phase 6 implementation that leaves real `HostDispatchScheduler` permanently wired to no-tool RunInputBuilder would only complete ToolRuntime components, not the Host tool execution path.

The implementation now closes that blocker: real local dispatch constructs a ToolRuntime handle and uses tool-enabled RunInputBuilder when Host construction tooling is present and policy allows tools. The no-tool path remains unchanged when tooling is absent or policy disables tools.

## Findings Adjudication

### MiMo Review

- Verdict: accepted.
- Findings: no blocking findings.
- Controller decision: accept all MiMo findings as evidence that the scope expansion is goal-driven, not scope creep.
- Residuals:
  - no-tool fallback explicit coverage is already present through existing default scheduler tests; no additional fix required.
  - policy digest field coverage is a maintenance concern for later policy provider changes.

### DS-F1 — `HostToolingOptions` private alias in `api.py`

- Decision: accepted as non-blocking advisory and fixed.
- Fix: updated `dayu/host/api.py` module docstring to explain that `HostLocalExecutionOptions` keeps a construction-time tooling input field while tooling types remain exported from `dayu.host.tooling`, not `dayu.host.api.__all__`.
- Evidence: `tests/host/test_package_exports.py` passes and confirms `HostToolingOptions` is not in `dayu.host.api`.

### DS-F2 to DS-F6

- Decision: accepted as pass findings.
- Reason: scheduler ToolRuntime construction uses the current dispatch snapshot identity, uses Host durable accept barrier, keeps schema/executor from the same `ToolRuntimeHandle`, preserves no-tool fallback, and the new test exercises the real scheduler path through ToolRuntime accept barrier into canonical EventLog facts.

### DS Residual — duplicate index per Attempt / ToolRuntime instance

- Decision: deferred tracking, not a P6-S6 blocker.
- Reason: P6-S5 plan explicitly scoped the duplicate index to the ToolRuntime instance; P6 does not implement steer / resume / recovery multi-Attempt continuation. For later same-Run multi-Attempt owners, this must be re-evaluated against the design phrase "run-local".
- Owner: Phase 7 wait / resume, later steer owner, and recovery hardening if they require same-Run duplicate memory across Attempt boundaries.

## Validation

- `source .venv/bin/activate && pytest tests/host -q`
  - 348 passed
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_package_exports.py -q`
  - 20 passed
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Residual Risks

- Multi profile / per-scene tool profile is still a later ToolsDiscovery / policy provider concern.
- `policy_snapshot_digest` remains a diagnostic digest, not durable attempt tool snapshot truth.
- Duplicate governance index currently follows ToolRuntime instance lifetime; future same-Run multi-Attempt features must decide whether to carry a run-level in-memory index across attempts.
- Phase 6 still needs final aggregate review before ready-to-create-PR.
