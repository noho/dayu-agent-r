# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Fins Storage Atomicity Plan

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-C`
- Gate: `plan fix`
- Risk profile: `production-high`
- Status: `pass`
- Plan owner: `AgentCodex`
- Implementation authorization: none；本 artifact 只定义后续 code-generation-ready 实施边界，不实施代码。
- Source adjudication:
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-goal-confirmation.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-controller-adjudication.md`

## Goal

在不引入工具安全策略、远端下载策略或新的 durable Fins job system 的前提下，关闭以下 owner 级语义：

1. `dayu.fins.storage` 在任何文件系统 key/path 构造前统一校验 ticker、document id、entry name、filename 与 local object key；blob 写入前确认 `SourceHandle` / `ProcessedHandle` 对应文档真实存在。
2. Fins filesystem batch 把“方法成功返回”和“新 target 已成为已提交状态”绑定到同一个明确 commit point；commit 报错时不得把新 target 当作成功状态暴露。
3. 单个财报文档的 upload/download mutation 对 source meta、blob 与 processed reprocess 状态实行同成同败；取消、业务异常与 commit 失败后，正式 target 必须保持操作前状态或保持不存在。
4. CN/HK downloader 不再把 `delete=False` 临时 PDF 的清理责任跨异步线程/生成器边界转交给 workflow；成功、取消、异常、iterator/generator close 均不遗留临时 PDF。
5. `dayu.fins` 不再 import `dayu.host`；Fins observation 到 Host wait contract 的 cross-domain glue 归属 `dayu.service` assembly，Host 只向 adapter 投影最小 typed snapshot。

## First-Principles Judgment

R3-C 动机成立，且不是样式或“多加几条校验”的低风险 cleanup。

### F1 — Storage identity 与 handle existence

- 严重性判断：接受，production-high。
- 第一性原理：文件系统路径的业务身份必须在拥有布局和 key construction 的 storage owner 处成立。只在调用方、工具 schema 或最终 `Path.resolve()` 后补救，会让同一个 ticker/document/file 事实在不同入口拥有不同解释。
- 直接证据：
  - `dayu/fins/storage/_fs_storage_utils.py:30-52` 的 `_normalize_ticker()` 在 ticker 真源无法识别时只做 `strip().upper()`；`dayu/fins/storage/_fs_storage_infra.py:1202-1215` 随后直接用该字符串拼 `portfolio_root / ticker`，因此 fallback ticker 尚未满足单路径组件不变量。
  - `dayu/fins/storage/_fs_storage_utils.py:82-125` 已分别存在 entry/document-id 单组件校验，但 `dayu/fins/storage/_fs_blob_core.py:141-147` 的 `store_file()` 只 `strip()` filename，随后直接构造 store key，没有复用 entry-name owner。
  - `dayu/fins/storage/_fs_blob_core.py:144-147` 只对 `SourceHandle` 调用 `_get_handle_meta()`；`ProcessedHandle` 可在不存在 processed meta 时直接构造 key 并写 blob。
  - `dayu/fins/storage/_fs_storage_infra.py:939-958` 会校验 ticker/document id，但把未校验 filename 原样拼入 object key。
  - `dayu/fins/storage/_fs_storage_utils.py:196-218` 解析 `local://` URI 后直接 `resolve()` 返回，没有把解析结果约束回 `portfolio_root`；这是 storage-produced/consumed object identity，不是本 WU 排除的远端 URL 安全策略。
- 语义 owner：`dayu.fins.storage`，具体为 `_fs_storage_utils` 的 identity validator、`_FsStorageInfra` 的 layout/key builder 和 `_FsBlobMixin` 的 handle-backed blob mutation boundary。
- 修复边界：只在 storage owner 或它直接消费的 typed handle/object-key 输入处修复；不在 downloader、upload tool、read runtime、测试 fixture 或 UI 做 fallback。

### F2 — Filesystem commit atomicity 与 LocalFileStore durability

- 严重性判断：接受，production-high。
- 第一性原理：`commit_batch()` 的返回/异常是调用方唯一可依赖的提交事实。若方法抛错但新 target 被保留，caller 会报告失败，而 source/blob/processed 新状态已经对后续读者可见，形成双真源。
- 直接证据：
  - `dayu/fins/storage/_fs_storage_infra.py:260-270` 先备份、切换 target、删除 backup，最后才写 `COMMITTED` journal。
  - `dayu/fins/storage/_fs_storage_infra.py:272-289` 在 target 已切换且无法恢复时设置 `preserved_swapped_target=True`，保留新 target 后仍重新抛出异常。
  - `dayu/fins/storage/_fs_storage_infra.py:720-737` 把 `SWAPPED_TARGET` + target/backup 并存解释为删除 backup，即把尚未写入 `COMMITTED` 的状态恢复为提交成功；这与“commit 报错即未提交”不一致。
  - `dayu/fins/storage/local_file_store.py:63-78` 使用固定 `.part` 名写入并 `replace()`，但没有唯一临时名、异常清理、文件 `fsync` 或 replace 后目录元数据刷新。
  - `dayu/fins/storage/_fs_storage_utils.py:463-487` 已提供同目录 unique temp、文件 fsync、atomic replace 与目录 fsync 的 JSON 写入先例，说明无需引入新 runtime framework。
- 语义 owner：`_FsStorageInfra.commit_batch()/recover_orphan_batches()` 拥有 batch commit state machine；`LocalFileStore.put_object()` 拥有单对象落盘原子性和 best-effort crash durability。
- 接受范围：只增强当前 local filesystem owner，不设计分布式事务、WAL 服务、跨设备 copy fallback 或远端对象存储事务。

### F3 — Upload/download document mutation atomicity

- 严重性判断：接受，production-high。
- 第一性原理：atomicity unit 是“一份 document 的正式 repository mutation”，不是整个多文档 download run。一个 document 的 final source meta、其 blobs 和关联 processed reprocess 标志必须来自同一个 storage batch；不同 document 之间仍可独立提交，避免扩大锁时长和失败 blast radius。
- 直接证据：
  - `dayu/fins/pipelines/docling_upload_service.py:329-333` 只在 overwrite existing 时开启 batch；create 和普通 update 的 staging meta/blob 会通过各 repository auto-batch 分步提交。
  - `dayu/fins/pipelines/docling_upload_service.py:399-402` 在 `commit_batch()` 前把 `token` 清空，commit 抛错后 `:417-420` 无法再进入 rollback 分支。
  - `tests/fins/test_docling_upload_service.py:288-322` 当前测试明确固化“final upsert 失败后保留 incomplete meta 与两个 blob”的偶然行为；这与本轮成功信号相反，测试必须迁移到 owner contract，而不能让生产实现保留兼容分支。
  - `dayu/fins/ingestion_runtime.py:3790-3812` 虽然对 generic downloaded document 开启 batch，但同样在 commit 前清空 token；commit failure 的 all-or-nothing 只能依赖当前不成立的 storage commit contract。
  - `dayu/fins/pipelines/cn_download_filing_workflow.py:159-185` 在 PDF/Docling 完成前 reset/create staging source，`:360-421` 又分步写 PDF blob 与 staging meta，`:481-535` 最后写 Docling blob、final source 与 processed 标志；这些步骤目前不是一个显式 document batch。
  - `tests/fins/test_cn_download_workflow.py:598-629` 当前取消测试明确断言 Docling convert 后保留 incomplete staging source，证明失败语义已被测试固化。
