# WU-CLI-DOWNLOAD-01 Slice 4 Plan Amendment

## 1. 文档状态

- Work unit：`WU-CLI-DOWNLOAD-01`
- Gate：`plan fix`
- Slice：Slice 4 — Storage concurrency 与 integrity repair（DL-F08、DL-F10）
- Base plan：`docs/gateflow/wu-cli-download-01-plan-20260809.md`
- Stop-condition evidence：`docs/gateflow/wu-cli-download-01-slice4-amendment-evidence-20260810-060259.md`
- 第一轮 review：AgentMiMo 与 AgentDS 均 `FAIL`；总控已裁决全部 finding 成立。
- 当前 HEAD：`399a686f8113fb39c014b98938cfaf0d0d525b3e`
- Artifact path：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`
- Decision：本文件只修订 Slice 4 的 SEC transport/materialization owner boundary、allowlist 与相关验证规格；base plan §5.6、Slice 4、§9 的其它目标、状态机、不变量、forbidden boundary 与 Oracle pause 全部继续有效。
- Completion：本轮 plan fix 已收敛为单一路径；尚未通过原 AgentMiMo/AgentDS 双路 re-review，不授权恢复 implementation。

## 2. 动机、直接证据与 owner 裁决

DL-F08 要求合法同 ticker writer 阻塞等待并最终成功；DL-F10 要求 source repair 在 Phase A 取得 publication identity、锁外准备 replacement、Phase B 复制 latest 后 identity-first 重验证。两者共同要求远端 HTTP、PDF 下载与 Docling I/O 不可发生在 writer/publication lock 区间。

现有 SEC 普通 source 与 rejected artifact 两条调用链都违反该约束：

```text
普通 source:
run_download_single_filing_stream
  -> begin_batch
  -> SecDownloader.download_files_stream
       -> HTTP transport decision
       -> StoreDownloadedFile(..., batch=token)
  -> source upsert
  -> commit/rollback

rejected artifact:
persist_rejected_filing_artifact
  -> begin_batch
  -> SecDownloader.download_files_stream
       -> HTTP transport decision
       -> StoreDownloadedFile(..., batch=token)
  -> rejected meta / failure summary
  -> commit/rollback
```

直接证据：

- `sec_download_filing_workflow.py:445-465` 在 `download_files_stream` 前取得 batch。
- `sec_downloader.py:84-109,1488-1516` 把 `BatchToken` 与 storage callback 设为 `download_files_stream` required contract。
- `sec_downloader.py:1534-1596` 在同一方法中先执行 HTTP，再调用真实 storage callback。
- `sec_download_persistence.py:255-272` 在 rejected artifact 路径先 `begin_batch`，再调用同一下载 API。
- `sec_download_persistence.py:480-510` 的 callback 会立即调用 repository `store_file`，证明物理 materialization 需要真实 open batch。

Root cause 是 SEC downloader 把 transport decision/payload acquisition 与 storage materialization 放在一个 required-batch API 中。语义 owner 裁决如下：

- `sec_downloader.py` 是 SEC HTTP、conditional/unconditional transport、retry、throttle、304、empty、provider failure、transport cancellation 与 prefetch-event projection 的唯一 owner。
- `sec_download_persistence.py` 是 storage callback 构造、rejected artifact transaction、rejected meta/failure summary、commit/rollback 的 owner。
- `sec_download_filing_workflow.py` 是普通 source Phase A/Phase B identity-first orchestration owner。
- `SourceDocumentRepositoryProtocol`、`FsSourceDocumentRepository` 与共享 core 是 published/staged identity、integrity 与物理文件事实的唯一 owner；不另造 capability Protocol。

第一轮 review 已证明 prepared callable/captured replay wrapper 只是为匹配 `DownloadFilesStream` 旧签名而存在的 glue seam。该设计及其 request-identity replay 校验从本 amendment 完全删除，不保留备选、兼容或 fallback 路径。

## 3. Scope 与 allowlist amendment

### 3.1 唯一新增 production allowlist

- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/sec_download_persistence.py`

### 3.2 唯一新增 test allowlist

- `tests/fins/test_sec_downloader.py`

### 3.3 既有 base-allowed test owner

- rejected artifact 的 persistence 路径必须在 base plan 已允许的 `tests/fins/test_sec_pipeline_download.py` 内覆盖。
- 没有直接证据要求新增 `tests/fins/test_sec_download_persistence.py` 或其它测试文件，因此本 amendment 不允许新增它们。
- base plan Slice 4 已列出的其它 production/test allowlist 保持有效；本节只增加 §3.1 与 §3.2 的文件。

