# WU-TOOLS-01-F01-02 Slice 5 Closeout Review Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F01-02`
- Gate: Slice 5 closeout code review adjudication
- Design source: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-02-slice5-closeout-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-slice5-closeout-review-ds.md`
- Date: 2026-06-08

## Controller Decision

Slice 5 closeout review is accepted with one narrow test guard fix before the accepted slice commit.

Both reviewers independently verified that Slice 5 is test-only, covers the intended audit matrix, keeps LLM-facing schemas free of Host governance fields, and leaves the awaiting accept two-phase startup question deferred rather than expanding Host wait adapter or Fins runtime contracts in this WU.

## Findings

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| S5-F1 Fins awaiting schema test lacks explicit property/required assertions for `execution_context` and `cancellation_token` | AgentDS | accepted | The current JSON text check is indirectly protective, but explicit `parameters.properties` and `parameters.required` assertions match Web, Doc, and Fins read guards and reduce LLM-facing schema regression risk with minimal scope. |
| S5-F2 `_is_runtime_start_call` TypeGuard is semantically broader than its predicate | AgentMiMo | rejected-with-reason | This is a test-local style issue. The only caller depends only on `ast.Call` narrowing, so it does not weaken the cancellation bridge guard or production behavior. |

## Required Fix

AgentCodex must update only `tests/fins/test_fins_ingestion_tools.py` to make `test_ingestion_tool_schemas_hide_host_internal_fields` explicitly assert that `execution_context` and `cancellation_token` are absent from both schema properties and required fields for the Fins awaiting tools.

Expected fix artifact: `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md`.

Required validation:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q`
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`

## Residual Risk

No new residual risk is introduced by this adjudication. The already identified risks remain deferred with owner/destination in the closeout artifact:

- Awaiting accept two-phase startup and orphan job window: deferred to WU-WAIT-03 or an independent follow-up requiring design-source update.
- Non-preemptible synchronous I/O or processor internals: accepted limitation for this WU, to be handled by provider-specific runtime owners when needed.
- Legacy adapter `tool_cancelled` failed-outcome projection: deferred to a separate adapter cancellation contract WU.