- 语义 owner：upload 文档 mutation 由 `DoclingUploadService` 编排；generic adapter result persistence 由 `FinsIngestionRuntime` 编排；CN/HK 单 filing mutation 由 `cn_download_filing_workflow` 编排；三者都必须使用同一个 `dayu.fins.storage` batch source of truth。
- 不采用的路径：不在失败后逐文件 best-effort delete；不从 old meta 重算补偿；不在结果 projection 隐藏 partial state；不新增跨 repository compensation bag。

### F4 — CN/HK temp PDF lifecycle

- 严重性判断：接受，production-high cancellation/resource lifecycle finding。
- 第一性原理：资源创建者不能把 cleanup authority 交给一个可能永远收不到返回值的异步 consumer。`asyncio.to_thread()` 的 await task 被取消/生成器关闭时，同步线程仍可能完成并创建 temp file，但 coroutine 不再取得 `pdf_path`，下游 `unlink()` 无法执行。
- 直接证据：
  - `dayu/fins/downloaders/cninfo_downloader.py:337-353` 和 `dayu/fins/downloaders/hkexnews_downloader.py:334-350` 使用 `NamedTemporaryFile(delete=False)`，返回 `pdf_path`。
  - `dayu/fins/pipelines/cn_download_filing_workflow.py:206-246` 通过 `asyncio.to_thread()` 获取 asset；只有拿到返回值后，`:247-285` 才能在读成功/取消/异常分支 unlink。
  - `tests/fins/test_cninfo_downloader.py:1162-1178` 与 `tests/fins/test_hkexnews_downloader.py:1152-1179` 当前只测试临时路径唯一并由测试手工 unlink，没有覆盖 coroutine cancellation 或 generator close 丢失 handoff 的窗口。
- 语义 owner：`CnReportDiscoveryClientProtocol.download_report_pdf()` 的 downloaded asset contract 和两个 downloader 实现。
- 实施决策：移除没有业务价值的持久 temp handoff，`DownloadedReportAsset` 直接拥有已校验 `pdf_bytes: bytes`、digest、length 与 timestamp。HTTP client 当前已经完整持有 `response.content`，因此该变化消除一次磁盘 roundtrip 和 cleanup seam，不新增 remote byte budget，也不改变 URL/TLS/redirect policy。

### F5 — Fins -> Host reverse import

- 严重性判断：接受，architecture boundary finding。
- 第一性原理：Fins observation 是业务能力；Host wait record/outcome 是宿主治理。把两者映射的代码必须位于同时被授权理解两侧的 Service composition boundary。Fins 不应知道 Host durable row，Host 也不应 import Fins。
- 直接证据：
  - `dayu/fins/ingestion/wait_adapter.py:49-74` import Host API、durable `WaitRecordRow` 和 Host wait-adapter internals。
  - `dayu/service/host_assembly.py:28-38` 已经是 Fins runtime/tool 与 Host registry 的实际 assembly consumer；`:1885-1978` 构造 Fins wait/activation/poll registries。
  - `tests/fins/test_fins_storage_provider.py:2094-2104` 声称 Fins 不得 reverse depend，但 `:2853-2868` 对当前 Fins wait adapter 特判，允许它 import Host。
  - `tests/service/test_import_boundary.py:10-32` 禁止 Service import `dayu.host.durable`，同时只对 approved Fins assembly imports 开白名单；因此简单把旧文件原样移动到 Service 仍不正确。
  - `docs/host/design.md:2436-2442` 要求 Host composition root 提供 typed adapter binding，wait record 只保存 typed refs，poller 只能通过 Host `resolve_wait` 管线提交结果。
- 语义 owner：Host 拥有 durable row 到 adapter-facing snapshot 的投影；Service 拥有 Fins observation 到 Host adapter result/registry 的 glue；Fins 只拥有 observation runtime、handle parser 和业务 result summary。
- 最小 contract：Host `wait_adapter` 增加 frozen `WaitAdapterSnapshot(tool_name, resume_token, created_at)`；Host 从 `WaitRecordRow` 校验/解析后投影给 `poll_wait()` / `abandon_wait()`。Service adapter 不读取 wait id、status、deadline、durable store 或 state mutator。

## Success Signals

- 所有 storage ticker/document/entry/filename/local object key 入口在构造路径前 fail closed；非法 `..`、绝对 key、正反斜杠、多组件 filename 与越界 local URI 都不能创建、读取或删除 workspace 外路径。
- `store_file(ProcessedHandle(...))` 在 processed meta 不存在时抛 `FileNotFoundError`，且 `LocalFileStore.put_object()` 未被调用、目标 key 未创建。
- batch commit 的唯一 commit point 是 durable `COMMITTED` journal；该点之前的异常/进程恢复回到 pre-batch target，该点之后 cleanup 失败不把已提交业务状态伪装成 commit failure。
- upload create/update/overwrite 与 generic/CN/HK download 的单 document mutation，在取消、业务异常、blob/final-meta/processed 标记异常、commit failure 后，正式 source/blob/processed 状态与操作前一致。
- CN/HK downloader/workflow 不创建 `dayu_cn_downloads` / `dayu_hk_downloads` `delete=False` temp PDF；success、cancel、exception、generator close 测试均无 temp artifact。
- `rg -n '(^|\s)(from|import) dayu\.host' dayu/fins --glob '*.py'` 无匹配；不再存在 Fins wait-adapter 特判。
- Service-built wait/activation/poll registries 的行为、tool-name binding、poll terminal mapping、cancel/abandon 与 Host poller 行为保持不变。
- 无 tool schema、prompt、LLM-facing upload/download security text或安全配置变化。

## Non-Goals / Scope Boundary

