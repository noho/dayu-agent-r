# WU-SEMANTIC-OWNERSHIP-01 P3-J S2 Controller Validation

## Scope

- Sub-WU: P3-J S2 Queue Policy Owner And RunResult Terminal Row Surface.
- Base before implementation: `7eb9f128`.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s2-implementation-codex.md`.

## Owner Boundary

- Queue policy fact owner: `dayu.host.queue_policy`.
- Queue policy validation owner: public `StartRunRequest`, admission branch selection, durable run transition validation, durable `RunRow` decode / insert validation.
- Queue policy persistence owner: fresh `host_runs.queue_policy` schema CHECK, derived from the owner helper.
- RunResult terminal status owner: Host `RunStatus` terminal subset at the durable minimal read-model row boundary.
- RunResult text serialization owner: `serialize_run_result_terminal_status(...)` at SQLite / stable text comparison boundaries.

S2 keeps `execution_target` as deployment-resolved non-empty text and does not invent a closed set.

## Controller Review

- `dayu/host/queue_policy.py` defines the three-value closed set: `queue`, `reject`, `attach_active`.
- `AdmissionPolicy` was deleted; final scans found no residual reference and no compatibility alias/re-export pattern.
- `StartRunRequest.__post_init__` now validates queue policy through the owner helper.
- Admission branch logic consumes `RunQueuePolicy` enum values instead of local strings.
- Durable run transition and durable state insert/decode validate through the owner helper.
- `host_runs.queue_policy` fresh schema DDL uses owner values in a CHECK constraint; `HOST_SCHEMA_VERSION` is 23.
- `RunResultRow.terminal_status` is typed as `RunStatus`; SQLite write/read paths serialize/parse at the durable read-model boundary.
- `dayu/host/README.md` update is within its Agent update constraints: it documents the now-stable Host queue policy owner / durable CHECK behavior.

Controller accepted the implementation choice to leave `RunRow.queue_policy` as normalized text. `RunRow` is still a durable row snapshot and public snapshots preserve text. The owner closure is enforced at public input, admission, durable insert, durable decode, EventLog payload serialization, and DDL; typing `RunRow.queue_policy` itself would broaden fixture and public snapshot migration beyond the S2 plan.

## Propagation Audit

- Produce: public `StartRunRequest` and admission operations parse legal queue policy before transaction logic.
- Branch: active-run handling branches on `RunQueuePolicy.REJECT` / `RunQueuePolicy.ATTACH_ACTIVE`; ordinary queue paths use `RunQueuePolicy.QUEUE`.
- Persist: `host_runs.queue_policy` CHECK rejects unknown values on fresh schemas.
- Decode: `run_row_from_host_row(...)` rejects externally mutated queue policy values before downstream consumers see a valid `RunRow`.
- EventLog: run accepted payload serializes queue policy through the owner helper.
- Project: `RunResultRow.terminal_status` is returned as typed `RunStatus`; public/output text uses serializer or existing Host terminal projection.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_state_schema.py tests/host/test_durable_schema.py tests/host/test_projection_read_model.py -q` -> 146 passed.
- `source .venv/bin/activate && pytest tests/host/test_compact_pipeline.py tests/host/test_accepted_result_projection.py tests/host/test_compact_material.py -q` -> 81 passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.
- `rg -n 'AdmissionPolicy' dayu tests` -> no matches.
- `rg -n 'RunQueuePolicy\s*=|AdmissionPolicy\s*=|from dayu\.host\.admission import AdmissionPolicy' dayu tests` -> no matches.
- `rg -n 'queue_policy="[^"]+"|queue_policy = "[^"]+"' dayu/host tests/host` -> only legal values plus explicit `queue_policy="unknown"` invalid-policy test.

## README Decision

- `dayu/host/README.md`: updated because Host admission / durable schema now expose stable queue-policy owner and DDL CHECK behavior.
- `tests/README.md`: no update. S2 changes existing Host durable/admission tests and does not add a new stable test layer or maintenance command.

## Residual Risk

- Existing schema-22 databases are out of scope under the fresh-schema policy.
- Future queue policy values must be added to `dayu.host.queue_policy` before any request, durable row, or schema can accept them.