### 3.4 Scope 不变量

- 只允许修改 base plan Slice 4 allowlist与本 amendment明确增加的文件；不得修改 README、base plan、stop-condition evidence、review artifacts、Oracle/registry、真实 CLI/provider、Host/Engine、PR190 或 production timing hook。
- 不新增 capability Protocol、compat alias、compat wrapper/facade、prepared callable、replay wrapper、request-identity replay 校验、legacy path、默认参数、`getattr/hasattr` fallback 或 loose parsing。
- 不为 prefetch 构造/伪造 `BatchToken`，不把 batch、callback、repository、storage path 或 durable identity 塞入 extra payload。
- 若实现需要 §3 之外的新 production/test allowlist，必须先触发 §12 stop condition，implementation agent 不得自行扩 scope。

## 4. Storage-neutral typed prefetch contract

### 4.1 模块私有 discriminated intermediate

在 `dayu/fins/downloaders/sec_downloader.py` 定义模块私有的 frozen/slots discriminated variants；这些类型不从 `dayu.fins.downloaders` re-export，不进入公共 schema、storage meta、durable audit、LLM-facing 文本或 compatibility contract：

```python
@dataclass(frozen=True, slots=True)
class _PrefetchStarted:
    kind: Literal["started"]
    descriptor: RemoteFileDescriptor

@dataclass(frozen=True, slots=True)
class _PrefetchedFile:
    kind: Literal["prefetched"]
    descriptor: RemoteFileDescriptor
    http_status: int
    http_etag: str | None
    http_last_modified: str | None
    content: bytes

@dataclass(frozen=True, slots=True)
class _PrefetchSkipped:
    kind: Literal["skipped"]
    descriptor: RemoteFileDescriptor
    http_status: int
    reason_code: Literal["not_modified"]
    reason_message: str

@dataclass(frozen=True, slots=True)
class _PrefetchFailed:
    kind: Literal["failed"]
    descriptor: RemoteFileDescriptor
    http_status: int | None
    reason_code: str
    reason_message: str
    error: str

_PrefetchEvent: TypeAlias = (
    _PrefetchStarted | _PrefetchedFile | _PrefetchSkipped | _PrefetchFailed
)
```

字段名可按现有类型作机械对齐，但互斥语义不得改变：

- `_PrefetchedFile.content` 必须是非空 immutable `bytes`；它不得携带 `FileObjectMeta`、batch、local URI/path、reason 或 error。
- `_PrefetchSkipped` 只表达现有 HTTP 304 `not_modified` facts；它没有 content/file meta/error。
- `_PrefetchFailed` 只表达现有 path/contact-free transport failure；empty response、0-byte 与 provider/runtime failure 使用现有封闭 reason projection。
- started/skipped/failed 不得用 `content=None` 模拟另一 variant；prefetched 不得用 optional reason/error 形成 god bag。
- 若 implementation 发现单个 variant 或共享字段仍无法在类型构造时封闭互斥约束，必须继续拆成更窄的 typed variants；禁止退回一个包含多个 optional state 字段的大 dataclass。

### 4.2 Storage-neutral prefetch stream

`SecDownloader` 增加：

```python
async def prefetch_files_stream(
    self,
    remote_files: list[RemoteFileDescriptor],
    *,
    allow_not_modified: bool,
    existing_files: dict[str, dict[str, JsonValue]] | None = None,
    primary_document: str | None = None,
    cancellation_checker: Callable[[], bool] | None = None,
) -> AsyncIterator[_PrefetchEvent]:
    ...
```

`allow_not_modified` 是 required transport 参数，不是 request-level `overwrite_existing` 的别名：

- `True` 才允许使用 existing ETag/Last-Modified 发 conditional request并产生 304 skip。
- `False` 必须走现有 unconditional transport helper，不发送 conditional reuse decision。
- repair target 无论原请求 `overwrite_existing` 为何都必须传 `False`，取得完整 replacement；Phase B policy仍只使用原始 `overwrite_existing`。
- 普通显式 overwrite 传 `False`；非 repair 的普通 reuse path才可按现有语义传 `True`。

其它硬约束：