- 不实现 upload local-file allowlist、explicit user-file authority、symlink-safe upload source policy 或 capability token。
- 不实现远端 URL/TLS/redirect/SSRF/egress provenance policy。
- 不实现 remote download wire/decoded byte budget、streaming cap 或 response allocation policy。
- 不修改任何 LLM-facing upload/download security schema、tool description、prompt 或 result envelope。
- 不处理 R3-D 的 financial result、XBRL、fiscal period、processor freshness 或 read projection。
- 不处理 R3-E 的 Web/Documents egress、resource cap、diagnostic 或 oracle。
- 不处理 DR-024 Docling converter builder fallback；它不在用户列出的当前 R3-C scope 中，返回 umbrella controller 作为未来 Fins conversion-runtime WU 候选。
- 不把单 document atomicity扩大为“整个 ticker / 整次多文档 download run 全部回滚”。已经成功提交的前一份 document 不因后一份失败而撤回。
- 不新增 Fins durable job、distributed transaction、generic unit-of-work framework、repository compensation framework 或跨设备 filesystem copy fallback。
- 不改变 Host wait state machine、resolve semantics、Engine awaiting contract、tool outcome schema 或 observation handle durable 性质。
- 不保留 `dayu.fins.ingestion.wait_adapter` 兼容 re-export、wrapper 或 lazy import。

## Design Alignment

- `AGENTS.md:24-31` 要求业务事实有唯一 owner，修复必须落在 owner boundary；本计划把 identity/commit 放在 storage，把 document orchestration 放在各 ingestion owner，把 cross-domain wait glue 放在 Service。
- `AGENTS.md:54-66` 固定 `UI -> Service -> Host -> Engine`、禁止反向依赖，并要求财报存取只能经 `dayu.fins.storage`。
- `docs/host/design.md:23-59` 固定 Host/Fins 边界和内部 ownership；`docs/host/design.md:940-946` 要求 Service 只传 typed construction inputs，scheduler/wait wiring由 Host composition 接收；`docs/host/design.md:2318-2454` 保持 Host waiting/resolve 真源不变。
- `docs/engine/design.md:18-26` 明确 Engine 不拥有工具内部后台任务、财报语义或 Fins storage，本计划不修改 Engine。
- `dayu/README.md:68-81` 把 Service 定位为 composition boundary、Fins 定位为财报能力包；`dayu/README.md:210-220` 要求所有财报存取经过 Fins storage/runtime。
- `dayu/fins/README.md:99-107` 已声明 source acknowledgement、shared batch owner 和 document-id owner；本计划补齐 filename/ticker/object key 与 commit failure contract，而不是新建第二套真源。
- `dayu/fins/README.md:460-464` 已声明 source/blob 在 shared storage core 协作；`dayu/fins/README.md:494-512` 已声明 ingestion runtime 和 overwrite batch 责任；本计划把现有意图落实到 create/update/commit-failure 路径。
- `docs/host/issues-implementation-control.md:93-103` 要求 plan 基于设计、控制与直接代码证据；`:127-151` 要求按语义闭环、回滚风险和验证矩阵切片。
- `docs/phaseflow-umbrella-optimization-control.md:42-60` 将生产行为、事务、取消和 public contract 归为 High Risk；`:95-120` 禁止按 finding/file 机械切片；`:198-205` 要求 `production-high` 由 plan 明确 owner-specific validation。

## Contract And State-Machine Decisions

所有后续实现必须继续遵守项目编码边界：新增/修改函数提供完整中文 docstring（参数、返回值、异常）；新 contract 不使用 `Any`、`object`、裸容器或无类型签名；复杂 rollback/commit ordering 用中文行内注释解释意图；优先模块级私有 helper；不得使用 `hasattr/getattr`、lazy import、兼容 wrapper/re-export、无结构 payload 或 caller-side fallback 绕过 owner contract。

### Storage identity contract

1. `_fs_storage_utils` 提供一个 single-component source of truth；ticker、document id、entry name/filename 都复用它并保留各自 field-specific error message。
2. 合法 component 必须：trim 后非空；不等于 `.` / `..`；不包含 `/` 或 `\`；不把 absolute path、drive/UNC 表达或多个组件归一成单组件。
3. `_normalize_ticker()` 可继续先调用 `try_normalize_ticker()`，但 canonical/fallback 两条分支最终都必须经过相同 single-component validator；不得通过删除分隔符或取 basename“修复”非法输入。
4. local object key 是多组件 contract：拒绝空 key、leading slash、backslash、空 segment、`.` / `..` segment；每个 segment 使用同一 component validator。`_resolve_key()` 与 `_build_uri()` 复用同一个 normalized key，不得各自解释。
5. `local://` URI 只接受上述 canonical object key，解析后必须仍位于 `portfolio_root`；失败抛 `ValueError`，不做 basename fallback。
6. `_FsBlobMixin.store_file()` 先规范化 filename，再对两类 handle 无条件调用 `_get_handle_meta()`，最后构造 key。不存在 handle 时不得创建目录、temp file 或 object。

### Batch commit state machine

```text
STARTED
  -> secure pre-swap state
  -> BACKED_UP_TARGET       # 无旧 target 时也写该 phase，表示“原状态=不存在”已确认
  -> atomic rename staging -> target
  -> SWAPPED_TARGET         # 尚未对 caller committed
  -> COMMITTED              # 唯一 commit point
  -> best-effort backup/journal-container cleanup
```

- directory swap 使用同 filesystem 的 atomic rename/replace primitive；不得用可能退化为 copy+delete 的 `shutil.move()` 作为 commit primitive。
- 每次关键 rename 后刷新受影响 parent directory。所有 phase journal（包括唯一 commit point `COMMITTED`）必须复用 `_write_json()` 的 same-directory unique temp -> file flush/fsync -> atomic replace -> journal parent-directory fsync 完整模式；不得把 `COMMITTED` 降级为只写文件内容而不刷新目录项。（`R3-C-PF-10`）
- `COMMITTED` 之前异常：删除本次新 target（如已 swap），恢复 backup（如原 target 存在），刷新目录，然后抛原始 commit error。原 target 本来不存在时恢复为不存在。
- `COMMITTED` 之后：新 target 已提交。backup/staging cleanup failure 只记录有界 diagnostic 并保留给 orphan recovery，不让 `commit_batch()` 抛出“未提交”异常。
- `commit_batch()` 在 success 或已完成 pre-commit rollback 后消费 token；caller 只对“业务操作阶段异常”调用 `rollback_batch()`，不得在 `commit_batch()` 抛错后对已消费 token 二次 rollback。
- recovery 语义与同步 commit 同源：`STARTED/BACKED_UP_TARGET/SWAPPED_TARGET` 恢复 pre-batch 状态；只有 `COMMITTED` 保留 target并清理 backup。特别地，`SWAPPED_TARGET` 且尚无 `COMMITTED` 时必须先删除本次 new target，再把 backup恢复为 target；这与 `dayu/fins/storage/_fs_storage_infra.py:725-728` 当前“保留 new target、删除 backup”的行为相反，是 S1 必须落地并测试的行为变更，而非注释整理。（`R3-C-PF-04`）
- 若原 commit error 后的物理 rollback 再抛 filesystem error，传播形状固定为：原 commit exception仍是 caller捕获到的 primary exception；对它调用 `add_note()` 标明“rollback失败且recovery evidence已保留”，并以 `raise commit_error from rollback_error` 传播，使 rollback exception可从 primary的 `__cause__` 检查。不得只 log rollback error、不得让 rollback error替换 primary；journal、backup及任何无法安全判定的 staging/target证据均不得清理。测试必须按对象身份断言 primary与`__cause__`，并断言 recovery evidence仍存在。（`R3-C-PF-05`）

