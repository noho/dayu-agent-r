# WU-SEMANTIC-OWNERSHIP-01 P3-J S2 Implementation

## Gate / Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-J`
- Slice: `S2 - Queue Policy Owner And RunResult Terminal Row Surface`
- Gate: implementation
- Agent: Codex
- Base noted by user: `7eb9f128`
- Accepted plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`

## Stop-Condition Scans Before Edit

Command:

```bash
rg -n 'AdmissionPolicy' dayu tests
```

Output:

```text
dayu/host/admission.py:179:class AdmissionPolicy(StrEnum):
dayu/host/admission.py:951:    policy: AdmissionPolicy
dayu/host/admission.py:1018:        if self.policy == AdmissionPolicy.REJECT:
dayu/host/admission.py:1024:        if self.policy == AdmissionPolicy.ATTACH_ACTIVE:
dayu/host/admission.py:1132:                queue_policy=AdmissionPolicy.QUEUE.value,
dayu/host/admission.py:1144:            queue_policy=AdmissionPolicy.QUEUE.value,
dayu/host/admission.py:2811:            queue_policy=AdmissionPolicy.QUEUE.value,
dayu/host/admission.py:2824:            queue_policy=AdmissionPolicy.QUEUE.value,
dayu/host/admission.py:3423:def _parse_admission_policy(queue_policy: str) -> AdmissionPolicy:
dayu/host/admission.py:3432:        return AdmissionPolicy(queue_policy)
```

Command:

```bash
rg -n 'RunQueuePolicy\s*=|AdmissionPolicy\s*=|from dayu\.host\.admission import AdmissionPolicy' dayu tests
```

Output: no matches.

Decision: no production consumer outside `dayu/host/admission.py` imported or depended on `AdmissionPolicy`; deletion proceeded without alias, re-export, wrapper, or compatibility path.

## Changed Files

- `dayu/host/queue_policy.py`
- `dayu/host/api.py`
- `dayu/host/admission.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/read_model.py`
- `dayu/host/README.md`
- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_compact_material.py`

Note: `dayu/host/read_model.py` is the direct producer constructing `RunResultRow`; the typed row surface cannot be completed without changing that immediate projection boundary. Existing unrelated dirty files (`AGENTS.md`, `CLAUDE.md`, CLI CI docs/review files) were not modified by this slice.

## Owner Boundary

- `queue_policy` owner is now `dayu.host.queue_policy`.
- Legal values are exactly `queue`, `reject`, and `attach_active`.
- `execution_target` remains deployment-resolved non-empty text; no closed set was introduced.
- `RunResultRow.terminal_status` is now typed at the durable read-model row boundary as `RunStatus`.

## Queue Policy Owner

Added:

- `RunQueuePolicy`
- `parse_run_queue_policy(value: str) -> RunQueuePolicy`
- `serialize_run_queue_policy(policy: RunQueuePolicy) -> str`
- `run_queue_policy_values() -> tuple[str, ...]`

Propagation:

- Public `StartRunRequest` validates `queue_policy` through `parse_run_queue_policy`.
- Admission parses once and consumes `RunQueuePolicy` for `queue`, `reject`, and `attach_active` decisions.
- Durable transition and state validation parse through the owner; SQLite/EventLog text boundaries serialize through the owner.
- Legacy `AdmissionPolicy` was deleted rather than aliased.

## AdmissionPolicy Deletion Scan

Final command:

```bash
rg -n 'AdmissionPolicy' dayu tests
```

Output: no matches.

Final compatibility scan:

```bash
rg -n 'RunQueuePolicy\s*=|AdmissionPolicy\s*=|from dayu\.host\.admission import AdmissionPolicy' dayu tests
```

Output: no matches.

## Terminal Status Row Surface

- `dayu.host.durable.read_model.RunResultRow.terminal_status` changed from `str` to `RunStatus`.
- SQLite storage still writes text through `serialize_run_result_terminal_status(...)`.
- SQLite row decode parses text into typed `RunStatus` and rejects unknown or non-terminal values.
- Minimal read model projection now passes the typed `RunStatus` returned by `run_status_for_terminal_event(...)`.
- Existing `host_run_results.terminal_status` CHECK was preserved.

## Schema Change

- `HOST_SCHEMA_VERSION` changed from `22` to `23`.
- Fresh `host_runs.queue_policy` DDL now has:
  - `CHECK (queue_policy IN ('queue', 'reject', 'attach_active'))`
  - values are generated from `run_queue_policy_values()`.
- `host_runs.execution_target` remains `TEXT NOT NULL`.
- Added a schema test that verifies DDL owner values and that SQLite rejects `invalid_policy`.

## Tests Run

```bash
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_state_schema.py tests/host/test_durable_schema.py tests/host/test_projection_read_model.py -q
```

Result: `146 passed in 1.25s`.

Extra affected fixture validation:

```bash
source .venv/bin/activate && pytest tests/host/test_compact_pipeline.py tests/host/test_accepted_result_projection.py tests/host/test_compact_material.py -q
```

Result: `81 passed in 0.62s`.

## Pyright Result

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Pyright printed a version availability warning only: `v1.1.409 -> v1.1.411`.

## Diff Check

```bash
git diff --check
```

Result: no output.

## README Decision

- Read `dayu/host/README.md` Agent update constraints.
- Updated `dayu/host/README.md` because Host admission and durable schema now expose a stable queue policy owner and DDL CHECK.
- Read `tests/README.md` Agent update constraints.
- Did not update `tests/README.md`: no new test layer, command category, or maintenance convention was introduced.

## Source Scans

Final command:

```bash
rg -n 'queue_policy="[^"]+"|queue_policy = "[^"]+"' dayu/host tests/host
```

Result summary:

- Remaining literals are legal `queue`, `reject`, and `attach_active` fixtures, plus `queue_policy="unknown"` in `tests/host/test_admission_queue.py` for the explicit invalid-policy rejection test.
- Old invalid fixture value `fifo` was removed from compact/material projection tests.

Final command:

```bash
rg -n 'AdmissionPolicy' dayu tests
```

Result: no matches.

## Propagation Audit

- Public request boundary: `StartRunRequest.__post_init__` fails fast on invalid queue policy.
- Admission boundary: active-run policy branch uses `RunQueuePolicy` enum, not local text constants.
- Durable state boundary: `RunRow` decode, insert, and Python validation parse/serialize through queue policy owner.
- Durable transition boundary: Run accepted EventLog payload serializes queue policy through owner.
- Schema boundary: `host_runs.queue_policy` fresh schema CHECK derives from owner helper.
- Read-model boundary: `RunResultRow.terminal_status` is typed `RunStatus`; SQLite text remains behind one serializer helper.
- Fixture audit: arbitrary `fifo` queue policy fixtures were migrated to legal `queue`.

## Residual Risks

- No blocker.
- `queue_policy` remains a text field in `RunRow` because the accepted slice only required durable row validation through the owner; typing the durable run row itself would force broad unrelated fixture migration outside the S2 allowed scope. The owner still validates decode/insert and fresh DDL.
- Existing databases are treated under the project fresh-schema rule; no compatibility migration was added.
