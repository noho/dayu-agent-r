# WU-SEMANTIC-OWNERSHIP-01 R06 plan review fix — AgentCodex

## 0. 身份、目标与结论

- umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01` continuation；仍是同一 R06，不创建新 WU。
- gate：`R06 remediation plan review fix`。
- target plan：`docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`。
- Controller 裁决：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-controller-adjudication.md`。
- 本机时间：`2026-07-16 03:40:43 +0800`，由本机 `date` 读取。
- base HEAD：`9c07b88d9e855f19f0b828f671022119cc5599a1`。
- 修复前 immutable plan SHA-256：`f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`，563 行。
- 修复后 plan SHA-256：`ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43`，585 行。
- fix-gate conclusion：`pass`。Controller accepted `R06-PF-01..08` 已全部落实到同一 plan；plan 仍未 accepted，下一步只能是 Controller 验证和两路 fixed-complete-plan re-review，不授权 implementation、stage、commit、push 或 PR。

## 1. Reviewed target、scope 与只读输入

本次完整读取并以其作为约束或证据：

- `AGENTS.md`；
- `docs/host/issues-implementation-control.md`；
- `docs/fins/design.md`；
- 修复前 R06 plan 全文；
- AgentMiMo 与 AgentDS 两路最终 plan review 全文；
- Controller plan-review adjudication 全文。

允许写入的闭集只有：

1. `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`；
2. 本 artifact。

未修改 product、test、README、design、control、既有 review；未 stage、commit、push 或创建 PR。当前 `issues-implementation-control.md` 的 tracked 修改以及 plan/review/controller 输入的 untracked 状态均是进入本 gate 前的既有 workspace 状态，不由本次修复产生。

## 2. 第一性原理与 assumptions tested

### 2.1 动机与 owner

动机成立且严重性未被高估：

- `dayu/fins/domain/document_models.py:416-443` 的 public `BatchToken` 暴露 owner 与物理路径；
- `dayu/fins/storage/_fs_storage_infra.py:64-108,423-522` 用 `ContextVar`、task/thread identity 与 auto-batch 决定 mutation authority；
- `_fs_storage_infra.py:261-264` 在 `target -> backup` 与 `staging -> target` 两次 rename 间存在真实 online missing-target window；
- `dayu/fins/storage/_fs_source_document_core.py:1071-1115` 用 `ingest_complete=false` source meta 承担 staging acknowledgement；
- `dayu/fins/storage/_fs_blob_core.py:143` 要求 blob 写入前已有 source meta。

正确 owner 仍是 `dayu.fins.storage`：显式 transaction capability、active registry、完整 staged-tree validator、writer mutex、publication guard 与 recovery 必须同源；producer 只拥有业务输入与短 transaction 边界。

### 2.2 特殊 review lenses

- **Architecture boundary**：publication guard 复用层中立的 `dayu.runtime.filelock`，Fins storage 只拥有锁路径与使用语义；没有让 runtime 反向依赖 Fins，也没有把 read 补偿下沉到 processor/UI/fixture。
- **Best practice**：把长 writer mutex 与短 publication lock 分离；public outer guarded entry 只获取一次非重入跨进程锁，private helper 明确 unguarded，避免自死锁与 ambient lock-state marker。
- **Optimal solution**：沿用当前两次 rename 与现有跨进程 filelock，未引入 generation pointer/selector；完整 staged-tree validator 比 touched-set tracking 少一套状态与闭包证明。
- **Overengineering**：明确拒绝 R06 内修改 `materialize()`、增加 path copy/fd wrapper/lease/revision API、callback framework、touched-set framework或固定 diff 行数 gate。
- **Overcoupling**：CN company meta 与逐文档 Docling 分成可重试的短 publication units；四个 production composition root共享同一 core，但不从 source facade 反射 batching authority；S1/S2/S3 只作为累计 review checkpoints，不制造兼容中间版本。

## 3. Accepted fix ledger

### R06-PF-01 — 已关闭：独立 per-ticker 跨进程 publication lock