### LocalFileStore put contract

- 同目录 UUID temp file，避免同 key 并发/遗留 `.part` 冲突。
- 写入循环完成后 `flush()` + `os.fsync(file_fd)`，再 atomic replace，最后调用既有目录 fsync helper。
- 任一写入/fsync/replace异常清理尚存在的 temp file并透传原异常；旧 target 在 replace 前不变，replace 成功后只存在完整新对象。
- metadata digest/size来自实际写入 bytes；不使用 caller metadata重算 commit事实。

### Single-document mutation contract

```text
prepare/validate/download/convert outside batch
  -> cancellation checkpoint
  -> begin one ticker storage batch
  -> reset target document if replacement is required
  -> stage/ack source inside batch
  -> write all blobs inside same batch
  -> write final ingest_complete source meta inside same batch
  -> update processed reprocess marker inside same batch when applicable
  -> cancellation checkpoint before commit
  -> commit_batch (storage owner decides commit/rollback)
  -> emit document terminal success
```

- upload create/update/overwrite 全部开启一个 document batch；delete 保持现有单一 source mutation auto-batch，不扩大范围。
- `DoclingUploadService` 的 conversion/file validation 在 batch 外完成；所有 non-delete create/update/overwrite 路径先开启显式 caller-owned batch，再调用 `_acknowledge_source_before_blob_write()`。该 helper 在 create/未完成 update 时调用 `stage_source_document()`；shared storage core 必须复用当前 active batch并只写其 staging tree，不得触发 auto-batch commit。旧 completed update可返回 handle，但后续 blob/final meta仍写同一 active batch。helper本身不得 begin/commit/rollback，也不接管 token。（`R3-C-PF-10`；当前复用依据：`dayu/fins/storage/_fs_storage_infra.py:334-374`）
- generic `FinsIngestionRuntime._store_downloaded_document()` 与所有 S2 caller遵守同一 token lifecycle：token在 operation阶段由 caller持有；operation exception/cancellation才由 caller rollback。caller准备调用 `commit_batch()` 时即把生命周期所有权交给 storage；从调用开始，无论 success或failure，storage都负责消费 token与同步rollback/recovery，caller只原样传播 storage exception，绝不再调用 `rollback_batch()`。（`R3-C-PF-02`）
- 每个 caller采用显式 active-batch `try/finally` 结构：在进入同步 mutation段前保存 active token与 `commit_started=False`；operation抛出 `Exception`或`BaseException`子类 cancellation时记录 primary error；`finally`仅在 `commit_started=False` 且token仍由caller拥有时执行一次rollback，并按“primary保留、rollback为`__cause__`”传播双重错误；紧邻调用 `commit_batch()` 前把 `commit_started=True`，此后finally不得rollback。active token存在期间禁止任何 `yield`/`await`；取消测试通过同步 cancellation checker/注入点在mutation段内抛 `asyncio.CancelledError`，而不是靠增加batch内await制造窗口。（`R3-C-PF-03`）
- CN/HK workflow 在 batch 外完成 remote PDF acquisition与 Docling conversion；只有最终 source/blob/processed mutation进入 batch。`commit_cn_filing_source_document()` 的 contract固定为“只在 caller-owned active document batch内 stage final source meta与processed reprocess marker”；它不得开启、提交或回滚第二个batch。fast-skip与normal-convert两个 call site都必须处在同一 caller batch，验证必须证明 reset -> source acknowledgement -> PDF/Docling blob -> final meta -> processed marker全过程使用同一个active token。（`R3-C-PF-01`；直接证据：`dayu/fins/pipelines/cn_download_filing_workflow.py:303-319,519-535`，`dayu/fins/pipelines/cn_download_source_upsert.py:191-268`）
- 不得为了重试继续暴露 incomplete staging source 作为正式 repository state。filing terminal `FILING_COMPLETED` 只在 commit成功后发出；FILE_DOWNLOAD/CONVERSION progress可以在batch外继续表达 acquisition/convert进度。
- FILE_DOWNLOAD/CONVERSION progress 可以继续表达 acquisition/convert进度，但不得宣称 repository commit已经成功。

### CN/HK downloaded asset contract

- `DownloadedReportAsset` 的唯一类型 owner 是 `dayu/fins/pipelines/cn_download_models.py:233-249`；在该 dataclass把 `pdf_path: Path` 改为 `pdf_bytes: bytes`。`sha256`、`content_length`、`downloaded_at` 继续由 downloader owner产生并校验。（`R3-C-PF-06`）
- CNInfo/HKEX downloader不再 import/use `tempfile`，不创建 `dayu_cn_downloads` / `dayu_hk_downloads` 文件。
- workflow直接消费 `asset.pdf_bytes`；删除 `_unlink_temp_pdf()` 和所有 path read/unlink分支。
- 实施前后都必须对整个 `dayu/fins` 与 `tests` 扫描：类型定义/import与注解、全部 `DownloadedReportAsset(...)` constructor、`.pdf_path` attribute access、`pdf_path=` keyword、fixture/fake以及位置解包。当前直接constructor证据位于两个downloader及 `tests/fins/test_cn_download_runtime.py`、`test_cn_pipeline.py`、`test_cn_download_workflow.py`；任何额外命中必须先加入S2明确文件边界并更新对应owner测试，不得用兼容property/re-export或动态访问过渡。
- 这不是 remote byte-budget实现：不改变 `response.content` 读取方式、不增加大小上限、不改变 retry/redirect/TLS/URL行为。

### Wait adapter ownership contract

```text
Host WaitRecordRow (Host durable owner)
  -> Host WaitAdapterSnapshot(tool_name, resume_token, created_at)
  -> dayu.service.fins_wait_adapter
  -> FinsObservationRuntime poll/cancel/abandon
  -> Host WaitPollResult / activation registry
  -> existing Host resolve_wait pipeline
```

