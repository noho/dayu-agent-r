# Phase 12 Plan Re-Review — AgentDS

- Date: 2026-05-20
- Plan artifact: `docs/host/phase12-runtime-assembly-plan.md`
- Prior reviews: `docs/reviews/phase12-plan-review-mimo-20260520.md`, `docs/reviews/phase12-plan-review-ds-20260520.md`
- Controller adjudication: `docs/reviews/phase12-plan-review-controller-adjudication-20260520.md`
- Plan fix artifact: `docs/reviews/phase12-plan-fix-codex-20260520.md`

## Verdict: PASS

All three accepted blocking findings are fully fixed. No new blockers introduced.

## Finding Status

### P12-PLAN-F1 — Source ref contract migration path: FIXED

Evidence in plan:

- Line 31: `dayu.contracts` declared as canonical owner of `ToolBundleSourceKind` / `ToolBundleSourceRef`, with preference for `dayu/contracts/tool_source.py`. `dayu.host.tooling` imports canonical types from `dayu.contracts`; existing `dayu.host` public exports may continue exporting the same canonical type — explicitly stated as "不是兼容性 wrapper / facade，也不是旧语义转发".
- Lines 43–44 (Slice 1 tasks): Migration task listed as first implementation task.
- Line 62 (Slice 1 stop condition): Ownership migration to `dayu.contracts` explicitly excluded from stop condition; stop condition now only fires on changes that add, remove, rename, or reshape Host public fields, exports, or behavior.

### P12-PLAN-F2 — `execution_profiles.json` schema: FIXED

Evidence in plan:

- Lines 199–273: Concrete JSON sketch covering `default_profile`, `profiles` (ordinary / compactor / context_budget / memory_projection / truncation), `runner_options_profiles`, `agent_policy_profiles`, `runner_hints`, `agent_hints`.
- Lines 276–285: Typed config view shape — `ExecutionProfilesConfig`, `ExecutionProfileConfig`, `OrdinaryExecutionConfig`, `CompactorExecutionConfig`, `RunnerOptionsProfileConfig`, `AgentPolicyProfileConfig`, `RunnerHintConfig`, `AgentHintConfig`, `ContextBudgetConfig`, `MemoryProjectionConfig`, `TruncationConfig`.
- Lines 286–292: Scene hints override order fully specified — `model.default_name` overrides `model_id`, `model.temperature_profile` overrides `runner_options_profile_id`, `runtime.runner` / `runtime.agent` hit hints for field-level override, and post-override Service must produce complete `RunnerSpec`, `RunnerCallOptions`, `AgentPolicy` with no raw fragments entering Host.

### P12-PLAN-F3 — `context_slots` typing and rendering: FIXED

Evidence in plan:

- Lines 348–368: Manifest declaration shape with JSON example — `name`, `value_type="string"`, `required`, `description`.
- Lines 371–381: `ScenePrepareRequest` typed input — `context_slot_values: Mapping[str, str]`; non-string values fail fast.
- Lines 382–383: Rendering mechanism — deterministic `{{slot_name}}` text replacement; unknown placeholder fails, missing required slot fails, non-string value fails, unresolved placeholder fails. No expressions, function calls, conditionals, or JSON/YAML interpretation.
- Lines 122–123 and 381–383: Non-string slot values, structured slot values, list slot values, and renderer callbacks all explicitly out of scope for Phase 12.

## New Blocking Findings

None.

## Non-Blocking Notes

- The `execution_profiles.json` sketch uses `extends: null` for the ordinary profile — implementation should ensure the `extends` field on profiles follows the same single-inheritance rules as manifest `extends`.
- Slice 1 and Slice 2 introduce separate test files (`test_tools_discovery.py` vs `test_tools_discovery_digest.py`) for distinct concerns, no conflict.
- The additional hardening notes (SHA-256 digest, resolved-path fragment containment) from the plan fix are correctly positioned as implementation detail, not new plan-level requirements.

## Final Blocking Findings Count: 0
