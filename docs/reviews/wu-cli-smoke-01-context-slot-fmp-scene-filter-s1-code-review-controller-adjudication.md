# WU-CLI-SMOKE-01 S1 Code Review Controller Adjudication

## Metadata

- Gate: S1 code review
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Slice: S1 — ScenePrepare condition blocks and prompt exposure surface
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-code-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-code-review-ds.md`

## Decision

Accepted. No current fix gate is required for S1.

AgentMiMo concluded `pass-with-findings` with two low-severity findings. AgentDS concluded `pass` with one low-severity non-blocking finding. None of the findings indicates a correctness defect in S1's implemented behavior or a blocker to accepting the slice.

## Finding Adjudication

- MiMo 001 — infer no longer selects download/preprocess/get_current_time: accepted as expected S1 behavior. The fixed plan explicitly narrows non-interactive scenes away from long-transaction and utility time tools unless a scene has a current-time slot need. No current code change required.
- MiMo 002 — interactive missing-slot test now expects `base_user` rather than `fins_default_subject`: accepted as expected test correction. The current manifest has already removed `fins_default_subject` from interactive/wechat; full `base_user` removal belongs to later slices.
- DS 01 — empty fragment discard / final empty-line normalization not implemented in S1: accepted as deferred to later slice. S1 did not implement context-slot empty-line cleanup by design; later context-slot work owns optional placeholder-line removal and final prompt whitespace normalization.

## Controller Validation

Controller reran the required S1 validation:

- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py` — 58 passed.
- `pytest tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py` — 6 passed, with unrelated third-party `edgar` deprecation warnings.
- `pyright` — 0 errors, 0 warnings, 0 informations.
- `git diff --check` — passed.

## Residual Risks

- Real LLM prompt inspection is not covered in S1; prepared prompt assertions cover the deterministic scene assembly surface. Later smoke validation remains responsible for real-provider behavior.
- Empty context-slot line cleanup and final prompt whitespace normalization remain owned by later context-slot slices.
- Upload exposure remains unchanged and deferred to separate user裁决.

## Next Entry Point

Create the accepted S1 slice commit, then continue to implementation Slice S2 from the accepted plan.
