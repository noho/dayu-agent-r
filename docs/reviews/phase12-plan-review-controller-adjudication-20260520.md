# Phase 12 Plan Review Controller Adjudication

- Date: 2026-05-20
- Plan artifact: `docs/host/phase12-runtime-assembly-plan.md`
- Review artifacts:
  - `docs/reviews/phase12-plan-review-mimo-20260520.md`
  - `docs/reviews/phase12-plan-review-ds-20260520.md`

## Verdict

Plan review is blocked pending a narrow plan fix.

Accepted blocking findings count: 3.

## Accepted Findings

### P12-PLAN-F1: Source ref contract migration path must be explicit

Accepted.

Rationale: `ToolsDiscovery` is required to live in `dayu.runtime`, and `dayu.runtime` may only depend on standard library plus lower public contracts. The current plan cannot leave `ToolBundleSourceKind` / `ToolBundleSourceRef` in `dayu.host.tooling` while asking runtime to produce them. The plan must choose the canonical location and implementation path before implementation begins.

Required plan fix:

- Make `dayu.contracts` the canonical owner of `ToolBundleSourceKind` and `ToolBundleSourceRef`.
- Prefer a focused module such as `dayu/contracts/tool_source.py` or an equivalent contracts module; Host tooling imports these types from `dayu.contracts`.
- Existing `dayu.host` public exports may continue exporting the same canonical types as part of Host public surface preservation. This is not a compatibility wrapper that merely forwards old semantics; it preserves an existing Host public export while moving ownership to the correct lower layer.
- Remove the contradictory stop condition that treats this required ownership migration as an automatic design blocker. Keep the stop condition only for changes that add or reshape Host public fields or Host behavior.

### P12-PLAN-F2: `execution_profiles.json` schema needs concrete plan-level shape

Accepted.

Rationale: ConfigLoader schema is one of Phase 12's core deliverables. A plan that only names `execution_profiles.json` at a prose level leaves implementation agents to invent the highest-risk mapping from scene hints to typed execution inputs.

Required plan fix:

- Add a concrete JSON sketch for `execution_profiles.json`.
- Add a typed config view shape in plan prose, including ordinary profile, compactor profile, runner options, agent policy, context budget, memory projection and truncation sections.
- State how scene `model.default_name`, `model.temperature_profile`, `runtime.agent` and `runtime.runner` hints override profile fields before Service maps to complete `RunnerSpec`, `RunnerCallOptions` and `AgentPolicy`.

### P12-PLAN-F3: `context_slots` typing and rendering mechanism must be specified

Accepted.

Rationale: `context_slots` are the only stable input path by which Service provides scene-specific typed context to `ScenePrepare`. The plan must define the first-version contract tightly enough that implementation and tests cannot choose incompatible rendering semantics.

Required plan fix:

- Specify the first-version `context_slots` manifest declaration shape.
- Specify the `ScenePrepare` API input shape for context slot values without using `Any` or untyped payload bags.
- Specify the rendering mechanism. The first-version preferred mechanism is deterministic `{{slot_name}}` text replacement in prompt fragments, with string values only, unknown placeholder failure and missing required slot failure.
- If non-string slot values are intentionally deferred, state that they are out of scope for Phase 12.

## Non-Blocking Findings

The following are accepted as implementation-time hardening or documentation detail, not plan blockers:

- Digest algorithm should use deterministic serialization and SHA-256.
- Fragment path escape prevention should use resolved-path containment checks.
- Legacy `dayu-agent` migration source is a one-time local asset path and must be validated in Slice 5.
- Concrete schemas for `models.json`, `host_runtime.json` and `tool_discovery.json` may be refined in implementation, but plan fix may add sketches if convenient.

## Next Step

Return to plan fix. The fix must only update `docs/host/phase12-runtime-assembly-plan.md` unless the plan author finds a genuine design contradiction, in which case implementation remains blocked and the controller must return to design discussion.