- **plan 修改位置**：§4.2、§7.1 Tests、§8.4、§12。
- **落实内容**：固定使用 `batch_locks/<ticker>.publication.lock`，按 normalized ticker 分片，复用 `RuntimeFileLockToken`；与长 writer `batch_locks/<ticker>.lock` 分离，不进入 token/journal/meta。guard 只做并发 exclusion，不校验 batch。
- **guarded/unguarded 边界**：每个 public published read outer entry 获取一次 guard并持有到本次 meta/list/bytes I/O结束；内部只调用 private unguarded helper。禁止 `ContextVar`、task/thread-local、ambient“已持锁”标记、public 参数或重入 public read。
- **锁序**：writer/recovery 只能先 writer mutex 后 publication guard，释放顺序相反；reader只拿 publication guard，不允许反向嵌套。
- **`Source.open()`**：Fins `LocalFileSource` 通过窄 typed storage opener在延迟 open 时获取同一 guard，到 fd 成功打开或失败后释放；成功 fd保持 old-or-new stable file。
- **直接证据**：`_fs_storage_infra.py:56,597,651-688` 已有 per-ticker writer filelock；`dayu/runtime/filelock.py:68,220` 提供跨进程 token/API；`_fs_storage_infra.py:261-264` 是必须覆盖的 rename window。当前没有 publication lock，故必须新增独立路径而不能复用 writer lock。

### R06-PF-02 — 已关闭：`materialize()` 全调用图与 R07 residual

- **plan 修改位置**：§4.2、§11、§12。
- **落实内容**：记录当前 8 个 production 文件、9 个 `.materialize()` 调用点：
  - `dayu/documents/processors/bs_processor.py`；
  - `dayu/documents/processors/docling_processor.py` 两处；
  - `dayu/documents/processors/markdown_processor.py`；
  - `dayu/fins/processors/sec_processor.py`；
  - `dayu/fins/processors/bs_report_form_common.py`；
  - `dayu/fins/processors/bs_six_k_processor.py`；
  - `dayu/fins/processors/source_text.py`；
  - `dayu/fins/pipelines/sec_fiscal_fields.py`。
- **`source_snapshot.py` 核验**：它是 production `Source` adapter，`dayu/tools/doc_tools.py:1583,1670,1776,1824` 会使用它；但它不是 upstream bare-path `materialize()` 的独立 consumer。`source_snapshot.py:260-293` 通过一次 `self._source.open()` 复制到自有 spool，`:345-388` 的 `materialize()` 只物化该稳定 spool。因此不把它列入上述裸路径调用点。
- **residual owner**：裸 `Path` 返回后的延迟/多次读取仍由 R07 storage revision/snapshot 独占；R06不改变public contract，也不声称覆盖全部Source read。
- **直接证据**：`rg -n '\.materialize\(' dayu --glob '*.py'` 只返回上述9个production调用点；`source_snapshot.py` 没有调用 upstream `.materialize()`。

### R06-PF-03 — 已关闭：callback 精确 callable contract

