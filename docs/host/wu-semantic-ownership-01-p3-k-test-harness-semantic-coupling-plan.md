# WU-SEMANTIC-OWNERSHIP-01 P3-K Test Harness Semantic Coupling Plan

## 0. Plan Gate Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-K - Test harness semantic coupling cleanup`
- Gate: `plan`
- Role: AgentCodex
- Artifact path: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-p3-k-goal-confirmation.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Source review evidence: `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` TF-1..TF-5, lines 432-486.

Preflight evidence:

- Branch: `phaseflow/host-issues-control`
- Existing external dirty / untracked files observed before this plan:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `docs/cli_ci.md`
  - `docs/cli_ci_oracles.json`
  - `docs/cli_ci_scenarios.json`
  - `docs/reviews/code-review-20260710-135625.md`
  - `docs/reviews/code-review-20260710-141049.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-goal-confirmation.md`
- Implementation must not modify, format, delete, stage, or rely on those files except reading the goal-confirmation artifact.

## 1. First-Principles Judgment

The motivation is valid, but it is easy to overcorrect.

Tests are allowed to lock public contracts. Exact wire values, terminal status sets, required protocol fields, forbidden internal refs, and fail-closed behavior are legitimate regression locks when the production owner has promised those facts. The defect is narrower: some tests and helpers currently act as parallel owners of production schema, durable query semantics, cancellation protocol details, compaction schema shape, or LLM wording when the public promise is only an owner-level behavior.

P3-K must therefore replace brittle or ownerless assertions with owner-level assertions, not weaken coverage. If a test currently protects a real public contract, the implementation must leave the lock in place or make its owner explicit in test names / helper names. If current code has no production helper for a test-only fault injection, the plan must keep the test helper as a test fault-injection owner and document that it is not a production semantic source.

## 2. Goal / Motivation / Success Signal

Goal:

- Remove test-harness semantic coupling that makes tests a parallel schema registry or parallel semantic owner.
- Preserve public-contract regression coverage by moving assertions to owner-level behavior and shared test helpers.
- Keep this work unit test-only unless direct implementation evidence proves a production helper is already the correct semantic owner to reuse.

Motivation:

- Host owns Session / Run / Attempt / EventLog / recovery / memory / LLM-facing projection truth.
- Engine owns one-run protocol events, runner normalization, tool loop, and cancellation observation.
- `dayu.contracts.cancellation.CancellationToken` owns the test-visible cancellation observation protocol.
- Tests own verification. They must not own production facts independently through exact field tuples, raw SQL, duplicate fake protocols, or wording literals unless those exact values are public contract.

Success signals:

- TF-1..TF-5 are disposed with current-code evidence.
- Exact field-set assertions remain only where exact public / wire contract is the intended promise.
- Raw SQL reads are replaced with production durable read helpers where those helpers already express the queried truth.
- Raw SQL writes remain only for explicit test fault injection that production APIs intentionally cannot perform.
- Cancellation fakes converge on one protocol-faithful tests-side helper for controllable cancellation behavior.
- LLM-facing tests assert required semantic content and forbidden internal leakage without pinning non-contract wording.
- Affected tests and pyright pass.
- README trigger decision is recorded.

## 3. Source Finding Dispositions