- 签名与 prefetch body 不得出现 `BatchToken`、`StoreDownloadedFile`、repository、workspace storage locator、`FileObjectMeta`、begin/commit/rollback 或 storage callback。
- 这是 SEC file transport decision 的唯一 core：descriptor 顺序、conditional headers、unconditional repair、HTTP/retry/throttle、200/304、empty、primary 0-byte abort、safe failure projection 与 transport cancellation checkpoint全部只在此产生。
- primary 0-byte 仍只产生当前 started + failed，随后停止枚举其余 descriptor；普通 empty file失败后继续下一 descriptor，与现有 observable behavior一致。
- cancellation 命中后停止后续 transport，不伪造 failed；已取得但尚未 materialize 的 bytes 直接丢弃。
- 不新增 retry、timeout、sleep、throttle、UA 或 provider owner；完全复用当前 `SecDownloader` transport helpers 与 workspace-shared SEC throttle。

### 4.3 到 `DownloaderEvent` 的完整映射与唯一 materialization owner

`SecDownloader` 内只允许一个 typed event materialization/projection implementation（下称 `materialize_prefetched_event`；可按代码命名规范调整名称）。`download_files_stream`、普通 SEC Phase B 与 rejected persistence 都调用该实现，禁止各自复制映射分支：

| 私有 prefetch variant | Storage callback | `DownloaderEvent` 映射 |
|---|---:|---|
| `_PrefetchStarted` | 0 | `file_download_started`；逐字段投影 descriptor identity/transport facts |
| `_PrefetchSkipped` | 0 | `file_skipped`；保留 304 status、`not_modified` reason |
| `_PrefetchFailed` | 0 | `file_failed`；保留 safe reason/error projection |
| `_PrefetchedFile` | 恰好 1 次，且必须传 caller 的真实 open batch | callback 成功返回真实 `FileObjectMeta` 后才产生 `file_downloaded`；callback失败不得产生成功 event |

唯一 owner 分解为：

- `sec_downloader.py` 的该单一实现拥有 prefetch variant → callback invocation → `DownloaderEvent` 的映射，不做 repository 直写。
- `sec_download_persistence.py` 继续唯一拥有 `StoreDownloadedFile` callback 构造与实际 repository materialization 规则。
- persistence/workflow 只把当前轮私有 intermediate逐个交给单一 materializer；不得 inspect raw optional fields、重算 transport reason或实现第二张映射表。
- 这不是 replay API：不捕获 request facts，不伪装为 `DownloadFilesStream`，不接受/校验 remote request identity，不重放一个适配旧 Protocol 的 callable。

## 5. Single shared transport core 与两条 materialization 路径

### 5.1 现有 `download_files_stream` 的合法关系

`SecDownloader.download_files_stream(...)` 保留真实的“下载并 materialize”组合语义与现有 required batch/callback contract，但方法体必须是：

```text
prefetch_files_stream (唯一 HTTP/transport decision core)
  -> 每个 _PrefetchEvent
       -> materialize_prefetched_event (唯一映射/materialization implementation)
            -> control variant: 直接投影 DownloaderEvent
            -> _PrefetchedFile: StoreDownloadedFile(content, batch=真实 caller token)
                               -> callback成功后投影 file_downloaded
```

- `download_files_stream` 不得直接调用 `_http_download`、`_http_download_if_modified`、`_execute_sec_request` 或 provider client。
- 它把现有 `overwrite` 语义机械转换为 `allow_not_modified=not overwrite`；不在该 API 中引入 integrity/repair policy。
- `StoreDownloadedFile` 已声明的 `OSError`/`ValueError` 原样传播，不被 transport failure mapper吞掉；不为未承诺的偶然异常增加兼容捕获。
- `download_files(...)` 继续只聚合 `download_files_stream`，不得另走 HTTP 或第二套 prefetch branch。
- `download_files_stream` 仍承担真实 transport + materialization 组合行为，因此不是只为旧名字转发的 compatibility wrapper。

`tests/fins/test_sec_downloader.py` 必须增加 shared-core 集成断言：替换/spy `prefetch_files_stream` 返回预设 typed variants，调用真实 `download_files_stream`，证明输出及 callback/token行为完全来自该 core且旧直接 transport branch不再执行。该 owner test可以断言 core调用边界；pipeline/runtime tests不重复断言 provider调用次数。

### 5.2 Rejected artifact：persistence owner 直接 prefetch 后 transaction

`dayu/fins/pipelines/sec_download_persistence.py::persist_rejected_filing_artifact` 直接接收并调用 `SecDownloader.prefetch_files_stream`（或等价的 concrete typed method dependency），不再接收一个伪装的 prepared/replay downloader：

