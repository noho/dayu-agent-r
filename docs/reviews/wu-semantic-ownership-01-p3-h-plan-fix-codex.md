# WU-SEMANTIC-OWNERSHIP-01 P3-H plan fix report

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Gate: plan-fix only
- Agent: AgentCodex
- Target plan: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-controller-adjudication.md`

## Fixed items

- `P3-H-PF-01`: Added a concrete Fins propagation-path table that separates direct progress/result stream, wait resolution, direct-event-derived tool output, job event sidecar, and log/internal diagnostics. Job sidecar text is explicitly out of P3-H unless direct evidence shows projection into `FinsEvent`, wait outcome, tool result, memory, or trace.
- `P3-H-PF-02`: Expanded Web and Fins scan patterns to include preferred summary builders/fragments, direct-stream titles/messages, wait hints, and retained job sidecar evidence. The plan now states scans are evidence checks, not exhaustive proof.
- `P3-H-PF-03`: Specified Web type migration: provider-owned `SearchWebProviderResult`, projection-owned `SearchWebOutput`, `build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput`, and direct import migration for `web_tools.py` and tests.
- `P3-H-PF-04`: Narrowed Web display handling. `display_name` and `description` remain at the `@tool(...)` declaration owner unless duplicate ownership is found; the helper owns cancellation/recovery/search guidance text.
- `P3-H-PF-05`: Chose the replacement path for `web_cancellation_text.py`: move `WEB_CANCELLED_HINT` to `web_tool_projection_text.py`, update imports directly, and delete the old module with no compatibility re-export.
- `P3-H-PF-06`: Specified `direct_event_text.py` API boundary as typed text constants and small lookup functions only. It must not import or construct `FinsEvent`, `FinsResultSummary`, or `FinsProgress`.

## Changed files

- `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- `docs/reviews/wu-semantic-ownership-01-p3-h-plan-fix-codex.md`

## Validation

- `git diff --check -- docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md docs/reviews/wu-semantic-ownership-01-p3-h-plan-fix-codex.md`: pass.
- `git diff --check --no-index /dev/null docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`: no whitespace warnings. Command returned `1` because the untracked file differs from `/dev/null`, which is expected for no-index diff.
- `git diff --check --no-index /dev/null docs/reviews/wu-semantic-ownership-01-p3-h-plan-fix-codex.md`: no whitespace warnings. Command returned `1` because the untracked file differs from `/dev/null`, which is expected for no-index diff.

## Blockers

- None.