- `WaitAdapterSnapshot` 在 Host `wait_adapter` module定义为 frozen/slots dataclass，字段严格为 `tool_name: str`、`resume_token: str`、`created_at: datetime`。Host projection使用现有 `dayu.host.durable.codec.parse_utc_timestamp()` 把 `WaitRecordRow.created_at: str` 转成 timezone-aware UTC `datetime`；Service不解析、补时区或回退到 `now`。（`R3-C-PF-08`；直接证据：`dayu/host/durable/state.py:481-511`，`dayu/host/durable/codec.py:57-68`）
- Host `wait_adapter` 新增 typed `WaitAdapterSnapshotProjectionError(ValueError)` 作为具体fail-closed路径。projection先按Host-owned opaque-reference基础contract校验 `resume_token.strip()` 非空且原字符串长度不超过 `HOST_WAIT_RESUME_TOKEN_MAX_LENGTH`；trim只用于判空，不改写durable值，Host也不解析Fins私有handle语义。随后解析timestamp；非法durable token或timestamp统一由该Host error以原始校验/parse error为`__cause__`抛出。poll/abandon在调用Service adapter前捕获它，adapter不得被调用，并分别进入现有 `ADAPTER_ERROR` / `ABANDON_ERROR` release-with-backoff路径；不得把错误交给Service转成lost/pending或默认值。（`R3-C-PF-08`；现有contract依据：`dayu/contracts/tool_await.py:40-67`、`dayu/host/durable/schema.py:819-821`、`dayu/host/durable/state.py:6276-6281`）
- `WaitPollAdapter.poll_wait()` / `abandon_wait()` 改收 snapshot；Host poller内部仍持有完整 `WaitRecordRow` 做 claim/backoff/resolve，adapter看不到 durable governance字段。
- 原 `dayu/fins/ingestion/wait_adapter.py` 内容迁到 `dayu/service/fins_wait_adapter.py` 并改用 snapshot；Fins tool names/observation runtime仍从Fins public submodules导入。
- 删除旧 Fins module，不做 re-export、wrapper、facade、lazy import或旧测试兼容。
- `WaitActivationRequest`、Host wait state machine、registry shape、adapter key、tool names、poll result mapping与LLM-facing result文本不变。

## Implementation Slices

### S1 — Storage Identity, Commit Point, And Local Durability

#### Objective

在唯一 storage owner内建立 identity、handle existence、batch commit/recovery和LocalFileStore落盘契约，为后续 ingestion slice提供可信事务底座。

#### Allowed production files

- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/local_file_store.py`
- `dayu/fins/storage/repository_protocols.py`（只补齐 batch token/commit/rollback docstring contract，不改协议方法集合）

#### Allowed test files

- 新增 `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`（S1只补/调整 identity owner与现有shared-core行为断言；不得新增或保留由S1引入的TODO、compatibility branch或临时import特判。S3按mandatory sequencing在同一文件删除既有Fins->Host例外。）

#### Exact allowed changes

1. 抽取/复用 component与object-key validator；所有 path/key helper在拼接前调用。
2. `store_file()` 对 Source/Processed handle统一 existence check，filename规范化只做一次。
3. 重写 `commit_batch()` commit point与pre-commit rollback；同步重写 orphan recovery phase解释。
4. directory rename使用atomic primitive并按上文刷新parent；每个journal phase（包括`COMMITTED`）复用既有atomic JSON + file fsync + directory sync；不改变workspace layout或BatchToken public字段。（`R3-C-PF-10`）
5. `LocalFileStore.put_object()`使用unique temp、fsync/replace/dir-sync/exception cleanup。
6. 不修改source/processed/blob repository public方法集合，不新增transaction facade。

#### Per-phase failure injection strategy

- 优先使用storage owner内按语义命名的私有rename/journal helper作为受控seam；若不为生产逻辑增加helper，则monkeypatch既有 `_write_batch_journal(token, phase)` 与选定atomic rename helper，并按明确的`phase`值、source path与target path触发。禁止依赖“第N次调用”才抛错的call-count mock。（`R3-C-PF-07`）
- 同步commit测试分别注入：旧target -> backup rename失败、`BACKED_UP_TARGET` journal失败、staging -> target rename失败、`SWAPPED_TARGET` journal失败、`COMMITTED` journal失败，以及commit error后的backup restore失败。每例都断言target/backup/staging/journal的实际目录内容、token关闭状态和传播异常，不只断言mock调用。
- crash recovery测试不模拟进程控制流：用真实临时目录和owner journal writer构造每个phase对应的物理状态，再调用`recover_orphan_batches()`。必须包含“swap已完成但`COMMITTED`尚未写”的`SWAPPED_TARGET` case，断言new target删除、old backup恢复；若pre-state不存在则new target删除且target保持不存在。（`R3-C-PF-04`）
- directory fsync/atomic JSON行为用helper spy按path/phase断言；底层rename仍在真实临时filesystem执行。不得用platform-specific chmod/ENOSPC技巧作为唯一覆盖，也不得mock掉最终filesystem state。

#### Required assertions

- 参数化非法 component矩阵：`""`、空白、`.`、`..`、`a/b`、`a\\b`；覆盖ticker/document id/entry/filename。
- absolute/leading-slash、`..` segment、backslash、empty segment object key和越界 `local://` URI全部fail closed，workspace外无文件变化。
- SourceHandle/ProcessedHandle不存在时store均失败；spy FileStore调用次数为0。
- valid dot/hyphen ticker与普通文件名继续round-trip，避免把single-component误写成过窄字符allowlist。
- 按上述owner-level seam注入每个pre-commit phase失败：旧target存在时内容完全恢复；旧target不存在时target保持不存在；token关闭且无业务可见staging。（`R3-C-PF-07`）
- orphan recovery对STARTED/BACKED_UP/SWAPPED回滚，对COMMITTED保留target并清backup；crash-between-swap-and-`COMMITTED`用真实目录状态证明`SWAPPED_TARGET`执行语义反转。（`R3-C-PF-04`）
- commit与rollback同时失败时，断言caller捕获对象是注入的原commit exception、其`__cause__`是注入的rollback exception、note明确evidence retained，且journal/backup仍可供下一次recovery检查。（`R3-C-PF-05`）
- commit point后的cleanup失败不改变成功返回；orphan recovery随后可清理。
- object write失败清temp且旧object不变；fsync发生在replace前，directory sync发生在replace后。所有journal（尤其`COMMITTED`）也断言atomic JSON replace后的parent-directory sync。（`R3-C-PF-10`）

#### Validation

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

#### Completion signal

S1测试证明storage owner自身可以对caller承诺“commit success=新target可见；exception=旧target/absence可见”，后续slice不需要compensating delete。

#### Stop conditions

- 若atomic directory rename不能在当前workspace layout内成立，停止并回到storage design讨论；不得退回`shutil.move` copy+delete。
- 若commit failure后无法由storage owner确定恢复旧target还是保持新target，S1 blocked，不允许S2用caller fallback补偿。
- 若需要改变repository protocol方法集合或BatchToken durable schema，停止并先确认contract owner。

