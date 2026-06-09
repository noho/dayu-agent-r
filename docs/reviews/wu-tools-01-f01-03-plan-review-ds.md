# WU-TOOLS-01-F01-03 Plan Review (AgentDS)

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: plan review
- Reviewer: AgentDS
- Date: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Goal confirmation: `docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Review Scope

本 review 只审查 plan 是否 code-generation-ready、是否尊重设计真源、是否遵守 AGENTS.md 硬约束、是否把迁移变成重写、是否正确分类 upload 长事务风险。不做 implementation / fix / commit / push / PR。

## Evidence Collected

- 完整阅读 plan artifact（920 行），包括 6 个 implementation slices、migration map、contract changes、risk table。
- 完整阅读 `dayu/fins/ingestion_runtime.py`（2712 行），确认 `FinsIngestionOperationKind` 当前只有 `DOWNLOAD`/`PREPROCESS`、`FinsSourceDownloadAdapter` 是同步 Protocol、executor 是 daemon thread、`_run_download_job` 和 `_run_preprocess_job` 是同步方法。
- 完整阅读 `dayu/fins/ingestion/wait_adapter.py`，确认当前只绑定 `start_fins_download` 和 `start_fins_preprocess`。
- 完整阅读 `dayu/fins/tools/download_tools.py`、`download_provider.py`、`_ingestion_tool_helpers.py`，确认现有 tool→runtime→awaiting 数据流。
- 完整阅读 `dayu/fins/service_runtime.py`，确认 `get_ingestion_runtime()` 当前创建 runtime 时不传 `download_adapters`。
- 完整阅读 `dayu/config/tool_discovery.json`、`docs/engine/design.md`、`docs/host/design.md` 相关章节。
- Grep 确认 `dayu/fins` 下当前无 upload tool/provider/adapter。
- 阅读 control document 中 WU-TOOLS-01-F01-03 和 WU-TOOLS-01-F09 条目。

## Verdict

**PASS WITH FINDINGS** — 5 findings（0 critical, 3 high, 2 medium）。

Plan 的整体方向、边界尊重、迁移原则和 upload 长事务分类是正确的。6 个 slices 都具有可执行的结构（allowed files、exact changes、data flow、error handling、invariants、validation commands、completion signal、stop condition）。Plan 明确禁止重写 OLD 业务逻辑，正确使用 `ToolAwaitKind.EXTERNAL_JOB` + Fins wait adapter 处理 upload 长事务，不引入新 Host/Engine public contract。

以下 findings 不影响 plan gate pass，但必须在 implementation gate 前由 controller 裁决 disposition，否则 implementation agent 会在边界决策上遇到歧义。

---

## Findings

### Finding DS-F01 [HIGH] — 同步 Adapter Protocol 与 OLD Async/Streaming 下载器的桥接缺口

**Evidence:**
- `FinsSourceDownloadAdapter.download()` 是同步 Protocol（`def download`，非 `async def`），定义于 `dayu/fins/ingestion_runtime.py:274-291`。
- `_execute_download_request()` 同步调用 `adapter.download(adapter_request)`（line 1411）。
- `_run_download_job()` 是同步函数，通过 `FinsIngestionThreadExecutor` 在 daemon thread 中执行（line 644-649）。
- Plan Slice 2（line 442-447）说"Copy OLD SEC downloader logic and adapt imports"，但未说明如何把 OLD 下载器（很可能使用 `httpx.AsyncClient` 或等价 async HTTP）适配到同步 `FinsSourceDownloadAdapter.download()` 协议。
- Plan Slice 3（line 521-531）对 CN/HK 下载器有同样问题。
- Plan 的 Test Matrix（line 817）要求测试使用 `httpx.MockTransport`，进一步佐证 OLD 下载器使用 `httpx` 异步传输。

**Risk:**
- 如果 OLD 下载器核心逻辑是 async 的，而 adapter protocol 是 sync 的，implementation agent 面临三个选择：(a) 把 async 代码改为 sync（重写业务逻辑，违反 migration 约束），(b) 把 adapter protocol 改为 async（需修改 `FinsIngestionRuntime` 内部执行模型和 executor），(c) 在 adapter 内部用 `asyncio.run()` 桥接（引入嵌套 event loop 风险且违反 AGENTS.md 禁止胶水 seam 约束）。
- 选项 (b) 是正确方向，但会影响 `FinsIngestionRuntime._run_download_job` 和 executor 模型，这超出了 plan 当前 scope。

**Plan location:** Slice 2（line 422-499），Slice 3（line 501-575），Contract Changes（line 235-258）。

**Recommendation:**
- Implementation gate 开始前，controller 必须裁决：(a) `FinsSourceDownloadAdapter.download()` 改为 `async def download()`，(b) `_run_download_job` / `_run_upload_job` 改为 async 并通过 async executor 执行，还是 (c) 保持 sync adapter 但在文档中解释 OLD async→sync 桥接策略。
- 同步更新 Slice 2/3 的 allowed files 和 exact changes 以反映 adapter protocol 变更。

**Suggested disposition:** accepted — 改 adapter 为 async；同步更新 `FinsIngestionRuntime` 内部 job runner 和 executor。

---

### Finding DS-F02 [HIGH] — Upload Runner Protocol 未定义，Slice 1→4 Handoff 不完整

**Evidence:**
- Plan Slice 1（line 362）说"Add a private `_run_upload_job(...)` placeholder that delegates to a typed upload runner protocol"，但未定义该 protocol 的 shape。
- Plan Slice 4（line 612）说"Replace placeholder unsupported upload runner from Slice 1 with production upload runner selection"，但 Slice 1 未给出 protocol，Slice 4 无法知道 handoff contract。
- 对比 download：`FinsSourceDownloadAdapter` protocol 已在 `ingestion_runtime.py` 中明确定义（line 274-291），有明确的 `download(request) -> FinsSourceDownloadAdapterResult` 签名。Upload 缺少对等定义。
- Plan Contract Changes（line 254）说"Add a production download runner/adapter interface if current FinsSourceDownloadAdapter cannot preserve OLD workflow"，但对 upload runner 没有对称说明。

**Risk:**
- Slice 1 和 Slice 4 可能由不同 implementation agent 执行，若 upload runner protocol 未定义，Slice 4 的 agent 无法独立实现 production runner，需要回溯修改 Slice 1。
- Upload runner 需要处理文件路径验证、Docling 转换、存储写入、取消检查点等多个关注点，没有 typed protocol 会导致实现 agent 嵌入业务逻辑在 `FinsIngestionRuntime` 中。

**Plan location:** Slice 1 Functions/classes/types（line 366-373），Slice 4 Functions/classes/data flow（line 615-617）。

**Recommendation:**
- 在 Slice 1 中明确定义 `FinsUploadRunner` protocol，至少包含 `run_upload(request: FinsUploadRequest, *, cancellation_checker: Callable[[], bool]) -> FinsUploadResultSummary` 的签名。
- 与 `FinsSourceDownloadAdapter` 对等，确保 Slice 4 有明确 contract handoff。

**Suggested disposition:** accepted — 在 plan 或 implementation Slice 1 中补齐 `FinsUploadRunner` protocol 定义。

---

### Finding DS-F03 [HIGH] — Daemon Thread Executor 用于 Upload 长事务未评估

**Evidence:**
- `FinsIngestionThreadExecutor` 使用 `daemon=True` 线程（`ingestion_runtime.py:644-649`），Python 进程退出时 daemon 线程会被强制终止，不执行 cleanup。
- Plan Slice 4（line 610）说"Add cooperative cancellation checkpoints by passing a typed cancellation checker from runtime into upload workflow/service boundaries"。
- Plan Risk Table（line 844）承认"Fins jobs created by current daemon-thread executor may remain queued/running if the process dies before terminal record"，owner 为 Issue 129。
- Upload job 包含 Docling 转换（可能耗时数分钟）、文件写入、存储 upsert/delete 等外部副作用。daemon 线程中途被杀会导致：部分文件已写入 source repo 但 job record 困在 `running`、Docling 转换产物 orphan、overwrite 模式的 delete+create 不完整。
- 相比之下，download 的副作用主要是写入新 source document，overwrite 也是通过 repository 事务边界保护。Upload 的 delete action 和 overwrite 模式涉及先删后建，daemon 崩溃风险更高。

**Risk:**
- Upload 的副作用复杂度高于 download/preprocess，daemon thread 模型对 upload 的 crash safety 保证更弱。
- Plan 说 defer to Issue 129，但没有在 Slice 4 的 invariants 或 stop condition 中明确说明 upload 接受 daemon thread 的执行风险及其 crash recovery boundary。

**Plan location:** Slice 4（line 576-660），Risk Table（line 841-853）。

**Recommendation:**
- 在 Slice 4 中增加一条 invariant 或风险声明：upload 在 daemon thread 中执行，crash 时可能留下 orphan 文件/文档状态；Fins job state machine 的 `save_succeeded_or_cancelled` 原子性保护已覆盖的终态写入，但不能保护 Docling 中途产物和 overwrite 中间状态。
- 不需要在当前 WU 解决，但必须让 implementation agent 和 review agent 知道这条边界。

**Suggested disposition:** accepted — 在 Slice 4 invariants 中增加 crash risk 声明。

---

### Finding DS-F04 [MEDIUM] — `FinsUploadKind` 与 `SourceKind` 关系未定义

**Evidence:**
- Plan Contract Changes（line 241）说"Add `FinsUploadKind` if needed as `StrEnum` with `FILING` and `MATERIAL`, or use `SourceKind` directly"。
- `SourceKind` 已定义于 `dayu/fins/domain/enums.py`，值为 `FILING` 和 `MATERIAL`。
- Plan 上传 tool schema（line 267）说 `upload_kind: "filing" or "material"`。
- 但 Plan 未决策是用 `FinsUploadKind` 还是直接用 `SourceKind`。这个决策影响 `FinsUploadFilingRequest` 和 `FinsUploadMaterialRequest` 是独立 dataclass 还是用 `SourceKind` 做 discriminated union。

**Risk:**
- 如果两处选不同方案，LLM-facing schema、FinsIngestionRuntime、upload runner 三处的 kind 判断会不一致。
- Implementation agent 会在这个选择上花时间或做出与 reviewer 不一致的决定。

**Plan location:** Contract Changes（line 241-242），Upload Tool Interface（line 262-273）。

**Recommendation:**
- 裁决为直接使用 `SourceKind`（值 `"filing"` / `"material"`），因为 upload 源文档类型与 `SourceKind` 语义一致，不需要引入重复 enum。
- 在 plan 中明确写出这个裁决。

**Suggested disposition:** accepted — 使用 `SourceKind`，不引入 `FinsUploadKind`。

---

### Finding DS-F05 [MEDIUM] — Slices 2 和 3 的并行化机会未声明

**Evidence:**
- Slice 2（SEC download）和 Slice 3（CN/HK download）无代码依赖。两者都依赖 Slice 1 的 contract foundation，但彼此独立。
- 但它们共享 `FinsIngestionRuntime` 和 `service_runtime.py` 的 adapter registration。如果两个 agent 并行修改同一文件，会产生 merge conflict。
- Plan 未说明这些 slices 是必须串行还是可以并行。

**Risk:**
- 如果 controller 试图并行派发 Slice 2 和 Slice 3，两边的 adapter registration 代码（`service_runtime.py` 的 `get_ingestion_runtime()`）会发生冲突。
- 如果必须串行，排在后边的 slice 会因 adapter registration 模式不同而重新调整前一个 slice 的代码。

**Plan location:** Slices 2-3（line 422-575）。

**Recommendation:**
- 明确声明 Slice 2 和 Slice 3 必须串行（因为共享 `service_runtime.py` 的 adapter registration），并说明先后顺序：先 Slice 2（SEC）还是先 Slice 3（CN/HK）不影响结果。
- 或者抽取 adapter registration 的公共模式到 Slice 1，让 Slice 2/3 各自只提供具体 adapter 实现。

**Suggested disposition:** accepted — 声明 Slice 2→3 串行，或把 adapter registration pattern 提入 Slice 1。

---

## Residual Risks For Implementation/Review Gates

以下风险已在 plan 中正确分类，不需要在 plan gate 解决，但 implementation/review gate 必须验证：

| Risk | Plan location | Implementation gate check |
|---|---|---|
| OLD weak typing (`Any`) 替换为 strict typing 时可能触及业务分支 | Risk Table line 846 | 每个 slice 的 pyright 验证必须 clean；如发现无法替换的 `Any`，stop 并回 controller |
| HK upload 可能在 OLD 中无直接证据 | Risk Table line 848 | Slice 4 必须检查 OLD 证据；无证据时 fail HK upload explicitly |
| CN pipeline 迁移可能拉入不必要的 process/rebuild surface | Risk Table line 849 | 只迁 workflow/facade 模块；不迁 process/rebuild 除非测试要求 |
| Service assembly 的 upload awaiting provider recognition | Risk Table line 850 | Slice 5 只扩展现有 assembly；不引入新 Host public option |
| Issue 129 tracking for `start_upload` | Risk Table line 843 | Slice 6 必须获得 controller 授权或 stop with blocking residual risk |
| Fins daemon thread crash 残留 `running` job | Risk Table line 844 | Deferred to Issue 129；当前 WU 不解决 |
| 外部 job physical cancel 不保证 | Risk Table line 845 | Deferred to WU-WAIT-03 / Issue 92 |

## Plan Completeness Assessment

| Dimension | Status | Notes |
|---|---|---|
| Migration vs rewrite boundary | PASS | Plan 明确标注迁移规则，OLD→NEW map 完整，stop conditions 覆盖 |
| Host/Engine boundary respect | PASS | Upload 走 `ToolAwaitKind.EXTERNAL_JOB` + 已有 wait adapter，不改 Engine `ToolExecutor` protocol |
| AGENTS.md compliance | PASS | 禁止 Any/object/re-export/facade 均有明确约束和 stop condition |
| Upload long-transaction classification | PASS | 生命周期 10 步清晰，与 download/preprocess 对称 |
| Slice executability | PASS WITH FINDINGS | 6 slices 均有 allowed files/exact changes/validation；DS-F01/DS-F02 需先裁决 |
| Test coverage plan | PASS | 每 slice 有对应 test files 和 expected assertions；no live network |
| README update triggers | PASS | Slice 6 正确引用各 README 的 `Agent更新约束` |
| Stop conditions | PASS | 每 slice 有明确 stop condition；contract change 有 blocking conditions |
| Issue 129 tracking | PASS | Plan 明确标注"plan gate 不修改 Issue"，implementation closeout 必须获得授权或 stop |
| Non-goals clarity | PASS | 明确排除 prepare/activate、Host/Engine contract change、UI/CLI/OLD registry migration |

## Files Modified In This Gate

Only the review artifact was created:

```
?? docs/reviews/wu-tools-01-f01-03-plan-review-ds.md
```

Controller-owned dirty files remain untouched:
```
M  docs/host/issues-implementation-control.md
?? docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md
?? docs/reviews/wu-tools-01-f01-03-goal-confirmation-controller.md
```

## Completion Report

1. **Review artifact path:** `docs/reviews/wu-tools-01-f01-03-plan-review-ds.md`
2. **Verdict:** PASS WITH FINDINGS
3. **Findings count by severity:** 0 critical, 3 high, 2 medium
4. **Residual risks / open questions:**
   - DS-F01: 同步 `FinsSourceDownloadAdapter` protocol 与 OLD async 下载器的桥接方案需 controller 裁决
   - DS-F02: `FinsUploadRunner` protocol 需在 Slice 1 定义以完成 Slice 1→4 handoff
   - DS-F03: Daemon thread executor 用于 upload 的 crash safety 需声明
   - DS-F04: `FinsUploadKind` vs `SourceKind` 需裁决
   - DS-F05: Slice 2/3 并行化风险需声明
   - 7 条 residual risks 已由 plan 正确分类到 Issue 129 / WU-WAIT-03 / Issue 92 等 owner
5. **Files modified by me:** `docs/reviews/wu-tools-01-f01-03-plan-review-ds.md` (created)
