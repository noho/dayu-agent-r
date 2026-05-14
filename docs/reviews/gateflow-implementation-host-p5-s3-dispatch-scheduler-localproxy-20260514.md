# Gateflow Implementation Artifact: Host P5-S3 Dispatch Scheduler, Lane And LocalProxy

## Gate

- Work unit: Host Phase 5 RunInputBuilder local dispatch
- Slice: P5-S3 Dispatch Scheduler, Lane And LocalProxy
- Role: implementation
- Branch: `feat/host-phase5-local-dispatch`
- Design source: `docs/host/design.md` §17 / §22
- Approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S3, §3.4, §3.5, §4 cancel boundary

## Changed Files

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/dispatch.py`
- `dayu/host/local_proxy.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_command_handle.py`

## Implemented Plan Items

- Added typed local execution contracts:
  - `HostLocalExecutionOptions`
  - `LocalEngineWorkerFactory`
  - `LocalEngineWorker`
  - `LocalWorkerHandle`
- Added `HostDispatchScheduler`:
  - accepts `PendingDispatchRecord` wakeups;
  - marks dispatch `pending -> waiting_for_lane`;
  - acquires runtime lane capacity through `dayu.runtime.lane`;
  - performs durable recheck before `waiting_for_lane -> dispatching`;
  - releases lane token on CAS/recheck loss, pre-accept cancellation, startup timeout, worker stream completion, and close.
- Added LocalProxy default worker:
  - uses `dayu.engine.run_agent_messages(request)`;
  - exposes worker handle event stream;
  - keeps cancellation best-effort and does not treat dispatch/lane as active worker truth.
- Added worker accept primitive inside scheduler:
  - appends `ATTEMPT_RUNNING`;
  - CAS updates Attempt `STARTING -> RUNNING`;
  - records dispatch worker accept refs while keeping dispatch status `dispatching`;
  - includes P5-S3 residual payload fields: `local_worker_id`, `worker_accepted_at`, `lane_name`, `lane_claim_id`.
- Added startup timeout closeout:
  - lane acquire timeout closes STARTING Attempt and Run as `FAILED`;
  - worker accept timeout closes STARTING Attempt and Run as `FAILED`;
  - reason is `worker_startup_timeout`.
- Kept command-handle default behavior unchanged:
  - `HostCommandHandleOptions.local_execution` defaults to `None`;
  - existing command handle tests still exercise no-op dispatch wakeup behavior.
- Updated Host import-boundary test to allow Host -> Engine dependency, which is required by P5-S3 LocalProxy and still keeps Fins / Service / UI excluded.

## Tests Added Or Updated

- `tests/host/test_dispatch_scheduler.py`
  - pending dispatch reaches waiting/dispatching and worker accept marks Attempt RUNNING;
  - `ATTEMPT_RUNNING` payload contains local worker and lane diagnostics;
  - pre-accept cancelled dispatch skips worker call;
  - lane acquire timeout closes Run/Attempt as FAILED without calling worker;
  - worker startup timeout closes Run/Attempt as FAILED.
- `tests/host/test_local_proxy_engine_ingest.py`
  - default LocalProxy worker calls `run_agent_messages` and exposes the EngineEvent stream.
- `tests/host/test_command_handle.py`
  - import-boundary expectation updated for the new Host -> Engine dependency.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q`
  - Result: passed, `27 passed in 0.72s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Scope Notes

- Did not implement EngineEvent terminal ingest mapping or terminal closeout from Engine events; this remains P5-S4.
- Did not implement full active/session-scope cancel propagation; this remains P5-S5.
- Did not implement ToolRuntime, WAITING, RemoteProxy, recovery, lease/fencing/takeover, or Engine changes.
- Dispatch `dispatching` and lane token remain diagnostic/capacity facts only. Active worker truth starts only after durable `ATTEMPT_RUNNING`.
- Lane acquire cancellation is treated as scheduler close/cancel path and is skipped without FAILED closeout; only `LaneAcquireTimedOut` maps to `worker_startup_timeout` closeout.

## Residual Risks

- `AcceptWorkerRunningInput` in `dayu/host/durable/run_transition.py` still lacks the new P5-S3 residual fields because that file is outside this slice allowlist. The scheduler-owned accept primitive writes the required full `ATTEMPT_RUNNING` payload for the implemented local path.
- `HostCommandHandleOptions.local_execution` is typed and defaulted to `None`, but public command-handle construction still keeps local execution disabled by default. Full command-handle scheduler lifecycle wiring should be completed when the controller opens that scope explicitly.
- README was not updated even though `dayu/host/` changed, because this slice's allowed files did not include README files.

## Stop Status

- No stop condition triggered for fresh schema compatibility, owner truth misuse, or required Engine changes.
- Implementation is ready for code review gate.