| Finding | Disposition | Current-code evidence | Implementation boundary |
|---|---|---|---|
| TF-1 Field-set lock tests | `accepted` | `tests/host/test_memory_projection.py:121-158` defines `_POLICY_FIELDS` / `_SNAPSHOT_FIELDS` and `tests/host/test_memory_projection.py:691-703` asserts exact ordered field tuples. `tests/contracts/test_tool_result_envelope.py:116-126` also asserts complete envelope field sets. `tests/engine/test_engine_event_contract.py:62-210` contains exact Engine public protocol locks. | Replace ownerless exact field tuple locks with required-field / required-behavior assertions. Keep exact locks for public Engine wire values, terminal sets, and EngineEvent required protocol fields because Engine design exposes these as public stream contracts. |
| TF-2 raw SQL helpers | `accepted` | `tests/host/public_smoke_support.py:1505-1524` counts `event_log` with raw `sqlite3`; `tests/host/recovery_support.py:659-710` mutates liveness and projection checkpoint tables directly; `tests/host/stress_support.py:720-740` and `tests/host/stress_support.py:984-1035` read EventLog / liveness rows directly. | Replace raw reads with production durable read helpers where available. Keep raw writes only for test fault injection that production APIs intentionally do not expose, and make the helper name/docstring state `fault injection only`. |
| TF-3 compaction / memory fakes coupled to schema | `accepted` | `tests/host/fake_compaction.py` imports and constructs many vNext candidate types directly; `tests/host/memory_snapshot_factories.py:102-240` centralizes full `ConversationMemorySnapshotVNext(...)` construction and already uses production digest helpers. | Do not ban typed test fixtures. Keep `memory_snapshot_factories.py` as the single snapshot test factory owner. Narrow `fake_compaction.py` so tests depend on `ContextCompactor` / material-input behavior and shared proposal helpers, not scattered schema construction. |
| TF-4 duplicate cancellation fakes | `accepted` | `tests/host/fake_cancellation.py:14-63` provides `StubCancellationToken` with aware UTC timestamps and `request_cancel`; `tests/engine/runners/openai/_fakes.py:250-287` provides `FakeCancellationToken` with naive `datetime.now()` and `trigger`; `tests/service/test_fins_direct.py:45-73` defines another local fake. | Add one tests-side protocol-faithful controllable token and migrate Engine runner / Host compaction / Service direct tests to it where they need cancellation behavior. Keep per-test open-token stubs only when they do not encode cancellation semantics. |
| TF-5 exact LLM-facing wording assertions | `accepted` | `tests/host/test_run_input_builder.py:542-560` asserts specific resume guidance substrings and internal-ref absence. `tests/host/test_memory_projection.py:951-959` compares fallback evidence text through `render_accepted_tool_evidence_for_llm(None)`, which is owner-derived. | Replace exact non-contract wording checks with semantic-content helper assertions. Preserve negative leakage checks and renderer-derived equality where the renderer is the production owner. |

Disposition count:

- `accepted`: 5
- `rejected-with-reason`: 0
- `deferred-with-owner`: 0
- `needs-more-evidence`: 0

Important accepted-scope limits:

- P3-K must not change production contracts solely for tests.
- P3-K must not remove valid public-contract locks from `tests/engine/test_engine_event_contract.py` without a design-source change.
- P3-K must not include unrelated known failures such as baseline `tests/host/test_dispatch_scheduler.py` compaction previous-view failures unless same-path evidence appears during implementation.

## 4. Legitimate Contract Locks Versus Parallel Truth

Legitimate public-contract locks to preserve:

- `EngineEventType` wire values and mapping coverage in `tests/engine/test_engine_event_contract.py:62-91`.
- `TERMINAL_ENGINE_EVENT_TYPES` exact set in `tests/engine/test_engine_event_contract.py:108-118`.
- `EngineEvent` required field contract and no-default behavior in `tests/engine/test_engine_event_contract.py:121-142`.
- Engine event data fields that carry machine-readable public protocol facts, including wait/suspend records, provider request identity, content-complete finish-reason exclusion, iteration-started runner input signal, and tool observation event payload shape.
- `ToolResultSuccess.ok is True`, `ToolResultFailure.ok is False`, runtime rejection of disguised literals, non-empty failure fields, and forbidden `await_spec` / `await` / `awaiting` fields.
- LLM-facing negative checks that internal refs / digests / event ids / payload refs must not leak.
- Equality against `render_accepted_tool_evidence_for_llm(...)` when the renderer is the production LLM-facing owner.

Ownerless parallel truth to replace:

- `_POLICY_FIELDS` / `_SNAPSHOT_FIELDS` exact ordered tuples in `tests/host/test_memory_projection.py`.
- Complete `ToolResultSuccess` / `ToolResultFailure` field-set equality when the intended contract is required discriminant fields plus forbidden awaiting fields.
- Raw EventLog / checkpoint / liveness SQL reads that duplicate existing durable read helpers.
- Multiple cancellation fakes with different timestamp timezone semantics and different mutation method names.
- Resume guidance wording assertions that pin prose instead of required LLM-visible semantic content.

## 5. Implementation Slices

