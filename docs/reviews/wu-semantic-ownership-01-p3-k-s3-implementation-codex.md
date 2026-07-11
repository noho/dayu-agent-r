# WU-SEMANTIC-OWNERSHIP-01 P3-K S3 Implementation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: implementation slice S3 - Protocol-Faithful Test Double Consolidation
- Role: AgentCodex
- Previous accepted commit: `0ebea2c1`
- Stop condition: stop after implementation artifact and validation evidence; no commit, push, PR, control doc update, code review, aggregate review, or next gate.

## Changed Files

Cancellation helper owner:

- `tests/host/fake_cancellation.py`

OpenAI runner cancellation test migration:

- `tests/engine/runners/openai/_fakes.py`
- `tests/engine/runners/openai/test_cancellation_boundaries.py`
- `tests/engine/runners/openai/test_cancellation_no_done_event.py`
- `tests/engine/runners/openai/test_close_releases_resources.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/engine/runners/openai/test_http_unknown_status_runner.py`
- `tests/engine/runners/openai/test_protocol_surface.py`
- `tests/engine/runners/openai/test_request_identity.py`
- `tests/engine/runners/openai/test_response_cleanup_race.py`
- `tests/engine/runners/openai/test_retry_backoff.py`
- `tests/engine/runners/openai/test_runner_b3_extra.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`
- `tests/engine/runners/openai/test_stream_idle.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`

Additional Engine `.trigger(...)` cleanup required by S3 completion signal:

- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`

Host compaction / Engine ingest / LLM compaction migration:

- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_llm_compaction.py`

Service direct migration:

- `tests/service/test_fins_direct.py`

Pre-existing dirty files observed before implementation and not touched by this slice:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/cli_ci.md`
- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/reviews/code-review-20260710-135625.md`
- `docs/reviews/code-review-20260710-141049.md`

## Migration Summary

- Replaced the previous `StubCancellationToken` with `ControllableCancellationToken` in `tests/host/fake_cancellation.py`.
- Removed the local OpenAI runner `FakeCancellationToken` implementation from `tests/engine/runners/openai/_fakes.py`; OpenAI runner tests now import the canonical helper directly.
- Replaced constructor-as-cancelled setup with two-step setup: construct `ControllableCancellationToken()`, then call `request_cancel(...)`.
- Replaced all external `.trigger(...)` call sites under `tests/engine`, `tests/host`, and `tests/service` with `request_cancel(...)`.
- Removed the independent Service direct open token fake; `tests/service/test_fins_direct.py` now passes an unmutated `ControllableCancellationToken()`.
- Did not change production code under `dayu/`.
- Did not expand compaction or memory schema construction outside existing helpers.

## Helper Contract Details

`ControllableCancellationToken` implements `dayu.contracts.cancellation.CancellationToken` and exposes one test-side mutation method:

- `ControllableCancellationToken()` always starts open:
  - `is_cancelled() is False`
  - `cancel_reason() is None`
  - `requested_at() is None`
- `request_cancel(reason: str = "test_cancelled")` transitions open to cancelled.
- `request_cancel(...)` stores the first reason and first `datetime.now(UTC)` timestamp.
- `requested_at()` after cancellation is timezone-aware UTC.
- Repeated `request_cancel(...)` calls are idempotent and preserve the first reason and first timestamp.
- No external `.trigger(...)` alias remains.

Focused helper contract coverage was added in `tests/host/test_compaction_contract.py::test_controllable_cancellation_token_contract_is_protocol_faithful`.

## Validation

Required focused tests:

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_cancellation_boundaries.py tests/engine/runners/openai/test_cancellation_no_done_event.py tests/engine/runners/openai/test_retry_backoff.py tests/engine/runners/openai/test_response_cleanup_race.py -q
```

Result: `24 passed in 0.19s`.

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q
```

Result: `174 passed in 1.12s`.

```bash
source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q
```

