# Context Slot Placement Controller Adjudication

## Scope

- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Follow-up: `{{fins_default_subject}}` scene placement fix
- Controller decision date: 2026-07-07
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-context-slot-placement-fix-codex.md`
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-placement-review-ds.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-context-slot-placement-rereview-ds.md`

## Decision

Accepted.

The user correctly identified that `{{fins_default_subject}}` expands to a complete Markdown block:

```markdown
# 当前分析对象
你正在分析的是 V（Visa Inc.）。
```

Placing that placeholder immediately below the scene H1 inserted a second H1 between the execution-contract title and its body. The accepted fix moves the placeholder to the end of each scene that declares `fins_default_subject`, after the main execution contract text.

AgentMiMo and AgentDS both passed the initial review. Controller accepted DS's residual test gap: the source placement invariant did not verify the expanded `system_prompt` structure. AgentCodex added a real `ScenePrepare` expansion test, and both targeted re-reviews passed.

## Validation

Controller re-ran:

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py
# 51 passed

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py
# 41 passed, 3 edgar warnings

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

## Residuals

- Real provider smoke was not rerun for this placement-only fix.
- `test_prepared_fins_default_subject_does_not_interrupt_scene_contract` intentionally uses the prompt scene's current `- 输出 Markdown 格式。` line as a fail-loud anchor. If that prompt rule changes, the test should be updated with the scene text change.