```text
persist_rejected_filing_artifact
  -> 完整消费 prefetch_files_stream
       HTTP/304/empty/failure/cancel（无 batch、无 storage callback）
  -> cancellation checkpoint
  -> begin_batch(ticker)（真实 batch）
  -> 对当前轮 _PrefetchEvent 逐个调用唯一 materialize_prefetched_event
       只有 _PrefetchedFile 在此调用真实 rejected StoreDownloadedFile callback
  -> 保持既有 rejected file results、failure summary、meta、validator
  -> commit；任一失败/cancel则 rollback
```

硬约束：

- prefetch 必须在 `begin_batch` 调用前完整结束；没有 provider/PDF/Docling I/O 可从 begin 到 commit/rollback 区间到达。
- materialization只使用 `persist_rejected_filing_artifact` 当前 transaction 的真实 batch；不构造 fake token，不缓存或转交 batch。
- 保持 rejected artifact 现有 event顺序、成功/失败计数、file result、failure summary、meta、complete validator、commit/rollback 与 error projection语义。
- cancellation 在 prefetch完成后、`begin_batch` 前命中时，必须丢弃 bytes且不调用 `begin_batch`/callback；batch内命中则按既有 rollback/finally规则关闭。
- 删除 `DownloadFilesStream` 仅为该路径服务的 dependency/Protocol形态时，应改为直接、typed、具体参数；不得新增替代 capability Protocol、factory、replay adapter或兼容 facade。

## 6. SEC/CN 三轮 identity-first 状态机

base plan §5.6 的 SEC/CN 三轮状态机保持不变；本 amendment只具体化 SEC payload acquisition/materialization：

1. **Phase A classify/policy**：repository在短 publication guard内返回 typed integrity classification。`COMPLETE + overwrite_existing=False` 立即skip且不做target网络；其它apply候选进入锁外prefetch。
2. **Phase A prefetch**：没有 batch、writer lock、publication guard或storage callback。SEC repair强制 `allow_not_modified=False`；普通 overwrite同样unconditional；CN继续使用既有锁外PDF/Docling路径。
3. **Phase B begin/latest-copy**：全部target transport/precheck完成后才 `begin_batch(ticker)`；blocking writer返回的 staging必须复制latest published tree。
4. **Phase B identity-first**：第一条target operation必须是 `classify_staged_source_integrity(..., batch=token)`。先比较Phase A/staged publication identity；变化时不得解释latest status、不得materialize，立即rollback/release/notify、丢弃本轮全部prefetch并回Phase A。
5. **Phase B policy**：identity相同才使用latest integrity与原始 request-level `overwrite_existing`。`REPAIR_REQUIRED`强制apply；`MISSING` create apply；`COMPLETE + True` overwrite apply；`COMPLETE + False`丢弃prefetch并skip。transport的 `allow_not_modified` 绝不覆盖或替代该policy值。
6. **Phase B真实materialization**：apply分支逐个交给唯一materializer，callback使用同一真实token。repair不得接受304复用损坏physical file；304仅能在允许conditional且same-identity latest entry完整时复用既有条目。
7. **Publication**：materialization、source upsert、complete validator与atomic commit沿用storage owner；callback/upsert/validation/cancel任一失败均rollback，published latest保持不变。
8. **Revision churn**：identity变化最多消耗命名常量规定的3轮；每轮重新联网前释放writer/reservation。耗尽抛typed integrity conflict，不得变成writer timeout或普通业务冲突。

同 target 双 overwrite writer必须都成功：后writer发现revision变化后丢弃旧prefetch、重新取得replacement并按序列化顺序形成合法last-writer。不同target writer都在latest tree副本上只改自己的target，最终published集合保留并集。

### 6.1 Integrity classification 的结构错误边界

- `PHYSICAL_FILE_MISSING`、`SIZE_MISMATCH`、`DIGEST_MISMATCH` 只对结构合法的source meta产生 `REPAIR_REQUIRED`。
- `sha256` 非字符串、空串或不满足canonical 64位十六进制摘要结构属于meta结构错误，沿用strict storage error立即失败；不得把 malformed sha256降级为 `DIGEST_MISMATCH`、`REPAIR_REQUIRED`、`UNKNOWN` 或 repair fallback。
- 只有结构合法的expected sha256与实际physical bytes摘要不同，才分类为 `DIGEST_MISMATCH`。
- identity/meta其它结构损坏同样严格失败；不做字符串解析兜底，不放宽ordinary snapshot/read/commit validator。

## 7. Deterministic test specification

所有新增 thread/process/race tests只使用 `threading.Event`、`multiprocessing.Event`、`Barrier`与bounded test deadline协调；禁止 `sleep`、概率循环或production timing hook。timeout只作为测试挂死诊断，不能进入production writer语义。

