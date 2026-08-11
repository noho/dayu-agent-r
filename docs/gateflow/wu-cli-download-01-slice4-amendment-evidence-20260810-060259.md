# WU-CLI-DOWNLOAD-01 Slice 4 Allowlist Amendment Evidence

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-01`
- Slice：Slice 4 — Storage concurrency 与 integrity repair（DL-F08、DL-F10）
- 当前 gate：implementation precondition / owner call-chain inventory
- Decision：**STOP — 需要先修订并复核 Slice 4 allowlist 与 SEC downloader contract**
- 当前 HEAD：`399a686f8113fb39c014b98938cfaf0d0d525b3e`
- Branch：`codex/download-oracle`
- 工作树 preflight：开始时干净；本 artifact 写入前已撤回全部试探性 production 修改，产品与测试代码相对 HEAD 零 diff。
- Artifact path：`docs/gateflow/wu-cli-download-01-slice4-amendment-evidence-20260810-060259.md`

## 2. 目标与 stop condition

Slice 4 要求 SEC/CN 都执行 `Phase A classification -> lock 外 prefetch -> begin_batch/latest-copy -> staged identity-first revalidation`，并以 AST/call-graph 证明 provider/PDF/Docling I/O 不可达 `begin_batch` 到 commit/rollback 区间。

计划与用户指令同时规定：若 owner inventory 发现锁语义冲突、call graph 无法证明，或实现必须越出 allowlist，应立即停止并产出 amendment evidence；不得用 timeout、validator 放宽、compat/capability shim 或越界修改继续实现。

该 stop condition 已成立，且仅发生在 SEC target payload prefetch 边界。CN 当前调用图已把 PDF 下载与 Docling conversion 放在 `_commit_cn_filing_assets_batch()` 的 `begin_batch()` 之前，不构成本次 blocker。

## 3. Owner / implementer inventory

### 3.1 Storage owner

- `SourceDocumentRepositoryProtocol` 的 production 直接实现只有 `FsSourceDocumentRepository`，其操作委托共享 `_FsSourceDocumentCore`。
- 计划列出的 tests spy 均继承 production wrapper；`tests/fins/test_sec_pipeline_download.py` 另有显式 `cast(SourceDocumentRepositoryProtocol, ...)` fake，但位于 Slice 4 test allowlist 内。
- 普通 writer 与 recovery lock 入口已经分离：普通 writer 经 `_acquire_ticker_lock()`；recovery 经 `_try_acquire_recovery_ticker_lock(... blocking=False)`。DL-F08 本身可在现有 storage allowlist 内完成。

### 3.2 SEC target payload call chain

直接调用链为：

```text
run_download_single_filing_stream
  -> begin_batch(ticker)
  -> SecDownloader.download_files_stream(..., batch=token, store_file=...)
       -> _http_download_if_modified(...) / _http_download(...)
       -> store_file(..., batch=batch)
            -> DocumentBlobRepositoryProtocol.store_file(..., batch=batch)
  -> source upsert
  -> commit_batch / rollback_batch
