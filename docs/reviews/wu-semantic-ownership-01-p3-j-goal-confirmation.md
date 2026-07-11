# WU-SEMANTIC-OWNERSHIP-01 P3-J Goal Confirmation

## Work Unit

- Umbrella WU: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-J - Host durable schema and weak-contract hardening backlog`
- Type: architecture-sensitive durable schema / public contract hardening backlog
- Control source: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`

## First-Principles Judgment

The work unit is valid, but it must stay evidence-driven.

The underlying motivation is real: Host durable state and read models are part of the production truth boundary. If high-value closed sets are persisted as unconstrained text, invalid durable facts can be accepted and later interpreted inconsistently by projections, recovery, memory, audit, public event streams, or LLM-facing input assembly.

The severity is not uniform across all source findings. `event_type`, `execution_target`, `queue_policy`, read-model freshness, and stale legacy config exposure are credible correctness or maintainability risks at owner boundaries. Broad observations such as generic `HostRow` column strings or opaque metadata JSON are not automatically defects unless current code evidence proves a concrete semantic failure path. P3-J therefore must not become a whole-store rewrite or generic typed-schema campaign.

## Owner Boundary

- Host durable schema owns stored row shape, DDL constraints, and fresh-database legal-value rejection.
- Durable row decoders own typed read validation and fail-closed behavior for corrupted or manually-mutated rows.
- Host public durable contracts own values exposed across `dayu.host` public APIs and public read outputs.
- Conversation Memory projection and RunInputBuilder own snapshot cursor/freshness checks before memory content reaches LLM-facing input.
- `dayu.runtime.ConfigLoader` owns current runtime config filenames and any diagnostic exposure of removed legacy config names; it must not keep ownerless compatibility fossils.

Fixes must land at those owner boundaries or their direct input validation boundaries. Downstream display, tests, or one-off consumers must not patch around invalid durable semantics.

## Direct Current-Code Evidence

### Still Current

- `dayu/host/durable/event_log.py` defines `EventLogAppendRequest.event_type: str` and `EventLogRow.event_type: str`; append validation only requires non-empty text.
- `dayu/host/durable/schema.py` stores `event_log.event_type TEXT NOT NULL` without a closed-set constraint.
- `dayu/host/durable/state.py` defines `RunRow.execution_target: str` and `RunRow.queue_policy: str`.
- `dayu/host/durable/schema.py` stores `host_runs.execution_target TEXT NOT NULL` and `host_runs.queue_policy TEXT NOT NULL` without legal-set constraints.
- `dayu/runtime/config_loader.py` still exposes removed legacy names through `_LEGACY_CONFIG_FILES` and `legacy_config_file_names()`.

### Already Partly Covered Or Needs Fresh Proof

- `RunResultRow.terminal_status` is currently exposed as `str`, but `_run_result_from_host_row()` validates it through `_terminal_status_from_text()` before returning `.value`. Plan gate must decide whether the remaining public row type is still a defect or whether row-decoder ownership already closes the correctness risk.
- Memory snapshot upsert is still present, but current code also records `checkpoint_event_sequence` / `checkpoint_event_id`, has `write_memory_snapshot_with_checkpoint()`, and RunInputBuilder has missing/damaged/ahead/lag/inline-repair checks. Plan gate must prove any remaining stale-projection path with current code, not rely on pre-P3-C evidence.
- `host_run_results` is insert-only by design for terminal results. Plan gate must prove a realistic stale or duplicate-terminal path after P3-A/P3-B lifecycle fixes before changing projection semantics.
- `scope_kind`, `result_kind`, descriptor kind values, `HostRow`, `metadata_json`, memory digest double-write, and old `verified_fact` diagnostics need current-code classification. They may be accepted, rejected-with-reason, or deferred-with-owner depending on direct failure evidence and owner boundary.

## Success Signals

- High-value durable closed sets with provable legal values are enforced by typed contracts, DDL checks, row decoders, or direct upstream validators.
- Any stale read-model or memory-snapshot finding accepted by plan has a concrete current failure path and a minimal owner-boundary fix.
- Ownerless legacy config exposure is removed or given an explicit, tested owner and deletion condition.
- Every source finding assigned to P3-J is classified as accepted, rejected-with-reason, deferred-with-owner, or needs-more-evidence in the plan artifact.
- Tests cover fresh-schema rejection, decoder fail-closed behavior, public contract behavior, and any memory/read-model freshness behavior changed by implementation.
- Pyright remains clean and README trigger checks are explicitly recorded.

## Non-Goals

- No broad migration for old databases. Project policy is fresh schema unless the current task explicitly requires compatibility migration.
- No whole-store schema rewrite, generic ORM layer, or replacement of `HostRow` across the durable package without a concrete owner-boundary defect.
- No changes to Fins test-harness semantic coupling; that belongs to P3-K.
- No re-opening P3-A lifecycle terminal-source work or P3-C compact/memory typed-material work unless new direct current-code evidence proves an unresolved P3-J owner-boundary defect.
- No downstream masking in Service/UI/CLI/README/tests for invalid durable facts.

## Plan Handoff Requirements

AgentCodex must produce a code-generation-ready plan at:

`docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`

The plan must:

1. Read the design sources, control doc, this goal confirmation, and source review findings.
2. Re-audit current code for every P3-J source finding.
3. Classify each finding with direct evidence.
4. Propose the smallest implementation slices that form independently testable semantic closures.
5. Prefer high-value closed-set/schema/decoder fixes first, then freshness fixes only when current failure evidence exists, then legacy config cleanup.
6. Avoid expanding into whole-store migration or generic low-level rewrites without a proven root cause.

## Blocking Open Questions

None for entering plan gate. The plan gate itself must answer which P3-J source findings remain current defects and which are stale, already fixed, or too broad for this work unit.