### 7.1 Downloader owner matrix：`tests/fins/test_sec_downloader.py`

| Case | Prefetch assertion | Materialization/shared-core assertion |
|---|---|---|
| unconditional HTTP 200 | started + `_PrefetchedFile`，content exact | callback恰好一次使用caller真实token；成功后才有`file_downloaded` |
| conditional HTTP 200 | 同上并保留response facts | 同上 |
| HTTP 304 | started + `_PrefetchSkipped(not_modified)` | callback零调用，投影现有skipped facts |
| `payload is None` | `_PrefetchFailed(empty_response)` | callback零调用，继续下一descriptor |
| 0-byte non-primary | `_PrefetchFailed(empty_content)` | callback零调用，继续下一descriptor |
| 0-byte primary | 当前primary只有started + failed | 后续descriptor transport/materialization均不发生 |
| provider/transport failure | 现有safe mapper产生path/contact-free failed | callback零调用，不泄漏raw URL/payload |
| cancel before request | 无target transport、无伪failed | 无callback，流收口 |
| callback `OSError`/`ValueError` | prefetch facts不变 | 原异常传播，不产生`file_downloaded` |
| repair transport | `allow_not_modified=False`时强制unconditional，不产生304 | Phase B仍保留原请求overwrite policy |
| shared-core integration | spy prefetch core返回started/prefetched/skipped/failed variants | 真实`download_files_stream`逐个调用唯一materializer；不存在旧直接transport分支 |

`download_files` 聚合测试继续证明它只消费 `download_files_stream`。owner test可以对 injected/spied shared core做一次明确的调用边界断言；不得以runtime provider计数替代static call-site枚举。

### 7.2 Rejected persistence：`tests/fins/test_sec_pipeline_download.py`

- 使用现有base-allowed文件，不新增persistence专用测试文件。
- fake prefetch stream记录`prefetch_entered`与`prefetch_returned`；`SpyBatchRepository`记录`begin/commit/rollback`及每次调用序号，`SpyStoreFile`记录`(sequence, batch_token, name, payload_sha256)`。
- 正常200路径断言：`prefetch_returned < begin < first_store < commit`，真实token全等，rejected file results/failure summary/meta与既有语义一致。
- 304、empty、provider failure分别断言既有rejected结果与callback零调用/部分成功规则；runtime只断言端到端artifact、events与transaction结果，不断言冗余provider调用次数。
- **cancel after prefetch/before begin**：fake prefetch在返回最后一个typed event后设置`prefetch_returned`并等待test-owned `release_prefetch_return` Event；测试线程观察该Event后主动设置canonical cancel flag，再释放generator返回。函数在`begin_batch`前的既有cancellation checkpoint观察cancel；断言begin/callback/commit/rollback均为0、latest不变。不得在production增加hook或awaitable checkpoint。
- store/validator/cancel failure断言rollback、latest old tree及rejected语义不变；Spy记录必须证明不存在锁内provider阶段。

### 7.3 Phase A/B race 与 corruption matrix

在base-allowed SEC/CN workflow与storage tests中使用下列明确时序：

1. **同target双overwrite**：两个writer在各自Phase A classification后通过`phase_a_classified` Barrier；各自prefetch返回后通过`prefetch_complete` Barrier。测试先释放writer A进入`begin_batch`、materialize、commit；`a_committed` Event再释放writer B。B的首个staged classification观察revision变化，`SpyStoreFile`证明旧payload callback为0；B rollback/release后设置`b_retry_started`，第二轮prefetch完成后再进入batch并commit。断言两者terminal success，最终内容是B第二轮payload，不是B旧prefetch。
2. **三轮revision churn**：每轮target先完成Phase A与prefetch并设置`round_n_prefetched`；控制writer收到该Event后发布同target新revision并设置`round_n_published`，目标writer只有收到published Event后才进入`begin_batch`。三轮staged identity均变化、旧payload callback均为0；第三轮耗尽抛typed conflict，latest精确等于最后一个控制writer版本。
3. **不同target union**：同ticker的A/B在`prefetch_complete` Barrier会合；A先commit target A并设置`a_committed`，B随后取得writer。B的target identity未变化，staging已包含A，B只materialize target B并commit。断言两者成功且最终集合为A/B并集。
4. **overwrite policy**：stable identity下分别固定latest classification为COMPLETE/REPAIR_REQUIRED/MISSING。`overwrite_existing=True + COMPLETE`必须materialize并成功，不能skip；False按base matrix；repair prefetch始终unconditional。
5. **corruption**：physical missing、合法sha256的digest mismatch、size mismatch分别repair并通过production strict snapshot；失败保留old bytes/meta/manifest。malformed sha256单独断言strict结构错误且provider/prefetch/batch均未调用。
6. **ordering spies**：`SpyBatchRepository`至少记录`begin/staged_classify/commit/rollback/release`，`SpyStoreFile`记录首次callback与payload digest；断言每轮`prefetch_complete < begin < staged_classify < first_store < commit`，identity变化轮不存在`first_store`。

