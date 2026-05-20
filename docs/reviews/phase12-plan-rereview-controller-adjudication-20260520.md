# Phase 12 Plan Re-Review Controller Adjudication

- Date: 2026-05-20
- Work unit: Phase 12. ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Plan artifact: `docs/host/phase12-runtime-assembly-plan.md`
- Prior controller adjudication: `docs/reviews/phase12-plan-review-controller-adjudication-20260520.md`
- Plan fix artifact: `docs/reviews/phase12-plan-fix-codex-20260520.md`
- Re-review artifacts:
  - `docs/reviews/phase12-plan-rereview-mimo-20260520.md`
  - `docs/reviews/phase12-plan-rereview-ds-20260520.md`

## Verdict

PASS.

Both independent re-review artifacts confirm that the Phase 12 plan fix fully closes the accepted plan findings and introduces no new blocking finding.

Final blocking findings count: 0.

## Accepted Finding Status

### P12-PLAN-F1

Status: fixed.

Controller adjudication: accept both re-review conclusions. The plan now makes `dayu.contracts` the canonical owner of `ToolBundleSourceKind` / `ToolBundleSourceRef`, keeps Host public surface preservation limited to exporting the same canonical contract, and removes the contradictory stop condition that previously made this migration ambiguous.

Rationale: this is the best current-phase design because `source_refs` are shared ToolBundle provenance contracts, not Host lifecycle semantics, so their canonical ownership belongs below Host while Host behavior and public interface remain stable.

### P12-PLAN-F2

Status: fixed.

Controller adjudication: accept both re-review conclusions. The plan now specifies a concrete `execution_profiles.json` schema sketch, typed config view shape, scene hint override mapping, and the requirement that Service maps all resolved fragments into complete `RunnerSpec`, `RunnerCallOptions`, and `AgentPolicy` values before calling Host.

Rationale: this keeps ConfigLoader layer-neutral and prevents Host from receiving profile fragments or patch dictionaries, while still giving implementation agents a concrete schema target.

### P12-PLAN-F3

Status: fixed.

Controller adjudication: accept both re-review conclusions. The plan now constrains Phase 12 `context_slots` to string-only values, typed as `Mapping[str, str]`, with deterministic `{{slot_name}}` replacement and fail-fast behavior for missing required slots, unknown placeholders, non-string values, and unresolved placeholders.

Rationale: this keeps ScenePrepare as the owner of scene interpretation and prompt assembly without introducing a template language, callback renderer, or structured slot semantics before there is a concrete need.

## New Blocking Findings

None.

## Non-Blocking Follow-Up

- `execution_profiles.json` implementation should apply the same single-inheritance discipline to profile `extends` that scene manifests use.
- Tool and fragment digest implementation must use canonical content inputs only, not callable identity or filesystem path spelling.
- Fragment path handling should use resolved-path containment checks so prompt assets cannot escape the configured asset root through symlinks.

These points are already represented in the plan and do not block entering the accepted plan gate.

## Gate Decision

The Phase 12 plan re-review gate is accepted. Proceed to accepted plan local commit, then enter Phase 12 implementation gate after the required phaseflow confirmation point.
