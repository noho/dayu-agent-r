# Phase 12.5 Planning Handoff: Conversation Memory Optimization

## Controller Context

- Work unit: P12.5 Conversation Memory Optimization.
- Branch: `feat/phase-12-5-conversation-memory-optimize`.
- Design source: `docs/host/design.md`.
- Control doc: `docs/host/implementation-control.md`.
- Accepted design checkpoint: `9cfca70 docs: finalize conversation memory continuity decisions`.

Controller role: this artifact is a planning handoff, not an implementation plan. The planning agent must produce a handoff-ready, code-generation-ready plan and must not modify production code or tests.

## Goal

Produce an implementation-ready plan that turns the P12.5 design decisions into small, reviewable implementation slices. The plan must let an implementation agent update Host Conversation Memory so accepted tool evidence can become stable `evidence_backed_facts`, while recent raw turns and minimum preserve items remain continuity mechanisms rather than fact truth.

## Design Decisions Already Frozen

The plan must treat these as fixed decisions:

- Old `verified_facts` must migrate to `evidence_backed_facts` or an equivalent typed view.
- The minimum fact contract is `claim_text + accepted evidence_refs`; Host must not understand source / locator shape or financial business semantics.
- Tool providers do not generate final memory facts. ToolRuntime / tool result accept path records accepted evidence envelope.
- LLM extractor runs in Host-governed compaction. Normal compaction uses one structured JSON proposal that can include episode summary candidate, pinned state patch candidate, `evidence_backed_fact_candidates`, minimum preserve item candidates and preservation / diagnostic data.
- No eager per-tool-result extraction before compaction.
- If accepted evidence exists but no acceptable fact candidate can be accepted, Host records diagnostic / repair outcome and preserves evidence refs. It must not synthesize a neutral fallback fact.
- `recent_raw_turns_floor` keeps its name and means minimum recent raw turns retained for interaction continuity only.
- `minimum_preserve_items` are bounded continuity items for reference resolution; they do not create `evidence_backed_fact`.
- RunInputBuilder must render `evidence_backed_facts` with `claim_text` and `evidence_refs`, never only digest / ref.

## Direct Evidence To Use

Planning must cite and align with:

- `docs/host/design.md` §24 Conversation Memory.
- `docs/host/design.md` §25 Context Governance.
- `docs/host/design.md` §18 ToolRuntime / TruncationManager.
- `docs/host/design.md` §20 RunInputBuilder.
- `docs/host/implementation-control.md` Phase 12.5 section.
- `docs/host/conversation-memory-first-principles-discussion.md` as discussion context only, not design truth.

Current likely implementation touch points found by controller inspection:

- `dayu/host/memory.py`: existing `VerifiedFactView`, `ConversationMemorySnapshot.verified_facts`, projection from `TOOL_RESULT_ACCEPTED`, compaction materialization, policy limits and JSON codec.
- `dayu/host/run_input.py`: memory block rendering currently uses `stable:verified_facts`; must render claim text plus evidence refs.
- `dayu/host/durable/memory.py`: durable row / payload codec for memory snapshot items.
- `dayu/host/compaction.py`, `dayu/host/context_governance.py`, `dayu/host/llm_compaction.py`, `dayu/host/compact_artifact.py`, `dayu/host/compaction_operation.py`, `dayu/host/dispatch.py`: compaction candidate contract, JSON proposal mapping, accept barrier, artifact / event payload and operation diagnostics.
- `dayu/host/tool_runtime.py` and existing accept-barrier paths if accepted evidence envelope must be materialized at tool-result acceptance.
- `dayu/service/host_assembly.py`, `dayu/runtime/config_loader.py`, `dayu/config/execution_profiles.json`: current policy field still maps `max_verified_facts`; plan must decide exact migration to `max_evidence_backed_facts` without compatibility shims unless explicitly justified by current project rules.
- Tests likely affected: `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_compaction_contract.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/service/test_host_assembly.py`, `tests/runtime/test_config_loader.py`, `tests/README.md`.

