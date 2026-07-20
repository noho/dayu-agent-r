# WU-SEMANTIC-OWNERSHIP-01 P0-B Implementation

## Scope

- Work unit: WU-SEMANTIC-OWNERSHIP-01 / P0-B only.
- Role: AgentCodex implementation/fix.
- P0-A accepted commit: `6731b451`; this implementation did not modify P0-A semantics.
- Commit/push: not performed.

## S0 root-cause confirmation

### Motivation judgment

P0-B is valid. Direct code evidence showed three owner-boundary problems:

- `FinsPreprocessResultSummary.skipped_count` was built as `len(skipped_ids) + len(not_supported_ids)`, so unsupported documents were mixed into skipped semantics.
- Direct preprocess and legacy job preprocess each repeated the same `processed_count == 0 ...` failure predicate instead of consuming one typed Fins result contract.
- `ProductionFinsUploadRunner` received loose `dict[str, JsonValue]` pipeline results and `_upload_summary_from_result()` fabricated missing upload fields with `"unknown"` / `False`.
- `ingest_method` was encoded as scattered string literals across domain, pipeline, storage, and read path.

### `rg "ingest_method" dayu/fins/` initial classification

- Pipeline producer:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/pipelines/cn_pipeline.py`
  - `dayu/fins/pipelines/sec_upload_workflow.py`
  - `dayu/fins/pipelines/cn_download_source_upsert.py`
  - `dayu/fins/pipelines/sec_download_source_upsert.py`
- Pipeline rebuild/filter:
  - `dayu/fins/pipelines/cn_download_rebuild.py`
  - `dayu/fins/pipelines/sec_rebuild_workflow.py`
- Source upsert / manifest projection:
  - `dayu/fins/storage/_fs_source_document_core.py`
- Storage serialization/deserialization:
  - `dayu/fins/domain/document_models.py`
  - `dayu/fins/storage/_fs_maintenance_core.py`
- Maintenance/read path:
  - `dayu/fins/tools/read_runtime.py`
- Tests:
  - no production test path was included in the initial production scan; focused tests were later updated in `tests/fins/test_fins_ingestion_runtime.py`.

All initial production hits were inside the P0-B allowed files/modules. No blocker was found.

### Preprocess helper decision

Chosen type: typed status enum/helper, not a boolean helper.

Rationale: direct, job, awaiting, and direct-stream consumers need the same business status semantics, not just truthiness. `FinsPreprocessResultSummary.result_status()` now returns `FinsPreprocessResultStatus`, and validates count/detail consistency before classifying.

Consumers:

- Direct: `_produce_direct_preprocess(...)` uses `summary.result_status()`.
- Job: `_run_preprocess_job(...)` uses `summary.result_status()`.
- Awaiting: `FinsIngestionWaitPollAdapter` consumes the terminal `FinsResultSummary` produced by the direct/observation path; it does not rederive preprocess status.
- Direct-stream/CLI/Service rendering: consumes `FinsResultSummary.details` and JSON summaries derived from the same `FinsPreprocessResultSummary`.

### `not_supported_count` decision

Decision: add `not_supported_count` to JSON summary.

Propagation path:

- Producer: `_execute_preprocess_request(...)` counts `skipped_ids` and `not_supported_ids` separately.
- Typed summary: `FinsPreprocessResultSummary` stores `skipped_count`, `not_supported_count`, and their document-id tuples.
- Durable job record: `summary.to_json_summary()` writes both counts into `result_summary`.
- Direct result: `_preprocess_result_details(...)` reads the typed JSON summary and emits distinct `skipped` and `not supported` details.
- Direct progress: `_preprocess_summary_progress_payload(...)` emits both `skipped_count` and `not_supported_count`.
- Awaiting result: observation snapshots carry the same terminal `FinsResultSummary.details`; wait adapter projects those details without recomputing.
- CLI/Service rendering: consume direct stream events and terminal details; they do not infer counts independently.

## Owner boundary

- Fact producer:
  - preprocess summary facts: `FinsIngestionRuntime._execute_preprocess_request(...)`.
  - upload pipeline result facts: SEC/CN upload pipeline output, narrowed at `ProductionFinsUploadRunner`.
  - source classification facts: Fins pipeline producers and ingestion runtime.
- Fact validator:
  - preprocess: `FinsPreprocessResultSummary.result_status()` and `_bounded_preprocess_summary(...)`.
  - upload: `FinsUploadPipelineResult.from_pipeline_json(...)`.
  - ingest method: `FinsIngestMethod.from_storage_value(...)`.
- Persistence:
  - job store result summaries via `summary.to_json_summary()`.
  - source/rejected meta and manifest projection via Fins storage/domain model serialization.
- Projection:
  - direct result details, progress payload, wait adapter details, read path `SourceType`.

The fix is inside the Fins owner boundary or its direct upstream validation boundary. No downstream display special-case was added.

## Changes

- Added `FinsIngestMethod` in `dayu/fins/domain/document_models.py`; storage JSON still persists business-readable `"download"` / `"upload"` strings.
- Replaced production `ingest_method` string read/write points with enum conversion helpers across allowed Fins pipeline, storage, runtime, and read-path files.
- Added `FinsPreprocessResultStatus` and `FinsPreprocessResultSummary.result_status()`.
- Split preprocess `skipped_count` and `not_supported_count`; unsupported documents no longer increment skipped.
- Added `_bounded_preprocess_summary(...)` to validate count/detail consistency.
- Added `FinsUploadPipelineResult` and changed `ProductionFinsUploadRunner` to return typed upload pipeline results to runtime summary construction.
- Removed upload runtime missing-field fallback helpers that fabricated `"unknown"` and `False`.
- Updated focused tests for preprocess status/count semantics and upload typed result status validation.
- Updated `dayu/fins/README.md` and `tests/README.md` for the now-implemented stable behavior.

## Validation

- `source .venv/bin/activate && pytest tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py`
  - Result: `398 passed, 1 skipped, 3 warnings`.
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
  - Result: `47 passed`.
- `source .venv/bin/activate && rg -n "ingest_method" dayu/fins/`
  - Result: all production hits route through `FinsIngestMethod`, storage conversion, or explicit pipeline JSON serialization.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## README decision

- `dayu/fins/README.md`: updated because Fins runtime public/stable semantics changed for preprocess summary and upload typed result.
- `tests/README.md`: updated because focused `tests/fins/test_fins_ingestion_runtime.py` coverage changed.
- Root README: not updated; no user-facing CLI command, install, workspace path, or final workflow changed.
- `dayu/README.md`: not updated; no layer boundary or assembly relationship changed.

## Propagation audit

- Preprocess skipped/not-supported:
  - Produced in `_execute_preprocess_request(...)`.
  - Validated by `FinsPreprocessResultSummary.result_status()` / `_bounded_preprocess_summary(...)`.
  - Persisted through `summary.to_json_summary()` into legacy job `result_summary`.
  - Audited in progress events through `_preprocess_summary_progress_payload(...)`.
  - Projected through `_preprocess_result_details(...)` to direct result details and onward to Service/CLI/awaiting wait resolution.
  - Confirmed consistent: unsupported-only preprocess has `skipped_count=0`, `not_supported_count=1`, failed status.
- Upload result:
  - Produced by SEC/CN upload workflow JSON result.
  - Validated at `FinsUploadPipelineResult.from_pipeline_json(...)`; missing `status` fails instead of fabricating defaults.
  - Projected into `FinsUploadResultSummary` only from typed fields.
  - Persisted in job/direct summary through `FinsUploadResultSummary.to_json_summary()`.
  - Confirmed consistent: runtime no longer owns missing-field fallback semantics.
- `ingest_method`:
  - Produced by Fins download/upload pipeline boundaries via `FinsIngestMethod`.
  - Serialized to source/rejected meta as `"download"` / `"upload"` only at storage JSON boundary.
  - Deserialized by domain/storage/read/rebuild paths through `FinsIngestMethod.from_storage_value(...)`.
  - Projected to read path source classification using enum comparison.

## Residual risk

- Existing worktree had a pre-existing modification in `docs/host/issues-implementation-control.md`; this implementation did not modify that file.
- SEC `SecPipeline._build_result(...)` remains outside the P0-B allowed file list and still has its broader pipeline default behavior. P0-B runtime summary is protected by typed `FinsUploadPipelineResult` validation, and SEC upload workflow currently passes explicit `status`.
- No legacy meta compatibility was added. Missing `ingest_method` now fails at Fins owner boundary, consistent with the current task's full-new-schema rule.

## Completion status

P0-B implementation is complete locally. No commit or push was performed.