### S2 — Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets

#### Objective

让upload、generic download与CN/HK persisted download复用S1事务真源，并消除CN/HK temp PDF handoff seam。

#### Prerequisite

- S1已通过per-slice review且storage commit/recovery contract已accepted。

#### Allowed production files

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`（仅当需要使helper docstring明确“caller batch内执行”；不得新增第二个commit owner）
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`

#### Allowed test files

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_hkexnews_downloader.py`

#### Exact allowed changes

1. upload non-delete mutation无条件使用一个caller-owned document batch；转换/校验在batch外，`_acknowledge_source_before_blob_write()`、blob与final meta在batch内。helper的`stage_source_document()`必须检测并复用shared core当前active batch，只stage、不auto-commit；create/update/overwrite都不得产生第二个batch。（`R3-C-PF-10`）
2. 删除/重写当前“final upsert失败保留acknowledged staging”测试，断言create失败后source/blob均不存在；overwrite/update失败断言旧meta/blob完全不变。
3. upload、generic download与CN/HK caller都按operation-error/commit-error分开管理token：operation exception/cancellation的`finally` rollback active token；调用`commit_batch()`前切换为storage-owned生命周期，此后不清空token绕状态，也绝不在commit failure后caller rollback。（`R3-C-PF-02`、`R3-C-PF-03`）
4. 在type owner `dayu/fins/pipelines/cn_download_models.py`把CN/HK asset改为bytes；完成全仓`.pdf_path`、constructor、fixture与type-annotation扫描后删除tempfile/path/unlink实现和手工cleanup测试，不提供兼容property。（`R3-C-PF-06`）
5. CN/HK workflow把network/convert/reuse准备放batch外，把reset/ack/blob/final source/processed marker收束到一个无yield/await的batch commit段；`commit_cn_filing_source_document()`在fast-skip与normal-convert路径都只能stage到该caller batch，且不得成为第二个commit owner。（`R3-C-PF-01`）
6. active-batch段使用上文`try/finally`模式；取消/exception/generator close在commit前不得留下source/blob/processed变更，commit后terminal event保持现有summary contract。（`R3-C-PF-03`）
7. 不修改HTTP request、URL、redirect、TLS、response byte读取或tool schema。

#### Required state/rollback matrix

| Path | Pre-state | Failure/cancel point | Expected observable state |
| --- | --- | --- | --- |
| upload create | document absent | blob write / final upsert / commit | source absent，blob absent，processed不变 |
| upload update/overwrite | old completed document | after reset / blob / final upsert / commit | old source meta与old blobs不变 |
| generic download create | document absent | source/blob/processed/commit | document absent，processed不变 |
| generic download overwrite | old completed document | source/blob/processed/commit | old source/blob/processed flag不变；非目标document不变 |
| CN/HK new filing | absent | after download / after convert / storage mutation / commit | absent；无temp PDF |
| CN/HK replacement | old completed filing | after reset/blob/processed/commit | oldsource/blob/processed flag不变 |
| CN/HK generator close | beforecommit progress yield | `aclose()` / task cancel | 无active batch、无partial document、无temp PDF |
| success | any | commit返回success | final source、全部blobs、processed marker同时可见，随后才有filing terminal success |

#### Required assertions

- fake/spy shared repository记录active token identity，证明reset -> acknowledgement -> PDF/Docling blob -> final meta -> processed marker（含`commit_cn_filing_source_document()`两个call site）全部发生在同一个caller-owned active batch，且只有caller末尾调用一次commit。（`R3-C-PF-01`）
- operation exception与同步抛出的`asyncio.CancelledError`都在active-batch `finally`触发一次rollback；rollback自身失败不覆盖原业务异常，通过primary exception的note/`__cause__`保留两者；mutation段内无yield/await。（`R3-C-PF-03`）
- commit success/failure测试证明从`commit_batch()`调用开始token归storage owner；commit failure不会触发invalid-token二次rollback、不会返回uploaded/downloaded成功，并原样传播storage primary exception。（`R3-C-PF-02`）
- cancel after conversion从“保留staging”迁移为“旧状态/absence不变”。
- `_acknowledge_source_before_blob_write()`在create、update与overwrite显式batch内只stage到同一token；spy证明它没有触发nested begin/commit，ack失败走operation rollback。（`R3-C-PF-10`）
- CNInfo/HKEX asset的`pdf_bytes`、sha256、length一致；类型owner、constructors、fixtures、type annotations和所有consumer不再引用当前contract的`pdf_path`或`tempfile`。（`R3-C-PF-06`）
- success、download exception、conversion exception、cancel、inner/outergenerator close均不产生temp PDF。
- 既有fast skip、reuse、downloaded/skipped/failed计数与progress顺序在不虚构commit的前提下保持；任何必要顺序调整由测试明确写出。

#### Validation

```bash
source .venv/bin/activate
pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg -n "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path" dayu/fins/downloaders dayu/fins/pipelines tests/fins
rg -n '\bDownloadedReportAsset\b|\.pdf_path\b|pdf_path[[:space:]]*[:=]' dayu/fins tests --glob '*.py'
rg -n 'DownloadedReportAsset[[:space:]]*\(' dayu/fins tests --glob '*.py'
```

三个scan共同覆盖type owner、imports/type annotations、constructor、attribute/keyword与fixture。预期：`DownloadedReportAsset`仍在type owner及合法constructors命中，但所有constructor只传`pdf_bytes`；生产下载/管线与相关测试中无当前temp-PDF contract的`.pdf_path`/`pdf_path=`/tempfile命中。若其它不相关局部变量命中，implementation artifact必须逐条分类，不能机械删除。（`R3-C-PF-06`）

#### Completion signal

per-document failure matrix全部通过，且代码中不存在caller-side partial-state cleanup或temp PDF handoff。

#### Stop conditions

- 若production repositories并非同一个shared `_FsRepositorySet`，停止并澄清transaction owner；不得通过跨repo逐项delete伪造atomicity。
- 若实现需要在batch持有期间执行network/Docling `await`或跨yield保存token，停止并重新切storage commit段。
- 若修复要求引入URL/security/byte-budget policy或LLM schema变化，停止并记录到deferred tool-security WU。

### S3 — Host Adapter Snapshot And Service-Owned Fins Wait Glue

#### Objective

删除Fins -> Host imports，同时保持现有two-phase activation、poll、cancel/abandon与resolve行为。

#### Prerequisite

- 实施顺序强制为 `S1 -> S2 -> S3`：只有S1 production/tests已land且per-slice review accepted后才能开始S2；只有S2 production/tests已land且per-slice review accepted后才能开始S3。不得并行实施或以“无production依赖”为由提前S3。（`R3-C-PF-09`）
- S1/S2不得为S3新增TODO、temporary import allowlist、compatibility branch/re-export或永久过渡行为；S3在既有文件最终删除Fins->Host特判。

#### Allowed production files

- `dayu/host/wait_adapter.py`
- 删除 `dayu/fins/ingestion/wait_adapter.py`
- 新增 `dayu/service/fins_wait_adapter.py`
- `dayu/service/host_assembly.py`

不得修改Host durable schema、`dayu/host/durable/state.py`、Engine、Fins observation runtime或tool schema。

#### Allowed test files

- 新增 `tests/service/test_fins_wait_adapter.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_import_boundary.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_wait_observation_runner.py`
- `tests/host/test_open_host_runtime.py`

#### Allowed documentation files

以下文档只在S1、S2、S3全部production变更与对应测试均已land后做current-fact同步；即使S3 production较早通过focused tests，也必须等全部三个production slice完成后才能写README/docs。该同步并入S3/final validation closure，不另拆第4个slice：（`R3-C-PF-09`）

- `dayu/README.md`
- `dayu/fins/README.md`
- `dayu/service/README.md`
- `dayu/host/README.md`
- `tests/README.md`

除此之外不得修改根 `README.md`、design docs、control docs 或 review artifacts。

#### Exact allowed changes

1. Host定义minimal `WaitAdapterSnapshot`并在poll/abandon调用前从`WaitRecordRow`投影；adapter Protocol改收snapshot。
2. Host内部仍使用完整row做claim、deadline、backoff、resolve和diagnostic；不把snapshot反向作为durable truth。
3. 将Fins/Host cross-domain adapter classes、mapping helpers、registry builders和stable adapter key移动到Service module；`host_assembly`改从同层module导入。
4. adapter tests从`tests/fins`迁到`tests/service`；Fins tests只保留observation/tool业务contract，Host tests只保留poller/snapshot投影contract。
5. 删除Fins import-boundary exception，统一禁止Fins importHost/Service/UI/Engine。
6. 不保留旧module import path兼容层，不改变registry/tool name/adapter key/result text。
7. snapshot projection使用Host `parse_utc_timestamp()`生成timezone-aware `datetime`，并以Host-owned `WaitAdapterSnapshotProjectionError`拒绝空/超长resume token及非法timestamp；poll/abandon在adapter调用前映射到既有error/backoff路径。（`R3-C-PF-08`）

#### Required assertions

- Host adapter fake只收到三个允许字段；没有wait id、status、deadline、row mutator或durable module类型。
- Host用自己的timestamp parser投影timezone-aware `created_at: datetime`；空/超长resume token与非法durable timestamp都抛`WaitAdapterSnapshotProjectionError`并保留原校验异常为`__cause__`。fake adapter调用次数为0，poll/abandon分别留下Host-owned error/backoff diagnostic；Service没有parser/default-now/token容错分支。（`R3-C-PF-08`）
- Fins success/failure/cancelled/pending/lost/transient observation到Hostpoll outcome映射与旧行为等价。
- activation使用tool callable同一个`FinsIngestionRuntime`；accepted前不activate、重试不double-submit的现有覆盖继续通过。
- `tests/service/test_import_boundary.py`继续禁止`dayu.host.durable`，只对明确的Fins observation/direct-event/tool-name imports放行。
- 全量Fins AST import scan无特例、无Host命中；旧文件不存在。

#### Validation

```bash
source .venv/bin/activate
pytest tests/service/test_fins_wait_adapter.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_observation_runner.py tests/host/test_open_host_runtime.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
test ! -e dayu/fins/ingestion/wait_adapter.py
```

两个boundary命令预期均成功：`rg`无输出/exit 1需要在artifact中按“零匹配为pass”记录，`test` exit 0。

#### Completion signal

Fins import scan无Host例外，Service adapter不importHost durable internals，existing wait/poll/activation behavior矩阵通过。

#### Stop conditions

- 若Service adapter仍需要完整`WaitRecordRow`、durable store或state mutator才能工作，停止并回到Host adapter snapshot contract；不得给Service import-boundary再加特例。
- 若需要Host importFins来构造adapter，停止；composition owner选择错误。
- 若迁移会改变Host wait state machine、Engine awaiting contract或LLM-facingtool result，停止并拆出独立design/public-contract WU。

## Slice Count Justification

计划使用3个slice：

1. `S1 Storage Identity, Commit Point, And Local Durability`
2. `S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
3. `S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue`

