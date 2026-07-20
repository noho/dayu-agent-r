# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-B`.
- Gate: S1 implementation controller validation.
- Accepted plan commit: `77c15e15`.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-implementation-codex.md`.

## Independent judgment

The implementation is placed at the semantic owner and its direct projection boundaries. `_terminal_answer.py` now owns required and optional source selection; Outbox and live HostEvent consume the required contract in their existing durable transactions. Durable/public validators reject `succeeded` without an answer and reject an answer on non-success. No UI, Service, memory-consumer special case, schema migration, compatibility wrapper, callback seam, or second descriptor parser was added.

## Validation

```text
pytest tests/host/test_terminal_payload.py \
  tests/host/test_read_api_terminal_policy.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_open_host_options.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py -q
71 passed
```

```text
pytest tests/host/test_engine_ingest_mapping.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_projection_runner.py -q
305 passed
```

```text
pyright
0 errors, 0 warnings, 0 informations
```

- `git diff --check`: clean.
- Outbox private inline-answer parser scan: zero matches.
- Read API private descriptor/SQLite parser scan: zero matches.
- Required resolver consumers: exactly Outbox materialization and succeeded HostEvent projection.
- Agent coverage evidence: affected production files 90%-96%; combined 92%. Coverage-instrumented multiprocessing failures were isolated to unmodified executor tests, which passed separately (`61 passed`).

## Propagation audit

```text
Engine FinalAnswerData
  -> terminal descriptor + RUN_SUCCEEDED refs/canonical metadata
  -> required terminal-answer resolver
  -> live HostEvent + Outbox row/public read/drain

same optional resolver
  -> durable memory typed material + compact material + run input
```

Descriptor failure rolls back Outbox insertion and checkpoint advancement; a separate projection failure records the cause. Test-only restoration of the same descriptor identity permits retry, after which replay is duplicate and item identity remains singular. Failed/cancelled/lost paths never promote forged answer material.

## Decision

- Implementation validation: pass.
- Accepted source findings: implemented, pending independent code review.
- Blocking open question: none.
- Next gate: parallel S1 code review by AgentMiMo and AgentDS.