## 8. Static/call-graph gate：可执行证据，不作形式化不可达声明

implementation必须组合四类证据；任何单项都不能单独声称形式化证明Python动态调用图不可达：

1. `rg` 枚举全部定义与调用点；逐项分类为transport owner、materialization consumer或forbidden direct call。
2. Python AST脚本检查明确的syntax-level不变量；脚本只能报告它实际解析到的直接调用/签名/构造，不把结果表述为完整reachability证明。
3. full pyright验证typed variants、Protocol implementers、callback/token签名与所有调用方。
4. 人工call-graph review把普通source、rejected artifact与CN路径逐条展开到provider/PDF/Docling及begin/commit/rollback边界，在implementation artifact记录`file:line`证据和裁决。

可执行命令：

```bash
rg -n "def (download_files_stream|prefetch_files_stream|persist_rejected_filing_artifact)|\.(download_files_stream|prefetch_files_stream)\(" dayu tests
rg -n "_http_download(_if_modified)?\(|_execute_sec_request\(|begin_batch\(|commit_batch\(|rollback_batch\(" dayu/fins/downloaders dayu/fins/pipelines dayu/fins/storage tests/fins
rg -n "SourceDocumentRepositoryProtocol|class .*SourceDocumentRepository|classify_(staged_)?source_integrity" dayu tests
rg -n "BatchToken\(|getattr\(|hasattr\(|prepared|replay|compat" dayu/fins/downloaders/sec_downloader.py dayu/fins/pipelines/sec_download_persistence.py dayu/fins/pipelines/sec_download_filing_workflow.py
python workspace/tmp/wu_cli_download_01_slice4_static_gate.py
python -m pyright dayu/ tests/ utils/
```

临时AST脚本只允许位于 `workspace/tmp/wu_cli_download_01_slice4_static_gate.py`，不得放进production/tests。脚本至少检查：

- `prefetch_files_stream` required参数、annotation与直接body不包含batch/callback/repository/`FileObjectMeta`/begin/commit/rollback；
- `download_files_stream` 直接调用 `prefetch_files_stream`，且不直接调用HTTP/provider helpers；`download_files` 直接聚合 `download_files_stream`；
- 所有 `_http_download`、`_http_download_if_modified`、`_execute_sec_request` 调用点被完整列出并输出供人工复核；
- production不存在prefetch `BatchToken(...)` 构造、prepared/replay adapter、fake capability、compat alias/wrapper、`getattr/hasattr` fallback或新增timeout；
- source repository Protocol、production wrapper/core与`rg`列出的test subclasses全部实现/继承typed published+staged classification contract。

人工call-graph review必须明确记录：

- 普通SEC路径：prefetch完整返回后才begin；batch内只做staged classification、materialization、upsert、validator与publication。
- rejected路径：`persist_rejected_filing_artifact` prefetch完整返回后才begin；batch内无transport helper。
- CN路径：PDF/Docling继续在commit helper的begin前完成。
- 若因动态dispatch或独立Protocol implementer而无法根据`rg + AST + pyright + 人工展开`建立可信调用链，触发stop condition；不得把best-effort结果写成形式化不可达。

## 9. Validation commands

implementation恢复后，先运行owner tests：

```bash
source .venv/bin/activate
pytest tests/fins/test_sec_downloader.py -q
pytest tests/fins/test_sec_pipeline_download.py -q
```

再运行Slice 4 affected union：

```bash
pytest tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_docling_upload_service.py -q

for run in 1 2 3 4 5; do
  pytest tests/fins/test_sec_pipeline_download.py \
    tests/fins/test_sec_pipeline_download_stream.py \
    tests/fins/test_cn_download_workflow.py \
    tests/fins/test_fins_storage_atomicity.py -q || exit 1
done
```

随后执行base plan §9完整aggregate union及以下static/quality gates：

