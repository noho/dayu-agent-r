# WU-TOOLS-01-F01-03 Plan Fix (AgentCodex)

## Metadata

- Work unit: `WU-TOOLS-01-F01-03 Production Fins CN/SEC Download And Upload Runtime/Tool Migration`
- Gate: plan-fix
- Role: `AgentCodex`
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-03-plan-review-controller-adjudication.md`
- Artifact path: `docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md`

## Scope

This gate only fixed accepted plan-review findings in the plan artifact. It did not perform re-review, implementation, tests, pyright, commit, push, PR work, GitHub Issue edits, README edits, or source/test changes.

Allowed files touched by this gate:

- `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- `docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md`

## Fix Decisions

- Download adapter target is now the existing synchronous `FinsSourceDownloadAdapter`. OLD async/streaming internals may be bridged only through migrated OLD synchronous aggregation/facade code running inside the Fins background job thread. Any async adapter/executor redesign is a controller stop condition.
- Upload handoff is now a typed `FinsUploadRunner.run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary` boundary, with runtime owning job lifecycle and runner owning upload business logic.
- Upload filing/material kind now uses existing `SourceKind`; `FinsUploadKind` is explicitly disallowed unless direct evidence and controller approval prove `SourceKind` insufficient.
- Slice 2 and Slice 3 are now serial after Slice 1, with preferred order Slice 2 SEC then Slice 3 CN/HK.
- Slices 2, 3, and 4 now enumerate likely minimum OLD pipeline modules and require direct import tracing before adding more modules.
- Downloader defaults/config now state that source-module constants may remain, workspace-derived state paths come from `DefaultFinsRuntime.workspace_root`, config expansion must be typed/minimal, and SEC User-Agent/rate-limit defaults must be explicit and tested.
- Slice 4 now records the daemon-thread upload crash-risk invariant and assigns stronger crash hardening to Issue 129 / WAIT follow-ups.

## Accepted Findings Status

| Finding | Status | Plan fix evidence |
|---|---|---|
| DS-F01 / MiMo-F2 sync adapter and OLD async bridge | 已修复 | Contract section, implementation decisions, Slice 2, and Slice 3 now name synchronous `FinsSourceDownloadAdapter` as the target and make async redesign a stop condition. |
| DS-F02 upload runner handoff | 已修复 | Contract section and Slice 1 now define `FinsUploadRunner.run_upload(...)`; Slice 4 implements and registers production runner selection. |
| DS-F03 daemon-thread upload crash safety | 已修复 | Slice 4 invariants and risk table now describe non-terminal/partial artifact risk and classify hardening to Issue 129 / WAIT follow-ups. |
| DS-F04 `FinsUploadKind` versus `SourceKind` | 已修复 | Contract section, implementation decisions, Slice 1, and Slice 4 require existing `SourceKind` and forbid `FinsUploadKind` without controller approval. |
| DS-F05 Slice 2 and Slice 3 parallelization | 已修复 | Implementation slices now state serial order after Slice 1, preferred as Slice 2 SEC then Slice 3 CN/HK. |
| MiMo-F1 pipeline support module scope | 已修复 | Slices 2/3/4 now list likely minimum OLD pipeline modules and require direct import tracing for extra modules. |
| MiMo-F3 downloader config initialization | 已修复 | Implementation decisions plus Slices 2/3 now define source constants, workspace-root derived paths, typed/minimal config expansion, and explicit/tested SEC UA/rate defaults. |

## Deferred Or Rejected Findings

- MiMo-F4 remains deferred to Slice 5 implementation/review. The plan's existing constraint against `dayu.tools` imports and duplicate path frameworks was not expanded in this fix gate.
- MiMo-F5 remains rejected-with-reason by controller. No standalone fix was applied beyond the DS-F02 upload runner handoff clarification.

## Validation

Required validation for this gate is `git status --short` only.

Command:

```bash
git status --short
```

Result:

```text
 M docs/host/issues-implementation-control.md
?? docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
?? docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-controller-adjudication.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-ds.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md
```

Interpretation:

- `docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md` is the new fix artifact from this gate.
- `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md` is the allowed plan artifact updated by this gate.
- `docs/host/issues-implementation-control.md` and the goal/review/adjudication artifacts were already present in preflight status and were not modified by this gate.
- No source code, tests, README, GitHub Issue, commit, push, or PR changes were made.

## Docs Decision

No README or external docs were updated. This gate only changed plan/fix artifacts, so README trigger handling remains deferred to implementation slices after real code/config/test changes.

## Residual Risks

| Residual risk | Classification | Owner / destination |
|---|---|---|
| Implementation may find direct evidence that synchronous `FinsSourceDownloadAdapter` cannot preserve OLD stream semantics. | requiring controller decision if triggered | Slice 2 or Slice 3 must stop and return to controller before adapter/executor redesign. |
| Upload daemon-thread crash recovery remains weaker than prepare/activate. | tracked by existing issue | Issue 129 / WAIT follow-ups. |
| MiMo-F4 upload path helper shape still needs implementation evidence. | covered by later approved slice | Slice 5 implementation/review. |

No unclassified residual risk remains for this plan-fix gate.

## Completion Status

Plan accepted findings were fixed in the plan artifact. This gate stops here by user instruction and does not enter re-review, implementation, commit, push, or PR gates.