The work is split into three semantic-owner slices. This keeps the slice count within the small cleanup default while separating assertion ownership, durable diagnostic ownership, and test-double protocol ownership.

### S1 - Owner-Level Contract Assertions

Objective:

- Replace brittle exact assertions with owner-level assertions where the exact closed set is not the public contract.
- Keep legitimate public-contract locks intact and make their intent clearer.

Allowed files:

- `tests/host/test_memory_projection.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/host/test_run_input_builder.py`
- Optional if only comments / helper names are clarified: `tests/engine/test_engine_event_contract.py`
- Optional helper file if needed for assertion reuse: `tests/host/llm_text_assertions.py`
- `tests/README.md` only if a new helper file or reusable assertion convention is introduced and falls under the README's current responsibilities.

Exact allowed changes:

- In `tests/host/test_memory_projection.py`:
  - Delete `_POLICY_FIELDS` and `_SNAPSHOT_FIELDS` if no longer used.
  - Replace `test_memory_projection_policy_contract_uses_design_source_fields` with assertions that required owner-level fields exist and are consumed by owner helpers:
    - `default_memory_projection_policy()`
    - `digest_memory_projection_policy(...)`
    - at least one build path such as `build_empty_conversation_memory_snapshot(...)` or existing projection tests.
  - Replace `test_conversation_memory_snapshot_vnext_contract_fields_are_fixed` with assertions for required semantic sections:
    - identity: `schema_version`, `snapshot_id`, `session_id`, `cursor`
    - policy / lineage: `policy_digest`, `latest_compaction_event_ref`
    - memory sections: `trace_memory`, `evidence_fact_memory`, `session_summary_memory`, `answer_anchor_memory`, `forward_intent_memory`
    - governance: `diagnostics`, `built_at`, `snapshot_digest`
    - JSON / durable round-trip and digest checks remain the stronger owner contract.
- In `tests/contracts/test_tool_result_envelope.py`:
  - Change complete field-set equality to:
    - required success fields are present: `ok`, `value`, `meta`;
    - required failure fields are present: `ok`, `error`, `message`, `hint`, `meta`;
    - forbidden awaiting fields are absent from both envelopes.
  - Keep runtime discriminant and validation tests unchanged.
- In `tests/host/test_run_input_builder.py`:
  - Replace scattered resume guidance prose checks with a file-local private helper such as `_assert_resume_guidance_semantics(content, *, tool_name, status, result_text)`.
  - The helper must distinguish two assertion classes:
    - dynamic owner-derived content assertions: exact tool name, completion status, and result payload text that are produced from the wait completion projection / payload;
    - named production-owned guidance semantics: the resume guidance owner currently promises an intro that the prior waiting external tool step has completed and a no-repeat instruction for the same request.
  - The helper must assert the named production-owned guidance semantics, not vague keyword substrings. If the production owner exposes stable public constants for these guidance fragments, the helper should assert those constants directly. If the constants remain private implementation details, the helper may keep exact expected fragments in the test, but its name/docstring must state that those fragments mirror production-owned resume guidance semantics and must be updated when the owner intentionally changes the guidance.
  - The helper must assert:
    - the production-owned intro semantics: the content tells the LLM a prior waiting external tool step has completed;
    - the dynamic tool name is visible exactly enough to catch wrong or missing tool identity;
    - the dynamic completion status is visible exactly enough to catch wrong or missing status;
    - the dynamic result payload is visible exactly enough to catch wrong or missing payload projection;
    - the production-owned no-repeat semantics: the LLM is instructed not to restart the same download / upload / processing action for the same request.
  - Keep all internal leakage negative assertions from lines 550-560 or their equivalent.
- Do not loosen tests to accept missing required content.
- Do not change production LLM text in this slice.
- Do not add `tests/host/llm_text_assertions.py` unless at least two test modules need the same assertion helper with the same owner semantics. For the current `test_run_input_builder.py` resume guidance case, prefer a file-local private helper.

Propagation audit:

