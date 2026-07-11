# WU-SEMANTIC-OWNERSHIP-01 P3-J S1 Implementation - AgentCodex

## 1. Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-J - Host durable schema and weak-contract hardening backlog`
- Slice: `S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`
- Gate: implementation
- Role: AgentCodex
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Plan re-review adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-plan-rereview-controller-adjudication.md`

## 2. First-Principles / Owner Judgment

S1 动机成立。EventLog 是 Host durable truth 边界，`event_type` 被 append、projection、read API、memory、RunInputBuilder、audit 和 public event stream 消费；如果 durable row 接受任意文本，同一事实会在不同消费者处被不同解释。正确 owner 是 `dayu/host/lifecycle_events.py`，修复必须落在 producer append validation、durable row decoder 和 fresh schema DDL CHECK，而不是在下游消费者各自补 fallback。

本 slice 未发现 intentionally open-ended 的生产 EventLog append type。pre-edit scan 发现 accepted plan baseline 之外还有明确生产 append path `SESSION_CREATED` / `SESSION_CLOSED`，其语义属于 Host Session lifecycle，不是开放扩展点，因此已作为独立 category 纳入 owner。

## 3. Pre-Edit Source Scans

执行的 scan:

```bash
rg -n '_EVENT_TYPE_[A-Z0-9_]+\s*=\s*"|event_type\s*=\s*"|event_type="\w|CONTEXT_COMPACTION_[A-Z_]+\s*="' dayu/host
rg -n '_host_event_type\(EngineEventType\.|EngineEventType\.[A-Z_]+|event\.type\.value\.upper' dayu/host/engine_ingest.py
rg -n 'event_type\s*=\s*"[^"]*\.|event_type="\w|TYPE_A|TEST_EVENT|host\.test' tests/host
```

Pre-edit findings:

- Production append values matched accepted plan baseline plus `SESSION_CREATED` / `SESSION_CLOSED`.
- `CONTENT_DELTA` and `TOOL_CALL_DELTA` are recognized by `engine_ingest` as transient delta events and are not appended to EventLog.
- Tests contained arbitrary `TYPE_A`, `TYPE_B`, `DIAG_A`, `DIAG_B`, `SIGNAL_A`, `PREVIEW_B`, `host.test`, `host.nulls`, `host.other`, `TEST_EVENT`, `host.payload.accepted`, `host.artifact.accepted`, `host.multiprocess`, `host.race`, and `host.idempotent` fixtures.

## 4. Production Event Type Table After Scan

| Category | Legal production EventLog values |
|---|---|
| Session lifecycle | `SESSION_CREATED`, `SESSION_CLOSED` |
| Run lifecycle | `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_WAITING`, `RUN_CANCELLING`, `RUN_RECOVERING`, `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST` |
| Attempt lifecycle | `ATTEMPT_STARTED`, `ATTEMPT_RUNNING`, `ATTEMPT_SUCCEEDED`, `ATTEMPT_FAILED`, `ATTEMPT_CANCELLED`, `ATTEMPT_SUSPENDED`, `ATTEMPT_STEERED`, `ATTEMPT_LOST` |
| Admission / command request | `USER_INPUT_ACCEPTED`, `STEER_REQUESTED`, `RETRY_REQUESTED`, `REPLAY_REQUESTED`, `CANCEL_REQUESTED`, `RESUME_REQUESTED` |
| Tool / wait | `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED`, `TOOL_RESULT_ACCEPTED`, `TOOL_AWAITING`, `TOOL_CALLS_BATCH_READY`, `TOOL_CALLS_BATCH_DONE`, `WAIT_LATE_RESULT_REJECTED` |
| Context governance | `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED` |
| Runner input / usage | `RUNNER_CALL_INPUT_ASSEMBLED`, `RUNNER_CALL_INPUT_ITERATION_LINKED`, `USAGE_REPORTED` |
| Engine / provider diagnostic | `ENGINE_EVENT_REJECTED`, `ENGINE_EVENT_DIAGNOSTIC`, `HOST_LIFECYCLE_DIAGNOSTIC`, `PROVIDER_DIAGNOSTIC`, `PROVIDER_PROTOCOL_ERROR` |
| Preview-only Engine events | `ITERATION_STARTED`, `CONTENT_COMPLETED`, `ITERATION_COMPLETED`, `REASONING_DELTA` |

## 5. Implementation Summary

Changed production owner / boundary files:

- `dayu/host/lifecycle_events.py`
  - Preserved `HostRunEventType` and `HostAttemptEventType`.
  - Added category enums: `HostSessionEventType`, `HostAdmissionCommandEventType`, `HostToolWaitEventType`, `HostContextGovernanceEventType`, `HostRunnerInputEventType`, `HostEngineDiagnosticEventType`, `HostPreviewEventType`.
  - Added `HostEventType` union, `HOST_EVENT_TYPE_CATEGORIES`, `parse_host_event_type`, `serialize_host_event_type`, `all_host_event_type_values`, and `host_event_type_values`.
- `dayu/host/durable/event_log.py`
  - `EventLogAppendRequest` validation rejects unknown `event_type` through `parse_host_event_type`.
  - `EventLogRow` decoding rejects mutated unknown `event_type` before returning a row.
- `dayu/host/durable/schema.py`
  - Fresh schema `event_log.event_type` now has a `CHECK event_type IN (...)` generated from `all_host_event_type_values()`.
  - `HOST_SCHEMA_VERSION` moved from `21` to `22`.

Changed test / fixture files:

- `tests/host/test_lifecycle_events.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_durable_concurrency_matrix.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_durable_transaction.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_artifact_store.py`
- `tests/host/test_storage_orphan_proof.py`
- `tests/host/test_event_log_multiprocess.py`
- `tests/host/test_idempotency_store.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_wait_record_state.py`

## 6. Fixture Migration Summary

- Generic canonical EventLog fixtures now use `USER_INPUT_ACCEPTED`.
- Distinguishing secondary canonical type fixtures use `RUN_ACCEPTED`.
- Diagnostic fixtures use `ENGINE_EVENT_DIAGNOSTIC` or `PROVIDER_DIAGNOSTIC`.
- Preview fixture in public event stream uses `REASONING_DELTA`; `CONTENT_DELTA` remains transient and is not an EventLog legal value.
- Projection signal fixture uses `USAGE_REPORTED`.
- Lowercase dotted storage / multiprocess / idempotency fixtures were migrated to legal Host EventLog values.
- Arbitrary illegal values remain only in explicit rejection tests: `INVALID_TEST_EVENT_TYPE` and `INVALID_MUTATED_EVENT_TYPE`.

## 7. DDL CHECK Status

Fresh schema status: enabled.

DDL source of truth: `dayu/host/durable/schema.py` imports `all_host_event_type_values()` from the owner and renders the value set into the `event_log.event_type` CHECK. No old DB compatibility or migration path was added, consistent with S1 non-goals and schema-change constraints.

Tests added:

- append rejection for unknown event type;
- row decoder rejection for a manually mutated row after bypassing SQLite CHECK with `PRAGMA ignore_check_constraints=ON`;
- fresh schema DDL rejection for unknown event type;
- lifecycle owner full legal set / parse / serialize round-trip coverage.

## 8. Propagation Audit

Producer -> validation:

- Existing producers continue passing durable text, but `EventLogAppendRequest` validation now parses through `lifecycle_events.py`. Invalid producer values fail before encoding, digesting, or writing.

Validation -> persistence:

- Valid append requests persist the same SQLite text representation.
- Fresh DB rejects unknown `event_type` even for direct SQL insert attempts.

Persistence -> row decoder:

- All EventLog read paths that return `EventLogRow` go through `_event_log_row_from_host_row`, which parses `event_type` via the same owner before returning.
- Mutated durable rows fail closed as `HostDurableError`.

Row decoder -> public / projection / LLM-facing consumers:

- Projection runner, public event stream, RunInputBuilder, memory, tool trace, audit and read APIs keep consuming `EventLogRow.event_type` text, but no valid `EventLogRow` can now carry an unknown type.
- No consumer-wide redirection was performed; local comparisons remain in place where they are not necessary for invalid write/read rejection.
- LLM-facing RunInputBuilder / memory benefit from append and decoder closure because unknown committed event types cannot be returned as valid input material.

## 9. README Decision

- `dayu/host/README.md` was checked. No update: this slice hardens internal Host durable schema and row-decoder invariants without changing the documented public Host API or developer workflow.
- `tests/README.md` was checked. No update: tests remain in existing Host durable/projection command groups; no new stable test command group or maintenance convention was introduced.

## 10. Validation

Required validation:

```bash
source .venv/bin/activate
pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_schema.py -q
```

Result: `97 passed in 0.95s`.

```bash
source .venv/bin/activate
pytest tests/host/test_state_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_public_event_stream.py -q
```

Result: `91 passed in 0.95s`.

Additional fixture validation:

```bash
source .venv/bin/activate
pytest tests/host/test_event_log_multiprocess.py tests/host/test_idempotency_store.py tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_storage_orphan_proof.py -q
```

Result: `48 passed in 1.42s`.

Type / whitespace validation:

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: pass.

## 11. Post-Implementation Source Scans

Required scans:

```bash
rg -n '_EVENT_TYPE_[A-Z0-9_]+\s*=\s*"|event_type\s*=\s*"|event_type="' dayu/host tests/host
rg -n 'TYPE_A|TEST_EVENT|host\.test|event_type\s*=\s*"[^"]*\.' tests/host dayu/host
```

Scan summary:

- First scan returns existing production and test event type constants / assignments. Values are either legal owner values or explicit invalid rejection cases.
- Second scan returns expected false positives because `TYPE_A` matches the substring inside `ATTEMPT_*` identifiers. It also returns the explicit invalid rejection cases.

Precision follow-up scans:

```bash
rg -n '"TYPE_A"|"TEST_EVENT"|"host\.test"|event_type\s*=\s*"[^"]*\.' tests/host dayu/host
rg -n '"host\.(multiprocess|race|idempotent|payload\.accepted|artifact\.accepted|nulls|other|test)"' tests/host dayu/host
```

Result: no matches.

Additional non-EventLog projection fixture scan:

```bash
rg -n 'event_type\s*=\s*"(CONTENT_DELTA|TOOL_CALL_DELTA|FUTURE_PROGRESS|PREVIEW_DELTA)"|_EVENT_TYPE_PREVIEW_DELTA' tests/host dayu/host
```

Remaining matches are direct projection/activity/audit fixtures that do not append through EventLog and do not exercise fresh schema DDL. `CONTENT_DELTA` and `TOOL_CALL_DELTA` remain non-persisted transient Engine events in production ingest.

## 12. Residual Risks / Open Questions

- No blocking open questions.
- Residual diagnostic-only risk: the broad required scan pattern is noisy because `TYPE_A` is a substring of `ATTEMPT_*`. Precision scans show the arbitrary `"TYPE_A"` fixture was removed.
- This slice intentionally did not redirect every consumer comparison to the new owner; that is a non-goal unless review finds a concrete downstream drift.
