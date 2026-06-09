# WU-TOOLS-01-F01-03 Plan Re-Review (AgentDS)

## Metadata

- Work unit: `WU-TOOLS-01-F01-03 Production Fins CN/SEC Download And Upload Runtime/Tool Migration`
- Gate: plan re-review
- Reviewer: AgentDS
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-03-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-03-plan-review-controller-adjudication.md`
- Prior review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-plan-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-03-plan-review-mimo.md`
- Artifact path: `docs/reviews/wu-tools-01-f01-03-plan-rereview-ds.md`

## Re-Review Scope

逐项复核 controller adjudication 中 accepted findings 是否已被 plan fix 关闭。不在本 gate 做 implementation / commit / push / PR。

## Verdict

**PLAN REREVIEW PASS**

所有 7 项 accepted findings 均已修复。MiMo-F4（deferred-with-owner）owner 仍然明确。MiMo-F5（rejected-with-reason）按 controller 裁决不要求修复。未发现 plan fix 引入新 blocking risk。

---

## Accepted Findings 逐项复核

### Finding DS-F01 / MiMo-F2: 同步 Adapter Protocol 与 OLD Async Bridge

- **Controller 要求**: 明确现有同步 `FinsSourceDownloadAdapter` 为目标协议；OLD async stream 仅通过迁移后的 OLD 同步聚合/facade 代码桥接；async adapter/executor 改造为 stop condition。
- **Status**: 已修复
- **Evidence**:
  - Contract section（line 254）："Keep existing synchronous `FinsSourceDownloadAdapter` as the production download target protocol. Migrated SEC/CN/HK download implementations must adapt to `download(request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult`."
  - Contract section（line 255）："OLD async streams may be bridged only by migrating OLD synchronous aggregation/facade code, such as existing workflow or pipeline methods that already consume async internals and return an aggregate result. That bridge runs inside the current Fins background job thread."
  - Contract section（line 256）："Do not introduce an async download adapter or change the runtime executor model by default."
  - Contract section（line 257）：stop condition — 若同步 adapter 无法保留 OLD 语义则停止并回 controller。
  - Implementation decisions（line 342）："Download adapter target is the existing synchronous `FinsSourceDownloadAdapter`. OLD async internals are acceptable only behind migrated OLD sync aggregation/facade boundaries running in the Fins background job thread. Do not add a parallel async adapter protocol without controller approval."
  - Slice 2（line 491）："Bridge OLD async/streaming internals only through migrated OLD synchronous aggregation/facade code running inside the Fins background job thread. Do not convert `FinsSourceDownloadAdapter` to async and do not add a parallel adapter protocol."
  - Slice 2（line 514）："The target runtime protocol is synchronous `FinsSourceDownloadAdapter`; adapter/executor async redesign is a controller stop condition."
  - Slice 3（line 591, 614）：对 CN/HK 下载器有相同约束。
- **Plan location**: Contract section（line 254-257），Implementation decisions（line 342），Slice 2（line 491, 514），Slice 3（line 591, 614）

---

### Finding DS-F02: Upload Runner Protocol Handoff

- **Controller 要求**: 在 plan 中定义 upload runner boundary，包括 request type、cancellation checker、`FinsUploadResultSummary` return。
- **Status**: 已修复
- **Evidence**:
  - Contract section（line 257）："Define `FinsUploadRunner` as the upload handoff boundary so upload workflow logic stays outside `FinsIngestionRuntime`: `run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`. `FinsJobCancellationChecker` is a typed zero-argument callable or protocol returning `bool`."
  - Implementation decisions（line 343）：明确 protocol 的充分理由——Slice 1 用 fake runner 测试 job lifecycle，Slice 4 提供 production runner，不将 upload 业务逻辑嵌入 runtime。
  - Slice 1（line 389）："`FinsUploadRunner` protocol with `run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary`"
  - Slice 4（line 695）："Implement production `FinsUploadRunner.run_upload(request: FinsUploadRequest, *, cancellation_checker: FinsJobCancellationChecker) -> FinsUploadResultSummary` and register it with `FinsIngestionRuntime`."
- **Plan location**: Contract section（line 257），Implementation decisions（line 343），Slice 1（line 389），Slice 4（line 695）

---

### Finding DS-F03: Daemon Thread Upload Crash Safety

- **Controller 要求**: 在 Slice 4 invariants/risk 中声明 daemon-thread upload 执行在进程 crash 时可留下 non-terminal 或 partial Fins-side artifact，并分类到 Issue 129 / WAIT follow-ups。
- **Status**: 已修复
- **Evidence**:
  - Slice 4 invariants（line 717）："Upload runs in the current daemon-thread Fins executor. A process crash during upload can leave a non-terminal Fins job or partial Fins-side artifacts, especially around Docling conversion, blob writes, delete, overwrite, and source upsert. Current WU only preserves repository atomicity where existing storage APIs provide it; crash hardening and prepare/activate coverage remain assigned to Issue 129 / WAIT follow-ups."
  - Risk table（line 932）：更新为明确描述 upload 的 partial artifact 风险，owner 为 Issue 129 / WU-WAIT-02 / Issue 90。