```bash
python workspace/tmp/wu_cli_download_01_slice4_static_gate.py
python -m pyright dayu/ tests/ utils/
python -m ruff check <本WU全部changed-python-files>
python -m ruff format --check <本WU全部changed-python-files>
python -m compileall dayu tests
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
git diff --check
```

使用同一affected union产生coverage data后，对每个修改production文件逐一执行：

```bash
coverage report --include=dayu/fins/downloaders/sec_downloader.py --fail-under=80
coverage report --include=dayu/fins/pipelines/sec_download_persistence.py --fail-under=80
coverage report --include=<每个其它Slice-4修改production文件> --fail-under=80
```

validation artifact还必须附上：完整`rg`调用点枚举、AST脚本位置与输出、人工call-graph `file:line`清单、5次repeat结果、逐production文件coverage。任何通过方式若放宽safe failure、primary abort、304、cancellation、strict validator、真实batch、owner contract或使用sleep猜时序，均判失败。

## 10. Non-goals 与无过度设计说明

- 不新增通用下载框架、跨provider prefetch abstraction、spool backend、operation-wide transaction、storage capability Protocol、第二套SEC throttle或future-provider扩展点。
- 不改变SEC discovery、UA、retry参数、provider装配、CLI schema、public terminal summary、Oracle或registry。
- 不把private prefetch intermediate持久化或暴露给LLM，不新增public capability/compat contract。
- 不保留prepared callable、captured-data replay、request-identity replay validation或匹配旧`DownloadFilesStream`签名的adapter。
- 不用业务timeout解决OS/file lock永久I/O卡死；该项继续作为后续runtime/storage reliability WU风险。
- README仍留到四个slices完成后的documentation closeout，本gate不修改。

## 11. Review finding adjudication

| Review finding | 总控裁决后的plan resolution |
|---|---|
| AgentMiMo F-01 / AgentDS 2：prefetch type接近god bag、与`DownloaderEvent`重叠 | 改为模块私有discriminated variants；列出完整映射；单一materializer拥有投影，无法封闭互斥约束时继续拆variant。 |
| AgentMiMo F-02 / AgentDS 1：prepared rejected callable是glue seam | allowlist增加`sec_download_persistence.py`；由`persist_rejected_filing_artifact`直接preload再用真实batch materialize；删除prepared/replay设计。 |
| AgentDS 3 / OQ-1：request-identity replay校验owner不清 | 整个replay contract与request equality校验删除；persistence直接消费当前调用产生的typed stream，不存在二次request输入。 |
| AgentMiMo F-03 / F-09：single core与现有API关系 | 保留真实`download_files_stream`组合语义；明确它只调用shared prefetch core与唯一materializer，`download_files`继续聚合。 |
| AgentMiMo F-04 / AgentDS OQ-3：AST工具规格与不可达表述 | 改为`rg`全枚举 + 指定`workspace/tmp` AST脚本 + full pyright + 人工call-graph review；明确不是形式化reachability证明。 |
| AgentMiMo F-05/F-06 / AgentDS 6：identity-first与repair/overwrite混淆 | 保持base三轮状态机；新增required `allow_not_modified` transport语义；repair强制unconditional，Phase B仍使用原`overwrite_existing`。 |
| AgentMiMo F-07 / AgentDS 4：测试矩阵缺shared-core断言且race/cancel时序不充分 | 增加shared-core integration、cancel精确Event placement、SpyStoreFile/SpyBatchRepository、同target/revision churn/different-target barrier序列，全面禁止sleep。 |
| AgentDS 5：runtime provider调用计数冗余 | runtime只断言rejected artifact端到端结果与transaction时序；direct call归属由owner test、`rg`、AST与人工review覆盖。 |
| AgentMiMo F-08 / AgentDS OQ-2：allowlist与rejected owner scope | 精确增加一个production文件；rejected tests落在既有base-allowed`test_sec_pipeline_download.py`，没有证据不新增测试文件。 |
| AgentDS RR-2：`download_files_stream`未来可能dead API | 当前仍有真实组合语义与消费者，不在Slice 4删除；Slice 4 closeout执行调用点枚举，若未来无消费者再由独立plan裁决。 |
| AgentDS RR-3：CN锁外I/O回归 | CN不扩大production scope；本Slice barrier/static/manual call-graph gate继续覆盖CN begin边界。 |

本轮用户另行裁决的 malformed sha256边界已写入§6.1：它是严格结构错误，不进入repair classification/fallback。

## 12. Stop conditions

出现任一项立即停止implementation，产出新evidence并回到plan fix/re-review：

