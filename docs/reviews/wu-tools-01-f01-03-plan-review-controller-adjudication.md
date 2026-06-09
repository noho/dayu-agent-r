# WU-TOOLS-01-F01-03 Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: plan review
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-plan-review-ds.md`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Verdict

Plan review result: `PASS WITH ACCEPTED FINDINGS`.

The plan direction is valid, but accepted findings must be fixed in the plan artifact before the re-review gate. The most important correction is to make the OLD async/streaming workflow to NEW synchronous `FinsSourceDownloadAdapter` boundary explicit without prematurely changing the runtime executor model.

## Controller Findings Adjudication

| Finding | Decision | Controller rationale | Required fix |
|---|---|---|---|
| DS-F01 sync adapter versus OLD async downloader bridge | accepted | The bridge gap is real, but the suggested default of making `FinsSourceDownloadAdapter` async is not accepted as the default solution. OLD already has synchronous aggregation wrappers using `asyncio.run(...)`, and NEW `FinsIngestionRuntime` currently runs jobs in a background thread. The smallest current-phase plan is to target the existing sync `FinsSourceDownloadAdapter` and explicitly use migrated OLD sync aggregation/facade boundaries where available. If direct implementation evidence proves that cannot preserve OLD semantics, stop and return to controller before changing the runtime executor/protocol model. | Update plan Slices 2/3 and contract section to state that existing sync `FinsSourceDownloadAdapter` is the target protocol; OLD async streams are bridged only through migrated OLD sync aggregation/facade code running inside the Fins background job thread. Do not introduce a parallel adapter protocol. Treat changing the adapter/executor to async as a stop condition requiring controller discussion. |
| DS-F02 missing upload runner protocol handoff | accepted | Slice 1 to Slice 4 handoff is underspecified. Upload business logic must not be embedded into `FinsIngestionRuntime`, and implementation needs a typed boundary. | Define the upload runner boundary in the plan. Prefer `FinsUploadRunner` protocol only if it removes real complexity and enables tests; otherwise name the concrete runner class and method. The contract must include request type, cancellation checker, and `FinsUploadResultSummary` return. |
| DS-F03 daemon thread crash safety for upload | accepted | Upload has stronger side-effect risk than download because it may combine file reads, Docling conversion, delete/overwrite, blob writes, and source upsert. Current WU should not solve Host-level crash recovery, but the plan must make the accepted risk explicit. | Add Slice 4 invariant/risk: daemon-thread upload execution can leave non-terminal or partial Fins-side artifacts on process crash; current WU only preserves repository atomicity where existing storage APIs provide it and classifies crash hardening to Issue 129 / WAIT follow-ups. |
| DS-F04 `FinsUploadKind` versus `SourceKind` | accepted | Introducing a second enum for filing/material would duplicate existing `SourceKind` semantics and increase drift risk. | Update plan to use existing `SourceKind` for upload filing/material discrimination; do not add `FinsUploadKind` unless direct implementation evidence proves `SourceKind` is semantically insufficient and controller approves. |
| DS-F05 Slice 2 and Slice 3 parallelization | accepted | SEC and CN/HK download slices share `service_runtime.py` and runtime adapter registration. Parallel implementation would create ownership conflicts. | State that Slices 2 and 3 are serial after Slice 1. Preferred order: Slice 2 SEC first, then Slice 3 CN/HK. Alternatively, Slice 1 may introduce a shared registration pattern if that remains small and tested. |
| MiMo-F1 pipeline support module scope vague | accepted | Code-generation-ready plan should not leave implementation agents to guess broad `dayu/fins/pipelines/` scope. | Enumerate likely minimum OLD pipeline modules for Slices 2/3/4, and require direct import tracing before adding any additional module. Keep process/rebuild surfaces out unless directly required by migrated download/upload workflow imports or tests. |
| MiMo-F2 existing `FinsSourceDownloadAdapter` protocol not primary | accepted | This overlaps DS-F01 and matches the controller decision. | Fix with DS-F01: name `FinsSourceDownloadAdapter` as the primary target protocol. |
| MiMo-F3 downloader config initialization detail missing | accepted | SEC/CN/HK downloader constructors need endpoint, rate, UA, and workspace-path decisions. The plan must prevent hardcoded or ad hoc config spread. | Add implementation decision: downloader defaults may remain source-module constants where OLD already owns them; workspace-derived state paths come from `DefaultFinsRuntime.workspace_root`; provider config expansion must be typed and minimal. SEC User-Agent and rate-limit defaults must be explicit and tested. |
| MiMo-F4 upload path helper uncertainty | deferred-with-owner | The plan already states no `dayu.tools` dependency and provider-local validation unless a layer-neutral helper exists. The exact helper shape is best verified in Slice 5 implementation review. | Owner: Slice 5 implementation and code review. Verify no `dayu.tools` import and no duplicate cross-package path framework. |
| MiMo-F5 `FinsUploadRunner` protocol justification | rejected-with-reason | This is not a plan defect. The plan's conditional protocol language is directionally correct, but DS-F02 requires a clearer typed handoff. | No standalone fix for MiMo-F5; DS-F02 covers the necessary clarification. |

## Required Plan Fix Scope

AgentCodex must update only `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`.

Required changes:

- Clarify download adapter target protocol and async/stream bridge strategy.
- Define the upload runner handoff boundary.
- Add daemon-thread upload crash-risk invariant.
- Decide upload kind uses `SourceKind`.
- Mark Slices 2 and 3 as serial, or move a small shared registration pattern into Slice 1.
- Enumerate likely minimum OLD pipeline modules for SEC download, CN/HK download, and upload.
- Add downloader config/defaults guidance.

Forbidden changes:

- Do not implement code.
- Do not modify review artifacts, control doc, GitHub Issues, or README files.
- Do not change the work unit goal or broaden scope into Host/Engine public contract changes.

## Re-Review Entry

After AgentCodex updates the plan, dispatch both `AgentMiMo` and `AgentDS` for plan re-review focused on the accepted findings above.
