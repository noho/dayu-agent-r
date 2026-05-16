# P7-S1 Code Re-Review Controller Adjudication

## Scope

- Phase: Phase 7 `Tool Awaiting / resolve_wait / Wait Adapter`
- Slice: P7-S1 `Public Contracts And Durable Wait Record`
- Gate: code re-review after accepted finding fix
- Branch: `feat/host-phase7-tool-awaiting-resolve-wait`
- Inputs:
  - `docs/reviews/host-phase7-code-review-s1-controller-adjudication-20260516.md`
  - `docs/reviews/host-phase7-fix-s1-public-contracts-wait-record-20260516.md`
  - `docs/reviews/host-phase7-code-re-review-s1-mimo-20260516.md`
  - `docs/reviews/host-phase7-code-re-review-s1-ds-20260516.md`

## Verdict

PASS.

两路 re-review 均确认 P7-S1 accepted findings 已关闭，rejected / deferred findings 未被误修，未提出新的 blocking finding。

## Finding Disposition

| Finding | Prior disposition | Re-review status | Controller disposition |
| --- | --- | --- | --- |
| S1-F1: wait length constants duplicated between `api.py` and `schema.py` | accepted | fixed | closed |
| S1-F2: orphan `snapshot_digest` DDL CHECK gap | accepted | fixed | closed |
| S1-F3: adapter key regex should be duplicated in DDL | rejected | not implemented | remains rejected |
| S1-F4: deterministic CAS_LOST race coverage | deferred to P7-S4 | not implemented | remains deferred |

## Evidence

- `dayu/host/durable/schema.py` imports all `HOST_WAIT_*_MAX_LENGTH` constants from `dayu.host.api`; no local duplicate constant definitions remain in schema DDL.
- `host_wait_records` snapshot group CHECK now permits only:
  - no snapshot group: `snapshot_ref`, `snapshot_captured_at`, and `snapshot_digest` all `NULL`;
  - snapshot group present: `snapshot_ref` and `snapshot_captured_at` non-`NULL`, with optional `snapshot_digest`.
- `tests/host/test_wait_record_state.py` covers direct SQL rejection of orphan `snapshot_digest`.
- No adapter-key regex / glob DDL CHECK was added.
- No CAS_LOST deterministic race test was added in S1; this remains owned by P7-S4 where resolve / cancel races become executable.

## Validation

- Implementation validation: `pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_public_run_api.py -q` -> 84 passed.
- Implementation pyright: `python -m pyright dayu/host tests/host` -> 0 errors.
- Fix validation: `pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q` -> 15 passed.
- Fix pyright: `python -m pyright dayu/host/durable/schema.py tests/host/test_wait_record_state.py` -> 0 errors.
- `git diff --check` clean before README synchronization.

## Residual Risk

- P7-S4 must cover deterministic CAS_LOST / first-committer-wins behavior once `resolve_wait` and waiting cancel paths both mutate executable wait records.
- P7-S1 intentionally does not implement ToolRuntime awaiting behavior, public `resolve_wait` behavior, wait adapter polling, or Engine result ingestion.

## Decision

P7-S1 code gate is accepted after README synchronization and final local validation.