- Semantic fact owner: memory policy / snapshot owners in `dayu.host.memory`, tool result envelope owner in `dayu.contracts.tool_result`, resume guidance owner in `dayu.host.run_input`, accepted evidence renderer in `dayu.host.evidence`.
- Test helper / assertion: required-field and semantic-content assertions consume owner helpers or owner-rendered text.
- Verification target: tests fail if required owner-level fields disappear, if digest / JSON round-trip breaks, if forbidden awaiting fields return, or if required LLM guidance semantics / leakage boundaries regress.

Focused validation:

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/contracts/test_tool_result_envelope.py tests/host/test_run_input_builder.py -q
python -m pyright dayu/ tests/ utils/
```

Completion signal:

- No exact ordered field tuple remains for `MemoryProjectionPolicy` or `ConversationMemorySnapshotVNext`.
- Tool result envelope test protects required fields and forbidden awaiting fields without becoming a closed schema registry.
- Resume guidance tests protect required semantics and leakage boundaries without requiring exact prose.
- Resume guidance helper does not use vague substring checks; it either asserts stable production guidance constants directly or asserts named production-owned guidance semantics with exact expected fragments plus a docstring documenting the owner relationship.

Stop condition:

- Stop and return to plan review if implementation discovers a production design source explicitly promises exact field closure for memory policy / snapshot or resume guidance wording.

### S2 - Durable Diagnostic Helper Boundary

Objective:

- Reduce raw SQL helper coupling where production durable query helpers already exist.
- Preserve test-only fault injection for states that production APIs intentionally cannot create.

Allowed files:

- `tests/host/public_smoke_support.py`
- `tests/host/recovery_support.py`
- `tests/host/stress_support.py`
- Optional shared tests helper if useful: `tests/host/durable_diagnostics.py`
- `tests/README.md` only if new shared helper responsibilities need documentation.

Exact allowed changes:

- TF-2 raw SQL helper final dispositions:
  - `tests/host/public_smoke_support.py::_diagnostic_event_type_count(...)`: keep raw SQL as diagnostic-only. It is a cross-Run EventLog `event_type` count without `run_id`; `EventLogStore.count_committed_events_by_run_and_type(...)` / `dayu.host.durable.event_log.count_committed_events_by_run_and_type(...)` are run-scoped and are not exact equivalents. Add or keep a docstring stating this is point-in-time test synchronization diagnostic, not EventLog truth.
  - `tests/host/recovery_support.py::force_owner_pid_missing_and_heartbeat_stale(...)`: keep raw SQL as fault-injection-only. Production liveness APIs must not fabricate missing pid / stale heartbeat state.
  - `tests/host/recovery_support.py::force_memory_projection_lag(...)`: keep raw SQL as fault-injection-only. Confirmed production checkpoint helpers are `read_projection_checkpoint(transaction, consumer_id)`, `ensure_projection_checkpoint(transaction, consumer_id, *, now)`, and `advance_projection_checkpoint(transaction, consumer_id, *, event_sequence, event_id, now)` in `dayu.host.durable.projection`; `ensure` initializes only when absent and `advance` is monotonic, so they are not exact helpers for forcing an existing checkpoint backwards or clearing `checkpoint_event_id`.
  - `tests/host/recovery_support.py::event_type_count(...)`: keep raw SQL as diagnostic-only for the same cross-Run EventLog count reason as `_diagnostic_event_type_count(...)`.
  - `tests/host/recovery_support.py::projection_checkpoint_sequence(...)`: replace raw SQL with exact existing owner helper `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)` through the Host durable store transaction runner, returning `row.checkpoint_event_sequence` or `None`.
  - `tests/host/stress_support.py::read_latest_event_sequence(...)`: keep raw SQL as diagnostic-only. The global `MAX(event_sequence)` aggregate is a stress lag / point-in-time diagnostic; production EventLog readers consume by cursor and have no exact max-sequence helper.
  - `tests/host/stress_support.py::read_event_log_count(...)`: keep raw SQL as diagnostic-only. The global EventLog row count has no exact production helper and must not be represented as EventLog canonical truth.
  - `tests/host/stress_support.py::read_host_instances(...)`: keep raw SQL as diagnostic-only all-instance liveness view. The actual production helper is `HostInstanceLivenessStore.read_host_instance(transaction, host_instance_id)` / `dayu.host.durable.liveness.read_host_instance(transaction, host_instance_id)`, which reads one known id and is not an exact helper for all-instance stress diagnostics.
- For EventLog counting / latest-sequence reads:
  - Do not route global aggregate diagnostics through `read_events_after(...)` / `read_events_after_matching(...)` merely to reduce raw SQL; unbounded event replay would change the helper's diagnostic shape without using an exact owner helper.
  - Keep diagnostic helpers diagnostic-only; they must not become production read APIs.
- For active wait id in `public_smoke_support.py`:
  - Keep the existing `read_active_wait_records_for_run(...)` production helper usage.
  - Do not introduce raw SQL for wait records.
- For `force_owner_pid_missing_and_heartbeat_stale(...)`:
  - Keep raw SQL mutation because it is fault injection for startup recovery orphan proof and production liveness APIs must not fabricate a missing pid / stale owner.
  - Rename only if needed to make the boundary explicit, e.g. `inject_missing_pid_stale_owner_liveness(...)`.
  - Docstring must state the owner: tests fault-injection helper, not liveness semantic truth.
- For `force_memory_projection_lag(...)`:
  - Do not replace with `ensure_projection_checkpoint(...)` / `advance_projection_checkpoint(...)`; those helpers are confirmed to exist but are not exact semantic equivalents for this fault-injection state.
  - Keep raw SQL as fault injection and document that production checkpoint APIs intentionally reject backwards movement and do not expose a helper to clear an existing checkpoint event id.
- For `read_host_instances(...)` in stress helpers:
  - Prefer `HostInstanceLivenessStore.read_host_instance(...)` only when callers have specific ids.
  - If the stress diagnostic needs all instance rows and no production helper exists, retain raw SQL with the current diagnostic-only boundary and do not invent a production list API solely for tests.
- Do not add production query helpers just to satisfy tests.

Propagation audit:

- Semantic fact owner: Host durable EventLog / liveness / projection checkpoint modules.
- Test helper / assertion: diagnostic helpers either call owner read helpers or clearly declare test-only fault injection.
- Verification target: tests still observe the same recovery / smoke / stress behavior, but no helper silently defines recovery or liveness semantics independent of production owners.

Focused validation:

```bash
source .venv/bin/activate
pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
python -m pyright dayu/ tests/ utils/
```

If stress runtime is too long for the implementation pass, the implementation artifact must record why it was not run and must at least run the non-stress focused support consumers that import `stress_support.py`.

Completion signal:

- Only exact-replaceable raw SQL is removed: for the current S2 scope, `projection_checkpoint_sequence(...)` is the expected replacement.
- Remaining raw SQL is explicitly diagnostic-only or fault-injection-only in helper names / docstrings, and each retained helper has the final disposition listed above.
- No production helper is added solely for tests.

Stop condition:

- Stop and return to plan review if a required replacement would need a new production public/durable API.

### S3 - Protocol-Faithful Test Double Consolidation

Objective:

- Consolidate cancellation fakes behind one protocol-faithful tests-side helper.
- Keep compaction / memory fixture helpers as tests-side owners, but shrink direct schema coupling where it is not the test's subject.

Allowed files:

- `tests/host/fake_cancellation.py`
- `tests/engine/runners/openai/_fakes.py`
- Engine runner tests importing `FakeCancellationToken`
- Host compaction tests importing `StubCancellationToken`
- `tests/service/test_fins_direct.py`
- `tests/host/fake_compaction.py`
- `tests/host/memory_snapshot_factories.py`
- Tests importing `FakeContextCompactor`, `FakeConversationCompactorVNext`, or `fake_compaction_proposal_from_material_json`
- `tests/README.md` if helper names / responsibilities change.

Exact allowed changes:

- In `tests/host/fake_cancellation.py`:
  - Replace `StubCancellationToken` with, or add alongside it during the same slice, a single canonical helper such as `ControllableCancellationToken`.
  - The helper must implement `dayu.contracts.cancellation.CancellationToken`.
  - `ControllableCancellationToken()` must always construct an open token: `is_cancelled()` is `False`, `cancel_reason()` is `None`, and `requested_at()` is `None`.
  - There must be no constructor-as-cancelled semantics. Existing `StubCancellationToken(reason="...")` style call sites must become explicit two-step setup: construct an open token, then call `request_cancel("...")`.
  - `requested_at()` must return timezone-aware UTC `datetime`.
  - Mutation method must be semantically named once: `request_cancel(reason: str = "test_cancelled")`.
  - `request_cancel(...)` must transition the token from open to cancelled, preserve the first reason and first UTC-aware `requested_at`, and be idempotent on repeated calls.
  - Optional aliases such as `trigger()` are allowed only inside the canonical helper, only if they call `request_cancel(...)` with identical semantics, and only after all external call sites have migrated away from `.trigger(...)`.
  - Provide the open-token constructor/default state instead of separate fake classes.
- In `tests/engine/runners/openai/_fakes.py`:
  - Remove the local `FakeCancellationToken` implementation or import the canonical tests helper under the old name only if the import is not a compatibility re-export. Preferred: update importing tests to import the canonical helper directly.
  - Do not keep a second fake with naive timestamp semantics.
- In `tests/service/test_fins_direct.py`:
  - Default decision: use `ControllableCancellationToken()` for the existing never-cancelled Service pass-through tests; because it is open by default, callers can leave it unmutated.
  - A local stub is allowed only if the test explicitly needs a non-mutable observation object. If retained, it must be named as an open observation stub, must have no `request_cancel` / `trigger` mutation method, and must not encode cancellation semantics beyond the `CancellationToken` observation protocol.
- In Host compaction / Engine ingest / LLM compaction tests:
  - Replace `StubCancellationToken()` with the canonical helper.
  - Replace `.trigger(...)` calls with `request_cancel(...)`.
  - Keep existing `.request_cancel(...)` call sites only after they target the canonical helper.
- In `tests/host/fake_compaction.py`:
  - Keep `FakeContextCompactor` as the test double for the public `ContextCompactor` protocol.
  - Keep `fake_compaction_proposal_from_material_json(...)` as the LLM strict JSON proposal helper because LLM compactor tests need strict JSON text.
  - Avoid expanding direct production vNext type construction outside this helper. If repeated construction exists in callers, route it through the helper rather than adding new schema-coupled fixtures.
  - Do not move production compaction schema into tests or add production compatibility wrappers.
- In `tests/host/memory_snapshot_factories.py`:
  - Keep it as the single owner for test snapshot construction.
  - Do not scatter new `ConversationMemorySnapshotVNext(...)` calls into business tests.

Propagation audit:

- Semantic fact owner: `dayu.contracts.cancellation.CancellationToken` owns cancellation observation protocol; `dayu.host.compaction.ContextCompactor` owns compactor protocol; `dayu.host.memory` owns memory snapshot schema and digest.
- Test helper / assertion: canonical cancellation helper implements only the protocol observation surface plus test mutation; compaction and memory helpers centralize schema construction and digest recalculation.
- Verification target: cancellation-boundary tests fail if protocol methods drift; compaction tests fail if public compactor protocol or material-derived proposal behavior breaks; memory tests fail through factory/digest owner behavior rather than scattered field constructors.

Focused validation:

```bash
source .venv/bin/activate
pytest tests/engine/runners/openai/test_cancellation_boundaries.py tests/engine/runners/openai/test_cancellation_no_done_event.py tests/engine/runners/openai/test_retry_backoff.py tests/engine/runners/openai/test_response_cleanup_race.py -q
pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q
pytest tests/service/test_fins_direct.py -q
python -m pyright dayu/ tests/ utils/
```

Additional S3 helper contract validation:

- Add or migrate a focused helper contract test for `ControllableCancellationToken` covering:
  - construction starts open: `is_cancelled() is False`, `cancel_reason() is None`, `requested_at() is None`;
  - `request_cancel("reason")` transitions to cancelled and exposes the exact reason;
  - `requested_at()` after cancellation is a timezone-aware UTC `datetime`;
  - repeated `request_cancel(...)` calls are idempotent and preserve the first cancellation observation.
- After S3 migration, `.trigger(...)` must not remain in external Engine / Host / Service test call sites; a `trigger` alias, if any, may exist only inside the canonical helper.

Completion signal:

- There is one protocol-faithful controllable cancellation token helper for tests.
- No local Engine runner cancellation fake uses naive `datetime.now()`.
- Service Fins direct tests no longer define an independent cancellable fake.
- `tests/service/test_fins_direct.py` uses the canonical open token, or documents a clearly named non-mutable open observation stub with no mutation semantics.
- A focused helper contract test covers open state, UTC-aware `requested_at`, reason, and idempotent cancellation.
- No external test call site uses `.trigger(...)`.
- Compaction and memory schema construction remains centralized in tests helpers.

Stop condition:

- Stop and return to plan review if a test requires cancellation behavior outside the `CancellationToken` observation protocol, because that would imply a production contract question rather than a test cleanup.

## 6. README / Docs Decision

Implementation must read `tests/README.md` before changing tests. Current README says tests facts follow current code and helper responsibilities should be synchronized when new test layers or helper conventions are introduced.

Expected docs behavior:

- `tests/README.md`: update only if S1 introduces a new reusable LLM assertion helper, S2 introduces a shared durable diagnostic helper, or S3 renames / consolidates cancellation or compaction helper responsibilities in a way the README currently documents.
- If none of those README trigger conditions apply, the implementation artifact must explicitly record `tests/README.md: no update needed`.
- `docs/host/design.md`: no update planned because P3-K is test-harness cleanup and should not change Host public contracts.
- `docs/engine/design.md`: no update planned because P3-K should preserve Engine public event / cancellation contracts.
- Root `README.md` and `dayu/README.md`: no update planned because no user-visible CLI / install / workflow / layer-boundary behavior should change.

## 7. Validation Matrix

Minimum per-slice validation is listed in each slice. After all slices, run:

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_result_envelope.py tests/engine/test_engine_event_contract.py tests/engine/runners/openai tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/service/test_fins_direct.py -q
python -m pyright dayu/ tests/ utils/
```

