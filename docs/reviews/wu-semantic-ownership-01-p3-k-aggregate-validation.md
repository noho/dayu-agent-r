# WU-SEMANTIC-OWNERSHIP-01 P3-K Aggregate Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: aggregate validation before aggregate deepreview
- Accepted plan commit: `8515364a`
- Accepted slice commits:
  - S1 Owner-Level Contract Assertions: `f0d4c76a`
  - S2 Durable Diagnostic Helper Boundary: `6e8b786e`
  - S3 Protocol-Faithful Test Double Consolidation: `2f69a5d1`

## Validation Matrix

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/contracts/test_tool_result_envelope.py tests/host/test_run_input_builder.py -q`
  - Result: `166 passed`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q`
  - Result: `27 passed, 1 skipped`
- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - Result: `380 passed`
- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/service/test_fins_direct.py -q`
  - Result: `193 passed, 3 warnings`
  - Warning classification: existing third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass

## Source Scan Summary

S1 assertion ownership:

- Removed exact tuple-lock helpers `_POLICY_FIELDS` / `_SNAPSHOT_FIELDS`.
- S1 tests assert owner-level required fields, owner helper construction, JSON projection, digest behavior, and round-trip behavior.

S2 durable diagnostic boundary:

- `tests/host/recovery_support.py::projection_checkpoint_sequence(...)` calls `read_projection_checkpoint(...)`.
- Remaining S2 raw SQL helpers are marked `diagnostic-only` or `fault-injection-only`.
- `public_smoke_support.py` active wait lookup still uses `read_active_wait_records_for_run(...)`.
- `read_events_after(...)` / `read_events_after_matching(...)` scan hits are EventLog owner tests or unrelated consumers, not S2 diagnostic helper rewrites.

S3 protocol-faithful test doubles:

- No external `.trigger(...)` call sites under `tests/engine`, `tests/host`, or `tests/service`.
- No old `FakeCancellationToken` / `StubCancellationToken` / constructor-as-cancelled usages in S3 scope.
- No no-argument `datetime.now()` in migrated cancellation fake scope.
- One no-argument `datetime.now()` remains in `tests/host/test_toolruntime_duplicate_governance.py`; this file is outside P3-K S3 approved scope and was not touched by the slice.
- `ConversationMemorySnapshotVNext(...)` construction remains centralized in `tests/host/memory_snapshot_factories.py`; the additional hit in `tests/host/test_import_boundary.py` is scanner fixture text.

## README Decision

No README update was required by S1, S2, or S3:

- S1 introduced only file-local assertion helpers and no shared test convention.
- S2 did not add a shared durable diagnostics helper or new test layer.
- S3 changed the concrete cancellation helper class name and removed duplicate fakes, while keeping the documented helper responsibility in `tests/host/fake_cancellation.py`.

## Residual Risk Classification

| Residual risk | Classification | Controller decision |
| --- | --- | --- |
| S2 stress validation failures in scheduler cleanup / runner-call manifest payload paths. | Assigned outside current slice | Failure traces are outside S2 helper semantics. They remain later stress / scheduler / payload evidence, not a P3-K aggregate blocker. |
| `tests/runtime/test_lane.py` has a private cancellation fake. | Outside approved P3-K S3 scope | Runtime lane tests were not part of P3-K accepted S3 file ownership. This can be considered in later runtime test cleanup, not as a current blocker. |
| `tests/host/test_toolruntime_duplicate_governance.py` has a local no-argument `datetime.now()` helper. | Outside approved P3-K S3 scope | Not touched by P3-K S3 and not part of the migrated cancellation helper surface. |
| Full `tests/` suite not rerun in aggregate validation. | Accepted validation scope | Aggregate validation ran the approved focused matrices plus full OpenAI runner tests, pyright, diff check, and source scans. |

## Propagation Audit

- Memory policy / snapshot semantics flow from `dayu.host.memory` helpers to tests; tests no longer claim exact closed dataclass field registries.
- Tool result envelope tests preserve required discriminants and forbidden awaiting fields without claiming the complete field set.
- Resume guidance tests centralize exact LLM-facing semantic line checks and internal leakage negatives in a file-local helper.
- Durable checkpoint reads use the production projection owner helper; global diagnostics and impossible recovery injections remain explicitly test-owned.
- Cancellation observation protocol remains owned by `dayu.contracts.cancellation.CancellationToken`; test mutation is centralized in `ControllableCancellationToken`.
- Compaction and memory fixture construction remain centralized in their test helper owners.
- No production durable state, trace, memory, audit, prompt, tool schema, or user / LLM-facing output changed.

## Completion Status

P3-K aggregate validation is complete. All three approved implementation slices are committed and all accepted slice-level findings are closed. Next gate: aggregate deepreview by AgentMiMo and AgentDS.
