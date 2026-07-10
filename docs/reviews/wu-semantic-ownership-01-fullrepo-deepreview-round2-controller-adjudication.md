# WU-SEMANTIC-OWNERSHIP-01 full-repo deepreview round 2 controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Gate: post P2-E full-repository deepreview controller adjudication
- Source artifacts:
  - `docs/reviews/repo-review-20260710-092911.md` (AgentCodex)
  - `docs/reviews/repo-review-20260710-091608.md` (AgentDS)
  - `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` (AgentMiMo)
- Raw finding count:
  - AgentCodex: 12 enumerated findings
  - AgentDS: 22 enumerated findings
  - AgentMiMo: 41 enumerated findings by section heading. The artifact conclusion says 31, but the controller uses the explicit headings as the traceable count.
  - Total raw findings: 75

This document deduplicates those 75 raw findings into owner-boundary sub work units. It does not close the umbrella WU and does not implement fixes.

## First-principles controller judgment

The motivation is valid. The high-signal findings are not style preferences: they identify business or governance facts being produced, parsed, guessed, reformatted, or reclassified by multiple owners. That violates the project requirement that durable state, trace, memory, audit, UI output, LLM-facing material, and tool schemas derive the same business fact from a single source of truth.

The fix boundary is not "make every reviewer line disappear." Each accepted fix must land where the fact is first produced, validated, persisted, or projected. Findings that only describe future architecture preference, or whose direct evidence conflicts with current design truth, are rejected or deferred with owner.

## Controller disposition summary

| Disposition | Count | Meaning |
| --- | ---: | --- |
| accepted groups | 11 | Fix inside this umbrella WU as P3 sub WUs. |
| deferred / rejected bucket | 1 | Not an immediate fix target; retained with reason below. |
| raw findings represented | 75 | Raw review findings before deduplication. |

## Accepted sub WUs

### P3-A - Host lifecycle, run status, and terminal event source of truth

Sources:

- AgentCodex 12
- AgentDS 1, 9, 10, 11, 17
- AgentMiMo SM-1, SM-2, SM-3, SM-4, SM-5, SM-7, SM-8

Owner boundary:

- Host durable state and `dayu.host.lifecycle_events` own Run / Attempt terminal status, lifecycle event type, terminal event sets, and lifecycle closeout predicates.

Accepted scope:

- Remove duplicate terminal run status/event type sets and duplicate lifecycle mappings.
- Make SQL active/non-terminal filters derive from the same status truth where feasible.
- Replace terminal detection based on nullable terminal event fields with status-owned predicates.
- Ensure worker lifecycle closeout and cancel late-result classification do not depend on synthetic Engine event semantics.

Non-goals:

- Do not redesign all EventLog event types in this sub WU.
- Do not introduce a broad schema migration unless direct code evidence shows the P3-A fix cannot be correct without it.

### P3-B - Terminal final answer projection and Outbox continuity

Sources:

- AgentCodex 1
- AgentMiMo DS-2, DS-4

Owner boundary:

- Host terminal answer continuity resolver owns assistant final answer text. Outbox, memory, compact material, run input, and read APIs must project from the same resolver/helper instead of reading terminal payload shapes independently.

Accepted scope:

- Make succeeded Outbox terminal items derive final answer from the same descriptor-aware resolver as terminal continuity.
- Collapse inline-only final answer readers into one policy-driven resolver.
- Add propagation tests covering final answer production, terminal descriptor persistence, EventLog refs, Outbox read model, memory/run-input material, and failed/cancelled/lost negatives.

### P3-C - Context compaction payload, evidence text, and LLM-safe projection contract

Sources:

- AgentDS 6, 14, 16, 22
- AgentMiMo DS-1, DS-5, DS-6, DS-7, DS-8

Owner boundary:

- Context compact accepted payload and accepted tool evidence projection own the typed compact/evidence facts. Memory, compact material, run input, and LLM-facing renderers must consume one projection contract.

Accepted scope:

- Centralize `CONTEXT_COMPACTED` payload parsing and field names.
- Centralize LLM-facing accepted evidence text rendering and unavailable-text fallback.
- Remove repeated evidence envelope exception handling and repeated payload text accessors.
- Move post-compact budget estimation to the context budget owner if direct code inspection confirms it is a pure estimator.
- Validate compact-produced forward intent / reference continuity enum-like values at projection boundary.

