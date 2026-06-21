# WU-TOOLS-01-F01-03 Production Fins Ingestion Plan

## Metadata

- Work unit: `WU-TOOLS-01-F01-03 Production Fins CN/SEC Download And Upload Runtime/Tool Migration`
- Gate: plan only
- Date: 2026-06-09
- Branch observed by plan gate: `phase/wu-tools-01-f01-03`
- Artifact path: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Goal confirmation source: `docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md`
- Current gate constraint: only this plan artifact may be created or updated. Do not implement, review, commit, push, open PR, or modify GitHub Issues in this gate.

## Goal

Migrate the proven OLD SEC / CN / HK downloader and SEC / CN download-upload workflow capability into the NEW shared Fins runtime and tool surface.

The implementation target is:

- SEC, CN, and HK production download can be started through `FinsIngestionRuntime.start_download(...)` and through the existing awaiting tool path.
- SEC and CN upload can be started through a new `FinsIngestionRuntime.start_upload(...)` and a new awaiting tool provider.
- Future CLI / CI / tool callers use the same `DefaultFinsRuntime` and `FinsIngestionRuntime` path instead of copying download or upload business rules.
- All source / processed document writes continue to go through `dayu.fins.storage`.
- All ticker and market decisions continue to go through `dayu.fins.ticker_normalization`.
- Upload is treated as a long transaction: the tool starts a durable Fins ingestion job and returns `ToolAwaitingOutcome` with `ToolAwaitKind.EXTERNAL_JOB`; Host wait-resume observes the Fins job through the Fins wait adapter.

## Motivation

The motivation is valid and not overestimated.

Direct NEW evidence shows a real production gap:

- `dayu/fins/ingestion_runtime.py` defines `FinsIngestionOperationKind` with only `DOWNLOAD` and `PREPROCESS`.
- `FinsIngestionRuntime.create(...)` accepts `download_adapters`, but `DefaultFinsRuntime.get_ingestion_runtime()` creates the runtime without production adapters.
- `FinsIngestionRuntime._select_download_adapter(...)` requires an exact `(source, market)` adapter and fails unsupported download jobs when no adapter exists.
- `dayu/fins/tools/download_tools.py` and `dayu/fins/tools/preprocess_tools.py` expose awaiting start tools, but there is no upload tool.
- `dayu/fins/ingestion/wait_adapter.py` binds only `start_fins_download` and `start_fins_preprocess`.
- `dayu/config/tool_discovery.json` has `financial-read-tools`, `financial-download-tools`, and `financial-preprocess-tools`, but no upload provider.

Direct OLD evidence shows the capability already exists and should be migrated, not reinvented:

- OLD `dayu/fins/downloaders/sec_downloader.py` contains `SecDownloader`, `RemoteFileDescriptor`, `DownloaderEvent`, SEC ticker / CIK lookup, submissions fetch, archive index fetch, file download, retry, conditional request, and SEC throttling logic.
- OLD `dayu/fins/downloaders/cninfo_downloader.py` contains `CninfoDiscoveryClient` for CN company resolution, report candidate selection, CNInfo PDF download, category mapping, title filtering, pagination, retry, and PDF validation.
- OLD `dayu/fins/downloaders/hkexnews_downloader.py` contains `HkexnewsDiscoveryClient` for HK stock mapping, title search, report period inference, language handling, PDF download, retry, and validation.
- OLD `dayu/fins/pipelines/sec_pipeline.py` routes SEC download through `FinsIngestionService` and `sec_download_workflow`, and upload through `sec_upload_workflow`.
- OLD `dayu/fins/pipelines/cn_pipeline.py` routes CN/HK download through `cn_download_workflow`, and upload through `DoclingUploadService` plus CN-specific filing/material id rules.
- OLD `dayu/fins/pipelines/sec_upload_workflow.py` and `docling_upload_service.py` implement upload action resolution, company meta upsert, overwrite reset, Docling conversion, source document upsert/delete, file event mapping, and result normalization.
- OLD tests under `/Users/leo/workspace/dayu-agent/tests/fins/` cover downloader behavior, SEC/CN pipeline download, SEC/CN upload, Docling upload service, path/file validation, overwrite/skip/delete, and pipeline event boundaries.

Therefore the correct implementation path is OLD-to-NEW migration with typed contract adaptation. Rewriting the downloader or pipeline business rules in NEW runtime or tools would be higher risk and would discard existing tested semantics.

## Success Signals

- `start_fins_download` starts real SEC/CN/HK download jobs for supported markets and unsupported source/market combinations fail with clear terminal job evidence.
- `start_fins_upload` starts real SEC/CN filing/material upload jobs and returns an awaiting external-job outcome without blocking the Engine tool handshake on Docling conversion or filesystem writes.
- Fins wait adapter can bind download, preprocess, and upload awaiting tools, poll terminal Fins job records, and request cooperative cancel on abandoned waits.
- Migrated OLD tests, adapted to NEW typed boundaries, pass with no new pyright errors.
- Tool schema text is self-contained and business-readable; it does not expose Host internals, job record file paths, event ids, cursors, digests, tool call ids, or raw internal payloads.
- `dayu/fins/README.md`, `dayu/config/README.md`, `tests/README.md`, and, if the cross-package summary becomes stale, `dayu/README.md` are updated only after implementation makes those facts true.

## Non-Goals

- Do not implement Host prepare / activate two-phase awaiting in this work unit.
- Do not change Host or Engine public request/response dataclasses, durable schema, EventLog event types, Run/Attempt state machine, or Engine `ToolExecutor` protocol.
- Do not update GitHub Issue 129 in this plan gate. In implementation closeout, updating Issue 129 still needs controller/user authorization.
- Do not rewrite OLD SEC/CN/HK downloader business logic.
- Do not rewrite OLD SEC/CN pipeline download/upload workflow business logic.
- Do not migrate OLD UI, FastAPI, Streamlit, OLD ToolRegistry, OLD truncation manager, OLD `fetch_more`, or OLD path safety framework.
- Do not introduce separate CLI, CI, and tool implementations.
- Do not preserve compatibility re-export paths solely for OLD imports.
- Do not add a generic ingestion orchestration platform, job scheduler framework, or new Host-owned workflow engine.

## Scope Boundary

In scope:

- Migrating OLD Fins downloader and pipeline modules into NEW `dayu.fins` package modules.
- Adapting imports from OLD package boundaries to NEW package boundaries, especially:
  - `dayu.log` -> `dayu.fins._log.Log`
  - `dayu.engine.processors.*` -> `dayu.documents.processors.*`
  - OLD env/path helpers -> local typed constants/helpers or existing runtime helpers when available.