- 需要增加§3以外的新production/test allowlist，或修改README/base plan/evidence/review artifact/Oracle/registry/真实CLI/provider/Host/Engine/PR190；
- 独立`SourceDocumentRepositoryProtocol` implementer不在inventory，或必须用default/compat/getattr/hasattr掩盖新typed contract；
- prefetch API需要batch、callback、repository、`FileObjectMeta`、local path、fake capability或prepared/replay adapter；
- transport decision在shared prefetch core之外重复，或`download_files_stream`/persistence/workflow直接调用HTTP/provider helper；
- rejected artifact在`begin_batch`后仍可达provider，或改变既有rejected file results/failure summary/meta/validator语义；
- repair prefetch允许conditional/304，request-level overwrite被transport参数覆写，或`overwrite_existing=True`被latest COMPLETE转成skip；
- Phase B staged identity comparison前调用storage callback，identity变化后旧prefetch进入callback，或三轮retry未在重新联网前release/notify；
- 合法writer因timeout失败、recovery try-lock变blocking、lock顺序冲突、漏release/notify、lost update、same-target任一stable writer失败或different-target丢失并集；
- malformed sha256被归类为repair/UNKNOWN而非strict结构错误，或为通过测试放宽snapshot/read/complete validator；
- deterministic race/cancel测试需要sleep、概率时序或production timing hook；
- `rg + AST + pyright + 人工review`仍无法建立普通SEC、rejected与CN的可信call graph，或动态dispatch使边界无法裁决；
- callback/cancel/validation/3轮耗尽改变latest published tree，5次repeat不稳定，pyright新增/扩散错误，或任一修改production文件coverage低于80%。

## 13. 风险裁决

| 风险 | 分类与裁决 | Owner / destination | Gate影响 |
|---|---|---|---|
| SEC普通/rejected路径当前锁内HTTP | `covered by this amended slice` | `sec_downloader.py` shared prefetch core；workflow与`sec_download_persistence.py`锁外消费 | re-review接受前blocking |
| prepared callable/replay seam | `resolved by plan fix` | 设计已删除；persistence owner直接消费typed stream | implementation禁止复活 |
| private variants与`DownloaderEvent`重复/膨胀 | `covered by this amended slice` | downloader单一projection/materializer；discriminated variants封闭约束 | owner tests + pyright gate |
| repair transport与request overwrite混淆 | `covered by this amended slice` | required `allow_not_modified`只管transport；Phase B原值管policy | matrix/race tests gate |
| DL-F08 blocking writer/release/notify尚未实现 | `covered by this amended slice` | base Slice 4 storage owner allowlist/tests | 不扩大本amendment新增文件 |
| DL-F10 typed integrity/三轮revalidation尚未实现 | `covered by this amended slice` | base Slice 4 repository/workflow allowlist/tests | identity/race/corruption gate |
| malformed sha256可能误作repair | `covered by this amended slice` | storage integrity owner strict结构校验 | corruption matrix gate |
| Python动态调用图不能形式化证明不可达 | `accepted with controls` | `rg`枚举、AST直接规则、pyright、人工call graph与barrier共同举证 | 证据不足即stop |
| OS/file lock永久I/O卡死 | `assigned to later work unit` | 后续runtime/storage reliability WU；当前禁止业务timeout | 非本slice blocker，implementation artifact继续记录 |
| `download_files_stream`未来可能无消费者 | `assigned to closeout/dead-code review` | Slice 4 closeout调用点inventory | 当前仍有真实语义，非blocker |
| CN未来锁外I/O回归 | `accepted with regression controls` | base-allowed CN tests + static/manual call graph | 当前不改CN transport owner |

所有已知evidence与两路review风险均已有owner、验证destination与gate影响；无静默defer项。

## 14. Docs、completion signal 与下一入口

- README：本gate不修改；仍留到四slices后的documentation closeout。
- Base plan/evidence/review artifacts：零修改。
- Oracle/registry：`not updated`。
- Plan-fix completion signal：本artifact只修订正式amendment；allowlist、private typed contract、owner mapping、rejected path、repair transport、deterministic tests、static gate、stop conditions与风险表自足；`git diff --check`通过。
- 当前gate：`plan fix`完成待原reviewers re-review，不是implementation或code review。
- Next entry point：原 AgentMiMo/AgentDS 分别对base plan + stop-condition evidence + 本amendment执行双路`$planreview` re-review；两路均accepted且总控裁决前不得恢复Slice 4 implementation。
- 本gate禁止commit、push、PR。
