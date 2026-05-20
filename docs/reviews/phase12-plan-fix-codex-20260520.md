# Phase 12 Plan Fix — AgentCodex

- Date: 2026-05-20
- Fixed artifact: `docs/host/phase12-runtime-assembly-plan.md`
- Review artifacts:
  - `docs/reviews/phase12-plan-review-mimo-20260520.md`
  - `docs/reviews/phase12-plan-review-ds-20260520.md`
- Controller adjudication: `docs/reviews/phase12-plan-review-controller-adjudication-20260520.md`

## Summary

AgentCodex updated the Phase 12 implementation-ready plan to address the controller-accepted plan review findings.

## Fixes

### P12-PLAN-F1

The plan now explicitly sets `ToolBundleSourceKind` / `ToolBundleSourceRef` canonical ownership in `dayu.contracts`, preferring `dayu/contracts/tool_source.py` or an equivalent focused contracts module. It states that `dayu.host.tooling` imports those canonical types and that existing `dayu.host` public exports may continue exporting the same canonical types to preserve Host public surface without creating a compatibility wrapper.

The previous contradictory stop condition was narrowed: the required ownership migration is not an automatic design blocker; implementation must stop only if it needs to add, remove, rename or reshape Host public fields, exports or behavior.

### P12-PLAN-F2

The plan now includes an `execution_profiles.json` concrete sketch and a typed config view shape covering ordinary profile, compactor profile, runner options, agent policy, context budget, memory projection and truncation sections.

It also specifies how scene `model.default_name`, `model.temperature_profile`, `runtime.runner` and `runtime.agent` hints override profile fields before Service maps the resolved view to complete `RunnerSpec`, `RunnerCallOptions` and `AgentPolicy` values.

### P12-PLAN-F3

The plan now specifies Phase 12 `context_slots` as string-only. Manifest declarations include slot name, `value_type="string"` and required status. `ScenePrepareRequest` receives `context_slot_values: Mapping[str, str]`.

Rendering is defined as deterministic `{{slot_name}}` text replacement in prompt fragments. Missing required slots, unknown placeholders, non-string values or unresolved placeholders fail fast. Non-string slot values are out of scope for Phase 12.

## Additional Hardening Notes Added

- Tool and scene digest generation should use deterministic serialization and SHA-256.
- Fragment path containment should use resolved-path checks so fragment paths cannot escape the prompt asset root.

## Validation

No tests or pyright were run because this was a plan-only documentation fix. Controller performed text checks against the plan for the accepted findings.
