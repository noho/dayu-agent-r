# WU-CM-01-F02 Slice 6 Re-review Controller Adjudication

## Gate

- gate: re-review adjudication
- work unit: WU-CM-01-F02 Compact Evidence Query Readability Quality Closeout
- slice: Slice 6 Compactor Prompt Semantic Rewrite
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- status: accepted-with-residual

## Inputs

- implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice6-implementation-codex.md`
- code review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-slice6-code-review-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-slice6-code-review-ds.md`
- fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice6-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-slice6-rereview-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-slice6-rereview-ds.md`
- plan source: `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 6

## Code Review Adjudication

AgentMiMo verdict: PASS. No blocking findings.

AgentDS verdict: PASS with findings. Controller adjudication:

- DS Finding 1: accepted as real residual, not accepted as Slice 6 prompt-text fix. Runtime `instruction.output_schema_name = "ConversationCompactOutputVNext"` is LLM-facing material JSON and still exposes a Python type name. Fixing it requires changing Host production compact instruction literal / validation outside Slice 6 allowed files. This must be tracked as a production contract rescope residual before final public smoke acceptance.
- DS Finding 2: accepted fix. The prompt retention rule used `应为`, which weakens an evidence-backed fact constraint. Required fix is strong wording with `必须`.
- DS Finding 3: non-blocking maintenance risk. Generic forbidden terms such as `digest` / `cursor` / `policy` may create future false positives, but they guard the current internal-term stop condition and do not block this slice.

## Fix Verification

AgentCodex fixed DS Finding 2:

- `conversation_compaction_user.md` now says: `必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。`
- `test_public_compact_smoke.py` now asserts the strong wording appears in the real default compactor prompt assembly and the weaker `应为每个确实需要保留的 evidence label` wording does not.

AgentMiMo re-review verdict: PASS. DS Finding 2 fixed; Finding 1 intentionally deferred; Finding 3 remains non-blocking.

AgentDS re-review verdict: PASS. DS Finding 2 fixed; no new blockage or regression.

## Validation

Controller validation after fix:

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py`
  - result: 6 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - result: 0 errors
- `git diff --check`
  - result: passed

AgentCodex and re-review agents also ran focused validation with the same passing results recorded in their artifacts.

## Decision

Slice 6 prompt-template implementation and accepted prompt wording fix are accepted.

Active residual to track in `docs/host/issues-implementation-control.md`:

- `WU-CM-01-F02-S6-R1`: runtime compact material JSON still exposes `ConversationCompactOutputVNext` through `instruction.output_schema_name`. This is outside Slice 6 prompt asset allowed files, but it is LLM-facing and must be resolved by a production compact instruction contract rescope before final WU-CM-01-F01 public smoke acceptance.