- Extending `FinsIngestionRuntime` to support production download adapters/runners and upload jobs.
- Adding a Fins upload tool provider and registering it in default `tool_discovery.json`.
- Extending Fins wait adapter binding to include upload.
- Migrating or adapting OLD tests into NEW `tests/fins/`, plus Service/config/tool discovery tests needed for upload awaiting assembly.
- Updating README files triggered by actual code changes.

Out of scope:

- Host/Engine contract changes. If required, stop and return to controller discussion.
- Physical cancel/revoke/abandon for external jobs beyond current cooperative Fins `request_cancel(...)`; deeper physical cancellation remains owned by WU-WAIT-03 / Issue 92.
- True crash-time restart of already-running Fins daemon jobs unless it can be done inside current Fins runtime without Host contract changes. If crash recovery requires prepare/activate or Host wait state changes, stop and classify under Issue 129.

## Design Source Alignment

Host design alignment:

- Host remains the truth owner for Session / Run / Attempt / EventLog / wait record. Fins only owns Fins business job records and source document storage.
- Tool facts and awaiting facts must go through ToolRuntime accept barrier. Fins tools return `ToolAwaitingOutcome`; they do not write Host EventLog or wait records.
- Existing Host wait model supports `ToolAwaitKind.EXTERNAL_JOB`, wait records, poll adapter bindings, `resolve_wait`, and `WAITING -> resume` without new Host public contract.
- `cancel_run` on a `WAITING` Run cancels the Host wait record; Fins wait adapter `abandon_wait(...)` can request cooperative job cancellation. It must not claim physical provider cancellation.

Engine design alignment:

- Engine only sees `ToolSchema`, `ToolExecutor`, `ToolAwaitingOutcome`, `tool_awaiting`, and `run_suspended`.
- The bounded Engine tool handshake must not wait for upload conversion/download completion. Long transactions must return awaiting outcome promptly after durable Fins job creation.
- If an implementation path cannot return `ToolAwaitingOutcome` before `AgentPolicy.tool_execution_timeout_seconds`, it is invalid for this work unit.

Fins design alignment:

- `dayu.fins` remains a business capability package, not a new `UI / Service / Host / Engine` layer.
- `DefaultFinsRuntime` remains the shared runtime assembly root.
- `dayu.fins.storage` remains the only financial document storage boundary.
- `ticker_normalization` remains the only ticker/market normalization truth.

## First-Principles Judgment

The problem is not "missing a tool name"; it is an execution-boundary mismatch.

Download and upload are external I/O workflows with network calls, filesystem writes, optional Docling conversion, retry, skip/overwrite decisions, and storage side effects. If they run inside a normal synchronous tool result path, they can exceed Engine's bounded tool handshake, lose cancellation/wait-resume observability, and duplicate logic across future CLI / CI / tool entrypoints. The right boundary is the existing Fins ingestion job model plus Host-governed awaiting.

The OLD implementations already encode business-specific selection and storage semantics. Reimplementing them as fresh NEW adapters would be a logic rewrite. The migration should instead preserve OLD module logic and adapt only the surfaces required by NEW layering, typed contracts, storage protocols, cancellation checkpoints, tool schema, and tests.

## Direct Code Evidence

OLD evidence paths inspected:

- `/Users/leo/workspace/dayu-agent/dayu/fins/downloaders/sec_downloader.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/downloaders/cninfo_downloader.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/downloaders/hkexnews_downloader.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/sec_pipeline.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/cn_pipeline.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/sec_upload_workflow.py`
- `/Users/leo/workspace/dayu-agent/dayu/fins/pipelines/docling_upload_service.py`
- `/Users/leo/workspace/dayu-agent/tests/fins/` relevant downloader / pipeline / upload tests

NEW evidence paths inspected:

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/preprocess_provider.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/storage/`
- `dayu/fins/ticker_normalization.py`
- `dayu/config/tool_discovery.json`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `dayu/README.md`
- `dayu/config/README.md`

Plan-gate read-only command categories executed:

- `git branch --show-current`
- `git status --short`
- `sed` reads for AGENTS, Gateflow, design/control/goal/README/code/test evidence
- `rg --files` and `rg -n` searches for Fins, Host awaiting, Engine awaiting, OLD tests, provider config, and path validation evidence

One exploratory `rg` command included non-existent optional filenames such as `uv.lock` and returned `rg` code 2 for those missing inputs; no repository file was modified by that command.

## OLD-To-NEW Migration Map

| OLD source | NEW destination | Migration rule |
|---|---|---|
| `dayu/fins/downloaders/sec_downloader.py` | `dayu/fins/downloaders/sec_downloader.py` | Migrate SEC network/throttle/download logic. Adapt imports/logging/env/path helpers and typing only. Do not change SEC selection/download business rules. |
| `dayu/fins/downloaders/cninfo_downloader.py` | `dayu/fins/downloaders/cninfo_downloader.py` | Migrate CNInfo discovery/PDF download logic. Adapt imports/logging/typing only. |
| `dayu/fins/downloaders/hkexnews_downloader.py` | `dayu/fins/downloaders/hkexnews_downloader.py` | Migrate HKEXNews discovery/PDF download logic. Adapt imports/logging/typing only. |
| OLD `dayu/fins/pipelines/cn_download_models.py`, `cn_download_protocols.py`, `cn_download_pdf_gate.py`, `cn_download_*workflow*.py`, `cn_form_utils.py` | NEW `dayu/fins/pipelines/` support modules or narrower `dayu/fins/ingestion/` adapter modules | Preserve CN/HK download workflow and candidate/id/fingerprint semantics. Prefer same module names under `dayu.fins.pipelines` unless a narrower adapter wrapper can reuse the migrated workflow without copying logic. |
| OLD `dayu/fins/pipelines/sec_download_*`, `sec_form_utils.py`, `sec_filing_collection.py`, `sec_6k_*`, `sec_sc13_filtering.py`, `sec_company_meta.py`, `sec_safe_meta_access.py` | NEW `dayu/fins/pipelines/` support modules or narrower SEC adapter modules | Preserve SEC download workflow, 6-K/SC13 handling, rejection registry, cache, skip/rebuild/overwrite semantics. |
| `dayu/fins/pipelines/sec_pipeline.py` | NEW SEC runtime adapter/facade under `dayu/fins/pipelines/sec_pipeline.py` or `dayu/fins/ingestion/sec_download_adapter.py` | Migrate only needed production download/upload facade behavior. Avoid copying process/rebuild surfaces unless required by imported workflow/tests. |
| `dayu/fins/pipelines/cn_pipeline.py` | NEW CN runtime adapter/facade under `dayu/fins/pipelines/cn_pipeline.py` or `dayu/fins/ingestion/cn_download_adapter.py` | Migrate only needed CN/HK download and CN upload facade behavior. Avoid process surfaces unless required by imported workflow/tests. |
| `dayu/fins/pipelines/sec_upload_workflow.py` | `dayu/fins/pipelines/sec_upload_workflow.py` | Preserve SEC filing/material upload workflow; adapt host protocol to NEW runtime repositories and cancellation checkpoints. |
| `dayu/fins/pipelines/docling_upload_service.py` | `dayu/fins/pipelines/docling_upload_service.py` | Preserve upload service logic; adapt imports, typing, storage model field names if NEW differs, and add cooperative cancellation checkpoints without changing business decisions. |
| OLD upload helper/event modules: `upload_company_meta.py`, `upload_filing_events.py`, `upload_material_events.py`, `upload_progress_helpers.py` | NEW `dayu/fins/pipelines/` same names | Preserve event/result mapping and company meta semantics. |
| OLD downloader tests | NEW `tests/fins/test_sec_downloader.py`, `test_cninfo_downloader.py`, `test_hkexnews_downloader.py` | Adapt fixtures to NEW imports and strict typing. No live network. |
| OLD SEC download tests | NEW `tests/fins/test_sec_pipeline_download*.py` plus runtime integration tests | Preserve behavior assertions for skip/overwrite/rejection/6-K/SC13/cache/event stream. |
| OLD CN/HK download tests | NEW `tests/fins/test_cn_download_*.py`, `test_cn_pipeline.py` | Preserve CN/HK candidate filtering, PDF gate, Docling conversion, skip/recovery/overwrite behavior. |
| OLD upload tests | NEW `tests/fins/test_sec_pipeline_upload_*.py`, `test_docling_upload_service*.py`, `test_upload_company_meta.py`, `test_upload_progress_helpers.py`, plus new upload tool tests | Preserve filing/material create/update/delete/skip/overwrite/docling behavior. |

## Affected Files And Modules

Likely production files:

- `dayu/fins/downloaders/__init__.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/` migrated support modules for SEC/CN download and upload
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/upload_provider.py`
- `dayu/config/tool_discovery.json`
- `dayu/service/host_assembly.py` if Service awaiting-provider recognition must include upload

