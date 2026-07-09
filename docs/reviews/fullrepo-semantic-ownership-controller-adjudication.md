# Full-repo semantic ownership review — controller adjudication

## Scope

- Source reviews:
  - `docs/reviews/fullrepo-semantic-ownership-review-mimo.md`
  - `docs/reviews/fullrepo-semantic-ownership-review-ds.md`
- Review mode: whole-repository semantic ownership review using `AGENTS.md` / `CLAUDE.md` "语义所有权与修复边界".
- Controller role: de-duplicate findings, classify owner boundaries, and group fix candidates into coherent work units. This document does not implement fixes.

## Severity Summary

| Source | High | Medium | Low | Total |
| --- | ---: | ---: | ---: | ---: |
| AgentMiMo | 5 | 7 | 0 | 12 |
| AgentDS | 4 | 8 | 0 | 12 |
| Controller accepted | 8 | 13 | 0 | 21 |

Three review findings were merged into broader owner-boundary groups:

- MiMo 03 and DS 07 are one Host evidence/query projection problem.
- DS 01 and DS 09 are one Fins preprocess result contract problem.
- MiMo 07 and part of MiMo 03 are one accepted tool result envelope/status/query contract problem.

## Priority Work Units

### P0 — Engine runner authority and terminal durable correctness

Accepted findings:

- MiMo 01: `finish_reason` has two competing sources. Runner emits content-completed and done events with potentially different finish reasons; Agent currently keeps the earlier value.
- MiMo 02: usage events are not aggregated at Runner boundary and lose `provider_request_id`; Host persists incomplete usage facts.

Owner boundary:

- Runner contracts own provider-response normalization. Agent and Host must consume a single normalized final authority, not arbitrate provider stream fragments.

Why this is P0:

- These facts enter durable terminal closeout and usage diagnostics. Incorrect values are durable-state correctness issues, not display issues.

Expected fix shape:

- Make `RunnerDoneData.finish_reason` the sole authority or remove `finish_reason` from intermediate content-completed signals.
- Aggregate streaming usage into a single normalized usage fact with request identity before Agent/Host ingestion.

### P0 — Fins ingestion typed result contracts

Accepted findings:

- DS 01: `FinsPreprocessResultSummary.skipped_count` includes `not_supported` while `skipped_document_ids` excludes it.
- DS 02: upload pipeline returns loose `dict[str, JsonValue]`; runtime consumers parse with fallback helpers.
- DS 09: preprocess success/failure rule is duplicated in direct-stream and job paths.
- DS 12: `ingest_method` is a string flag hardcoded across modules.

Owner boundary:

- Fins domain/result contracts own operation result semantics. CLI, tools, wait adapter, and runtime should render typed facts, not parse loose dictionaries or re-create result rules.

Why this is P0:

- The recent ATAT issue was exactly a result-summary owner-boundary error. These findings show the same class remains in preprocess/upload/source classification.

Expected fix shape:

- Add typed result contracts for upload/preprocess and source classification.
- Make counts internally consistent and expose domain methods for success/failure.
- Replace ad hoc string flags with typed contract values at storage/pipeline boundaries.

### P1 — Host accepted tool evidence/query/status contract

Accepted findings:

- MiMo 03: tool request query text is independently back-queried by tool trace, durable memory, and memory rendering.
- MiMo 07: tool result status is independently inferred by tool trace and read API from overlapping fields.
- DS 07: readable evidence source text mixes internal refs with business text, then consumers filter by blacklist.
- DS 08: tool schema descriptions promise output details independently from the wait adapter's actual generic `{title, details}` result shape.

Owner boundary:

- `TOOL_CALL_REQUESTED`, accepted evidence envelope, and `TOOL_RESULT_ACCEPTED` should carry one typed LLM-safe request/result/status contract. Trace, memory, run input, read API, and prompt-facing materials should project from it.

Why this is P1:

- This area was improved in the latest fix, but reviewers found remaining repeated back-query and independent status inference. It is not currently known to corrupt durable state, but it creates drift risk across trace/memory/read API.

Expected fix shape:

- Add typed query/status/readable-source fields to accepted evidence/result material where appropriate.
- Keep digest/ref anchors, but do not require every consumer to re-read EventLog and re-validate the same envelope.
- Split business-readable source categories from internal refs.

### P1 — Host event and cancellation durable contract

Accepted findings:

- MiMo 04: terminal event type strings are duplicated across 11+ production modules.
- MiMo 06: outbox terminal status set and terminal event type set disagree on `RUN_LOST`.
- MiMo 10: `cancel_request_event_id` lives only in `RUN_CANCELLING` payload JSON, with loose parsing and no durable indexed state.

Owner boundary:

- Host durable state contracts own event types, terminal lifecycle sets, and cancellation linkage. Projections should not define private copies or parse critical links from payload JSON.

Expected fix shape:

- Introduce a public `HostEventType` / terminal event contract.
- Align outbox terminal status/event sets with actual item production.
- Move cancellation request linkage into typed durable state or a typed indexed relation.

### P1 — LLM-facing governance leakage and compaction schema ownership

Accepted findings:

- DS 04: Fins ingestion tool text still exposes "等待工具结果", "等待状态", "后续调度".
- DS 05: compaction `evidence_kind` asks the LLM to classify internal evidence pipeline stages.
- DS 06: compaction `trace_kind=user_visible_run_state` exposes run-state governance concepts.
- MiMo 11: runtime `host_cancelled_outcome()` contains Host-governance LLM-facing default text in a layer-neutral package.

Owner boundary:

- Host/tool/runtime may hold governance facts, but LLM-facing text must be produced at the business projection boundary and must not require the model to understand Host/Engine lifecycle.

Expected fix shape:

- Remove governance terms from tool schema/errors/hints.
- Pre-classify evidence/trace kinds in Host where possible; do not require LLM to classify internal pipeline stages.
- Make runtime helper text caller-supplied, not layer-owned.

### P2 — CLI/service boundary consistency

Accepted findings:

- DS 03: `session resume` imports private functions from prompt/interactive modules.
- DS 10: CLI duplicates Service `_ensure_result_event` missing-result fallback.
- DS 11: `HostApiError` formatting/exit-code handling differs across prompt/interactive/session.

Owner boundary:

- Service or a public CLI command contract should own shared command execution and error semantics. CLI modules should not import each other's private helpers or reconstruct service-layer result events.

Expected fix shape:

- Promote shared prompt/interactive-on-session execution to a public service/CLI helper.
- Make missing direct RESULT a hard contract violation outside service, not a CLI fallback.
- Centralize `HostApiError` formatting and exit-code mapping.

### P2 — Host memory/test contract hardening

Accepted findings:

- MiMo 08: memory projection mutates EventLog payload to hydrate final-answer fallback from artifacts.
- MiMo 09: import-boundary tests miss relative imports.
- MiMo 12: memory snapshot construction is scattered across tests, with `"pending"` digest sentinel patterns and no cross-path equivalence test.

Owner boundary:

- Durable facts should be complete at ingest time. Test fixtures should exercise the same public constructors and boundary checks as production code.

Expected fix shape:

- Move final-answer text resolution into ingest-time committed facts or a shared typed resolver.
- Extend import-boundary AST scanning to relative imports.
- Add shared memory snapshot fixture factories and cross-path equivalence tests.

### P2 — Config fallback prompt source of truth

Accepted finding:

- MiMo 05: Runtime config and Engine `AgentPolicy` define different default fallback prompts.

Owner boundary:

- Execution profile config should own fallback/continuation prompt defaults. Engine policy should receive resolved values, not define independent text defaults.

Expected fix shape:

- Make fallback/continuation prompt fields explicit or inject from config loader at assembly boundaries.

## Findings Requiring Extra Evidence Before Fix

None of the 24 source findings are rejected. The following need a short root-cause confirmation before implementation because the fix touches schema or migration boundaries:

- MiMo 03 / MiMo 07 accepted evidence query/status material: confirm whether to extend envelope schema or add a sibling accepted-result projection atom.
- MiMo 10 cancellation request linkage: confirm schema migration policy for existing workspaces.
- DS 05 / DS 06 compaction schema: confirm whether existing compacted memory artifacts can be treated as new-schema-only.

## Recommended Execution Order

1. P0-A: Engine runner finish reason and usage authority.
2. P0-B: Fins preprocess/upload typed result contracts.
3. P1-A: Host accepted evidence/query/status typed projection contract.
4. P1-B: Host event type and cancellation durable contract.
5. P1-C: LLM-facing governance leakage cleanup.
6. P2-A: CLI/service boundary consistency.
7. P2-B: Memory/test contract hardening.
8. P2-C: Config fallback prompt source of truth.

This order keeps high-risk durable-state correctness ahead of text cleanup and test hardening, while grouping related owner boundaries together.

## Deferred Backlog Entry

Controller disposition on 2026-07-09:

- These findings are accepted as backlog, but they are not the active implementation lane now.
- The active lane remains WU-CLI-SMOKE-01 real-environment validation and closeout.
- Do not start fixes from this review until WU-CLI-SMOKE-01 is manually revalidated and the user explicitly resumes this review backlog.
- When resumed, use the `Recommended Execution Order` above as the推进优先级. Start at P0-A unless a fresher root-cause check shows a different high-severity durable correctness blocker.
- Each resumed item must still pass normal phaseflow gates: inspect current code, confirm root cause from direct evidence, update design truth if the fix changes public contracts or durable semantics, implement, verify, review, and only then close the item.

## Review Artifacts

- MiMo artifact: `docs/reviews/fullrepo-semantic-ownership-review-mimo.md`
- DS artifact: `docs/reviews/fullrepo-semantic-ownership-review-ds.md`
