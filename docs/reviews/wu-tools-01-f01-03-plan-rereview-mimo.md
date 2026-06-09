# WU-TOOLS-01-F01-03 Plan Re-Review (AgentMiMo)

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: plan re-review
- Reviewer: AgentMiMo
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Plan fix artifact: `docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-03-plan-review-controller-adjudication.md`
- Prior reviews: `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md`, `docs/reviews/wu-tools-01-f01-03-plan-review-ds.md`

## Verdict

**PLAN REREVIEW PASS**

所有 controller adjudication 中 accepted findings 均已被 plan fix 正确关闭，无新增 blocking finding。Plan 已达到 code-generation-ready 状态。

## Accepted Findings Final Status

| Finding | Adjudication decision | Status | Evidence in plan fix |
|---|---|---|---|
| DS-F01 / MiMo-F2 sync adapter vs OLD async downloader bridge | accepted — target sync `FinsSourceDownloadAdapter`，async redesign 为 stop condition | 已修复 | Plan line 254-256: 明确 `FinsSourceDownloadAdapter` 为同步目标协议；line 255: OLD async 仅通过已迁移的 sync aggregation/facade 桥接；line 287: async adapter/executor redesign 为 stop condition；Slice 2 line 491: "Bridge OLD async/streaming internals only through migrated OLD synchronous aggregation/facade code"；Slice 3 line 591: 同样约束。 |
| DS-F02 upload runner protocol handoff | accepted — 定义 typed `FinsUploadRunner` boundary | 已修复 | Plan line 257: 定义 `FinsUploadRunner.run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`；Slice 1 line 389: 完整 protocol 定义包含 request type、cancellation checker、return type；Slice 1 line 378: default runner 缺失时 terminally fail；Slice 4 line 695: production runner 注册。 |
| DS-F03 daemon-thread upload crash safety | accepted — Slice 4 增加 crash risk invariant | 已修复 | Slice 4 line 717: "Upload runs in the current daemon-thread Fins executor. A process crash during upload can leave a non-terminal Fins job or partial Fins-side artifacts, especially around Docling conversion, blob writes, delete, overwrite, and source upsert. Current WU only preserves repository atomicity where existing storage APIs provide it; crash hardening and prepare/activate coverage remain assigned to Issue 129 / WAIT follow-ups."；Risk Table line 932: 同一风险描述及 owner 分类。 |
| DS-F04 `FinsUploadKind` vs `SourceKind` | accepted — 使用已有 `SourceKind`，禁止 `FinsUploadKind` | 已修复 | Plan line 241: "Upload filing/material discrimination must use existing `SourceKind` from `dayu.fins.domain.enums`. Do not add `FinsUploadKind` unless direct implementation evidence proves `SourceKind` is semantically insufficient and the controller approves"；Implementation Decisions line 344: "Upload request kind uses existing `SourceKind`"；Slice 1 line 376: "Use `SourceKind` for filing/material discrimination"；Slice 4 line 699: "Use existing `SourceKind` on `FinsUploadRequest`... Do not add `FinsUploadKind`"。 |
| DS-F05 Slice 2/3 parallelization | accepted — 声明串行，优选 Slice 2 SEC → Slice 3 CN/HK | 已修复 | Plan line 357: "Slices 2 and 3 must run serially after Slice 1 because both touch runtime adapter registration in `dayu/fins/service_runtime.py` and may touch shared download adapter tests. Preferred order is Slice 2 SEC first, then Slice 3 CN/HK."；Slice 2 line 478: "Slice 2 must run before Slice 3 unless the controller explicitly accepts a different serial order."；Slice 3 line 582: "Slice 2 completed first in the preferred serial order, or the controller explicitly approved a different serial order."。 |
| MiMo-F1 pipeline support module scope vague | accepted — 每个 slice 枚举 likely minimum OLD pipeline modules | 已修复 | Slice 2 line 451-467: 枚举 16 个 SEC pipeline 模块（download_events, sec_download_workflow, sec_download_filing_workflow, sec_download_persistence, sec_download_source_upsert, sec_download_state, sec_download_event_mapping, sec_download_diagnostics, sec_form_utils, sec_filing_collection, sec_6k_rules, sec_6k_primary_document_repair, sec_sc13_filtering, sec_company_meta, sec_safe_meta_access, sec_pipeline as narrow facade）；Slice 3 line 558-569: 枚举 10 个 CN/HK pipeline 模块；Slice 4 line 655-663: 枚举 upload helper/event 模块；三个 slice 均要求 "direct import tracing before adding more modules" 和 "Do not migrate process/rebuild surfaces"。 |
| MiMo-F3 downloader config initialization detail missing | accepted — 补齐 config/defaults guidance | 已修复 | Implementation Decisions line 345: "Downloader defaults may remain source-module constants where OLD already owns them, including SEC endpoints, SEC User-Agent, SEC rate-limit defaults, CNInfo endpoints, and HKEXNews endpoints. Workspace-derived state/cache paths must come from `DefaultFinsRuntime.workspace_root`. Provider/config expansion must be typed and minimal"；"SEC User-Agent and rate-limit defaults must be explicit and covered by tests"；Slice 2 line 486-487: "source-owned endpoint/User-Agent/rate-limit defaults -> module-level typed constants whose values are explicit and tested"；Slice 3 line 588: "Keep source-owned endpoint/rate/default constants inside the downloader modules where OLD already owns them"。 |