Likely test files:

- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- `tests/tools/test_combined_tools_acceptance.py` if default combined fixture enables upload

Likely README/docs after code implementation:

- `dayu/fins/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- `dayu/README.md` only if cross-package Fins summary becomes stale after upload lands.

## Contract, Schema, State Machine, Public Interface Changes

Allowed Fins contract changes:

- Add `FinsIngestionOperationKind.UPLOAD = "upload"`.
- Add typed upload request contracts:
  - `FinsUploadFilingRequest`
  - `FinsUploadMaterialRequest`
  - `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest`
- Upload filing/material discrimination must use existing `SourceKind` from `dayu.fins.domain.enums`. Do not add `FinsUploadKind` unless direct implementation evidence proves `SourceKind` is semantically insufficient and the controller approves the contract change before implementation continues.
- Add `FinsUploadResultSummary` with bounded JSON summary fields:
  - `source_kind`
  - `document_id`
  - `internal_document_id`
  - `status`
  - `uploaded_files`
  - `primary_document`
  - `deleted`
  - `skip_reason`
  - `document_version`
  - `source_fingerprint`
- Add `FinsIngestionRuntime.start_upload(request, *, cancellation_token=None) -> FinsIngestionJobStart`.
- Keep existing synchronous `FinsSourceDownloadAdapter` as the production download target protocol. Migrated SEC/CN/HK download implementations must adapt to `download(request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult`.
- OLD async streams may be bridged only by migrating OLD synchronous aggregation/facade code, such as existing workflow or pipeline methods that already consume async internals and return an aggregate result. That bridge runs inside the current Fins background job thread. Do not introduce an async download adapter or change the runtime executor model by default.
- If direct implementation evidence proves the existing synchronous `FinsSourceDownloadAdapter` cannot preserve OLD downloader/workflow semantics without rewriting business rules, stop and return to controller discussion before changing the adapter protocol or executor model.
- Define `FinsUploadRunner` as the upload handoff boundary so upload workflow logic stays outside `FinsIngestionRuntime`: `run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`. `FinsJobCancellationChecker` is a typed zero-argument callable or protocol returning `bool`; its only purpose is cooperative cancellation checkpoints across runtime and migrated workflow boundaries.
- Extend `FinsIngestionJobRecord.operation_kind` validation/serialization to accept upload. Existing job files do not require compatibility handling for this work unit.
- Extend `FinsIngestionWaitPollAdapter` and `build_fins_wait_adapter_registry(...)` to support `start_fins_upload`.
- Add `dayu.fins.tools.upload_provider:discover_tools`.
- Add default disabled `financial-upload-tools` provider to `dayu/config/tool_discovery.json`.

Required upload tool interface:

- Tool name: `start_fins_upload`.
- Provider id: `financial-upload-tools`.
- Await kind: `ToolAwaitKind.EXTERNAL_JOB`.
- Tool returns awaiting immediately after durable job creation.
- Tool schema must be self-contained and business-readable. It must explain:
  - `upload_kind`: `"filing"` or `"material"`; the tool parser maps this value to existing `SourceKind`.
  - `ticker`: company ticker or exchange-qualified ticker.
  - `action`: `"auto"`, `"create"`, `"update"`, or `"delete"`.
  - `files`: local file paths under configured upload roots; required except delete.
  - filing-specific fields: `fiscal_year`, `fiscal_period`, `amended`, `filing_date`, `report_date`, `company_name`, `ticker_aliases`.
  - material-specific fields: `form_type`, `material_name`, optional `document_id`, optional `internal_document_id`, optional fiscal/date/company fields.
- Tool schema must not expose `Host`, `EventLog`, `wait_id`, `tool_call_id`, `digest`, `cursor`, raw job record paths, or implementation module names.

Required upload provider config:

- `workspace_root`: absolute Fins workspace root, same rule as other Fins providers.
- `allowed_upload_roots`: non-empty array of absolute paths when provider is enabled. The upload provider must fail closed if enabled without at least one allowed root.
- Path validation must be Fins-provider-local unless a suitable layer-neutral runtime helper already exists at implementation time. Do not import `dayu.tools.doc_provider` or `dayu.tools._legacy_adapter` into `dayu.fins`.

Blocking contract conditions:

- If implementation needs a new Host public command, Host durable table/column, EventLog type, WaitRecord state, `ToolAwaitSpec` field, Engine event, or Engine `ToolExecutor` shape, stop. Record a blocking controller discussion before implementation continues.
- If implementation needs to change `FinsSourceDownloadAdapter` from the current synchronous protocol to an async protocol, stop and return to controller discussion with direct evidence.
- If `start_upload` cannot be modeled as existing `ToolAwaitKind.EXTERNAL_JOB` plus current Fins poll adapter semantics, stop.
- If production upload requires prepare / activate two-phase semantics before it can safely start, stop and return to controller discussion. Do not implement a private Host-like state machine inside Fins.

## Upload Long-Transaction Lifecycle Decision

`start_upload` must be implemented as an awaiting external job, not as a synchronous completed tool.

Lifecycle:

1. Tool validates JSON arguments, upload path permission, and cancellation token.
2. Tool calls `FinsIngestionRuntime.start_upload(...)`.
3. Runtime normalizes ticker through `ticker_normalization`.
4. Runtime creates a durable Fins job record with `operation_kind="upload"` and `status="queued"`.
5. Runtime observes cancellation again before submitting background work. If cancelled, it marks the Fins job cancelled and the tool returns `ToolCancelledOutcome`.
6. Runtime submits background upload operation through the existing executor boundary.
7. Tool returns `ToolAwaitingOutcome` with:
   - `await_kind=ToolAwaitKind.EXTERNAL_JOB`
   - `resume_token=<fins job id>`
   - snapshot id derived from the Fins job id only, not from Host internals
8. Fins wait adapter polls the job:
   - queued/running/cancelling -> not ready
   - succeeded -> completed resolve outcome
   - failed -> failed resolve outcome
   - cancelled -> cancelled resolve outcome
   - missing/corrupt -> lost resolve outcome
9. `abandon_wait(...)` calls `runtime.request_cancel(job_id)`.
10. Background upload job checks `job_store` cancellation state at bounded points:
    - before file validation/read
    - before each Docling conversion
    - before each blob store
    - before source document upsert/delete
    - before final succeeded write

Issue 129 requirement:

- If this WU introduces `start_upload`, Issue 129 must later track `start_upload` together with `start_download` and `start_preprocess` for prepare / activate two-phase awaiting coverage.
- This plan gate must not modify Issue 129.
- Implementation closeout must either:
  - obtain controller/user authorization and update Issue 129, or
  - stop with a blocking residual risk that Issue 129 tracking has not been updated.

Cancel boundary:

- Current WU implements cooperative Fins job cancellation only.
- Host `WAITING -> CANCELLED` remains the canonical user-visible cancellation path.
- External job physical cancel/revoke/abandon remains owned by WU-WAIT-03 / Issue 92 unless the migrated OLD code already supports a local cooperative checkpoint.

## Implementation Decisions

- Migrate, do not rewrite. Preserve OLD downloader and workflow logic; only adapt imports, typing, storage protocol calls, cancellation checkpoints, runtime/tool contracts, and tests.
- Keep source-specific business rules outside `download_tools.py` and `upload_tools.py`. Tool modules only parse arguments, call runtime start methods, and map start failures to current tool outcomes.
- Keep storage writes inside `dayu.fins` and through `dayu.fins.storage`.
- Keep market/source decisions tied to `ticker_normalization`.
- Prefer explicit typed dataclasses/protocols over callback/factory/profile abstractions. Use a protocol only where the runtime truly needs a substitutable source-specific runner or upload executor for tests.
- Download adapter target is the existing synchronous `FinsSourceDownloadAdapter`. OLD async internals are acceptable only behind migrated OLD sync aggregation/facade boundaries running in the Fins background job thread. Do not add a parallel async adapter protocol without controller approval.
- Upload runner target is `FinsUploadRunner.run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`. This protocol is justified because Slice 1 must test runtime job lifecycle with a fake/unsupported runner while Slice 4 supplies the production runner without embedding upload business logic in `FinsIngestionRuntime`.
- Upload request kind uses existing `SourceKind`; schema string values are parsed into `SourceKind.FILING` or `SourceKind.MATERIAL`.
- Downloader defaults may remain source-module constants where OLD already owns them, including SEC endpoints, SEC User-Agent, SEC rate-limit defaults, CNInfo endpoints, and HKEXNews endpoints. Workspace-derived state/cache paths must come from `DefaultFinsRuntime.workspace_root`. Provider/config expansion must be typed and minimal; do not spread ad hoc env reads or stringly config through runtime registration. SEC User-Agent and rate-limit defaults must be explicit and covered by tests.
- Do not introduce compatibility re-exports. If a migrated module imports another migrated helper, update the import to the NEW true module path.
- Do not introduce `Any`, `object`, untyped parameters, or untyped returns while migrating OLD code. If an OLD module uses weak JSON typing, adapt annotations to `JsonValue`, `Mapping[str, JsonValue]`, typed dataclasses, `TypedDict`, or narrow helper functions without changing business branches. If this cannot be done without semantic rewrite, stop.
- Use module-level private helpers for migration glue; avoid nested helpers/classes unless the migrated OLD code already uses them for parser/local callback state.
- Do not hide explicit request fields in `extra` payloads. Upload request dataclasses must carry explicit fields.
- Additional OLD pipeline modules beyond the likely minimum lists in Slices 2/3/4 may be migrated only after direct import tracing from the listed workflow entrypoints or migrated tests. The implementation artifact must record that direct evidence. Do not migrate process/rebuild surfaces only because they exist in OLD.

## Implementation Slices

Slice ordering:

- Slice 1 must run first.
- Slices 2 and 3 must run serially after Slice 1 because both touch runtime adapter registration in `dayu/fins/service_runtime.py` and may touch shared download adapter tests. Preferred order is Slice 2 SEC first, then Slice 3 CN/HK.
- Slice 4 depends on Slice 1 upload contract and may reuse pipeline helpers migrated in Slices 2/3. It must not back-edit Slice 2/3 download semantics except where direct import tracing requires a shared helper.

### Slice 1: Shared Fins Ingestion Contract And Upload Job Foundation

Objective:

Add the typed upload job contract and runtime start path without migrating full OLD upload business logic yet.

Allowed files/modules:

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Exact allowed changes:

- Add `FinsIngestionOperationKind.UPLOAD`.
- Add `FinsUploadFilingRequest` and `FinsUploadMaterialRequest` dataclasses.
- Add `FinsUploadResultSummary`.
- Use `SourceKind` for filing/material discrimination inside upload requests; do not introduce `FinsUploadKind`.
- Add `start_upload(...)` mirroring `start_download(...)` and `start_preprocess(...)` start semantics.
- Add `FinsUploadRunner` protocol and a private `_run_upload_job(...)` that delegates to it. The default runner may be absent and must fail the job terminally with a clear "unsupported upload runtime" message until Slice 4 wires production upload.
- Extend job serialization/deserialization validation for upload.
- Add tests for queued upload job persistence, ticker normalization, create-before-submit cancellation, unsupported upload terminal failure, and bounded request/result summaries.

Functions/classes/types:

- `FinsUploadFilingRequest`
- `FinsUploadMaterialRequest`
- `FinsUploadResultSummary`
- `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest`
- `FinsJobCancellationChecker`: typed zero-argument callable or protocol returning `bool`
- `FinsUploadRunner` protocol with `run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`
- `FinsIngestionRuntime.start_upload`
- `FinsIngestionRuntime._run_upload_job`

Data flow:

`FinsUploadRequest(SourceKind.FILING | SourceKind.MATERIAL) -> ticker_normalization.normalize_ticker -> queued FinsIngestionJobRecord(operation_kind=UPLOAD) -> executor.submit(...) -> _run_upload_job -> FinsUploadRunner.run_upload(..., cancellation_checker=runtime job checker) -> FinsUploadResultSummary -> job terminal record`

Error handling:

- Argument validation errors raise `ValueError` before job creation.
- Cancellation before durable create raises/returns the same start-cancel behavior as download/preprocess.
- Cancellation after durable create but before submit marks the job cancelled and does not submit.
- Unsupported runner marks the job failed, not succeeded.

Invariants:

- No Host or Engine imports.
- No document storage outside repositories.
- No `Any`/`object`/untyped signatures.
- `FinsIngestionRuntime` owns job lifecycle only; upload business decisions live behind `FinsUploadRunner`.
- Existing download/preprocess tests remain unchanged except where enum exhaustiveness must include upload.

Non-goals:

- No upload tool.
- No production upload workflow.
- No download adapter migration.
- No README update yet unless code comments/docstrings alone would make README inaccurate; normally defer docs to final slice.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_runtime.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- Upload start writes a queued job record with `operation_kind == UPLOAD`.
- Upload start cancellation does not submit background work.
- Unsupported upload runner produces a failed terminal job with bounded failure summary.

Completion signal:

- `start_upload(...)` exists as a typed runtime method and is tested, but production provider/tool is still absent.

Stop condition:

- Stop if adding upload job records requires Host or Engine schema/state changes.

### Slice 2: Migrate SEC Downloader And SEC Download Runtime

Objective:

Migrate OLD SEC downloader and SEC download workflow into NEW runtime so `start_download` can execute real SEC download for US tickers.

Allowed files/modules:

- `dayu/fins/downloaders/__init__.py`
- `dayu/fins/downloaders/sec_downloader.py`
- Likely minimum SEC download support modules under `dayu/fins/pipelines/`:
  - `download_events.py`
  - `sec_download_workflow.py`
  - `sec_download_filing_workflow.py`
  - `sec_download_persistence.py`
  - `sec_download_source_upsert.py`
  - `sec_download_state.py`
  - `sec_download_event_mapping.py`
  - `sec_download_diagnostics.py`
  - `sec_form_utils.py`
  - `sec_filing_collection.py`
  - `sec_6k_rules.py`
  - `sec_6k_primary_document_repair.py`
  - `sec_sc13_filtering.py`
  - `sec_company_meta.py`
  - `sec_safe_meta_access.py`
  - `sec_pipeline.py` only as a narrow download facade if the workflow/tests require it
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Prerequisites/dependencies:

- Slice 1 completed.
- Slice 2 must run before Slice 3 unless the controller explicitly accepts a different serial order.
- Additional OLD SEC pipeline modules require direct import tracing from the listed workflow entrypoints or migrated tests. Process/rebuild surfaces remain out of scope unless such tracing proves they are required.

Exact allowed changes:

- Copy OLD SEC downloader logic and adapt imports:
  - `dayu.log` -> `dayu.fins._log`
  - missing env key constants -> module-level typed constants
  - source-owned endpoint/User-Agent/rate-limit defaults -> module-level typed constants whose values are explicit and tested
  - missing workspace path helper -> private helper using `DefaultFinsRuntime.workspace_root` derived paths
  - file locking -> use existing `dayu.runtime.filelock` where it preserves semantics, or keep platform-specific local lock only if runtime filelock cannot cover the async/SEC throttle case.
- Migrate the minimum SEC pipeline support modules required by download tests.
- Build a SEC `FinsSourceDownloadAdapter` implementation that preserves OLD `SecPipeline.download_stream_impl` / `sec_download_workflow` behavior and returns `FinsDownloadResultSummary`.
- Bridge OLD async/streaming internals only through migrated OLD synchronous aggregation/facade code running inside the Fins background job thread. Do not convert `FinsSourceDownloadAdapter` to async and do not add a parallel adapter protocol.
- Register default download adapters/runners in `DefaultFinsRuntime.get_ingestion_runtime()`:
  - source `sec`, market `US`
  - source `auto`, market `US` resolves to SEC before adapter lookup, or equivalent deterministic fallback.
- Keep adapter registration typed and minimal. Use `DefaultFinsRuntime.workspace_root` as the only source for workspace state/cache paths.
- Adapt tests from OLD to NEW imports and strict typing.

Functions/classes/data flow:

`FinsDownloadRequest(ticker=AAPL, source=auto/sec) -> normalize_ticker -> resolve source US/sec -> SEC runner -> SecDownloader + migrated SEC workflow -> storage repositories -> FinsDownloadResultSummary -> job terminal record`

Error handling:

- SEC network/download exceptions are caught by runtime and mark job failed.
- OLD workflow per-filing skipped/rejected/downloaded semantics remain intact.
- Unsupported explicit source/market combinations fail clearly.
- Cancellation checkpoints must be wired through the runtime job cancellation state into migrated workflow boundaries where OLD code already accepted `cancel_checker`, without adding a Host dependency.

Invariants:

- SEC files, source meta, rejected filing artifacts, and processed reprocess markers are written through NEW storage repositories.
- `ticker_normalization` is the source of normalized ticker and market.
- OLD SEC business rules for form windows, 6-K, SC13, rejection registry, cache, and skip/overwrite are not rewritten.
- The target runtime protocol is synchronous `FinsSourceDownloadAdapter`; adapter/executor async redesign is a controller stop condition.
- SEC User-Agent and SEC rate-limit defaults are explicit module constants and tested, not implicit env/path side effects.
- No compatibility `dayu.log` or `dayu.engine.processors` re-export is added.

Non-goals:

- No CN/HK download.
- No upload.
- No CLI entrypoint.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- SEC downloader tests remain network-free through fixtures/fakes.
- SEC pipeline tests preserve downloaded/skipped/rejected/failed summaries.
- `start_download(... source="auto")` for US uses SEC production adapter.

Completion signal:

- A US ticker download job can complete against deterministic SEC fixtures and write source documents through NEW storage.

Stop condition:

- Stop if OLD SEC download workflow cannot be migrated without rewriting core filtering/download decisions.
- Stop if direct implementation evidence proves the synchronous `FinsSourceDownloadAdapter` boundary cannot preserve OLD SEC async/stream semantics.
- Stop if strict typing adaptation would require changing SEC business behavior.

### Slice 3: Migrate CN/HK Downloader And CN/HK Download Runtime

Objective:

Migrate OLD CNInfo/HKEXNews downloader and CN/HK download workflow into NEW runtime so `start_download` can execute real CN and HK download jobs.

Allowed files/modules:

- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- Likely minimum CN/HK download support modules under `dayu/fins/pipelines/`:
  - `download_events.py`
  - `cn_download_models.py`
  - `cn_download_protocols.py`
  - `cn_download_pdf_gate.py`
  - `cn_download_workflow.py`
  - `cn_download_filing_workflow.py`
  - `cn_download_source_upsert.py`
  - `cn_download_staging.py`
  - `cn_download_company_meta.py`
  - `cn_form_utils.py`
  - `cn_pipeline.py` only as a narrow download facade if the workflow/tests require it
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Prerequisites/dependencies:

- Slice 1 completed.
- Slice 2 completed first in the preferred serial order, or the controller explicitly approved a different serial order.
- Additional OLD CN/HK pipeline modules require direct import tracing from the listed workflow entrypoints or migrated tests. `cn_download_rebuild.py` and broader process/preprocess helpers remain out of scope unless direct tracing proves they are required by download workflow/tests.

Exact allowed changes:

- Copy OLD CN/HK downloader logic and adapt imports/logging/typing.
- Keep source-owned endpoint/rate/default constants inside the downloader modules where OLD already owns them. Workspace-derived state/cache paths must come from `DefaultFinsRuntime.workspace_root`.
- Migrate CN download typed models/protocols/PDF gate/workflow helpers required by downloader and workflow tests.
- Build CN/HK `FinsSourceDownloadAdapter` implementations that preserve OLD `run_cn_download_stream_impl` behavior.
- Bridge OLD async/streaming internals only through migrated OLD synchronous aggregation/facade code running inside the Fins background job thread. Do not convert `FinsSourceDownloadAdapter` to async and do not add a parallel adapter protocol.
- Register default download adapters/runners:
  - source `cninfo`, market `CN`
  - source `hkexnews`, market `HK`
  - source `auto`, market `CN` resolves to `cninfo`
  - source `auto`, market `HK` resolves to `hkexnews`
- Keep adapter registration typed and minimal. Do not add provider/factory abstractions unless direct implementation evidence proves simple registration cannot preserve the OLD workflow.
- Preserve PDF gate semantics and ensure Docling conversion is not performed while holding the PDF download gate.

Functions/classes/data flow:

`FinsDownloadRequest(ticker=600519/0700.HK, source=auto/cninfo/hkexnews) -> normalize_ticker -> source resolution -> CN/HK runner -> CninfoDiscoveryClient or HkexnewsDiscoveryClient -> CN download workflow -> storage repositories -> FinsDownloadResultSummary -> job terminal record`

Error handling:

- Discovery-stage remote errors remain failures; empty candidates remain skipped/no-op according to OLD workflow semantics.
- PDF download failures affect candidate/file-level events according to OLD workflow.
- Cancellation checkpoints use runtime job cancellation state and OLD `cancel_checker` boundaries.

Invariants:

- CN/HK source documents and Docling outputs are stored through NEW storage.
- CN/HK id, fiscal period, title filtering, amended preference, language, PDF fingerprint, and overwrite/skip semantics are preserved.
- The target runtime protocol is synchronous `FinsSourceDownloadAdapter`; adapter/executor async redesign is a controller stop condition.
- No live network tests.

Non-goals:

- No upload.
- No broad process/preprocess rewrite beyond what migrated CN download workflow requires.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- CNInfo candidate filtering and PDF download tests pass.
- HKEXNews candidate filtering and PDF download tests pass.
- Runtime download for CN/HK uses migrated production workflow and writes expected source documents.

Completion signal:

- `start_download` has production adapters for US/CN/HK and deterministic tests cover all three markets.

Stop condition:

- Stop if CN/HK workflow migration requires introducing a second storage path outside `dayu.fins.storage`.
- Stop if direct implementation evidence proves the synchronous `FinsSourceDownloadAdapter` boundary cannot preserve OLD CN/HK async/stream semantics.

### Slice 4: Migrate Upload Service And Production Upload Runtime

Objective:

Wire production SEC/CN upload workflow into `FinsIngestionRuntime.start_upload(...)` while preserving OLD upload behavior.

Allowed files/modules:

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- Likely minimum upload helper/event modules under `dayu/fins/pipelines/`:
  - `upload_company_meta.py`
  - `upload_filing_events.py`
  - `upload_material_events.py`
  - `upload_progress_helpers.py`
  - `sec_company_meta.py` and `sec_safe_meta_access.py` if not already migrated by Slice 2 or if direct upload imports require them
  - `sec_pipeline.py` only as a narrow upload facade if the workflow/tests require it
  - `cn_pipeline.py` only as a narrow CN/HK upload facade if OLD evidence supports that upload path
  - `cn_download_company_meta.py` or other CN company-meta helpers only if directly imported by the CN upload facade/workflow/tests
- CN upload behavior from migrated `dayu/fins/pipelines/cn_pipeline.py` or a narrower CN upload workflow module
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- CN upload tests adapted from OLD `test_cn_pipeline.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Prerequisites/dependencies:

- Slice 1 completed and `FinsUploadRunner` protocol is available.
- Slice 2 completed for SEC shared company-meta helpers if SEC upload imports require them.
- Slice 3 completed if CN/HK upload relies on migrated CN/HK facade helpers.
- Additional OLD upload/pipeline modules require direct import tracing from `docling_upload_service.py`, `sec_upload_workflow.py`, narrow `sec_pipeline.py`/`cn_pipeline.py` upload facades, or migrated upload tests. Do not migrate unrelated process/rebuild modules.

Exact allowed changes:

- Migrate `DoclingUploadService` and helpers with NEW imports and strict typing.
- Preserve `execute_upload(...)` behavior:
  - validate files and suffixes
  - convert with Docling
  - store original and Docling assets
  - choose Docling primary document
  - create/update/delete source documents
  - skip same source fingerprint
  - resolve document version
- Preserve SEC filing/material id and result semantics from `sec_upload_workflow`.
- Preserve CN filing/material id and period semantics from `cn_pipeline` / `docling_upload_service`.
- Add cooperative cancellation checkpoints by passing a typed cancellation checker from runtime into upload workflow/service boundaries. Do not alter successful upload results.
- Implement production `FinsUploadRunner.run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary` and register it with `FinsIngestionRuntime`.
- Replace placeholder unsupported upload runner from Slice 1 with production upload runner selection:
  - US filing/material -> SEC upload workflow
  - CN/HK filing/material -> CN upload workflow if OLD semantics support it; if HK upload is unsupported by OLD evidence, fail explicitly and document as out of scope.
- Use existing `SourceKind` on `FinsUploadRequest` to branch filing/material behavior. Do not add `FinsUploadKind`.

Functions/classes/data flow:

`FinsUploadFilingRequest | FinsUploadMaterialRequest with SourceKind -> start_upload -> queued job -> FinsUploadRunner.run_upload(..., cancellation_checker=runtime job checker) -> SEC/CN upload workflow -> DoclingUploadService -> storage repositories -> FinsUploadResultSummary -> job terminal record`

Error handling:

- Invalid upload action, missing required files, unsupported file suffix, missing file, missing update target, duplicate create target, Docling conversion failure, and storage errors become failed terminal job records.
- `delete` does not require files and maps to deleted result.
- Same fingerprint without overwrite maps to skipped succeeded job, matching OLD upload behavior.
- Cancellation after job start maps to cancelled terminal record if observed before final success.

Invariants:

- Upload files are read only from paths already validated by the upload tool/provider or direct runtime caller.
- Upload never writes source docs except through `SourceDocumentRepositoryProtocol` and `DocumentBlobRepositoryProtocol`.
- OLD action resolution and id generation are preserved.
- Upload runs in the current daemon-thread Fins executor. A process crash during upload can leave a non-terminal Fins job or partial Fins-side artifacts, especially around Docling conversion, blob writes, delete, overwrite, and source upsert. Current WU only preserves repository atomicity where existing storage APIs provide it; crash hardening and prepare/activate coverage remain assigned to Issue 129 / WAIT follow-ups.
- No Host or Engine imports.

Non-goals:

- No upload tool/provider yet.
- No physical cancellation of in-flight Docling beyond cooperative checkpoints.
- No CLI.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- Upload create/update/delete/skip/overwrite behavior matches OLD tests.
- `start_upload` background jobs produce succeeded/failed/cancelled terminal records with bounded summaries.
- Docling integration tests remain explicit and deterministic; if real Docling fixture is optional, skip reasons must be precise.

Completion signal:

- Runtime direct callers can start SEC/CN upload jobs and observe terminal job records.

Stop condition:

- Stop if upload cannot be safely represented as a Fins durable job without Host/Engine contract changes.
- Stop if production acceptance requires crash-time recovery stronger than current repository atomicity and Fins job terminal writes.

### Slice 5: Upload Awaiting Tool, Provider, Wait Adapter, And Service Assembly

Objective:

Expose upload as a production awaiting tool and bind it to existing Host wait-resume assembly.

Allowed files/modules:

- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/upload_provider.py`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/config/tool_discovery.json`
- `dayu/service/host_assembly.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- `tests/tools/test_combined_tools_acceptance.py` if combined provider fixture changes

Exact allowed changes:

- Add `UPLOAD_TOOL_NAME = "start_fins_upload"`.
- Add `FinsUploadToolCallable`.
- Add `build_fins_upload_tool(...)`.
- Add upload argument parser with typed helper functions; no raw `extra` payload.
- Add provider `dayu.fins.tools.upload_provider:discover_tools`.
- Parse `workspace_root` and `allowed_upload_roots` in upload provider.
- Validate upload file paths:
  - each path must be non-empty string
  - expand/resolve path
  - path must be inside one allowed upload root
  - create/update/auto require non-empty files
  - delete forbids or ignores files only if OLD delete semantics clearly allow it; prefer fail on unnecessary files to avoid accidental reads
- Extend wait adapter constants:
  - `FINS_UPLOAD_AWAITING_TOOL_NAME`
  - `FINS_SUPPORTED_AWAITING_TOOL_NAMES`
- Extend Service Fins awaiting provider recognition to include `financial-upload-tools` / upload import path / upload source id.
- Add default disabled `financial-upload-tools` provider config.

Functions/classes/data flow:

`ToolsDiscovery -> upload_provider.discover_tools -> DefaultFinsRuntime.get_ingestion_runtime -> build_fins_upload_tool -> ToolRuntime executes callable -> start_upload -> ToolAwaitingOutcome -> Fins wait adapter poll/abandon`

Error handling:

- Argument/path validation errors return `ToolFailedOutcome` before durable job creation.
- Runtime start cancellation returns `ToolCancelledOutcome`.
- OSError during job creation returns start-failed outcome.
- Unexpected start exception returns start-failed outcome.

Invariants:

- Tool schema hides Host internals and raw job record paths.
- Upload provider fails closed when enabled without absolute `workspace_root` or without non-empty `allowed_upload_roots`.
- Service assembly fails before `open_host` on Fins awaiting workspace mismatch or duplicate upload binding.
- Download and preprocess provider behavior remains unchanged.

Non-goals:

- No Host wait schema changes.
- No GitHub Issue modification in this slice unless controller explicitly authorizes after implementation review.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- ToolsDiscovery discovers read/download/preprocess/upload independently.
- Workspace overlay can enable upload provider.
- `start_fins_upload` returns `EXTERNAL_JOB` awaiting outcome.
- Upload schema does not contain Host/internal governance terms.
- Fins wait adapter registry binds download/preprocess/upload deterministically.
- Service assembly includes upload in wait adapter registry when upload provider is enabled.

Completion signal:

- Upload is available as a production awaiting tool through runtime discovery and Host wait adapter assembly.

Stop condition:

- Stop if Service assembly needs a new Host public option to bind upload wait adapter.

### Slice 6: Documentation, Full Validation, And Issue-Tracking Closeout

Objective:

Synchronize documentation with implemented facts, run full relevant validation, and classify residual risks.

Allowed files/modules:

- `dayu/fins/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- `dayu/README.md` only if existing cross-package summary is stale
- Implementation/review artifacts required by the gate after this plan is accepted

Exact allowed changes:

- Read each README's `Agent更新约束【必须遵守】` before editing.
- Update `dayu/fins/README.md` to describe only implemented upload/download facts.
- Update `dayu/config/README.md` to include `financial-upload-tools` provider config after it lands.
- Update `tests/README.md` to describe new Fins downloader/pipeline/upload test coverage after tests land.
- Update `dayu/README.md` only if its Fins summary still omits implemented upload capability or new Service assembly fact.
- Record Issue 129 tracking status:
  - If controller authorized a GitHub Issue update, record that `start_upload` was added to Issue 129 prepare/activate tracking.
  - If not authorized, stop with a blocking residual risk before final closeout.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q
python -m pyright dayu/ tests/ utils/
git status --short
```

Expected assertions:

- Fins tests cover migrated downloader, runtime, upload, tool, and wait adapter paths.
- Service assembly tests cover upload awaiting binding.
- Pyright has no new or expanded errors.
- `git status --short` shows only intended work-unit files for the implementation gate, not controller-owned files unless controller explicitly changed them.

Completion signal:

- Plan-approved implementation is complete and ready for code review gate.

Stop condition:

- Stop on undocumented README trigger, unclassified residual risk, missing Issue 129 tracking decision, or any Host/Engine contract mismatch.

## Tests And Validation Matrix

Minimum targeted validation by capability:

```bash
source .venv/bin/activate
pytest tests/fins/test_sec_downloader.py -q
pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q
pytest tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py -q
pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py -q
pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py -q
pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py -q
pytest tests/service/test_host_assembly.py -q
pytest tests/tools/test_combined_tools_acceptance.py -q
python -m pyright dayu/ tests/ utils/
```

Expected global assertions:

- No live network tests are introduced.
- Tests use `httpx.MockTransport`, fake downloader/discovery clients, temporary workspaces, or explicit optional real Docling fixtures.
- Upload path tests prove disallowed paths fail before job creation.
- Existing read/download/preprocess tests continue to pass.
- No new `Any`, `object`, untyped signature, or untyped return is added.
- Import boundary tests continue to prevent Host/Engine from importing Fins and prevent runtime from importing Fins.

## README / Docs Decision

Implementation must apply README trigger rules after code changes:

- `dayu/fins/` changes trigger `dayu/fins/README.md` check/update.
- `dayu/config/tool_discovery.json` changes trigger `dayu/config/README.md` check/update.
- `tests/` changes trigger `tests/README.md` check/update.
- Service assembly changes or cross-package Fins capability summary changes require checking `dayu/README.md`; update only if current implemented facts make the existing summary stale.

README writing constraints already read in this plan gate:

- `dayu/fins/README.md` writes only current implemented Fins capability, boundaries, contracts, components, and state machine facts. It must not write future plans.
- `tests/README.md` writes only current tests structure, commands, and maintenance facts.
- `dayu/config/README.md` writes only current default config and workspace overlay facts.
- `dayu/README.md` writes only total package-level implemented boundaries and summaries.

## Risks And Open Questions

| Risk / question | Classification | Owner / destination | Required handling |
|---|---|---|---|
| `start_upload` must be added to Issue 129 prepare / activate tracking after implementation introduces it. | tracked by existing issue | GitHub Issue 129; controller authorization required | Do not modify issue in plan gate. Implementation closeout must obtain authorization or stop. |
| Fins jobs created by current daemon-thread executor may remain queued/running if the process dies before terminal record; upload can additionally leave partial Fins-side artifacts around Docling conversion, blob writes, delete, overwrite, or source upsert. | tracked by existing issue | Issue 129 for two-phase start/activation and/or WU-WAIT-02 / Issue 90 poller hardening | Current WU only preserves repository atomicity where existing storage APIs provide it. Do not solve with a private Host-like state machine. If production acceptance requires stronger crash recovery now, stop. |
| External job physical cancel/revoke is not guaranteed by cooperative Fins `request_cancel`. | tracked by existing issue | WU-WAIT-03 / Issue 92 | Current WU only adds bounded cooperative checkpoints. |
| OLD code uses weak typing such as `Any`; NEW constraints forbid introducing it. | fixed in current slices | Implementation slices 2-4 | Replace weak annotations with strict JSON/dataclass/protocol types while preserving business branches. Stop if not feasible without rewrite. |
| Upload tool reads local file paths. | fixed in current slices | Slice 5 | Add provider-level `allowed_upload_roots` and fail closed before job creation. |
| HK upload support may not have direct OLD evidence. | requiring user/controller decision if unsupported | Slice 4 | If OLD code only supports CN/SEC upload, fail HK upload explicitly and classify as non-goal or later WU before implementation continues. |
| Migrating whole `SecPipeline` / `CnPipeline` may pull process surfaces not needed by this WU. | fixed in current slices | Slices 2-4 | Prefer narrow migrated workflow/facade modules. Do not migrate process/rebuild surfaces unless imported workflow/tests require them. |
| Service assembly may need to recognize upload awaiting provider. | fixed in current slice | Slice 5 | Update existing Fins awaiting assembly path; stop if new Host public option is needed. |
| README facts may become stale after upload/provider additions. | fixed in current slice | Slice 6 | Update only README sections whose current-code facts changed. |

Blocking open questions at plan time:

- None for entering implementation, provided implementation obeys the stop conditions above.

## Why This Is Not Over-Designed

- It reuses existing Host/Engine awaiting contracts instead of adding new lifecycle states or public APIs.
- It reuses existing `DefaultFinsRuntime`, `FinsIngestionRuntime`, job store, and Fins wait adapter instead of introducing another service layer.
- It migrates OLD proven downloader/workflow logic instead of inventing fresh SEC/CN/HK business rules.
- It keeps upload as one new Fins operation kind and one new tool provider, not a generic workflow platform.
- It adds provider-local upload path validation because upload reads local files; that is a concrete production safety requirement, not a speculative framework.
- It defers prepare/activate, poller hardening, and physical external-job cancellation to existing issue owners instead of expanding this WU into Host wait architecture work.

## Completion Report Format

The final report for the implementation gate should use:

1. Plan artifact path
2. Implemented slices and changed files
3. Key OLD/NEW evidence used
4. Validation commands and results
5. README/docs updates
6. Issue 129 tracking status for `start_upload`
7. Blocking questions / residual risks with classification
8. Actual modified files

The completion report for this plan gate should use:

1. Plan artifact path
2. Key OLD/NEW evidence checked
3. Plan slices summary
4. Blocking questions / residual risks
5. Files modified in this gate

## Plan Gate Validation

Pre-write preflight:

```text
git branch --show-current
phase/wu-tools-01-f01-03

git status --short
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
```

The dirty files above are controller-owned and were not modified by this plan gate.

Required post-write validation:

```bash
git status --short
```

Actual post-write status:

```text
 M docs/host/issues-implementation-control.md
?? docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
```

Interpretation:

- Existing controller-owned dirty files remain present and untouched.
- `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md` is the only plan-gate file added by this agent.
