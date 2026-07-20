# WU-SEMANTIC-OWNERSHIP-01 P3-H goal confirmation

## Work unit

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Type: semantic ownership bug-fix sub WU under the umbrella semantic ownership WU.
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Review source: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`

## First-principles judgment

The motivation is valid. The accepted P3-H findings are not wording-style requests; they identify user-facing or LLM-facing instructions being produced by modules whose primary ownership is provider execution, downloader adaptation, runtime orchestration, or wait-state mapping. That creates multiple owners for the same visible semantics and makes later projection, memory, trace, and CLI behavior depend on low-level implementation wording.

The correct fix boundary is not to delete useful messages. The fix must keep machine facts and typed action/status facts at the producer boundary, then generate LLM-facing instructions and user-visible copy at the tool projection, direct event projection, CLI/service, or prompt/schema owner boundary.

## Owner boundary

- Web provider internals may own search rows, preferred result selection, and machine action facts such as `fetch_web_page` plus arguments. They must not own prose instructions telling the model what to do next.
- Web tool declaration/projection owns LLM-facing tool descriptions, display names, cancellation result wording, and search-result guidance assembled from provider facts.
- Fins ingestion runtime owns ingestion execution facts and direct-stream business events. It must not become a general UI copy registry outside the direct event contract.
- Fins direct event/projection boundary owns reusable direct-stream user-visible labels, titles, and bounded messages shared by Service/CLI and direct runtime.
- Fins wait adapter owns mapping observation snapshots into Host wait outcomes. It may carry typed status/failure facts but must not hardcode product recovery hints unless those hints come from a projection helper with the same Fins direct/wait visible-language owner.
- SEC downloader owns HTTP/SEC adapter diagnostics. CLI command names belong to CLI/user-facing setup documentation, not downloader warnings.
- Host ToolRuntime DS12 hidden hint protocol is already closed by P3-E in current code: direct source scan found no `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, no `_hint_with_diagnostic_refs`, and no `hint=policy_decision.reason_code`. Current `diagnostic_refs` uses typed fields rather than a hidden `hint` subprotocol.

## Direct code evidence

- `dayu/tools/web/web_search_providers.py` builds `preferred_result_summary`, `next_action`, `next_action_args`, and a prose `hint` inside provider code.
- `dayu/tools/web/web_tools.py` owns `search_web` / `fetch_web_page` declarations, display names, cancellation outcomes, and existing web recovery hint helpers.
- `dayu/fins/ingestion_runtime.py` emits direct-stream progress/result text such as download/preprocess/upload preparation, failure titles, success titles, cancellation text, and fallback error text.
- `dayu/fins/direct_events.py` already defines the shared Fins direct event contract and validates user-visible bounded text, making it the natural owner for reusable direct event copy/projection helpers.
- `dayu/fins/ingestion/wait_adapter.py` hardcodes failed/cancelled recovery hints in Host wait outcome mapping.
- `dayu/fins/downloaders/sec_downloader.py` warns about missing SEC User-Agent and names `dayu-cli init` inside the downloader adapter.

## Success signals

- Provider/downloader/low-level adapter modules no longer hardcode LLM next-step prose, CLI command names, or ad hoc UI copy outside their owner boundary.
- Web search still returns enough structured facts for the LLM/tool projection layer to choose `fetch_web_page` or query refinement without guessing.
- Fins direct and wait visible text derives from a shared Fins projection/copy helper or typed direct event contract rather than duplicate literals in runtime and wait adapter code.
- Tool schema and LLM-facing text remain self-explanatory, with no internal Host/Engine/adapter terminology leaked as business facts.
- Affected tests and pyright pass; source scans prove the accepted P3-H literal/protocol leaks are removed or explicitly closed as evidence-invalid.

## Non-goals

- Do not redesign the Fins direct event schema unless the plan proves a current contract bug that cannot be fixed by projection helpers.
- Do not migrate durable Host EventLog, memory, trace, or wait schemas in P3-H.
- Do not change SEC download behavior, provider selection, retry behavior, or cancellation state machines.
- Do not remove useful user-visible messages from CLI/direct output; move ownership or centralize projection instead.
- Do not reopen DS12 Host ToolRuntime hidden hint protocol unless new direct code evidence shows it still exists.

## Current gate decision

Goal confirmation is accepted. Enter plan gate for P3-H. AgentCodex should produce a code-generation-ready plan with small implementation slices and explicit source-scan, tests, README, and propagation-audit criteria.