## Deferred / Rejected Findings Verification

| Finding | Adjudication decision | Verification |
|---|---|---|
| MiMo-F4 upload path helper uncertainty | deferred-with-owner — owner: Slice 5 implementation/review | Plan line 282: "Path validation must be Fins-provider-local unless a suitable layer-neutral runtime helper already exists at implementation time. Do not import `dayu.tools.doc_provider` or `dayu.tools._legacy_adapter` into `dayu.fins`." Owner 明确为 Slice 5 implementation/review。确认仍有明确 owner/destination。 |
| MiMo-F5 `FinsUploadRunner` protocol justification | rejected-with-reason — DS-F02 覆盖必要澄清 | Plan line 343: "This protocol is justified because Slice 1 must test runtime job lifecycle with a fake/unsupported runner while Slice 4 supplies the production runner without embedding upload business logic in `FinsIngestionRuntime`." 理由充分，无需额外修复。 |

## New Findings

未发现 plan fix 引入的新 blocking risk。Plan 的 stop conditions、risk table、non-goals 和 blocking contract conditions 均保持完整且一致。

## Plan Gate Validation

### Pre-write status

```text
git status --short
 M docs/host/issues-implementation-control.md
?? docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
?? docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-controller-adjudication.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-ds.md
?? docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md
```

Controller-owned dirty files and prior artifacts were not modified by this re-review gate.

### Post-write validation

```bash
git status --short
```

Expected: Only `docs/reviews/wu-tools-01-f01-03-plan-rereview-mimo.md` added.

## Completion Report

1. **Re-review artifact path**: `docs/reviews/wu-tools-01-f01-03-plan-rereview-mimo.md`
2. **Verdict**: PLAN REREVIEW PASS
3. **Accepted findings final status**:

| Finding | Status |
|---|---|
| DS-F01 / MiMo-F2 sync adapter vs OLD async bridge | 已修复 |
| DS-F02 upload runner protocol handoff | 已修复 |
| DS-F03 daemon-thread upload crash safety | 已修复 |
| DS-F04 `FinsUploadKind` vs `SourceKind` | 已修复 |
| DS-F05 Slice 2/3 parallelization | 已修复 |
| MiMo-F1 pipeline support module scope | 已修复 |
| MiMo-F3 downloader config initialization | 已修复 |

4. **New findings**: 无
5. **Files modified by me**: `docs/reviews/wu-tools-01-f01-03-plan-rereview-mimo.md` (new file only)