Result: `19 passed, 3 warnings in 0.64s`. Warnings are existing third-party `edgar` deprecation warnings.

Additional affected Engine Agent tests, run because the S3 no-trigger scan found local Engine cancellation call sites:

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q
```

Result: `109 passed in 0.34s`.

Type check:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`. Pyright also printed a version-availability notice, not a type-check failure.

Whitespace check:

```bash
git diff --check
```

Result: pass, no output.

## Source Scans

External trigger scan:

```bash
rg -n "\.trigger\(" tests/engine tests/host tests/service
```

Result: no matches.

Old cancellation fake / constructor-as-cancelled scan:

```bash
rg -n "FakeCancellationToken|StubCancellationToken|class ControllableCancellationToken|ControllableCancellationToken\(cancelled" tests/engine tests/host tests/service
```

Result: only the canonical helper definition remains:

```text
tests/host/fake_cancellation.py:14:class ControllableCancellationToken(CancellationToken):
```

OpenAI runner / Engine Agent naive timestamp scan:

```bash
rg -n "datetime\.now\(\)" tests/engine/runners/openai tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/host/fake_cancellation.py tests/service/test_fins_direct.py
```

Result: no matches. The canonical helper uses `datetime.now(UTC)`.

Memory snapshot construction scan:

```bash
rg -n "ConversationMemorySnapshotVNext\(" tests/engine tests/host tests/service
```

Result:

```text
tests/host/memory_snapshot_factories.py:113:    snapshot = ConversationMemorySnapshotVNext(
tests/host/memory_snapshot_factories.py:164:    snapshot = ConversationMemorySnapshotVNext(
tests/host/test_import_boundary.py:537:factory.ConversationMemorySnapshotVNext(
```

Interpretation: actual snapshot construction remains centralized in `tests/host/memory_snapshot_factories.py`; the import-boundary hit is scanner fixture text, not business-test construction.

## README Trigger Decision

Read `tests/README.md` before implementation. It already documents that the test-only deterministic compactor is in `tests/host/fake_compaction.py`, the test-only controllable cancellation token is in `tests/host/fake_cancellation.py`, and memory snapshot construction should go through `tests/host/memory_snapshot_factories.py`.

Decision: no README update needed. S3 changed the concrete helper class name and removed duplicate fakes, but did not change the documented helper responsibilities or introduce a new test layer / reusable helper file.

## Propagation Audit

Cancellation:

- Owner: `dayu.contracts.cancellation.CancellationToken` owns the observation protocol.
- Test mutation owner: `tests/host/fake_cancellation.py::ControllableCancellationToken`.
- Consumers now observe only `is_cancelled()`, `cancel_reason()`, and `requested_at()`.
- Test-side mutation is only `request_cancel(...)`; external `.trigger(...)` is gone.
- OpenAI runner `_fakes.py` no longer contains a second cancellable fake or naive `datetime.now()` timestamp semantics.

Compaction:

- Owner: `dayu.host.compaction.ContextCompactor` owns the compactor protocol.
- Test double owner remains `tests/host/fake_compaction.py`.
- `FakeContextCompactor` and `fake_compaction_proposal_from_material_json(...)` were preserved.
- No production compaction behavior or schema was changed.

Memory:

- Owner: `dayu.host.memory` owns snapshot schema and digest.
- Test construction owner remains `tests/host/memory_snapshot_factories.py`.
- No new `ConversationMemorySnapshotVNext(...)` construction was added to business tests.

## Residual Risks / Uncovered Areas

- This slice did not run the entire `tests/engine`, `tests/host`, or `tests/service` suites. It ran the required focused matrices plus the two extra Engine Agent files touched to satisfy the no-trigger invariant.
- Third-party `edgar` deprecation warnings remain in `tests/service/test_fins_direct.py`; they are unrelated to cancellation helper semantics.
- No production behavior was intentionally changed; residual risk is limited to test helper migration coverage outside the focused matrices.

## Stop Status

ready-for-controller-validation
