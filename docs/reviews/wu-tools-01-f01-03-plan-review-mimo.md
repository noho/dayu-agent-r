# WU-TOOLS-01-F01-03 Plan Review (AgentMiMo)

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: plan review
- Reviewer: AgentMiMo
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Goal confirmation: `docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Verdict

**PASS WITH FINDINGS**

Plan is code-generation-ready with 3 medium findings and 2 low findings. No blocking findings. Plan correctly identifies migration scope, respects Host/Engine boundaries, handles upload as long transaction, and includes appropriate stop conditions. Findings relate to slice scope precision, existing protocol alignment, and adapter instantiation detail.

## Findings

### F1: Slice 2/3/4 Pipeline Support Module Scope Is Vague

- **Severity**: medium
- **Evidence**: OLD `dayu/fins/pipelines/` contains 30+ modules (sec_download_workflow, sec_download_filing_workflow, sec_download_persistence, sec_download_source_upsert, sec_download_state, sec_download_event_mapping, sec_download_diagnostics, sec_6k_rules, sec_6k_primary_document_repair, sec_sc13_filtering, sec_company_meta, sec_safe_meta_access, sec_form_utils, sec_filing_collection, cn_download_workflow, cn_download_models, cn_download_protocols, cn_download_pdf_gate, cn_download_filing_workflow, cn_download_source_upsert, cn_download_staging, cn_download_rebuild, cn_download_company_meta, cn_form_utils, cn_pipeline, sec_pipeline, sec_upload_workflow, docling_upload_service, upload_company_meta, upload_filing_events, upload_material_events, upload_progress_helpers, download_events, base, factory, processed_snapshot_helpers, processing_helpers). Plan Slice 2 says "Required SEC pipeline support modules under `dayu/fins/pipelines/`" without enumerating which modules are needed.
- **Plan location**: Slices 2, 3, 4 — "Required SEC/CN/HK pipeline support modules under `dayu/fins/pipelines/`"
- **Risk**: Implementation agent must guess which OLD modules to migrate. Could under-migrate (missing required dependencies, test failures) or over-migrate (pulling process/rebuild surfaces not needed by this WU, violating non-goal "Do not rewrite OLD pipeline business logic").
- **Recommendation**: For each slice, enumerate the minimum set of OLD pipeline modules required to make the listed tests pass. At minimum, list the direct imports from the downloader and workflow entry points. The plan's stop condition "Stop if OLD SEC download workflow cannot be migrated without rewriting core filtering/download decisions" is correct but doesn't help with module selection.
- **Suggested disposition**: accepted — add module enumeration to Slices 2-4 during implementation planning, or accept that implementation agent will discover required modules through import tracing.

### F2: Plan Does Not Reference Existing `FinsSourceDownloadAdapter` Protocol

- **Severity**: medium
- **Evidence**: NEW `dayu/fins/ingestion_runtime.py:274` defines `FinsSourceDownloadAdapter(Protocol)` with `download(request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult`. `FinsIngestionRuntime` accepts `download_adapters: Mapping[tuple[str, NormalizedTickerMarket], FinsSourceDownloadAdapter]` at construction. Plan's migration map describes building "SEC download runner/adapter" and "CN/HK download runners/adapters" but does not mention `FinsSourceDownloadAdapter` or state whether migrated OLD downloaders should implement this protocol.
- **Plan location**: Migration map, Slice 2 "Build a SEC download runner/adapter that preserves OLD behavior", Slice 3 "Build CN/HK download runners/adapters"
- **Risk**: Implementation agent may create a parallel adapter interface instead of implementing the existing `FinsSourceDownloadAdapter` protocol, leading to two competing adapter abstractions in `FinsIngestionRuntime`.
- **Recommendation**: Explicitly state that migrated OLD downloaders should be wrapped as `FinsSourceDownloadAdapter` implementations (or that the existing protocol may need extension if it cannot accommodate OLD workflow semantics). The plan already says "Add a production download runner/adapter interface if current `FinsSourceDownloadAdapter` cannot preserve OLD workflow without rewriting" — this conditional is correct, but should be the primary path, not an afterthought.
- **Suggested disposition**: accepted — clarify in Slice 2/3 that `FinsSourceDownloadAdapter` is the target protocol, and only deviate if OLD workflow semantics genuinely cannot fit.

### F3: Download Adapter Instantiation Detail Missing

- **Severity**: medium
- **Evidence**: Plan says to "Register default download adapters/runners in `DefaultFinsRuntime.get_ingestion_runtime()`" but does not detail constructor arguments for OLD downloaders. OLD `SecDownloader` needs SEC API endpoints, rate limiting config, workspace paths. OLD `CninfoDiscoveryClient` needs CNInfo API config. OLD `HkexnewsDiscoveryClient` needs HKEX config. `DefaultFinsRuntime.create(workspace_root)` currently only takes `workspace_root`.
- **Plan location**: Slice 2 "Register default download adapters/runners in `DefaultFinsRuntime.get_ingestion_runtime()`", Slice 3 same
- **Risk**: Implementation agent may hardcode config values, skip required initialization, or create overly complex factory patterns to satisfy the registration requirement.
- **Recommendation**: State that downloader config (API endpoints, rate limits, workspace paths) should be derived from `workspace_root` and existing Fins config patterns. If new config fields are needed, they should follow the existing `tool_discovery.json` or Fins workspace config pattern. The plan's "prefer explicit typed dataclasses/protocols over callback/factory/profile abstractions" decision applies here.
- **Suggested disposition**: accepted — implementation should follow existing Fins config patterns; no plan change needed but implementation gate should verify.

### F4: `allowed_upload_roots` Path Validation Runtime Helper Uncertainty

- **Severity**: low
- **Evidence**: Plan says "Path validation must be Fins-provider-local unless a suitable layer-neutral runtime helper already exists at implementation time. Do not import `dayu.tools.doc_provider` or `dayu.tools._legacy_adapter` into `dayu.fins`."
- **Plan location**: Contract section, "Required upload provider config"
- **Risk**: Implementation agent may either (a) create a new path validation helper in `dayu.fins` that duplicates existing logic, or (b) import from `dayu.tools` violating the constraint.
- **Recommendation**: The plan's constraint is correctly stated. Implementation should check if `dayu.runtime` or `dayu.fins` already has path validation before creating new code. This is an implementation-time decision, not a plan gap.
- **Suggested disposition**: deferred-with-owner — implementation gate should verify.

### F5: `FinsUploadRunner` Protocol Justification

- **Severity**: low
- **Evidence**: Plan proposes `FinsUploadRunner` protocol "only if needed to avoid embedding upload workflow logic in `FinsIngestionRuntime`". AGENTS.md requires protocols to have "充分理由".
- **Plan location**: Slice 1 "Functions/classes/types"
- **Risk**: Low. The conditional "only if needed" language is appropriate. If the upload workflow can be cleanly separated from runtime, a protocol is justified for test substitutability. If not, a concrete implementation is acceptable.
- **Recommendation**: No plan change needed. Implementation should evaluate whether a protocol is actually needed based on the complexity of the upload workflow integration.
- **Suggested disposition**: accepted — conditional language is sufficient.

## Design Alignment Assessment

### Host Design Alignment: PASS

- Plan correctly keeps Host as truth owner for Session/Run/Attempt/EventLog/wait record.
- Fins tools return `ToolAwaitingOutcome`; they do not write Host EventLog or wait records.
- Plan uses existing `ToolAwaitKind.EXTERNAL_JOB` and wait adapter polling — no new Host public contract needed.
- `cancel_run` on `WAITING` Run correctly delegates to Fins wait adapter `abandon_wait(...)`.
- Plan explicitly stops if Host/Engine contract changes are needed.

### Engine Design Alignment: PASS

- Engine only sees `ToolSchema`, `ToolExecutor`, `ToolAwaitingOutcome`, `tool_awaiting`, `run_suspended`.
- Plan correctly states "The bounded Engine tool handshake must not wait for upload conversion/download completion."
- Long transactions return `ToolAwaitingOutcome` promptly after durable Fins job creation.
- Plan correctly identifies that if implementation cannot return `ToolAwaitingOutcome` before `AgentPolicy.tool_execution_timeout_seconds`, it is invalid.

### Fins Design Alignment: PASS

- `dayu.fins` remains a business capability package, not a new layer.
- `DefaultFinsRuntime` remains the shared runtime assembly root.
- `dayu.fins.storage` remains the only financial document storage boundary.
- `ticker_normalization` remains the only ticker/market normalization truth.

### AGENTS.md Compliance: PASS

- No `Any`/`object`/untyped signatures introduced (plan explicitly forbids).
- No compatibility re-exports (plan explicitly forbids).
- No glue facades (plan uses typed dataclasses/protocols).
- Storage writes only through `dayu.fins.storage` repositories.
- Docstrings required in Chinese (plan does not contradict).
- Protocols used with clear justification (test substitutability).

## Upload Long-Transaction Lifecycle Assessment: PASS

- Upload modeled as `ToolAwaitKind.EXTERNAL_JOB` — correct.
- Tool returns awaiting immediately after durable job creation — correct.
- Fins wait adapter polls job terminal state — correct.
- `abandon_wait(...)` calls `runtime.request_cancel(job_id)` — correct cooperative cancellation.
- Background upload checks cancellation at bounded points — correct.
- Issue 129 tracking requirement correctly identified — controller authorization required before closeout.
- Plan correctly does not implement prepare/activate two-phase — deferred to Issue 129.

## Residual Risks For Implementation/Review Gate

1. **Pipeline module enumeration**: Implementation agent must determine minimum OLD pipeline modules for each slice through import tracing. Review gate should verify no unnecessary modules were migrated.

2. **`FinsSourceDownloadAdapter` integration**: Implementation should implement existing protocol, not create parallel abstraction. Review gate should verify.

3. **Downloader config initialization**: Implementation should follow existing Fins config patterns. Review gate should verify no hardcoded values.

4. **HK upload OLD evidence**: Plan correctly flags that HK upload may not have OLD evidence. Implementation should verify and fail explicitly if unsupported.

5. **Weak typing adaptation**: OLD code uses `Any` in some places. Implementation must replace with strict types. Plan's stop condition "Stop if strict typing adaptation would require changing SEC business behavior" is correct.

6. **Issue 129 update**: Implementation closeout must obtain controller authorization to update Issue 129 with `start_upload` tracking.

## Plan Gate Validation

### Pre-write status

```text
git branch --show-current
phase/wu-tools-01-f01-03

git status --short
 M docs/host/issues-implementation-control.md
?? docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
```

Controller-owned dirty files were not modified by this review gate.

### Post-write validation

```bash
git status --short
```

Expected: Only `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md` added.

## Completion Report

1. **Review artifact path**: `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md`
2. **Verdict**: PASS WITH FINDINGS
3. **Findings count**: 3 medium, 2 low, 0 blocking
4. **Residual risks**: 6 items listed above, all with clear owner/destination
5. **Files modified by this review**: `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md` (new file only)