Optional broader validation if time allows:

```bash
source .venv/bin/activate
pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q
```

Stress validation remains explicit because the suite is marked stress:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

Coverage expectation:

- Changed test helper files should remain covered by the focused tests that import them.
- If a new helper file is added, at least one focused test must exercise its public helper behavior.
- For `ControllableCancellationToken`, add a focused helper contract test covering open state, requested UTC timestamp, reason, and idempotent cancellation; indirect business-test coverage is not sufficient.

## 8. Non-Goals

- No production contract changes solely for tests.
- No schema migration, durable DDL change, or Host / Engine public API change.
- No broad rewrite of all tests that use `dataclasses.fields(...)`; only current TF-1 evidence scope.
- No removal of valid public-contract locks for Engine wire values, terminal event sets, tool result discriminants, or forbidden internal LLM leakage.
- No new production list/query API solely to avoid raw SQL in tests.
- No attempt to fix unrelated baseline failures, including known `test_dispatch_scheduler.py` compaction previous-view failures, unless same-path evidence appears.
- No commit, push, PR, implementation gate, or README change during this plan gate.

## 9. Residual Risks

- Some raw SQL may remain because fault injection intentionally creates impossible production states. This is acceptable only when helper names / docstrings clearly assign ownership to test fault injection.
- LLM-facing semantic assertions can become too loose if implemented as vague substring checks. S1 must assert concrete required semantic facts and forbidden internal leakage.
- Keeping Engine exact protocol locks can be challenged as over-strict. Current design treats EngineEvent stream and data shapes as public contracts; changing that requires design-source update, not P3-K cleanup.
- Consolidating cancellation helpers touches many tests. Implementation should migrate call sites incrementally within S3 and use pyright to catch remaining old imports.

## 10. Completion Report Format

Implementation closeout must report:

- Source finding dispositions count.
- Slices completed and any scope deviations.
- Files changed per slice.
- README trigger decision and whether `tests/README.md` was updated.
- Validation commands run and results.
- Propagation audit summary:
  - semantic fact owner;
  - test helper / assertion owner;
  - verification target;
  - remaining raw SQL or exact text / field assertions and why they are legitimate.
- Residual risks classified as fixed, covered by later approved slice, assigned to later work unit, tracked by existing issue, or requiring user decision.

Ready state:

- This plan is ready for plan review if the reviewer accepts the partial-preservation stance for legitimate public-contract locks.
