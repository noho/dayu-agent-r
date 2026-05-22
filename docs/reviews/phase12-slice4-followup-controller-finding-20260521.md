# Phase 12 Slice 4 Follow-up Controller Finding

## Scope

- Work unit: Phase 12 ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Current discovered issue: `SceneModelHints` does not preserve `model.temperature_profile`
- Discovery point: controller preparation for Slice 5 legacy scene asset migration

## Finding

Slice 4 accepted implementation parses only `model.default_name` into `SceneModelHints`. It does not preserve `model.temperature_profile`.

This conflicts with the accepted Phase 12 design and plan:

- `docs/host/design.md` states that scene `model.temperature_profile` overrides the execution profile runner options profile.
- `docs/host/phase12-runtime-assembly-plan.md` states the same override mapping.
- Legacy `dayu-agent` scene manifests use `model.temperature_profile` extensively, so Slice 5 migration depends on this field being representable in `PreparedSceneInputs`.

## Controller Decision

Accepted as a blocking follow-up fix before Slice 5 implementation continues.

Required fix:

- Add a typed optional temperature profile field to `SceneModelHints`.
- Parse `model.temperature_profile` from manifest as a string when present.
- Preserve it in `PreparedSceneInputs.model_hints` and scene digest.
- Add focused tests proving the field is parsed and remains stable through assembly.
- Update README / implementation report if needed.

Non-goals:

- Do not reintroduce `allowed_names` into runtime output.
- Do not map temperature profile to `RunnerCallOptions` in ScenePrepare. Service / composition root owns that mapping.
- Do not modify Host public interface.