```

直接代码证据：

1. `dayu/fins/pipelines/sec_download_filing_workflow.py:445-465` 在进入 `download_files_stream` 前取得真实 batch，并把 token 传入 downloader。
2. `dayu/fins/downloaders/sec_downloader.py:84-109` 的 `StoreDownloadedFile` contract 要求显式 `BatchToken`，语义是 storage 写入 callback。
3. `dayu/fins/downloaders/sec_downloader.py:1488-1516` 的 `download_files_stream` 同时要求 `StoreDownloadedFile` 与 `batch`。
4. `dayu/fins/downloaders/sec_downloader.py:1534-1596` 在同一个方法内先执行远端 HTTP，再立即调用 `store_file(..., batch=batch)`。
5. `dayu/fins/pipelines/sec_download_persistence.py:158-177,480-510` 证明 production callback 最终调用 `DocumentBlobRepositoryProtocol.store_file`，不是 storage-neutral payload collector。

因此当前 call graph 明确证明的是“HTTP 位于 writer lock 内”，与 Slice 4 invariant 相反；无法在现有 allowlist 内证明锁外 I/O。

## 4. 被拒绝的局部绕法

以下路径均被拒绝，不进入实现：

1. **伪造 `BatchToken` 给 downloader 的内存 callback**：`BatchToken` 是 storage owner capability；构造未登记 token 即使 callback 暂时忽略它，也会把无效 authority 伪装成 typed capability，违反语义所有权与 strict contract。
2. **从 workflow 直接调用 `_http_download*` 私有方法**：绕过 SEC downloader 的 retry、throttle、取消、错误投影 owner，并形成反向依赖私有实现的胶水 seam。
3. **继续使用真实 batch、只把 payload 复制到内存**：现有 callback 即使带 `payload_sink` 仍会调用 repository `store_file`；HTTP 依然发生在 writer lock 区间。
4. **在 allowed workflow 中重复实现 HTTP/retry/304 逻辑**：制造第二套 provider policy 真源，违反 source of truth 与最小依赖约束。
5. **新增 timeout 或放宽 complete validator**：与 DL-F08/DL-F10 明确不变量直接冲突，且不能消除锁内 provider I/O。

## 5. 最小 plan / allowlist amendment 建议

在继续 Slice 4 前，建议先经过 plan fix + 双路 re-review，仅增加以下最小 scope：

### Production allowlist 增量

- `dayu/fins/downloaders/sec_downloader.py`

该文件是 SEC HTTP、retry、throttle、304、取消与文件级安全失败事实的现有 owner。应在此增加 storage-neutral typed prefetch contract，例如：

- typed prefetched file/event 同时携带 descriptor transport facts 与 `bytes`；
- 新的 `prefetch_files_stream(...)` 不接受 `BatchToken`、不接受 storage callback；
- 现有 `download_files_stream(...)` 若仍有其它真实消费者，应复用同一 prefetch core 后再以真实 batch materialize，禁止复制 HTTP policy；
- Slice 4 filing workflow 消费 storage-neutral prefetch，Phase B identity-first 通过后才使用现有真实 storage callback 在 batch 内写 blob。

这不是 compatibility shim：它把当前混合在一个函数中的 provider payload acquisition 与 storage materialization 拆回各自 owner，并由单一 downloader core 保持 transport 语义同源。

### Test allowlist 增量

- `tests/fins/test_sec_downloader.py`

新增 owner assertions：storage-neutral prefetch 不要求/构造 `BatchToken`，完整覆盖 200/304/empty/failure/cancellation，且原 `download_files_stream` 与新 prefetch 路径共享同一 transport decision core。既有 Slice 4 SEC workflow tests继续负责 barrier/race/last-writer/no-I/O-under-batch 证明。

### 无需增加的 scope

- 不需要修改 Oracle、registry、真实 CLI/provider 装配、Host/Engine、PR190、README 或 production timing hook。
- 暂无证据要求修改 `dayu/fins/pipelines/sec_download_persistence.py`：Phase B 可在 identity-first 通过后复用现有 storage callback，以真实 token materialize 已预取 bytes。
- storage typed integrity 与 per-ticker reservation 仍可保持原 Slice 4 allowlist。

## 6. Validation / evidence commands

已执行：

```text
git branch --show-current
git status --short
git rev-parse HEAD
rg / nl / sed owner-call-chain inventory
git diff --check
```

结果：branch/HEAD/preflight 与用户给定状态一致；产品/测试代码已恢复至 HEAD；`git diff --check` 通过。曾在试探性局部修改期间启动 storage owner union，前 243 项通过后旧 fail-fast test 因预期语义已被 blocking writer 改变而等待；该运行被主动中止，试探性代码与测试影响均已撤回，因此不作为当前实现 pass 证据。

未运行 full pyright/Ruff/format/compileall/coverage：没有可接受 implementation，运行这些检查不能解除 contract blocker，也不得伪装 Slice 4 已完成。

## 7. Docs decision

- README：未修改；按用户指令保留到四 slices 后 documentation closeout。
- Plan artifact：未修改；本文件只记录 amendment evidence，等待 plan fix/re-review 授权。
- Oracle / registry：`not updated`。

## 8. Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
|---|---|---|
| SEC downloader 把 HTTP 与 storage batch callback 绑定，无法满足锁外 prefetch | requiring new issue or explicit user decision | 当前 WU plan fix：扩充上述 production/test allowlist并双路 re-review |
| DL-F08 storage blocking writer / notify 尚未实现 | covered by later approved slice | Slice 4 implementation，待 amendment accepted 后继续 |
| DL-F10 published/staged integrity 与 SEC/CN 3-round revalidation 尚未实现 | covered by later approved slice | Slice 4 implementation，待 amendment accepted 后继续 |
| 底层 OS/file lock 永久 I/O 卡死 | assigned to later work unit | 既有计划 residual；本 WU 禁止用业务 timeout 掩盖 |

## 9. Completion status / next entry point

- Slice 4 implementation：**未完成，按 hard stop 正确暂停**。
- Code review：**未进入**；不得声称位于 MiMo/DS 双路 code review 入口。
- Blocking question：是否接受最小 allowlist amendment，并授权先更新 plan、执行 planreview 双路 re-review，再重新进入 Slice 4 implementation。
- Next Gateflow entry point：`plan fix -> plan re-review`，不是 `code review`。
