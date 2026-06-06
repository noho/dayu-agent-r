# WU-TOOLS-01 S4 Ingestion Blocker

Gate: implementation
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Agent: AgentCodex
Status: blocker documented; ingestion tools not migrated in S4

## Affected Tools

OLD source: `/Users/leo/workspace/dayu-agent/dayu/fins/tools/ingestion_tools.py`

- `start_financial_filing_download_job`
- `get_financial_filing_download_job_status`
- `cancel_financial_filing_download_job`
- `start_financial_document_preprocess_job`
- `get_financial_document_preprocess_job_status`
- `cancel_financial_document_preprocess_job`

## Direct Evidence

- `register_ingestion_tools(...)` registers `start/status/cancel` job tools, not a single synchronous completed/failed tool.
- Start tools return a job snapshot and instruct the model to poll status until terminal state.
- Status tools use `DupCallSpec(mode="poll_until_terminal", status_path="job.status", terminal_values=["succeeded", "failed", "cancelled"])`.
- Cancel tools state that cancellation is not immediately complete and require follow-up status polling.
- `/Users/leo/workspace/dayu-agent/dayu/fins/ingestion/job_manager.py` creates `_IngestionJob` records with statuses `queued`, `running`, `cancelling`, `succeeded`, `failed`, `cancelled`.
- `IngestionJobManager._start_job(...)` enqueues job ids and returns immediately with `started` or `reused_active_job`.
- `IngestionJobManager._ensure_worker_started_locked(...)` starts daemon worker threads.
- `_worker_loop(...)` executes jobs later; `_run_download_job(...)` and `_run_process_job(...)` consume async event streams and update snapshots.

## Why Current Completed / Failed Mapping Is Insufficient

Current `ToolRuntime` completed/failed outcomes describe the result of one tool execution. OLD ingestion start tools do not complete the requested download or preprocessing operation; they only acknowledge that a background job was queued or reused.

Mapping `start_*_job` to `ToolCompletedOutcome` would falsely tell Host/Engine that the business operation completed. Mapping it to `ToolFailedOutcome` would be incorrect for a valid queued/running job. Status polling is also semantic, not just duplicate governance: it needs durable waiting, cancellation, late result handling, and resume semantics.

## Required Fins Awaiting Adapter

Ingestion needs a Fins provider / adapter slice that maps the OLD background job model into the current Host / Engine awaiting contract. The base `ToolAwaitingOutcome`, wait record, resume, cancellation and late terminal governance already exist; the missing work is the Fins ingestion migration into that contract.

The adapter must represent:

- accepted start request with a durable job or wait handle;
- suspended/awaiting tool outcome while background work continues;
- status polling or callback integration owned by Host/ToolRuntime governance;
- cancellation propagation from Host cancel to the background job;
- late terminal result ingestion and resume/closeout;
- deterministic mapping from terminal `succeeded` / `failed` / `cancelled` to current tool outcomes.

## Proposed Owner / Destination

Owner: `WU-TOOLS-01-F01`.

Destination: Fins ingestion provider / adapter migration using current `ToolAwaitingOutcome` and Host wait-resume contract. Production callback / poller / physical cancel hardening may depend on #89 / #90 / #92 as needed, but the residual owner is the Fins ingestion migration work unit.

## Later Work Unit Needed

Yes. `WU-TOOLS-01-F01` is needed to migrate Fins ingestion tools into the current awaiting contract. S4 therefore migrates read tools only and makes `include_ingestion_tools=true` fail closed in `dayu.fins.tools.provider`.

## Residual Risk

classified as assigned to `WU-TOOLS-01-F01`: users cannot invoke Fins download / preprocessing tools through current provider until the OLD ingestion job model is adapted to current Host / Engine awaiting semantics.
