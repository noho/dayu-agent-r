# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate validation before aggregate deepreview
- Accepted plan commit: `f91cd6d5`
- Accepted slice commits:
  - S1: `a63a27c7`
  - S2: `2b2718a2`
  - S3: `e8f32b77`
  - S4: `9ffb1a3d`

## Owner Closure Summary

- S1 closes EventLog event-type append / decoder / fresh-schema DDL owner.
- S2 closes queue-policy owner and typed `RunResultRow.terminal_status` row surface.
- S3 closes idempotency scope/result kind Python owner validation and payload descriptor-kind owner / producer / expected-kind consumer validation.
- S4 removes runtime public exposure of removed config filenames and re-owns the remaining `dayu-cli init` fail-fast guard to CLI.

## Validation Matrix

- `source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_schema.py -q`
  - Result: `98 passed`
- `source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_public_event_stream.py -q`
  - Result: `91 passed`
- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_projection_read_model.py tests/host/test_idempotency_store.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q`
  - Result: `137 passed`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_durable_concurrency_matrix.py -q`
  - Result: `250 passed`
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q`
  - Result: `66 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Source Scans

- `rg -n 'AdmissionPolicy|legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests README.md`
  - Result: no matches.
- `rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py`
  - Result: no matches.
- `rg -n '\\bTYPE_A\\b|\\bTEST_EVENT\\b|host\\.test|event_type\\s*=\\s*"[^"A-Z_][^"]*"' tests/host dayu/host`
  - Result: only invalid-event tests and test helper import-name noise; no production append path or arbitrary lowercase/dotted EventLog fixture remains.
- `rg -n 'queue_policy="[^\"]+"|queue_policy = "[^\"]+"|AdmissionPolicy' dayu/host tests/host`
  - Result: legal queue-policy test literals plus one `queue_policy="unknown"` negative test; no `AdmissionPolicy` match.
- `rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES' dayu tests README.md`
  - Result: no matches.

## README Decisions

Slice-local README decisions were accepted:

- S1/S2/S3 checked `dayu/host/README.md` and `tests/README.md`; no stable developer-manual or test-guidance update was needed beyond existing coverage.
- S4 checked `dayu/config/README.md`; it already documents current config files and deletion / no compatibility read for old `llm_models.json` / `run.json`.
- Root `README.md` was not triggered by S4 because user-visible init/config behavior did not change.

## Residual Risk

- Historical old-config filename references remain in design, review archive, and Engine migration/negative tests. They are not runtime public exposure and are outside P3-J S4 scope.
- Direct SQL corruption / historical-row tests can still construct invalid durable rows to prove fail-closed or retention behavior; production owner write paths reject them.
- Queue-policy tests still use legal string literals at public request boundaries because those public APIs accept user text and parse through `RunQueuePolicy`.

## Aggregate Deepreview Handoff

Review scope should be current branch relative to `f91cd6d5`, excluding unrelated dirty / untracked files:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/cli_ci.md`
- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/reviews/code-review-20260710-135625.md`
- `docs/reviews/code-review-20260710-141049.md`