- **Plan location**: Slice 4 invariants（line 717），Risk table（line 932）

---

### Finding DS-F04: `FinsUploadKind` versus `SourceKind`

- **Controller 要求**: 使用现有 `SourceKind` 做 upload filing/material 区分；不引入 `FinsUploadKind` 除非直接证据证明 `SourceKind` 不足且 controller 批准。
- **Status**: 已修复
- **Evidence**:
  - Contract section（line 241）："Upload filing/material discrimination must use existing `SourceKind` from `dayu.fins.domain.enums`. Do not add `FinsUploadKind` unless direct implementation evidence proves `SourceKind` is semantically insufficient and the controller approves the contract change before implementation continues."
  - Implementation decisions（line 344）："Upload request kind uses existing `SourceKind`; schema string values are parsed into `SourceKind.FILING` or `SourceKind.MATERIAL`."
  - Slice 1（line 376）："Use `SourceKind` for filing/material discrimination inside upload requests; do not introduce `FinsUploadKind`."
  - Slice 4（line 699）："Use existing `SourceKind` on `FinsUploadRequest` to branch filing/material behavior. Do not add `FinsUploadKind`."
- **Plan location**: Contract section（line 241），Implementation decisions（line 344），Slice 1（line 376），Slice 4（line 699）

---

### Finding DS-F05: Slice 2 和 Slice 3 并行化

- **Controller 要求**: 声明 Slice 2 和 Slice 3 必须串行（因为共享 `service_runtime.py` adapter registration），说明先后顺序。
- **Status**: 已修复
- **Evidence**:
  - Slice ordering（line 356-358）："Slice 1 must run first. Slices 2 and 3 must run serially after Slice 1 because both touch runtime adapter registration in `dayu/fins/service_runtime.py` and may touch shared download adapter tests. Preferred order is Slice 2 SEC first, then Slice 3 CN/HK."
  - Slice 2 prerequisites（line 477）："Slice 1 completed. Slice 2 must run before Slice 3 unless the controller explicitly accepts a different serial order."
  - Slice 3 prerequisites（line 581）："Slice 1 completed. Slice 2 completed first in the preferred serial order, or the controller explicitly approved a different serial order."
- **Plan location**: Slice ordering（line 356-358），Slice 2 prerequisites（line 477），Slice 3 prerequisites（line 581）

---

### Finding MiMo-F1: Pipeline Support Module Scope

- **Controller 要求**: 为 Slices 2/3/4 枚举 likely minimum OLD pipeline modules，并要求 direct import tracing 后方可增加额外模块。
- **Status**: 已修复
- **Evidence**:
  - Slice 2（line 451-467）：枚举 16 个 SEC download 相关模块，包括 `download_events.py`、`sec_download_workflow.py`、`sec_download_filing_workflow.py`、`sec_download_persistence.py`、`sec_download_source_upsert.py`、`sec_download_state.py`、`sec_download_event_mapping.py`、`sec_download_diagnostics.py`、`sec_form_utils.py`、`sec_filing_collection.py`、`sec_6k_rules.py`、`sec_6k_primary_document_repair.py`、`sec_sc13_filtering.py`、`sec_company_meta.py`、`sec_safe_meta_access.py`、`sec_pipeline.py`（仅 narrow download facade）。
  - Slice 2（line 479）："Additional OLD SEC pipeline modules require direct import tracing from the listed workflow entrypoints or migrated tests. Process/rebuild surfaces remain out of scope unless such tracing proves they are required."
  - Slice 3（line 559-569）：枚举 CN/HK download 相关模块。
  - Slice 3（line 583）：相同 import tracing 要求。
  - Slice 4（line 655-663）：枚举 upload 相关模块。
  - Slice 4（line 679）：相同 import tracing 要求。
- **Plan location**: Slice 2（line 451-467, 479），Slice 3（line 559-569, 583），Slice 4（line 655-663, 679）

---

### Finding MiMo-F3: Downloader Config Initialization