### P3-D - Engine provider protocol normalization

Sources:

- AgentCodex 4, 5
- AgentDS 2, 4, 21
- AgentMiMo BI-7

Owner boundary:

- Runner adapters own provider wire normalization, fatal protocol errors, non-fatal diagnostics, provider choices, finish reasons, context-overflow detection, and Engine error code semantics before Agent or Host sees them.

Accepted scope:

- Split fatal provider protocol error from non-fatal provider diagnostic/warning events.
- Define one stream/non-stream choice policy for multi-choice responses.
- Stop silently treating unknown wire `finish_reason` as `STOP`.
- Type known Engine error codes while preserving a deliberate extension path for provider-specific runner codes.
- Keep context-overflow string fallback as adapter diagnostic fallback only; do not let it become hidden business truth.

### P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts

Sources:

- AgentCodex 8, 9, 10
- AgentDS 12, 13
- AgentMiMo DS-3, SS-5, BI-8

Owner boundary:

- Tool result contracts, Host accept barrier, wait adapter/callback contracts, and Fins runtime stream protocol own result status and provider identity. Downstream projection, CLI, and callback parsing may validate transport input but must not reconstruct or fabricate those facts.

Accepted scope:

- Enforce `ToolResultSuccess.ok is True` and `ToolResultFailure.ok is False` at contract construction.
- Make missing or duplicate Fins direct `RESULT` a typed protocol error, not a manufactured business failure result.
- Reject bare string `provider_status_ref` in the generic callback endpoint unless an owner-provided resolver exists.
- Remove fallback status reconstruction from raw outcome JSON where structured accepted result status is required.
- Separate governance reason and diagnostic refs from LLM-facing `hint` text if direct code inspection confirms the hidden string protocol is still present.

### P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership

Sources:

- AgentCodex 3, 6
- AgentDS 15, 19
- AgentMiMo SM-6

Owner boundary:

- Fins source document repository owns source document existence, ingestion completeness, source provider/provenance, file membership, and document freshness. Tool citation builders and wait adapters must consume that typed repository truth.

Accepted scope:

- Prevent blob writes from creating source documents the source repository does not acknowledge, or introduce an explicit staging source contract.
- Make citation `source_type` / provider derive from repository provenance, never from `document_id` prefix.
- Use wait record deadline/expiry truth instead of Fins adapter hardcoded transient pending age where applicable.
- Define stale/refresh semantics for company metadata if direct code inspection confirms stale data can be reused indefinitely.

### P3-G - Fins form/domain typed rules and processor result contracts

Sources:

- AgentCodex 11
- AgentDS 7, 8
- AgentMiMo BI-1, SS-10

Owner boundary:

- Fins domain/pipeline contracts own SEC form normalization, fiscal period, document quality, financial-report filtering, rejection registry shape, and processor result validity.

Accepted scope:

- Consolidate SEC form type normalization into one domain helper or enum-backed parser.
- Type or validate `fiscal_period`, `form_type`, and `quality` at domain boundaries without adding compatibility shims.
- Move product-level financial-report filtering and fiscal inference out of HTTP downloader adapters into domain/pipeline-owned helpers.
- Stop read runtime from recomputing required XBRL `total` in a way that hides processor contract violations.

### P3-H - LLM-facing and UI-copy boundary cleanup

Sources:

- AgentDS 12
- AgentMiMo BI-2, BI-3, BI-4, BI-5, BI-6

Owner boundary:

- Business prompt/tool projection boundaries own LLM-facing instructions and user-visible copy. Runtime, provider, downloader, and low-level adapter modules may carry machine facts, not product instructions disguised as internal diagnostics.

Accepted scope:

- Move web search LLM next-action instructions out of provider internals.
- Remove UI copy from ingestion runtime and web tool runtime where it is not the UI/projection owner.
- Remove Fins wait adapter LLM-facing hints from adapter-owned machine state.
- Remove CLI command names from SEC downloader diagnostics or route them through the CLI/user-facing owner.

### P3-I - Public CLI/package entrypoints and terminal display watermark

Sources:

