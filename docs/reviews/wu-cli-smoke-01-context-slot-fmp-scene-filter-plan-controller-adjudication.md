# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Filter Plan Controller Adjudication

## Metadata

- Gate: plan review / fix / re-review
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Controller: AgentController
- Plan artifact: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Initial review artifacts:
  - `docs/reviews/plan-review-20260707-151057.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview2-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-rereview2-ds.md`

## Decision

Accepted. The fixed plan is code-generation-ready and may enter implementation.

Both initial reviews concluded `pass-with-findings` with no blocking finding. AgentCodex updated the plan and produced the fix artifact. AgentMiMo and AgentDS re-reviewed the fixed plan; DS concluded `pass`, while MiMo identified one non-blocking RF-01 clarification. AgentCodex applied the RF-01 follow-up, and both targeted re-reviews concluded `pass`.

## Finding Adjudication

Accepted and fixed:

- MiMo F01: `<when_tag fins>` was too broad for read and ingestion guidance.
- MiMo F02: plan needed to reflect checkpoint commit `2a61fbfd` and avoid removing nonexistent `fins-upload` tag.
- MiMo F03: `base_user` removal scope needed explicit grep coverage across prompts, CLI, tests, and smoke helpers.
- MiMo F04: `<when_tag>` selected tag derivation needed an implementation path.
- MiMo F05: `EntrypointContextSlotRequest` needed concrete fields.
- MiMo F06 / DS-F02: empty slot line cleanup needed precise rules and ordering.
- MiMo F07: tests must assert prepared output has no conditional markers.
- DS-F03: `current_time` needed a fixed LLM-facing text format.
- DS-F04: FMP API key env name needed to be specified as `FMP_API_KEY`.
- DS-F05: Service slot module name needed to converge on `dayu.service.scene_context`.
- DS-F06: `tuple[str, ...]` for aliases needed an immutable public contract rationale.
- DS utilities/time note: `get_current_time` has `utils` and `time` tags; packaged manifests currently select it through `"utils"`.
- DS FMP timeout note: Service slot path must use a short configurable timeout and fall back to ticker-only subject on FMP failure.
- MiMo RF-01: `<when_tag TAG>` remains based on actual selected tools and their catalog tags; the safeguard is precise prompt asset blocks and tests that reject mixed-purpose broad `<when_tag fins>` guidance.

Rejected with reason:

- DS-F01 as written: current `dayu/config/prompts/base/soul.md` does not contain `{{base_user}}`, so it is not a required modification target for `base_user` removal. The broader `base_user` residual scope was accepted through MiMo F03.

## Residual Risks

- Real FMP and LLM smoke depend on external credentials and network; implementation must cover FMP behavior with fake HTTP / monkeypatch tests and treat real smoke as optional environment-supported validation.
- Upload exposure is not widened by this plan. If users want `start_fins_upload` exposed in `interactive` / `wechat`, local file authorization and path-safety UX need a separate product裁决.
- Conditional block nesting remains out of scope. The implementation should fail closed on malformed or nested marker shapes.

## Validation

Controller observed:

- AgentCodex ran `git diff --check` on the fixed plan and fix artifact.
- AgentCodex confirmed no production code or tests were modified during plan/fix gates.
- AgentMiMo and AgentDS targeted re-reviews concluded RF-01 is fixed and reported no blockers.

## Next Entry Point

Proceed to `accepted plan commit`, then implementation Slice S1 from the accepted plan.