- **Controller 要求**: 添加 implementation decision——downloader defaults 可在 OLD 已有处保留为 source-module 常量；workspace-derived state paths 来自 `DefaultFinsRuntime.workspace_root`；config expansion 必须 typed/minimal；SEC User-Agent 和 rate-limit defaults 必须 explicit 且 tested。
- **Status**: 已修复
- **Evidence**:
  - Implementation decisions（line 345）："Downloader defaults may remain source-module constants where OLD already owns them, including SEC endpoints, SEC User-Agent, SEC rate-limit defaults, CNInfo endpoints, and HKEXNews endpoints. Workspace-derived state/cache paths must come from `DefaultFinsRuntime.workspace_root`. Provider/config expansion must be typed and minimal; do not spread ad hoc env reads or stringly config through runtime registration. SEC User-Agent and rate-limit defaults must be explicit and covered by tests."
  - Slice 2（line 484-488）：具体适配规则——env key 常量→module-level typed constants；endpoint/UA/rate-limit→explicit tested constants；workspace path→`DefaultFinsRuntime.workspace_root` 派生。
  - Slice 2（line 495）："Use `DefaultFinsRuntime.workspace_root` as the only source for workspace state/cache paths."
  - Slice 2（line 515）："SEC User-Agent and SEC rate-limit defaults are explicit module constants and tested, not implicit env/path side effects."
  - Slice 3（line 588）：CN/HK 下载器遵循相同模式。
- **Plan location**: Implementation decisions（line 345），Slice 2（line 484-488, 495, 515），Slice 3（line 588）

---

## Deferred / Rejected Findings 确认

### MiMo-F4: Upload Path Helper Uncertainty

- **原始 disposition**: deferred-with-owner（controller adjudication）
- **Owner**: Slice 5 implementation and code review
- **确认**: Plan 中 Contract section（line 282）仍保留约束——"Path validation must be Fins-provider-local unless a suitable layer-neutral runtime helper already exists at implementation time. Do not import `dayu.tools.doc_provider` or `dayu.tools._legacy_adapter` into `dayu.fins`." Slice 5 为 implementation owner。Owner 和 destination 仍然明确。
- **Status**: 证据失效（deferred from start，非 plan-fix 项；owner 未变）

### MiMo-F5: `FinsUploadRunner` Protocol Justification

- **原始 disposition**: rejected-with-reason（controller adjudication）
- **Controller 理由**: 非 plan defect；DS-F02 已覆盖必要的 typed handoff 澄清。
- **Status**: 不要求修复（controller 已 reject）

---

## New Findings

未发现 plan fix 引入新的 blocking risk。Plan 内部一致性检查：

- Contract section 中 sync adapter 目标、async bridge 策略、upload runner protocol、SourceKind 决策在所有章节中保持一致。
- Slice ordering（line 356-358）与 Slice 2/3 prerequisites（line 477, 581）一致。
- Implementation decisions（line 342-345）与 Contract section（line 254-257, 241）一致。
- Slice 4 daemon-thread invariant（line 717）与 Risk table（line 932）一致。
- 各 Slice 的 stop condition 与 contract section 的 blocking conditions 一致。

无新增 finding。

---

## Accepted Findings 最终状态表

| Finding | Status | Plan fix evidence location |
|---|---|---|
| DS-F01 / MiMo-F2 | 已修复 | Contract line 254-257, Impl decisions line 342, Slice 2 line 491/514, Slice 3 line 591/614 |
| DS-F02 | 已修复 | Contract line 257, Impl decisions line 343, Slice 1 line 389, Slice 4 line 695 |
| DS-F03 | 已修复 | Slice 4 invariants line 717, Risk table line 932 |
| DS-F04 | 已修复 | Contract line 241, Impl decisions line 344, Slice 1 line 376, Slice 4 line 699 |
| DS-F05 | 已修复 | Slice ordering line 356-358, Slice 2 prereq line 477, Slice 3 prereq line 581 |
| MiMo-F1 | 已修复 | Slice 2 line 451-467/479, Slice 3 line 559-569/583, Slice 4 line 655-663/679 |
| MiMo-F3 | 已修复 | Impl decisions line 345, Slice 2 line 484-488/495/515, Slice 3 line 588 |
| MiMo-F4 | 证据失效 | Deferred with owner from start; Slice 5 owner still clear; plan constraint line 282 unchanged |
| MiMo-F5 | — | Rejected with reason by controller; 不要求修复 |

---

## Validation

```bash
git status --short
```

Expected: 仅新增 `docs/reviews/wu-tools-01-f01-03-plan-rereview-ds.md`。不运行测试/pyright。

---

## Completion Report

1. **Re-review artifact path**: `docs/reviews/wu-tools-01-f01-03-plan-rereview-ds.md`
2. **Verdict**: PLAN REREVIEW PASS
3. **Accepted findings final status**: 7 项已修复（DS-F01/MiMo-F2, DS-F02, DS-F03, DS-F04, DS-F05, MiMo-F1, MiMo-F3），1 项证据失效（MiMo-F4 deferred），1 项不要求修复（MiMo-F5 rejected）
4. **New findings**: 无
5. **Files modified by this gate**: `docs/reviews/wu-tools-01-f01-03-plan-rereview-ds.md`（新增）