- AgentCodex 2, 7

Owner boundary:

- Packaging entrypoints and public README own declared commands; CLI display delivery owns terminal cursor/watermark advancement, independent of Host run success/failure.

Accepted scope:

- Either restore missing public `dayu-web`, `dayu-wechat`, `dayu-render` modules with smoke coverage, or remove scripts/docs for capabilities that are not currently shipped.
- Advance CLI terminal cursor after terminal render succeeds, even when the terminal Run status is failed/cancelled/lost, while keeping command exit status separate.

### P3-J - Host durable schema and weak-contract hardening backlog

Sources:

- AgentDS 5, 20
- AgentMiMo SS-1, SS-2, SS-3, SS-4, SS-6, SS-7, SS-8, SS-9, SS-11, SS-12

Owner boundary:

- Host durable schema, durable row decoders, and public durable contracts own closed sets, row shapes, read-model freshness, and legacy-data rejection.

Accepted scope:

- Add typed contracts and/or CHECK constraints for high-value naked string fields where the code owner can prove the legal set.
- Improve read model and memory snapshot freshness detection where stale projection can affect LLM input or public read output.
- Remove ownerless legacy config exposure or give it an explicit deletion owner and condition.

Execution note:

- This is intentionally not first in P3 because it can turn into broad schema churn. Each slice must start with a root-cause confirmation and avoid a whole-store migration unless the specific field requires it.

### P3-K - Test harness semantic coupling cleanup

Sources:

- AgentMiMo TF-1, TF-2, TF-3, TF-4, TF-5

Owner boundary:

- Production contracts own semantics; tests should verify public/owner-level behavior and should not become a parallel schema registry through raw SQL, exact field-set locks, or exact LLM text locks unless that exact shape is the public contract.

Accepted scope:

- Replace brittle exact field-set assertions with owner-level contract assertions where exact closed sets are not the public promise.
- Reduce raw SQL helper coupling where production query helpers already exist.
- Consolidate cancellation fakes behind one protocol-faithful test helper.
- Keep LLM-facing text tests focused on required semantic content unless exact wording is the contract.

## Deferred or rejected source findings

### DR-1 - Host importing Engine public function entrypoints

Sources:

- AgentDS 3
- AgentDS 18, partially related future runner assembly concern

Disposition:

- `AgentDS 3` is rejected-with-reason as stated. The Host design truth explicitly defines Host -> Engine as the allowed dependency direction, and Engine public entrypoints are exported from `dayu.engine`. Direct import of `run_agent_messages` / `run_agent_and_wait` from the package root is not by itself a reverse dependency or owner-boundary violation.
- `AgentDS 18` is deferred-with-owner to a future multi-runner/provider assembly WU. Current Engine design says the OpenAI-compatible default runner is the current implementation path. A broader runner factory/registry would be architectural expansion, not a semantic ownership bug proven by the current review.

Residual risk:

- If future design introduces multiple concrete runner implementations, runner selection should be moved to a typed assembly boundary. That is not a P3 immediate fix.

## Recommended execution order

1. P3-A Host lifecycle, run status, and terminal event source of truth.
2. P3-B Terminal final answer projection and Outbox continuity.
3. P3-C Context compaction payload, evidence text, and LLM-safe projection contract.
4. P3-D Engine provider protocol normalization.
5. P3-E Tool result, accepted status, wait callback, and Fins direct stream contracts.
6. P3-F Fins source document, blob, provenance, citation, and wait timeout ownership.
7. P3-G Fins form/domain typed rules and processor result contracts.
8. P3-H LLM-facing and UI-copy boundary cleanup.
9. P3-I Public CLI/package entrypoints and terminal display watermark.
10. P3-J Host durable schema and weak-contract hardening backlog.
11. P3-K Test harness semantic coupling cleanup.

This order keeps durable lifecycle correctness and LLM-visible fact continuity ahead of broader schema hardening and test cleanup. It also keeps sub WUs aligned to owner boundaries rather than reviewer ownership or file count.

## Next entry point

Enter `WU-SEMANTIC-OWNERSHIP-01 P3-A` at plan gate. AgentCodex should produce a code-generation-ready plan for P3-A only. AgentMiMo and AgentDS should then review that plan before implementation.
