# Phase 12.1 Plan Review Controller Adjudication 2026-05-21

## Inputs

- Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`
- MiMo review: `docs/reviews/phase12-1-plan-review-mimo-20260521.md`
- DS review: `docs/reviews/phase12-1-plan-review-ds-20260521.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

Plan review accepted. Both independent reviewers returned PASS with no blocking findings. The plan is implementation-ready for Phase 12.1.

## Findings Adjudication

### Accepted As Implementation Constraints

- MiMo O-1 / DS O-1: Slice 1 has a wide file surface. Accepted as an implementation artifact requirement. Slice 1 implementation must first record the call-site audit for removed policy fields and list expected file-level diff summaries before coding.
- MiMo O-2 / DS O-2: effective `ToolTruncateSpec` default-fill helper placement is underdetermined. Accepted as a binding placement constraint. If the helper only consumes `ToolTruncateSpec` from `dayu.contracts` plus policy default values, it belongs in `dayu.runtime`; it must not import Host or Engine. If implementation discovers it needs Host internals, the worker must stop and report a design mismatch rather than placing it in Host ad hoc.
- MiMo O-4 / DS O-4: smoke-private composition helpers need named future extraction targets. Accepted as an implementation artifact requirement. Slice 4 / Slice 5 artifacts must list private helper names and suggested future Service / Engine extraction targets.
- MiMo O-5 / DS O-5: old model migration source must be verified before migration. Accepted as a Slice 2 preflight requirement. The implementation artifact must record whether the referenced source is accessible and must map every migrated model.
- DS O-6: ConfigLoader `extends` validation should include missing, circular, self-reference and valid chained cases. Accepted as a Slice 2 focused-test requirement.

### Accepted As Non-Blocking Notes

- MiMo O-3 / DS O-3: concrete `MemoryProjectionPolicy` ratio/floor/cap field names must be checked against design truth during implementation. This is already covered by Slice 1 review and pyright; no plan fix is required.
- MiMo O-6: the plan artifact is untracked and belongs to plan acceptance, not implementation slices. Accepted as controller bookkeeping.

## Rationale

The findings improve implementation discipline but do not alter Phase 12.1 architecture, slice order, public contract boundary, or test strategy. Based on the design goal of keeping runtime assembly outside Host truth while making typed public contracts sufficient for Service-like assembly, the current plan is strong enough to enter implementation with the accepted constraints above.

## Next Gate

Proceed to Phase 12.1 implementation Slice 1 through `$init-agents` routing. The controller must include the accepted constraints above in the Slice 1 handoff.