没有按raw finding拆4个以上slice。CN/HK temp lifecycle与download mutation共享同一个downloaded-asset contract、async cancellation/generator-close matrix和单filing workflow；单独拆分会让中间slice保留temp handoff或再次改同一workflow。Storage必须先独立accepted，因为S2的rollback/commit语义依赖它；S2 accepted后才允许S3，避免共享测试边界和最终文档同步产生中间态。Wait glue有不同owner、不同验证矩阵和独立architecture blast radius，因此保留为S3。该切法符合production-high per-slice review要求且不超过3个slice，无需额外超限例外。（`R3-C-PF-09`）

## Review And Validation Route

- 每个slice修改production behavior/public adapter seam，必须执行per-slice code review；不得并入仅aggregate review。
- 实施与review的依赖链是强制 `S1 production+tests -> S1 review accepted -> S2 production+tests -> S2 review accepted -> S3 production+tests -> S3 review accepted -> README/docs sync -> final validation`；不得并行、跳序或提前同步文档。（`R3-C-PF-09`）
- 每个accepted finding修复后按High Risk执行双路re-review。
- 三个slice全部accepted后执行aggregate deepreview，重点做：
  - adversarial commit/crash phase review；
  - source/blob/processed propagation audit；
  - cancel/exception/generator-close failure pass；
  - storage identity/path traversal scan；
  - Fins/Service/Host import-boundary review；
  - tool-security scope exclusion audit。

### Final production-high validation

```bash
source .venv/bin/activate
pytest tests/fins tests/service tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_observation_runner.py tests/host/test_open_host_runtime.py -q
pytest -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
rg -n "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path" dayu/fins tests --glob '*.py'
rg -n '\bDownloadedReportAsset\b|\.pdf_path\b|pdf_path[[:space:]]*[:=]' dayu/fins tests --glob '*.py'
rg -n 'DownloadedReportAsset[[:space:]]*\(' dayu/fins tests --glob '*.py'
git diff -- dayu/config/prompts dayu/fins/tools dayu/config/tool_discovery.json
```

- Fins->Host scan预期零匹配。
- temp contract scan预期相关生产/测试零匹配；非R3-C同名命中必须逐条分类。
- 最后一个diff预期为空，证明没有LLM-facing/schema/provider security修改。
- modified production files的focused test覆盖率目标均为`>=80%`；implementation artifact应附`pytest --cov ... --cov-report=term-missing`结果并逐文件核对，不能用aggregate平均值掩盖低覆盖owner文件。
- 若默认pytest/pyright出现疑似pre-existing failure，按`docs/phaseflow-umbrella-optimization-control.md:206-221`复跑最小命令并引用baseline commit/artifact；不得跳过或用兼容分支压绿。

