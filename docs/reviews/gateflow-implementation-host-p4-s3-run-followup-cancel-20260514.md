# Gateflow Implementation Artifact: Host P4-S3 Run Follow-up Cancel

- gate: Phase 4 implementation
- slice: P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset
- design truth: `docs/host/design.md`
- accepted plan: `docs/host/phase4-public-api-command-path-plan.md`
- baseline: P4-S2 accepted slice commit `190d905`
- status: completed

## Scope Correction

Controller review identified blocking scope creep: the first implementation included public `get_run` and `stream_run_events`, which belong to P4-S4 read/event stream scope, not P4-S3. This artifact has been corrected to describe the narrowed P4-S3 implementation only. The public read/event stream facade and package exports were removed from this slice, and tests now inspect returned command snapshots or durable state directly where needed.

## Changed Files

- `dayu/host/command.py`
- `dayu/host/admission.py`
- `dayu/host/durable/state.py`
- `dayu/host/__init__.py`
- `dayu/host/README.md`
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_package_exports.py`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p4-s3-run-followup-cancel-20260514.md`

`tests/host/test_package_exports.py` was updated as a direct fixture consequence of exporting the new public Run facade from `dayu.host`; leaving it stale made the existing package export test fail.

## Implemented Items

- Added public `start_run(host, request) -> RunSnapshot` backed by `HostAdmissionService.start_run`.
- Preserved `start_run` active policies:
  - no active direct `RUNNING`;
  - active `queue`;
  - active `reject`;
  - active `attach_active` returning current `RunSnapshot` without canonical attach EventLog fact.
- Added public `submit_followup(host, session_id, request) -> FollowupSnapshot`.
  - Validates path `session_id == request.session_id`; mismatch raises `INVALID_STATE`.
  - `QUEUE` calls `HostAdmissionService.submit_followup_queue`.
  - `STEER` raises `UNSUPPORTED_OPERATION` with `retryable=False` before EventLog append.
- Added public `cancel_run(host, run_id, request) -> RunSnapshot`.
  - Queued and pre-dispatch `STARTING` paths reuse internal admission cancel.
  - Deferred cancel states are mapped to `UNSUPPORTED_OPERATION`; terminal or true invalid preconditions remain `INVALID_STATE`.
- Added internal `HostAdmissionService.cancel_session_runs` Phase 4 subset.
  - Uses idempotency scope `(cancel_session_runs, session_id, request.client_request_id)`.
  - Semantic digest includes session id, context digest, reason and mode, and excludes the dynamic Run list.
  - Reads all non-terminal Runs in a single write transaction before appending cancel facts.
  - Rejects unsupported non-terminal Runs with `UNSUPPORTED_OPERATION` before mutation.
  - Cancels queued Runs with `CANCEL_REQUESTED` + `RUN_CANCELLED`.
  - Cancels pre-dispatch `RUNNING` / `STARTING` / pending dispatch Runs with `CANCEL_REQUESTED` + `ATTEMPT_CANCELLED` + `RUN_CANCELLED`.
  - Does not trigger queue promotion.
  - Idempotent replay returns current `SessionSnapshot` and does not cancel Runs accepted after the first operation.
  - Empty supported set records session-scope idempotency without creating cancel events.
- Added state helpers:
  - `read_non_terminal_runs_for_session`
- Kept `run_snapshot_from_row` so P4-S3 command facade can return `RunSnapshot` without exposing a public Run read facade.
- Updated Host README and tests README for current public command path facts.

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q`
  - passed: 37 tests
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - passed: 0 errors
- `git diff --check`
  - passed
- Additional affected-test check:
  - `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`
  - passed: 5 tests
- Additional full Host regression check:
  - `source .venv/bin/activate && pytest tests/host -q`
  - passed: 191 tests

## Residual Risks

- Phase 4 `cancel_session_runs` is intentionally not final cancel semantics. Phase 5 owns dispatching / active worker cancel propagation, Phase 7 owns `WAITING` cancel, and Phase 11 owns `RECOVERING` cancel.
- Public `submit_followup(queue)` currently uses a Host facade default execution target because `SubmitFollowupRequest` has no public `resolved_execution_target` field and policy provider integration is outside this slice. A later policy-provider slice should replace this default with explicit Host policy resolution output.
- Public `get_run` and `stream_run_events` are intentionally not implemented or exported in this slice; P4-S4 owns that read/event stream work.