## Required Plan Contents

The plan must include:

- Goal / motivation and non-goals.
- Direct evidence with file / section references.
- Exact public / internal contract migration decisions, including type names, field names, event payload keys and config policy key names.
- Affected files and explicit allowed changes per slice.
- State and data flow from `TOOL_RESULT_ACCEPTED` to accepted evidence envelope, compaction candidate, memory projection, RunInputBuilder rendering and post-compaction reuse.
- JSON schema / typed contract for `evidence_backed_fact_candidates` and `minimum_preserve_item_candidates`.
- Host accept barrier rules, including no-fallback-facts behavior and diagnostics.
- Small implementation slices with file ownership, prerequisites, exact tests and stop conditions.
- README sync decision by path.
- Validation commands, including focused tests, integration / smoke tests and pyright.
- Residual risks and owners.

## Required Slice Coverage

The plan may adjust slice order, but it must cover these implementation responsibilities:

- Contract migration: `VerifiedFactView` / `verified_facts` / `max_verified_facts` to `EvidenceBackedFactView` / `evidence_backed_facts` / `max_evidence_backed_facts` or a clearly justified equivalent typed view, without compatibility re-export / wrapper shims.
- Accepted evidence envelope: stable evidence id per accepted tool result, opaque tool query / result / source / locator refs, and Host-neutral validation.
- Compaction candidate extension: structured JSON proposal includes `evidence_backed_fact_candidates` and `minimum_preserve_item_candidates`; LLM compactor parses and returns typed candidates.
- Accept barrier and diagnostics: candidate validation checks refs and shape only; no neutral fallback fact on missing / rejected candidates.
- Memory projection: materializes accepted evidence-backed facts and minimum preserve continuity items from canonical compact events; preserves recent raw turns semantics.
- RunInputBuilder rendering: renders claim text plus evidence refs and minimum preserve continuity items; does not rely on digest-only rendering.
- Tests / smoke: no-compaction short-link raw-turn reuse, post-compaction evidence-backed fact reuse, minimum preserve reference resolution and compaction confirmed facts not drifting.

## Required Tests

At minimum, the implementation-ready plan must assign tests for:

- Accepted evidence envelope can be referenced by `evidence_backed_fact_candidates`; Host does not parse source / locator.
- Assistant final answer, user input, episode summary and working assumption cannot become evidence-backed facts.
- Missing or invalid fact candidates produce diagnostic / repair outcome, not neutral fallback fact.
- `minimum_preserve_item_candidates` materialize only as continuity items and never as facts.
- RunInputBuilder renders `claim_text` and `evidence_refs` for evidence-backed facts.
- Recent raw turns support no-compaction follow-up, but are not used as stable post-compaction fact truth.
- Post-compaction revenue / gross-profit facts can be reused to answer a gross-margin follow-up without relying on compacted-away raw turns.
- Config loader / service assembly accept the new policy key and reject obsolete naming if the schema is changed.

## Scope Boundaries

Do not plan changes to:

- Engine Agent loop or Runner provider contract.
- Real Fins tool implementations or `dayu.fins.storage`.
- Service / UI workflow public methods.
- Long-term retrieval, cross-session research memory, vector index, public memory edit / forget API.
- New compatibility wrappers, compatibility re-exports or old schema compatibility reads.

## Stop Conditions

The planning agent must stop and return `Blocking Questions For Controller` if:

- It cannot define the accepted evidence envelope without changing public Host command APIs.
- It finds schema migration requires preserving old config/database compatibility.
- It needs to modify Engine, Fins storage or Service-facing command APIs.
- It cannot produce small slices with disjoint ownership and executable tests.

## Completion Report Required From Planning Agent

The planning agent output must include:

- Plan artifact path.
- Whether the plan is handoff-ready and code-generation-ready.
- Any blocking questions.
- Proposed implementation slice list.
- Tests / pyright / README sync matrix.
- Known residual risks and owners.