## README / Documentation Decisions

后续严格完成S1 -> S2 -> S3全部production与test变更并通过各slice review后，才执行以下文档同步；本plan gate不修改它们，S1/S2也不得提前修改或留下要求S3兼容的TODO/临时行为。（`R3-C-PF-09`）

- `dayu/fins/README.md`: 必须更新。删除Fins wait-adapter Host import例外；记录storage single-component/object-key、per-document atomic mutation、temp-less CN/HK downloaded asset与Service-owned adapter assembly的当前实现事实。
- `dayu/service/README.md`: 必须更新。把`dayu.service.fins_wait_adapter`记录为Fins observation到Host typed adapter registry的approved composition seam，说明不读取Fins storage或Host durable internals。
- `dayu/host/README.md`: 必须更新。记录Host poller向external adapter只投影minimal `WaitAdapterSnapshot`，durable row/claim/backoff仍为Host内部真源。
- `dayu/README.md`: 必须更新。跨包边界发生真实变化：Fins不再有Host import例外，Service拥有wait glue；只写稳定关系，不写WU过程。
- `tests/README.md`: 必须更新。把Fins wait adapter registry/mapping测试从`tests/fins`迁到`tests/service`，补充storage commit/ingestion atomicity/temp-less cancellation矩阵。
- 根`README.md`: 不更新。没有安装、CLI参数、用户workflow、输出通道、日志路径或workspace位置变化。
- `docs/host/design.md`: 不更新。现有设计已要求Service composition提供typed adapter binding、Host拥有wait record/resolve truth；本次是实现纠偏，不引入新架构决策。
- `docs/engine/design.md`: 不更新。Engine contract无变化。
- `docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`: implementation agent不得修改；后续controller按gate职责记录artifact/status。

## Tool-Security Deferred Items

以下finding真实存在，但按用户scope correction明确排除；不得在R3-C实现slice、测试期待、README承诺或LLM-facing文本中落地：

1. Upload user-file allowlist / explicit file authority / symlink-safe upload source policy。
   - 邻接证据：`dayu/fins/pipelines/docling_upload_service.py:581-590`读取调用方文件；`dayu/fins/pipelines/docling_upload_service.py:794-804`只校验存在、普通文件与suffix。
   - Deferred owner/destination：未来独立tool-security WU，在Host/policy与tool source authority设计确认后plan。
2. URL/TLS/redirect/SSRF provenance policy。
   - 邻接证据：CN/HK downloader当前URL/redirect行为由Round3裁决记录；本plan不修改HTTP policy。
   - Deferred owner/destination：未来独立Fins remote-egress/tool-security WU。
3. Remote download byte-budget policy。
   - 本plan把已有`response.content`直接交给typed asset，只移除重复temp I/O；不得增加或声称wire/decoded budget。
   - Deferred owner/destination：未来独立resource-budget/tool-security WU，与URL/provenance一起设计。
4. LLM-facing upload/download security schema changes。
   - 不修改tool name/description/parameter schema/error security wording或prompt。
   - Deferred owner/destination：只有上述authority/egress contracts先成为生产真源后，才由对应tool schema owner投影。

上述4项在R3-C状态均为`assigned to later work unit`，不是当前slice residual，也不得以“顺手加校验”的形式进入实现。

## Residual Risks And Uncovered Areas

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| OS/hardware在rollback rename本身失败时可能暂时留下需recovery的物理目录 | covered by current S1 recovery contract；若恢复证据也不可读则requiring explicit user decision | `dayu.fins.storage` orphan recovery；artifact必须报告双重错误，不能声称rollback成功 |
| Directory fsync在不支持的platform上只能best-effort | assigned to later work unit if cross-platform crash-durability requirement提高 | Fins filesystem backend portability WU；当前复用既有best-effort dir sync policy |
| 已成功提交的前一document不会因后续document失败回滚 | accepted non-goal, not a defect | multi-document transaction只有新业务需求时另开WU |
| CN/HK Docling同步第三方转换在线程内不能强制中断 | tracked by existing deferred finding noted in control history | future process/subprocess isolation WU；本plan只保证转换前后取消与无temp泄漏 |
| Tool-security四项 | assigned to later work unit | 见`Tool-Security Deferred Items` |
| DR-024 Docling converter builder fallback | assigned to later work unit | umbrella controller决定未来Fins conversion-runtime WU |
| R3-D financial/read semantics | covered by later approved sub-WU | `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D` |

所有当前R3-C residual均已分类；没有未分类residual。

## Global Stop Conditions

任一条件成立时，当前slice/implementation必须标记`blocked`并停止，不得发明workaround：

- single-component/object-key/storage URI的正确owner被证明不在`dayu.fins.storage`。
- source/blob/processed production path无法共享同一个storage batch owner，且需要新的public transaction contract。
- commit method无法同时满足“异常=pre-state”和crash recovery同源，或需要让caller通过loose cleanup补偿。
- CN/HK resource lifetime修复必须引入URL/TLS/redirect/SSRF/byte-budget策略才能继续。
- Service wait glue必须读取Host durable内部row/state mutator，或Host必须importFins。
- 任何实现需要修改LLM-facing schema/prompt/security说明、Engine awaiting contract或Hostwait state machine。
- 受影响测试揭示schema/public contract ownership与本plan不一致；先回到plan/design gate，不通过compatibility shim继续。

## No-Overdesign Rationale

- identity复用已有private storage validator，不增加业务ID类型层级或全局路径框架。
- atomicity复用现有ticker batch/shared core，不新增unit-of-work、distributed transaction或compensation ledger。
- atomicity unit限制为单document，避免长事务覆盖整个download run。
- CN/HK直接复用已经在内存中的PDF bytes，删除temp seam而不是设计resource manager平台。
- wait relocation只增加三个字段的Host snapshot和一个Service integration module，不改变Host/Engine状态机或公开await模型。
- 三个slice按真实owner/rollback/validation boundary合并，没有按finding数量拆分。

## Completion Report Format

plan gate完成时只报告：

- `status: pass / blocked`
- `artifact path: docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- `proposed slice count and names:`
  - `S1 Storage Identity, Commit Point, And Local Durability`
  - `S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
  - `S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue`
- `blocking questions: none`（若任一stop condition命中，列出具体owner问题并改为`blocked`）

## Plan Gate Decision

- status: `pass`
- blocking questions: none
- next gate: MiMo/DS plan re-review
- 本artifact不授权implementation、commit、control-doc更新或PR动作。