- **plan 修改位置**：§6 inventory/closure contract、§7.3 Tests、§12。
- **落实内容**：固定返回 callback 等价签名为 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`；`SecDownloader.download_files_stream` / `download_files` 都新增 required keyword-only `batch`，每次调用 `store_file(filename, stream, batch=batch)`。`partial`只绑定 repository/handle/ticker/document 等非authority输入；batch不得绑定/capture。
- **严格类型**：普通 `Callable[[...]]` 无法表达 keyword-only 参数，plan要求窄 callable protocol或等价严格类型，不引入callback framework。
- **直接证据**：`sec_download_persistence.py:139-164,459-480` 当前返回 `Callable[[str, BinaryIO], FileObjectMeta]` 并用 `partial`，底层callback无batch；`sec_downloader.py:1358-1372,1511-1527` 当前downloader contract同样无batch。

### R06-PF-04 — 已关闭：全 staged ticker tree validator与新双向manifest invariant

- **plan 修改位置**：§3.2、§5.2、§7.2、§12。
- **落实内容**：删除“full tree / touched identities 实现时再选”；固定遍历完整 staged ticker tree，不维护 touched set。source→manifest 与 manifest→source 双向一致性明确为新的 storage-owned commit-time invariant。
- **其它 invariant**：`primary_document` 必须同时命中files manifest和物理文件；files非空是当前所有producer产生blob前提下的有意contract，未来meta-only需求必须先改owner contract，不能增加validator例外。
- **直接证据**：`_fs_storage_infra.py:225` 从完整published ticker tree copy-on-stage，commit发布完整ticker tree；`_fs_source_document_core.py:618,641,1020,1043,1169,1192` 当前随mutation写manifest，但没有commit-time全树双向闭包验证。全树方案无需第二套touched状态。

### R06-PF-05 — 已关闭：S1 删除全部 implicit/ambient authority

- **plan 修改位置**：§7.0、§7.1 Contract handoff/Tests、§7.3、§8.3、§12。
- **落实内容**：S1 required-protocol/core cutover同时删除 `_execute_with_auto_batch`、`_BATCH_OWNER_CONTEXT`、`_bind_batch_owner`、`_unbind_batch_owner`、`_require_batch_owner`、`_current_execution_scope_id`、task/thread owner推断及相关ambient helper；private manifest helper显式接收resolved state/batch/path。S3只做真实producer/callback propagation与零残留证明。
- **直接证据**：`_fs_storage_infra.py:64,89,423-522,1132,1171,1210,1356-1399` 当前authority和read/write routing均依赖这些ambient/auto-batch helpers；required batch进入S1后继续保留它们会形成第二authority。

### R06-PF-06 — 已关闭：CN company meta与逐文档Docling分离短transaction

- **plan 修改位置**：§6 inventory、§7.3 Tests、§12。
- **落实内容**：CN company meta write是outer workflow拥有的短transaction；每个document的Docling write是另一个top-level caller拥有的短transaction。company meta成功、某document失败是可重试的分离publication unit，不跨transaction rollback，不新增profile/framework。
- **Docling contract**：`_handle_storage_write(..., *, batch: BatchToken)`或等价storage-write入口只消费caller batch，删除service内部begin/commit/rollback；commit开始前的cancel/exception由caller rollback。
- **直接证据**：`cn_pipeline.py:844-852,1097-1105` 当前先upsert company meta再调用Docling service；`docling_upload_service.py:331,403,422` 当前service内部自行begin/commit/rollback。把两者强绑成一条长事务没有当前一致性需求，且会扩大writer mutex持有期。

### R06-PF-07 — 已关闭：新的 shared-core production batching composition

- **plan 修改位置**：§3.5、§7.3 Production allowlist/Tests、§12。
- **落实内容**：明确当前production没有实例化`FsBatchingRepository`；S3必须在`service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py`四个真实composition root首次装配它，并与source/blob/processed/company/maintenance wrappers共享同一个`_FsRepositorySet`/core。禁止从source repository反射、cast或拆core。
- **直接证据**：`service_runtime.py:347`、`cn_pipeline.py:373`、`sec_pipeline.py:509` 当前各自创建shared set但未建batching wrapper；standalone 6-K在`sec_6k_primary_document_repair.py:162-164`分别创建repository实例。`rg -n 'FsBatchingRepository' dayu tests`显示production只有storage导出/类定义，实例化均在tests。

### R06-PF-08 — 已关闭：S1/S2/S3 cumulative reviewability gates

- **plan 修改位置**：§7.0、§8开头、§12。
- **落实内容**：三个slice是同一breaking cutover的累计working-tree checkpoints。每个slice结束、下一slice开始前执行Controller scope/focused-test验证与MiMo/DS双路cumulative review；accepted finding必须fix/re-review。gate不生成中间accepted commit，不把尚未propagation的预期类型错误包装为green。
- **最终接受边界**：S3后仍运行完整focused/full validation，并对complete R06 diff做统一双路code review/fix/re-review；只有final tree可进入accepted local commit裁决。
- **无magic threshold**：未采用review建议的固定约1500行，也未设置文件数阈值；Controller按semantic owner、实际diff与可审性裁决是否收窄任务，但不得拆compat版本。
- **直接证据**：总控“Slice切分原则”要求按semantic closure、依赖与失败风险切分，明确禁止把上下文规模等同于行数；R06 required `batch=` 会让S1/S2累计树在producer propagation前预期类型不完整，故reviewability与green/acceptance必须分离。

## 4. Stale wording / deferral 清理

已从plan清除或改写以下与Controller裁决冲突的陈旧表述：

- publication guard机制留给实现决定；
- validator在full staged tree与touched identities间实现时再选；
- CN转换/校验边界留给plan review再裁决；
- implicit mutation删除推迟到S3；
- slice-level review是否需要尚未决定；
- umbrella外required allowlist仍待review接受；
- 修复前plan完成后再进入初次双路review的旧gate文案。

## 5. Scope、diff 与 SHA

### 5.1 实际diff scope

- 修改：R06 plan，修复前SHA `f147079b...2336cd` → 修复后SHA `ed057fdf...03e43`，563 → 585行。
- 新增：本plan-fix artifact。
- 未修改：product/test/README/design/control/既有review。

目标plan在进入本gate前已是untracked文件，因此普通`git diff`无法提供“相对修复前plan”的tracked hunk；本artifact用Controller记录的immutable pre-fix SHA、修复后本地SHA、行数、逐项位置与最终`git status --short`共同界定diff，不把整个untracked plan误报成由本gate从零新增。

### 5.2 未触碰输入 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/host/issues-implementation-control.md` | `24415026f517c7a9d3c038288e7b7678e260b0c18babd486763e898683168a34` |
| `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| MiMo review | `2b545d4bedba4675c6e61d572b88ae2721270795fbea2886c2ad14e4f19b299d` |
| DS review | `c62d778f70fdef5365e83f8531ca73de8e0262362c65a1fd4fadf5bab1cf2056` |
| Controller adjudication | `478bd67b255f08348463bb3a3dd28e270433a41f852cc052e17259b691354090` |
| plan-entry Controller validation | `1a96545a85aeb59e3586370267bb019f5a2713482077eed43d3d8e2d0e814f22` |

## 6. Open questions、residual risks 与 tracking

### Open questions

无。八项 accepted fix 均能在既定 owner boundary 内落实，没有需要用户重新裁决的产品问题。

### Residual risks

1. R07仍唯一拥有跨repository call/长processor生命周期的snapshot/revision，包括8个文件/9个裸`materialize()`调用点；追踪到同umbrella后续R07，不在R06补偿。
2. R06 implementation必须用真实跨进程barrier证明publication lock、outer/private read boundary与锁序；若`RuntimeFileLockToken`不能支撑`LocalFileSource.open()`的延迟open seam，按plan stop回storage owner设计，不缩小测试或延期rename window。
3. S1/S2累计树会有尚未producer propagation的预期repo-wide类型错误；slice gate必须精确区分当前owner test结果与最终green状态，不能把预期失败登记成baseline或accepted state。
4. fixed plan尚未经过Controller validation与两路完整re-review；`pass`只表示本fix gate闭合，不表示plan accepted。

## 7. 验证

- `git diff --check`：PASS，无输出。
- 两个允许写入文件均为untracked，另分别执行 `git diff --no-index --check /dev/null <file>`：无whitespace诊断输出；exit code `1`只表示文件相对`/dev/null`存在内容差异。
- 内容扫描：未发现“validator两策略实现时再选”“CN/Docling plan review再裁决”“implicit mutation推迟到S3”“slice review未决定”等stale wording。
- 直接调用图：`.materialize()`为8个production文件/9个调用点；`source_snapshot.py`确认不是upstream bare-path materialize consumer。
- 工作区范围：本gate只写target plan与本artifact；既有control/review状态保持不变。

## 8. Final plan review conclusion

`pass` for R06 remediation plan review fix。

R06-PF-01..08全部关闭，未发现新的material finding或blocking question。停止在plan fix；下一步只能由Controller验证并触发AgentMiMo/AgentDS对fixed complete plan的两路re-review。
