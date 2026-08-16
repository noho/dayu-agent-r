# UF-FIX10 same-request-concurrency：实施计划

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`S2 acceptance`
- 日期：2026-08-17
- 当前分支：`codex/upload-filing-oracle`
- 基线提交：`7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`
- preflight：用户已确认；分支非 protected trunk，工作树中本 work unit 的 plan/fix/review artifacts 均由 Controller 明确纳入本 gate，ownership 清晰，无 merge/rebase/cherry-pick
- goal confirmation：用户已确认
- completion status：`S2 ACCEPTED / READY TO COMMIT`
- artifact path：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- blocking open questions：无；两路独立 re-review 均为 pass，全部 accepted findings 已根因关闭
- accepted commit：S1 基线为 `7e0941828c09d890ad04e3ff8f2c1cf5e28441ca`；S2 未创建 commit
- 下一入口：`S2 accepted slice commit`，完成后进入整分支 final deepreview

S1 acceptance 由 `docs/gateflow/uf-fix10-s1-acceptance-20260817.md` 记录。S2 implementation
evidence 记录于 `docs/gateflow/uf-fix10-s2-implementation-20260817.md`；两路 review 的
accepted findings 与修复边界由
`docs/gateflow/uf-fix10-s2-code-review-adjudication-20260817.md` 冻结，本轮修复证据记录于
`docs/gateflow/uf-fix10-s2-code-review-fix-20260817.md`；两路 re-review artifact 为
`docs/reviews/code-review-20260817-031615.md` 与
`docs/reviews/code-review-20260817-032141.md`。S2 已验收，下一 gate 按用户要求在当前分支
创建 accepted slice commit；仍不进入 UF-PF10/UF-PF12。

## 1. 输入、真源与边界

本计划以以下输入和当前代码为直接真源：

- `AGENTS.md`，SHA-256 `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`。
- Host 设计：`docs/host/design.md`，SHA-256 `7214cbcbef21b36c9020758da8fc4c5003c3813f6ded32ed77238af58327fe06`。
- Engine 设计：`docs/engine/design.md`，SHA-256 `b190e3a8ee2df84d29546ca04d4fb7d81a73877b27a3bddd04d2aaa40db17b1e`。
- Fins 当前开发契约：`dayu/fins/README.md`，SHA-256 `ff371e0a376e61cf495809df2e0973d2684669ee2d4dc0eb89e7974da8835f3b`。
- 测试维护契约：`tests/README.md`，SHA-256 `5036ca1f0f120910f94738665e64e36c54f5d01f972df28912743cb4bb04f189`。
- 当前 filing validator、fresh validation、SEC/CN/HK filing workflows、Docling preparation/publication、company decision、filesystem batch、filing upload state、source integrity、source/blob/meta/manifest 仓储与相关 tests。
- `docs/reviews/plan-review-20260816-221939.md` 与 `docs/reviews/plan-review-20260816-222742.md`；Controller 接受 MiMo 01-04、DS F1-F7 及 DS open questions 1-2，无 rejected finding。
- `docs/gateflow/uf-fix10-plan-review-fix-20260816.md`；记录首轮 accepted findings 的 plan fix 与当时的 re-review 入口。
- `docs/reviews/plan-review-20260816-224957.md` 与 `docs/reviews/plan-review-20260816-225732.md`；两路 re-review 结论均为 `pass`，Controller 将 DS residual R1/R2 提升为 accepted findings C-R1/C-R2，R3 保持已分类低风险。
- `docs/reviews/plan-review-20260816-231939-ds.md`；最终 review 结论为 `pass-with-risks`。Controller 将其中 F-1/F-2 接受为 blockers C-F1/C-F2：C-F1 不接受 expected-red 中间态，要求重划 S1/S2 owner 边界；C-F2 要求 staging meta 只有一个构造 owner。两项均已在本 plan 修复。
- `docs/gateflow/uf-fix10-s1-implementation-20260816.md` 中保存的 direct pyright evidence：`tests/fins/test_fins_ingestion_runtime.py:10865:40` 报 `_FixedFilingUploadStateRepository` 不满足 `FilingUploadStateRepositoryProtocol`，缺少 required `read_filing_upload_state_in_batch`。同文件 `_ForbiddenFilingUploadStateRepository` 也缺少该方法，只是其注入处 cast 暂时掩盖了相同 structural contract 缺口。该证据只授权 §10.1 的 fixture/protocol-conformance 修订，不授权生产或行为范围扩张。
- 同一 implementation artifact 新增的第二次 direct full-pyright evidence：首次 amendment 已完成、focused/full tests 与 coverage 已通过后，`tests/fins/test_fins_ingestion_tools.py:2474:40` 报该文件 `_ForbiddenFilingUploadStateRepository` 仍缺少 required `read_filing_upload_state_in_batch`。该第三个 fake 由 tool static-admission runtime 直接注入且无 cast；证据只授权 §10.1 对该 fake 做同型 protocol-conformance 与零行为断言修订，不授权其它 tool fixture、tool schema、production 或行为变化。

整个 work unit 始终禁止：

- 不修改 material 上传语义、UF-FIX11 company warning、CLI/Service/workflow fallback、tool schema、Host/Engine、oracle、scenario、registry 或 frozen evidence。
- 不运行 UF-PF10、UF-PF12 或真实 evidence/calibration；deterministic pytest 不属于 UF-PF evidence。
- 不捕获 `FileExistsError` 伪装成功，不按异常字符串分类，不用 `sleep`、重试、目录扫描 fallback、时间戳、文件顺序或历史行为判断竞争。
- 不新增通用 OCC、全局锁、跨 ticker semaphore、request registry、幂等数据库、第二套 transaction/journal/revision。
- 不在 CLI、Service、adapter、terminal renderer 或测试 fixture 补偿错误语义。
- 不把 explicit `create` 改写为 `auto`、`update` 或 `skipped`。
- 不改变显式 `create` / `update` / `delete` 的既有业务语义：特别是显式 `update` identical stable 重传仍为 `skipped`，显式 `create` 并发且 `overwrite=False` 仍 conflict，`create` + `overwrite=True` 仍 publish。
- 不为了旧测试、旧接口或旧 schema 增加 default、compatibility wrapper、loose parsing、`hasattr/getattr` 或 re-export shim。

## 2. 第一性原理判断与 root cause

### 2.1 动机成立

问题真实存在，严重性评估准确。当前代码已经有正确的原子发布和 per-ticker writer，但缺少“准备完成后、语义 mutation 前”的第二次 authoritative arbitration：

1. SEC `run_upload_filing_stream()` 在 `sec_upload_workflow.py:163-176` 先做 fresh validation，在 `:208-230` 完成读取 originals、fingerprint 与 Docling preparation；直到 `:234` 才 `begin_batch()`。CN/HK 在 `cn_pipeline.py:794-807`、`:839-865` 是同一窗口。
2. 两条 workflow 在 `begin_batch()` 后立即使用 preparation 前的 `authoritative_request.company_meta_decision` stage company（SEC `:236-240`，CN/HK `:867-871`），随后按 stale prepared mutation 写 source。没有第二次 validator 或等价 publication 判定。
3. `DoclingUploadService.prepare_upload()` 在 `docling_upload_service.py:365-410` 只对 preparation 当时的 `previous_meta` 做 create/update precondition 与 identical skip；并发 winner 在 preparation 后发布时，loser 的 `_PreparedAssetMutation.previous_meta/action/document_version` 不会自动刷新。
4. loser 进入 batch 后，`begin_batch()` 已复制 winner 的完整 ticker tree；stale `create` 最终会命中 staging `FileExistsError`。`FileExistsError` 是 `OSError` 子类，SEC/CN/HK workflow 的 `except OSError` 先于 generic handler，`fins_upload_failure_from_exception()` 实际将它投影为 `STORAGE_IO` / `storage_io`，而非 `UNEXPECTED_RUNTIME`。这仍既不是正确 skip，也不是业务可行动的 typed concurrency failure。
5. 根因不在 atomic swap：`_FsStorageInfra.begin_batch()` 在 `_fs_storage_infra.py:434-527` 先取得 canonical ticker 的 local reservation + cross-process writer lock，再复制 target 为 staging；同 ticker 后 writer 必须等待前 writer terminal。`commit_batch()` 在 `:550-560` 先验证完整 staging，再进入现有 commit 路径；`_commit_batch_with_publication_guard()` 在 `:683-697` 继续以 publication guard 完成 target→backup、staging→target、`COMMITTED` journal。
6. 因而第二套锁、retry 或全局 OCC 都不是 root-cause fix。正确边界是：`begin_batch()` 返回后，利用其 writer-owned、从最新 published tree 克隆的稳定 staging view重新读取 exact company/source state，调用同一 validator，并在任何 `stage_company_meta_intent`、reset、blob store、source create 或 manifest mutation 前裁决 publish/skip/conflict。

### 2.2 为什么不是局部捕获 `FileExistsError`

`FileExistsError` 只是 stale create 在某一 source consumer 的偶然症状：

- 它不能证明当前 source `COMPLETE`；可能是 damaged、deleted、不同 request、不同 converter output 或非法 staging。
- 它不证明完整 source fingerprint、primary/companions roles、derived assets、source meta 或 company requirements 等价。
- 它发生在 blob/source mutation 已经开始之后，已经错过要求的 arbitration boundary。
- 它无法覆盖 stale update、repair、company alias/meta decision、same ticker different filing union。

因此禁止捕获该异常伪装 skip；必须在 fresh state owner 与 prepared publication identity owner 的共同边界直接裁决。

## 3. Goal、成功信号与非目标

### 3.1 Goal / motivation

修复 exact auto filing upload 的同请求并发：在 ticker writer-owned publication batch 的 fresh authoritative view 上、任何 company/source 业务 mutation 前重新验证并裁决。winner 按现有路径正常发布；loser 只有在 durable publication 与 prepared candidate 完整等价且 company/source durable requirements 已满足时按封闭规则 skip，否则 typed fail closed。同时保留既有 sequential identical skip（含显式 `update`）与显式 create/update/delete 语义，并保证请求在等待 writer 期间被取消后不会最终投影为 skip/conflict/publish。

### 3.2 成功信号

1. 两个同 ticker、同 document、同 exact raw intent、同 primary/companions 与相同转换产物的 `auto` 请求并发准备后，恰好一个 `ok`，另一个 `skipped`；winner `stored_file_count=requested_file_count`，loser `stored_file_count=0`。
2. 任何 skip 前 fresh target 必须为 `COMPLETE`；其 canonical source fingerprint、primary original、companions、全部 original/derived asset metadata、primary Docling pointer、source business requirements、document version 与 prepared candidate exact 相等；fresh company decision 必须为 `keep`。stable retransmission 还必须携带 preparation owner 同源产生的 `IDENTICAL_PUBLICATION` typed disposition；changed concurrency convergence 只允许 raw `auto` + `overwrite=False` 的 `MISSING -> COMPLETE`。
3. canonical skip 不调用 company stage、blob store、reset、source create 或 `commit_batch()`；只终态 rollback 尚未发生业务 mutation 的 batch。published ticker tree、source revision、document version、assets、source meta、company meta、filing manifest 的 byte/digest snapshot 与 winner commit 后完全相同。
4. 显式 `update` 的 identical stable sequential 重传保持既有 `skipped`，`stored_file_count=0`，source revision/document version/tree 均不变；这是 stable retransmission preservation，不是 concurrency convergence。stable但内容有变化的显式`update`仍按既有语义publish；并发导致observation changed的显式`update`固定为closed typed conflict，不以action或近似identity降级。
5. 同 document 但 source fingerprint、primary/companions role、任一 original/derived asset metadata、source business requirement、converter output 或 company durable requirement不等价时，loser得到 `storage/source_publication_conflict` typed failure；failure 固定、有界、path-free、无 raw exception/revision/fingerprint。
6. 同 ticker、不同 filing 并发时，后 writer 在 batch view 中看到 winner，但 exact target 仍 `MISSING`；其 prepared source observation 未变，继续正常 stage/commit，最终 company tree 与 filing manifest保留两者并集。
7. 不同 ticker 的 batch-state read/arbitration 可同时进入 deterministic barrier；新增逻辑只消费既有 per-ticker writer，不增加 workspace/global lock。
8. `begin_batch()` 等待期间收到取消的请求，无论 fresh arbitration 原本会得出 `SKIP`、`CONFLICT` 还是 `PUBLISH`，取得 token 后都先 rollback 并返回 `cancelled`，company/source mutation、commit 与业务 terminal 均为0；rollback 失败则为 path-free `STORAGE_IO`。`PUBLISH` 进入既有 commit ownership 后保持现有 late-cancel boundary。
9. 继续复用现有 staged integrity、repair revision recheck、complete-tree commit validator、commit ownership/cancel boundary、publication guard、backup/journal old-or-new swap；错误或取消仍一次 rollback，无半发布。
10. SEC、CN、HK 三条 filing route 共享同一 publication owner；terminal `ok/skipped/failed`、stored count 与 failure JSON 继续由现有 Fins typed result/runtime owner投影，Host/Engine 不重判财报业务状态。
11. S1完成后现有`prepare_upload()` filing early-skip与SEC/CN/HK workflow行为不变，focused owner tests及完整`tests/fins`全绿，绝无expected red；S2以同一原子slice启用filing identical继续conversion、typed disposition、shared publication route与workflow tests后，focused tests、Fins suite、逐文件coverage目标与全仓pyright继续通过；README按职责更新。

### 3.3 Non-goals / scope boundary

- 不为一般不同 request 实现 winner selection、merge、last-writer-wins、automatic retry 或等待后重做 Docling。
- 不让 non-equivalent contender覆盖 winner；它只 typed fail closed。
- 不改变 material 的 prepare/skip/publication、existing source repair资格、UF-FIX11 warning、calendar/year/date、format、asset naming 或 primary selection规则。
- 不改变 source revision算法、manifest schema、company merge contract、batch journal或 storage recovery。
- 不修改 CLI参数、Service API、tool schema、LLM-facing prompt、HostEvent、EngineEvent、memory/trace/evidence。
- 不为保留 stable retransmission skip 新增下游 fallback；typed initial disposition 只由 Docling preparation owner 基于现有 `_can_skip_upload` 语义产生，publication owner 只消费该事实。
- 不运行或改写 UF-PF10/UF-PF12，不修改 oracle/scenario/frozen evidence。

## 4. Design document alignment

- `docs/host/design.md:35-43` 固定 `UI -> Service -> Host -> Engine` 分层，且明确 Host 不管理财报原文仓储规则；本修复只在 `dayu.fins` 内完成，不把 filing concurrency truth放入 Host/EventLog/ToolRuntime。
- `docs/host/design.md:59-72` 把 `dayu.runtime.filelock` 定位为层中立互斥而非 durable truth。本计划只复用现有 keyed filelock，不把 lock token当业务事实，也不扩展 runtime。
- `docs/engine/design.md:376-386` 明确工具批次执行策略属于 Host/ToolRuntime而非 Engine；`docs/engine/design.md:397-435` 要求 completed/failed/cancelled 为 typed outcome并在 owner boundary接受。本修复保持 Fins upload terminal/failure 为业务 owner，Engine不理解 `skipped` 或 publication conflict。
- `docs/engine/design.md:470-489` 的 accepted-fact/cancellation commit boundary与当前 `commit_prepared_upload_batch()` 一致：进入 storage `commit_batch()` 后不再以迟到取消回滚。新增 arbitration发生在 ownership transfer之前，不改变该边界。
- `dayu/fins/README.md:109-127` 已冻结 batch capability、per-ticker writer、short publication guard、blob-first complete source、fresh validation、company/source同批；本方案在这些现有边界内补齐 batch fresh recheck，不引入跨层或第二套事务。

结论：Host/Engine设计文档无需修改；实现只需保持其层次和 typed terminal原则。

## 5. 语义 ownership

| 语义 | 唯一 owner | 消费者限制 |
| --- | --- | --- |
| per-ticker writer顺序、batch capability、staging snapshot稳定性、commit/rollback terminal | `BatchingRepositoryProtocol` + `_FsStorageInfra` | workflow只持 token并调用明确API，不读取内部路径/lock |
| batch fresh company/source同版视图 | 扩展后的 `FilingUploadStateRepositoryProtocol` filesystem implementation | validator/publication owner只消费typed state，不读目录/raw path |
| source `MISSING/COMPLETE/REPAIR_REQUIRED/UNSAFE`、revision、files/primary/manifest可信性 | 现有 storage source integrity inspector | publication等价 owner不重新检查physical tree |
| canonical upload publication identity（fingerprint、roles、assets、source requirements） | `FilingUploadPublicationIdentity` contract；prepared producer为 `DoclingUploadService`，durable producer为 storage inspector projection | arbitration只做同类型exact equality，不从raw meta重建 |
| initial filing skip disposition（`NOT_ELIGIBLE` / `IDENTICAL_PUBLICATION`） | `DoclingUploadService.prepare_upload()` 与其 `_can_skip_upload` 同源判定 | S1只定义closed type/helper且保持现有filing early-skip；S2在同一原子slice接线为prepared filing required field，publication owner不从action/fingerprint/bool重算 |
| requested action、resolved action、repair authorization、file selection、company decision | `validate_fins_upload_filing_request()` | publication owner必须再次调用同一validator，不自行把create改auto/update |
| batch-time publish/skip/conflict裁决 | 新增 `dayu.fins.pipelines.filing_upload_publication` | S1只提供无I/O的closed arbitration helper；S2在同一模块接入batch lifecycle形成shared publication route，SEC/CN/HK workflow只调用一次并投影outcome，不复制判断 |
| company durable requirement | `resolve_upload_company_meta_decision()` | canonical skip仅接受fresh `disposition="keep"`；`stage`不被下游猜为“足够接近” |
| assets、fingerprint、document version、source meta、create-overwrite fresh rebase与staging write | `DoclingUploadService` | publication owner只取typed prepared facts、请求owner用fresh source meta重绑create-overwrite plan或调用publish，不访问pending bytes |
| staging upsert meta九字段（`updated_at`、`first_ingested_at`、`created_at`、`document_version`、`source_fingerprint`、`ingest_complete`、`source_provider`、`is_deleted`、`deleted_at`） | `docling_upload_service.py` 模块级私有 `_build_upsert_meta()` | 现有prepare与create-overwrite rebase必须共用该唯一owner；禁止复制字段逻辑。`first_ingested_at/created_at`从传入的fresh previous meta保持，version由`_resolve_document_version()`同源计算 |
| durable source `revision` | storage source-document owner | Docling staging meta不得生成、保持或推断revision；每次真正source write由storage owner覆盖为新revision |
| token 取消观察、rollback-first cancelled terminal与late-cancel handoff | `dayu.fins.pipelines.filing_upload_publication` 在 batch token 开放期内拥有；进入existing commit helper后由现有commit owner拥有 | workflow不在SKIP/CONFLICT分支各自补cancel，不在commit ownership后重判 |
| path-free concurrency failure | `dayu.fins.upload_failure` | workflow/runtime/CLI只透传closed reason，不读异常文本 |
| terminal `ok/skipped/failed`、count与durable summary | `UploadOperationResult` -> SEC/CN/HK workflow result -> `FinsUploadPipelineResult/FinsUploadResultSummary` | Host/Engine/Service不重算 |

owner 清楚，无需用户选择。

## 6. Contract / schema / public-interface changes

### 6.1 Storage typed publication identity

在 `dayu/fins/storage/repository_protocols.py` 新增 fresh contract，不保留旧 alias/default：

```python
FilingUploadAssetSource = Literal["original", "docling"]
FILING_UPLOAD_ASSET_SOURCE_ORIGINAL: Final[FilingUploadAssetSource] = "original"
FILING_UPLOAD_ASSET_SOURCE_DOCLING: Final[FilingUploadAssetSource] = "docling"

@dataclass(frozen=True, slots=True)
class FilingUploadAssetDescriptor:
    name: str
    original_filename: str
    derived_from: str | None
    sha256: str
    size: int
    content_type: str | None
    source: FilingUploadAssetSource

@dataclass(frozen=True, slots=True)
class FilingUploadPublicationIdentity:
    ticker: str
    document_id: str
    internal_document_id: str
    form_type: str
    company_id: str
    ingest_method: str
    fiscal_year: int
    fiscal_period: str
    report_kind: str
    filing_date: str | None
    report_date: str | None
    amended: bool
    source_provider: str
    is_deleted: bool
    document_version: str
    source_fingerprint: str
    primary_document: str
    primary_original_asset_name: str
    companion_original_asset_names: tuple[str, ...]
    assets: tuple[FilingUploadAssetDescriptor, ...]
```

严格不变量：

- ticker/document/internal/form/company/text字段非空且identity与外层state一致；`fiscal_year`为非bool整数；`amended/is_deleted`为精确bool。
- `source_fingerprint`与每个asset `sha256`必须是canonical lowercase SHA-256；size非负；asset storage `name`唯一，`assets` 在 prepared/durable 两端都按 `descriptor.name` 字典序排序。
- 至少一个original、恰好一个`primary_document` docling asset；该docling的`derived_from`精确命中original descriptor的 storage `name`，`primary_original_asset_name` 存的也是该 storage `name`，绝不是用户 basename / `original_filename`。`companion_original_asset_names` 是除primary外的original storage `name`，按storage `name`字典序排序；primary+companions恰好分割全部original，无重复。
- `FilingUploadAssetSource` 与两个 typed constant 由 `repository_protocols.py` contract 唯一定义并从 `dayu.fins.storage` 导出；`docling_upload_service.py` 与 `_fs_source_integrity.py` 必须直接使用该contract，删除各自的 filing asset-source private alias/constant，不得只依赖字面量恰好相同。
- `source_provider`必须是当前 user-upload storage值，`ingest_method`必须是upload，`is_deleted=False`才可成为canonical skip identity。
- 它是业务等价事实，不含filesystem path、URI、etag、last_modified、timestamps、revision token、batch id或raw bytes。

`FilingUploadPublishedState` 增加 required 字段：

```python
publication_identity: FilingUploadPublicationIdentity | None
```

- 只有 exact target `COMPLETE` 且storage能从同一次 trusted inspection形成完整user-upload identity时非空。
- `MISSING/REPAIR_REQUIRED/UNSAFE`固定为`None`；完整但非user-upload source或缺少上述upload身份字段也为`None`，因此不能canonical skip，但其现有integrity/source_meta行为不变。
- 不从manifest字符串、目录名或日志补值；只用 inspector 已验证的 business meta、file descriptors、primary/derived role facts投影。

### 6.2 Batch fresh read API

`FilingUploadStateRepositoryProtocol` 与 `FsFilingUploadStateRepository` 新增：

```python
def read_filing_upload_state_in_batch(
    self,
    batch: BatchToken,
    document_id: str,
) -> FilingUploadPublishedState: ...
```

契约：

- 先通过shared core `_resolve_active_batch(batch, batch.ticker)`验证token open、同core、ticker匹配。
- 只读该state的`staging_ticker_dir`；company meta与filing exact target来自同一次writer-owned稳定view。
- company meta 的唯一 storage owner 仍是 `_fs_company_meta_core.py`。在该文件新增私有 core helper `_read_company_meta_from_ticker_dir_unguarded(external_ticker, ticker_dir) -> CompanyMeta | None`：它对 caller 传入的exact ticker root调用现有 `_read_published_company_identity(ticker_dir, expected_storage_key=ticker_dir.name, known_directory_stat=...)` 做strict descriptor/meta/identity解析并校验canonical ticker。现有 `_get_company_meta_unguarded()` 改为先定位published root、再委托该helper；batch read 只传 `state.staging_ticker_dir` 给该helper。因此不读published path、不在filing state core重复解析，也不为 staging 放宽strict identity校验。
- filing source 仍复用现有 `_inspect_source_kind_unguarded(..., ticker_dir=state.staging_ticker_dir, requested_document_id=...)`；`_fs_filing_upload_state_core.py` 只编排两个core helper的typed投影。
- 不获取新writer/global lock，不调用published read，不扫描workspace。
- 方法本身不mutation staging，不stage intent，不consume token；错误仍使用现有path-free storage projection。
- `begin_batch()`的初始tree clone不是company/source业务mutation；第一项业务mutation仍必须发生在本方法与arbitration之后。

### 6.3 Prepared candidate identity 与 initial skip disposition

`dayu/fins/pipelines/docling_upload_service.py` 在 preparation owner 内新增 closed enum 与filing专用prepared subtype：

```python
class FilingInitialSkipDisposition(str, Enum):
    NOT_ELIGIBLE = "not_eligible"
    IDENTICAL_PUBLICATION = "identical_publication"

@dataclass(frozen=True)
class _PreparedFilingAssetMutation(_PreparedAssetMutation):
    initial_skip_disposition: FilingInitialSkipDisposition
```

- `_PreparedFilingAssetMutation` 是filing专用prepared candidate；继承既有asset mutation字段且新增required disposition，无default。严禁用 `bool`、裸 `str`、`None` 或default表达该事实。
- **S1只新增上述类型与下列Docling helper，不把它接入 `prepare_upload()`。** S1结束时，现有filing `_can_skip_upload` 命中仍在preparation阶段返回既有 `UploadOperationResult(status="skipped")`，不会继续conversion；SEC/CN/HK workflow行为必须与基线完全一致。
- **S2才在同一原子slice完成typed disposition接线与行为切换。** `IDENTICAL_PUBLICATION` 只在filing preparation当时既有 `_can_skip_upload(previous_meta, source_fingerprint, overwrite, repair_disposition=...)` 返回真时产生；其它filing candidate固定为 `NOT_ELIGIBLE`。该判定与既有skip语义同源，不在publication owner中从raw action或fingerprint重算。S2接线后，filing命中 `IDENTICAL_PUBLICATION` 不再在preparation阶段终结，而是继续primary Docling conversion、构造publication identity并进入batch。
- material 在S1/S2始终使用既有 `_PreparedAssetMutation`，在现有 `_can_skip_upload` 命中时直接返回early skip，不构造filing subclass或该disposition；delete/result也不携带该字段。这样不为material伪造filing事实，也不改变material行为。

`dayu/fins/pipelines/docling_upload_service.py` 在S1新增四个窄helper；S1通过直接构造typed candidate做owner contract tests，S2才把它们接入真实prepare/publication call path：

```python
def describe_prepared_filing_publication(
    prepared: PreparedDoclingUpload,
) -> FilingUploadPublicationIdentity: ...

def read_prepared_filing_initial_skip_disposition(
    prepared: PreparedDoclingUpload,
) -> FilingInitialSkipDisposition: ...

def rebase_prepared_filing_create_overwrite(
    prepared: PreparedDoclingUpload,
    *,
    fresh_previous_meta: JsonObject,
) -> PreparedDoclingUpload: ...

def build_prepared_filing_skip_result(
    prepared: PreparedDoclingUpload,
) -> UploadOperationResult: ...
```

- S1不得改变filing pre-prepare identical check的现有终态；其helper在未接线状态下不能改变任何workflow observable。S2在typed disposition、shared publication route与三条workflow同一slice内，才把filing identical从preparation early skip切换为继续conversion；`prepare_upload()` 仍只对material保留原early skip。继续conversion用于形成同时携带typed disposition与当前derived bytes/hash/size/content-type的candidate publication target，这是strict publication identity equality与stable retransmission preservation的必要输入，不是重复读published state。
- `describe...`只接受 filing `_PreparedAssetMutation`；delete/material/result输入fail fast。
- 它从已完成fingerprint/conversion的typed plan产生与storage相同的identity：roles从`primary_document`对应docling asset的`derived_from`确定，primary命中original storage `name`，companions为其它original storage `name`，`assets` 与 companions 均按storage `name`字典序排序，assets使用name/original_filename/derived_from/hash/size/content-type/source。
- source requirement从prepared target/form/meta中严格读取；禁止忽略字段、默认值、raw path或二次读取input files。
- `read_prepared_filing_initial_skip_disposition()` 只返回candidate上已生产的closed enum，拒绝material/delete/result；它不再调 `_can_skip_upload`。
- 将当前不依赖 `self` 的实例方法 `_build_upsert_meta()` 提升/重构为 `docling_upload_service.py` 模块级私有helper，签名保持显式接收 `previous_meta`、`source_fingerprint`、`document_version`、`base_meta`。该helper是九字段staging meta的唯一构造owner：现有prepare call path与 `rebase_prepared_filing_create_overwrite()` 必须共同调用它，禁止复制或局部拼装 `updated_at/first_ingested_at/created_at/document_version/source_fingerprint/ingest_complete/source_provider/is_deleted/deleted_at`。
- `rebase_prepared_filing_create_overwrite()` 只允许initial `MISSING`、raw/resolved explicit `create`、`overwrite=True`、fresh validator仍合法且fresh target `COMPLETE` 的分支。它以fresh source meta为 `previous_meta`真源，复用prepared bytes/fingerprint；用 `_resolve_document_version(fresh_previous_meta, prepared_source_fingerprint)` 重算version，再调用唯一 `_build_upsert_meta()` 重建staging meta，返回保留原disposition的严格filing candidate，使既有replace-existing publish路径完整执行。不重做conversion、不改raw/resolved action、不对其它changed branch开放。这是保留create-overwrite既有语义的owner内fresh rebase，不是retry或兼容shim。
- rebase后 `first_ingested_at` 与 `created_at` 必须精确保持fresh previous meta；同fingerprint保持fresh `document_version`，异fingerprint在fresh version上递增。staging meta不携带revision真源；真正publish时storage source-document owner必须覆盖写入新revision，测试必须同时断言该职责分离。
- `build...`复用prepared originals的authoritative selection顺序与canonical public basename产生`file_skipped`事件，返回`status="skipped"`、`stored_file_count=0`、同document/internal id、`skip_reason="already_uploaded"`；终态只携带canonical `file_skipped` events，不投影prepared期间内存的`conversion_started`，不误报`file_uploaded`/processed/stored，不携带path或假装写入。

### 6.4 Typed conflict failure

`dayu/fins/upload_failure.py` 增加：

```python
FinsUploadFailureCode.SOURCE_PUBLICATION_CONFLICT = "source_publication_conflict"

def fins_upload_source_publication_conflict_failure() -> FinsUploadFailureReason: ...
```

- kind固定`STORAGE`。
- message固定为“目标 filing 在上传准备期间已由另一请求发布，本次上传未提交”。
- retry hint固定为“请基于最新目标状态重新发起上传”。
- `file_label=None`；不含path、ticker、document id、revision、fingerprint、异常类型或repr。
- 不复用`SOURCE_REVISION_STALE`：后者唯一表达authorized repair expected revision失效；本work unit表达一般prepared publication竞争，避免owner语义漂移。

batch-time publication owner 必须按下表做封闭映射，实现者不得按exception message、路径或市场route重新分类：

| 发生边界 / typed 输入 | 唯一对外 failure/result | action 投影真源 | lifecycle |
| --- | --- | --- | --- |
| batch fresh validator 产生的state-dependent `FinsUploadUsageError`：`CREATE_TARGET_EXISTS`、`UPDATE_TARGET_MISSING`、`EXISTING_SOURCE_REPAIR_REQUIRES_AUTO`、`COMPANY_NAME_REQUIRED` | 新 `SOURCE_PUBLICATION_CONFLICT` | failed terminal 的 `requested_action` 始终取raw request；`resolved_action` / `filing_action` 取initial prepared action。因此显式create恒为`create/create`，绝不改写为auto/update/skip | 先形成closed conflict裁决，完成第二取消checkpoint；未取消才以conflict为primary rollback并抛`FinsUploadFailureError` |
| batch fresh validator 产生其它非state-dependent usage/format code | initial validated raw request与completed preparation的internal invariant breach；不映射为conflict，由既有generic owner投影`UNEXPECTED_RUNTIME` | initial prepared action | rollback后原样抛出；测试必须证明正常路径不会产生该类code |
| fresh target `UNSAFE` / `FinsUploadPrevalidationError` | 保留既有 `SOURCE_INTEGRITY_UNSAFE` reason，不改为conflict | initial prepared action | 以unsafe reason为primary rollback后抛typed failure |
| batch acquire/read 的 `OSError` / `RuntimeFileLockError` | 既有path-free prevalidation `STORAGE_IO` I/O reason | initial prepared action | 已有token则rollback；`begin_batch` 未返回token则无rollback |
| company descriptor/meta/identity、source projection 或published-state contract corruption（`CompanyTickerIdentityCorruptionError` / 可归属的`ValueError`） | 既有path-free prevalidation `STORAGE_IO` corruption reason | initial prepared action | 以corruption reason为primary rollback后抛typed failure |
| authorized repair 在publish reset时发现expected revision失效 | 保留既有 `SOURCE_REVISION_STALE` | initial prepared action（为`update`） | 复用`commit_prepared_upload_batch()`/rollback primary-error contract |
| authorized repair 在publish reset时被其它source阻断 | 保留既有 `SOURCE_REPAIR_BLOCKED` | initial prepared action（为`update`） | 复用existing rollback primary-error contract |
| `begin_batch()` 成功取得token后、任何fresh read/arbitration前观察到cancel | `UploadOperationResult(status="cancelled")` | 不投影publish/skip/conflict action；由现有cancelled terminal owner消费 | 先rollback；rollback成功才返回cancelled，rollback失败则是path-free `STORAGE_IO`；fresh read/arbitration/mutation均为0 |
| arbitration完成后、任何company/source mutation或`SKIP`/`CONFLICT` terminal前观察到cancel | `UploadOperationResult(status="cancelled")` | 不投影已计算的publish/skip/conflict action；由现有cancelled terminal owner消费 | 先rollback；rollback成功才返回cancelled，rollback失败则是path-free `STORAGE_IO`；company/source mutation、commit、skip/conflict terminal均为0 |
| canonical `SKIP` 的rollback失败 | 既有path-free `STORAGE_IO` | initial prepared action | 不构造skip result |
| 其它programming invariant（`TypeError`/`AssertionError`/不可归属`RuntimeError`） | 既有 `UNEXPECTED_RUNTIME` | initial prepared action | 有open token先rollback；不伪装conflict/skip |

batch-time 重用同一validator时，publication owner 只承诺将上表四个published-state/company-state usage code改写为conflict。其它usage code已由同一raw request的initial validation与completed preparation固定；不得将它们宽泛地隐藏为concurrency。

### 6.5 Arbitration helper 与 S2 shared filing publication owner

S1新增 `dayu/fins/pipelines/filing_upload_publication.py`，但只放置无I/O、无batch lifecycle、无workflow接线的closed arbitration type/helper。它消费typed initial/fresh observation、fresh validated request、prepared/durable identity与company decision，按§7.2-§7.4返回 `PUBLISH/SKIP/CONFLICT` 或既有typed failure；S1不得调用 `begin_batch()`、stage、commit、rollback，也不得改变现有filing route行为。

S2在同一模块把该arbitration helper接入shared publication route；这一接线与filing identical继续conversion、typed disposition接线、SEC/CN/HK workflow改造属于同一个不可拆分的行为slice：

```python
@dataclass(frozen=True, slots=True)
class FilingUploadPublicationOutcome:
    authoritative_request: ValidatedFinsUploadFilingRequest
    result: UploadOperationResult

def execute_prepared_filing_publication(
    *,
    request: ValidatedFinsUploadFilingRequest,
    prepared: PreparedDoclingUpload,
    filing_state_repository: FilingUploadStateRepositoryProtocol,
    company_repository: CompanyMetaRepositoryProtocol,
    batching_repository: BatchingRepositoryProtocol,
    upload_service: DoclingUploadService,
    cancellation: CancellationToken | None,
) -> FilingUploadPublicationOutcome: ...
```

`execute_prepared_filing_publication()` 只在S2新增/完成，是 begin/recheck/arbitrate/stage/publish/rollback 的唯一 shared owner；不接callback/factory/profile/query，不构造market event，不读取路径。S1之后若该route已可被workflow调用、现有filing early-skip已消失或任何SEC/CN/HK结果改变，均视为slice越界与S1失败。

## 7. 状态机、数据流与线性化点

### 7.1 固定执行顺序

以下是**S2原子接线完成后**的固定执行顺序。S1不得部分启用其中任一步骤；S1仍保持现有filing identical在`prepare_upload()` early skip、现有workflow begin/stage/commit路径及全部SEC/CN/HK observable。

1. SEC/CN/HK保留现有pre-prepare fresh validation和Docling preparation，避免在writer内做文件I/O或转换。S2使filing preparation在现有 `_can_skip_upload` 判定点生成closed `initial_skip_disposition`；identical fingerprint也完成conversion并形成prepared candidate；material early skip/cancel完全不变。
2. S2接线后filing preparation只有cancelled result可在batch前终结；既有filing sequential identical skip改为由batch owner在stable view上保留，而不是删除该语义。所有prepared filing candidate（包括 `IDENTICAL_PUBLICATION`）都进入同一publication owner。
3. 对prepared filing mutation调用`begin_batch(canonical_ticker)`；该调用等待同ticker前writer终态、取得writer、从最新published tree构造staging。
4. `begin_batch()`一旦成功返回token，立即执行第一取消checkpoint，必须早于任何fresh read/arbitration。命中时先rollback；成功返回cancelled，失败投影path-free `STORAGE_IO`。
5. 未取消才调用`read_filing_upload_state_in_batch(batch, document_id)`，再用原始不可变`request.request`调用同一个`validate_fins_upload_filing_request()`。此前不stage company，不reset/store/create source。
6. fresh read/validator 按§6.4形成typed operational failure或closed conflict候选；validator成功后按固定优先级裁决：`UNSAFE/failure` -> §7.3 stable retransmission preservation `SKIP` -> §7.3 `MISSING -> COMPLETE` exact-auto convergence `SKIP` -> stable observation `PUBLISH` -> explicit create-overwrite changed branch owner内fresh rebase后`PUBLISH` -> initial authorized repair observation漂移则`SOURCE_REVISION_STALE` -> 其它`SOURCE_PUBLICATION_CONFLICT`。
7. arbitration一经得出closed `PUBLISH`/`SKIP`/`CONFLICT`，立即执行第二取消checkpoint，必须早于任何company/source mutation与SKIP/CONFLICT terminal。命中时丢弃原裁决、先rollback；成功返回cancelled，失败投影path-free `STORAGE_IO`。
8. `PUBLISH`：未取消才使用batch fresh validator产生的`company_meta_decision` stage company，再调用现有`commit_prepared_upload_batch()`。stable branch直接复用prepared plan；`MISSING -> COMPLETE` explicit create-overwrite branch先经Docling owner helper以fresh previous meta重绑，再走既有replace-existing path。一旦进入existing commit ownership，保持现有store-time cancellation与late-cancel/commit boundary，不新增第三套语义。
9. `SKIP`：第二checkpoint未取消时先rollback，rollback成功后才构造prepared skip result；不调用commit，rollback失败是storage failure，不报skip。
10. `CONFLICT`：第二checkpoint未取消时才以typed conflict为primary执行rollback，随后由现有workflow typed handler形成failed terminal。因此等待writer期间取消的explicit create loser不得投影conflict。
11. publish/skip outcome携带batch fresh authoritative request；workflow completed terminal的`resolved_action/filing_action`使用它。failed terminal无outcome时使用initial prepared action；`requested_action`始终来自raw request。显式`create`绝不改写。

### 7.2 “source observation未变”精确定义

- initial/fresh都为`MISSING` -> stable，可`PUBLISH`；initial/fresh resolved action均必须为`create`。
- initial/fresh均为`COMPLETE`或均为`REPAIR_REQUIRED`，且target identity相同、现有`has_same_source_publication_identity()`为真 -> stable，可`PUBLISH`；resolved action必须与initial prepared action一致，repair disposition必须同类且（repair时）expected integrity同源。
- `MISSING -> COMPLETE` 不stable。只有两个封闭例外：§7.3 concurrent exact-auto predicate成立时`SKIP`；或raw explicit `create` + `overwrite=True`且fresh validator/action contract仍合法时经Docling owner fresh rebase后`PUBLISH`。前者prepared=`create`/fresh=`update`，后者两者仍为`create`；都不触发stable action invariant。
- initial authorized `REPAIR_REQUIRED` 的revision/status变化固定为`SOURCE_REVISION_STALE`；changed observation 不具备§7.3任一skip权限，不改为一般conflict。
- 其它status变化、revision变化、`MISSING`/present切换，若未命中§7.3或上述create-overwrite例外，固定为`SOURCE_PUBLICATION_CONFLICT`。任一fresh `UNSAFE`已按§6.4固定为`SOURCE_INTEGRITY_UNSAFE`。
- stable分支中的resolved action/repair invariant不一致是internal invariant failure，不降级为publish、skip或conflict。不得把此规则误用到上述`MISSING -> COMPLETE` exact-auto专用分支。
- company meta允许在source observation stable时变化：publish必须使用fresh company decision，commit-time现有company merge/identity guard继续最终裁决。这是same ticker different filing保留并集所需语义。

### 7.3 Canonical skip 的两个封闭predicate

两个predicate共用以下必要条件：

1. fresh validator/action contract成功，target `SourceIntegrityStatus.COMPLETE`，source meta精确`is_deleted=False`。
2. fresh `company_meta_decision.disposition == "keep"`且intent为`None`；即本请求要求的canonical ticker identity、aliases与resolver freshness已durable满足。
3. `fresh.published_state.publication_identity`非空，且`describe_prepared_filing_publication(prepared) == fresh publication_identity` exact dataclass equality；因此完整fingerprint、primary/companions、全部original/derived assets、primary pointer、source business fields、document version同时等价。
4. prepared target canonical ticker/document/internal identity与batch fresh validated request一致。

**A. stable retransmission preservation** 还必须全部满足：

- initial 与batch source observation 按§7.2为stable，且initial/fresh resolved action、repair contract合法一致。
- `read_prepared_filing_initial_skip_disposition(prepared) is FilingInitialSkipDisposition.IDENTICAL_PUBLICATION`。
- 该分支不限raw action为`auto`；它精确保留现有 `_can_skip_upload` 能够判定的sequential identical skip，特别包含explicit `update` + `overwrite=False`。由于 `_can_skip_upload` 对`overwrite=True`、missing target、deleted source、unsafe fingerprint或repair固定不可skip，这些情形的typed disposition为`NOT_ELIGIBLE`，不会被本predicate改写。
- 该分支的语义名称固定为 **stable retransmission preservation**，不得在代码、README、测试或artifact中称为concurrency convergence。

**B. changed concurrency convergence** 还必须全部满足：

- initial/fresh精确为`MISSING -> COMPLETE`。
- raw `requested_action == "auto"`且`overwrite is False`；prepared=`create`/fresh=`update`是该分支的合法专用例外。
- 该分支不要求initial disposition为`IDENTICAL_PUBLICATION`；initial missing时它应为`NOT_ELIGIBLE`。skip权限完全来自fresh complete、raw auto/no-overwrite、prepared/durable exact equality与company keep的联合事实。

只有predicate A或B之一成立才`SKIP`。changed `COMPLETE -> COMPLETE` 即使prepared/durable exact equal也不是B；显式 `update` changed 也不是B，固定typed conflict。任何缺失/不等价都不是“差不多相同”：若observation stable则按fresh decision正常`PUBLISH`；若为封闭create-overwrite changed例外则fresh rebase后`PUBLISH`；其它changed observation按§7.2映射为`SOURCE_REVISION_STALE`或`SOURCE_PUBLICATION_CONFLICT`。不重试、不重新convert、不将explicit action转成auto/update、不部分stage company。

### 7.4 封闭裁决表

| initial state | fresh state | 附加条件 | 固定裁决 |
| --- | --- | --- | --- |
| `MISSING` | `MISSING` | fresh validator成功，prepared/fresh均`create` | `PUBLISH` |
| `MISSING` | `COMPLETE` | raw exact `auto`、`overwrite=False`、publication identity exact equal、fresh company `keep` | `SKIP`；prepared=`create`/fresh=`update`合法 |
| `MISSING` | `COMPLETE` | raw explicit `create`、`overwrite=True`、fresh validator/action contract合法 | Docling owner按fresh previous meta rebase后`PUBLISH`；prepared/fresh均保持`create` |
| `MISSING` | `COMPLETE` | 其它情况，含explicit `create` + `overwrite=False`、`auto` + `overwrite=True`或identity/company不等价 | `SOURCE_PUBLICATION_CONFLICT`；explicit create failed terminal保持`create/create` |
| `MISSING` | `REPAIR_REQUIRED` | 任意 | `SOURCE_PUBLICATION_CONFLICT` |
| `COMPLETE` | `COMPLETE` | observation stable且§7.3.A stable retransmission predicate成立 | `SKIP`；包含explicit `update` identical sequential重传 |
| `COMPLETE` | `COMPLETE` | observation stable且§7.3.A不成立 | `PUBLISH`，使用fresh action/company decision |
| `COMPLETE` | `COMPLETE` | observation changed | `SOURCE_PUBLICATION_CONFLICT`；即使identity exact equal也不得冒充stable重传或MISSING收敛 |
| `COMPLETE` | `MISSING` 或 `REPAIR_REQUIRED` | 任意 | `SOURCE_PUBLICATION_CONFLICT` |
| `REPAIR_REQUIRED` | `REPAIR_REQUIRED` | expected observation/revision stable | `PUBLISH`，保持existing repair authorization |
| `REPAIR_REQUIRED` | `MISSING`/`COMPLETE`/`REPAIR_REQUIRED` | observation changed | `SOURCE_REVISION_STALE` |
| 任意prepared state | `UNSAFE` | 任意 | `SOURCE_INTEGRITY_UNSAFE` |
| initial `UNSAFE` | 任意 | pre-prepare validator已阻断，不存在prepared candidate | 不进入publication owner |

company-only变化不改变source observation分类；`keep`是skip硬条件，`stage`在stable publish分支合法并必须使用fresh decision。

### 7.5 线性化点

- 同ticker contender的全序由`begin_batch()`成功取得per-ticker writer确定。
- token取得后的第一取消checkpoint早于fresh read/arbitration；第二取消checkpoint晚于closed arbitration、早于任何company/source mutation或`SKIP`/`CONFLICT` terminal。任一取消命中均以rollback消费token，因而没有业务线性化点。
- `PUBLISH`的durable线性化点保持现有`_PHASE_COMMITTED` journal写入；publication guard内的old/new swap不变。
- `SKIP/CONFLICT`没有durable write，其业务线性化点是writer-held fresh view上完成closed arbitration的瞬间；writer直到rollback消费token后才释放，因此其它同ticker writer不能插入该decision与terminal cleanup之间。
- 不同ticker使用不同writer/publication keys，不形成全局顺序。

## 8. Affected files/modules

### 8.1 计划修改的生产文件

| 文件 | 精确职责 |
| --- | --- |
| `dayu/fins/storage/repository_protocols.py` | publication identity/asset typed contract、state字段、batch read protocol |
| `dayu/fins/storage/_fs_company_meta_core.py` | 新增strict ticker-dir company-meta core helper；published/staging共用唯一parser owner |
| `dayu/fins/storage/_fs_filing_upload_state_core.py` | published/staging共用typed state projection；从同一次inspector生成identity |
| `dayu/fins/storage/_fs_source_integrity.py` | durable asset descriptor/publication identity投影并消费contract-owned asset-source constants |
| `dayu/fins/storage/fs_filing_upload_state_repository.py` | 窄wrapper显式转发batch read（有效语义为protocol implementation，不是compat facade） |
| `dayu/fins/storage/__init__.py` | 导出新的storage public contract类型 |
| `dayu/fins/pipelines/docling_upload_service.py` | S1新增filing prepared subtype/closed disposition与prepared identity/rebase/skip helpers，并把九字段meta构造提升为模块级唯一owner，现有prepare行为不变；S2才接线typed disposition与filing identical继续conversion；material始终不改 |
| `dayu/fins/pipelines/filing_upload_publication.py` | S1新增无I/O closed arbitration helper；S2才接入batch lifecycle形成shared publication route |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 仅S2：SEC机械调用shared owner并用fresh outcome做terminal projection |
| `dayu/fins/pipelines/cn_pipeline.py` | 仅S2：CN/HK机械调用同一shared owner并用fresh outcome做terminal projection |
| `dayu/fins/upload_failure.py` | closed conflict code/reason与JSON roundtrip分组 |

`dayu/fins/pipelines/_filing_upload_fresh_validation.py`不需要改：它继续唯一拥有pre-prepare published fresh read及其operational projection；batch-time owner直接复用validator并处理batch lifecycle，避免把两种lock lifetime混入同一helper。

### 8.2 计划修改/新增的测试与文档

| 文件 | 精确职责 |
| --- | --- |
| `tests/fins/test_filing_upload_publication.py`（新增） | S1覆盖纯arbitration/identity owner contract；S2覆盖shared route lifecycle、skip/conflict/rollback与different ticker并行 |
| `tests/fins/test_fins_storage_atomicity.py` | real FS batch-view freshness、capability、published tree zero-mutation、strict staging company read与existing lock invariants |
| `tests/fins/test_docling_upload_service.py` | S1覆盖未接线helpers、唯一meta owner、rebase字段/version/revision职责与现有early-skip/material回归；S2覆盖typed disposition真实接线、继续conversion与skip result |
| `tests/fins/test_upload_failure.py` | 新code exact JSON、kind、bounded/path-free与未知值拒绝 |
| `tests/fins/test_sec_pipeline_upload_filing_stream.py` | SEC 线程+跨进程same-request winner/loser、explicit create/non-equivalent conflict、same-ticker union |
| `tests/fins/test_cn_pipeline.py` | CN/HK shared wiring各一条same-request success/skip，并保持route身份 |
| `tests/fins/test_fins_ingestion_runtime.py` | S1机械补required `publication_identity=None`，并同步 `_FixedFilingUploadStateRepository` / `_ForbiddenFilingUploadStateRepository` 的新 required batch-read protocol method、独立调用记录、去除 fake 注入 cast 与精确零行为断言；S2才允许增加terminal summary断言 |
| `tests/fins/test_fins_ingestion_tools.py` | S1仅同步 tool static-admission `_ForbiddenFilingUploadStateRepository` 的 required batch-read method、独立调用记录与现有 cases 的精确零行为断言；不得改 tool schema、其它 fixture 或断言语义 |
| `tests/fins/test_fins_service_runtime.py` | 仅机械补required `publication_identity=None`，不改断言语义 |
| `tests/cli/test_fins_commands.py` | 仅机械补required `publication_identity=None`，不改断言语义 |
| `tests/service/test_fins_direct.py` | 仅机械补required `publication_identity=None`，不改断言语义 |
| `dayu/fins/README.md` | 落地后记录稳定batch recheck/canonical skip/conflict边界 |
| `tests/README.md` | 落地后记录focused命令与并发owner矩阵 |

明确不修改：`README.md`、`dayu/README.md`、`dayu/host/**`、`dayu/engine/**`、`dayu/service/**`、`dayu/cli/**`、material-specific workflow/tests、oracle/scenario/registry/evidence。上表 `tests/cli/**` 与 `tests/service/**` 仅是required contract fixture机械更新，不授权任何CLI/Service生产变更。

## 9. Implementation decisions

1. 不延长publication guard覆盖Docling；长I/O仍在batch前。batch fresh view稳定性来自现有per-ticker writer，physical swap仍只短持publication guard。
2. 不在`begin_batch()`返回新复合对象，也不把filing语义塞进generic batching protocol；filing state repository显式接收`BatchToken`读取该batch view，符合仓储职责拆分。
3. 不让workflow读取`_PreparedAssetMutation`私有字段；Docling owner提供typed descriptor helper。
4. 不比较raw source meta mapping。prepared和durable两端都投影同一个严格`FilingUploadPublicationIdentity`，arbitration只exact equality。
5. 不比较path/URI/etag/last_modified/timestamp/revision token为publication content identity。physical bytes由现有integrity hash验证；业务等价使用canonical SHA-256、size、content type与role fields。
6. 不把company alias merge纳入source identity；fresh company resolver单独证明`keep`。若仍需stage，不能skip。
7. 不复用repair stale code表达一般publication竞争；新增一般conflict code，但initial authorized repair的revision漂移继续且只能使用existing `SOURCE_REVISION_STALE`，repair blocker继续使用`SOURCE_REPAIR_BLOCKED`。
8. 不为一般不同request自动publish stale plan。stable source observation按typed initial disposition保留既有sequential identical skip；changed observation只有`MISSING -> COMPLETE` raw auto/no-overwrite exact equality可收敛skip，另仅显式`create` + `overwrite=True`按fresh previous meta rebase后保留既有publish语义。
9. skip batch必须rollback而非commit原样tree，避免更新时间、journal `COMMITTED`或产生“空发布”版本事实。
10. rollback secondary failure沿现有`rollback_prepared_upload_batch()`保留最早typed conflict为primary；若无primary的skip rollback失败则storage failure terminal，绝不谎报skip。
11. cancellation 有两个强制checkpoint：取得batch token后、fresh read前一次；closed arbitration后、任何mutation或SKIP/CONFLICT terminal前一次。任一命中都rollback-first返回cancelled；进入既有commit ownership后保持现有late-cancel boundary。
12. filing prepared/durable identity共用storage contract-owned asset-source alias/constants；primary、companions、assets的匹配/排序只用storage name，用户basename只用于canonical file event label。
13. S1只落地可独立验证且不改变observable的owner infrastructure：types/protocol、batch fresh reader、pure arbitration helper、Docling helpers与owner tests。S1不得删除或绕过现有filing early-skip，不得让shared route可达，不得改任何SEC/CN/HK workflow；`pytest tests/fins -q`必须全绿。S2把filing identical继续conversion、typed disposition接线、shared publication route、三条workflow及其semantic tests作为同一原子行为slice一次完成，禁止拆出expected-red checkpoint。
14. staging meta不允许出现第二套字段拼装：模块级 `_build_upsert_meta()` 同时服务现有prepare与fresh rebase；version由fresh meta经 `_resolve_document_version()`计算，revision只由storage source-document owner在真正写入时新建。

## 10. Implementation slices 与 goal alignment

只使用两个slice。C-F1冻结的边界不是按文件机械拆分，而是按**observable activation boundary**拆分：S1只提供行为保持的owner contract/infrastructure并证明全量Fins无回归；S2是唯一启用新filing语义的原子slice。不能把S2的filing identical继续conversion、typed disposition接线、shared publication route或workflow tests提前到S1，也不能拆成会产生expected red的中间checkpoint。

| Slice | 可验证增量 | Goal/success映射 |
| --- | --- | --- |
| S1 — behavior-preserving owner contracts | 新types/protocol、writer-owned batch fresh reader、prepared/durable identity、pure arbitration helper、Docling helpers与唯一staging-meta owner均可独立测试；现有filing early-skip和SEC/CN/HK workflow行为完全不变，`tests/fins`全绿 | 为成功信号2/5/7提供owner contract；以成功信号11与既有全量行为零回归作为本slice验收；不声称成功信号1/3/4/6/8/10已实现 |
| S2 — atomic filing activation & terminal closure | 在一个slice内同时完成filing identical继续conversion、typed disposition接线、shared publication route、SEC/CN/HK wiring与workflow tests；端到端证明winner/loser、union、取消和typed terminal | 成功信号1-11；尤其1/3/4/5/6/8/10/11的observable closure |

### 10.1 Slice S1 — behavior-preserving owner contracts

- objective：建立后续原子接线所需的types/protocol、batch fresh reader、pure arbitration helper与Docling helpers，同时严格保持当前所有filing prepare/workflow observable。
- allowed production files：
  - `dayu/fins/storage/repository_protocols.py`
  - `dayu/fins/storage/_fs_company_meta_core.py`
  - `dayu/fins/storage/_fs_filing_upload_state_core.py`
  - `dayu/fins/storage/_fs_source_integrity.py`
  - `dayu/fins/storage/fs_filing_upload_state_repository.py`
  - `dayu/fins/storage/__init__.py`
  - `dayu/fins/pipelines/docling_upload_service.py`
  - `dayu/fins/pipelines/filing_upload_publication.py`
  - `dayu/fins/upload_failure.py`
- allowed tests：
  - `tests/fins/test_filing_upload_publication.py`
  - `tests/fins/test_fins_storage_atomicity.py`
  - `tests/fins/test_docling_upload_service.py`
  - `tests/fins/test_upload_failure.py`
  - `tests/fins/test_fins_ingestion_runtime.py`（全部既有direct constructor机械补required `publication_identity=None`；并仅允许两个既有 structural fakes 同步新 required protocol method、独立 `batch_calls`、移除 fake 注入处 cast 及新增精确 conformance/零行为断言）
  - `tests/fins/test_fins_ingestion_tools.py`（仅允许 tool static-admission `_ForbiddenFilingUploadStateRepository` 同步 required batch-read method、独立 `batch_calls` 与现有 static-admission cases 的精确零行为断言）
  - `tests/fins/test_fins_service_runtime.py`（仅机械补`publication_identity=None`）
  - `tests/cli/test_fins_commands.py`（仅机械补`publication_identity=None`）
  - `tests/service/test_fins_direct.py`（仅机械补`publication_identity=None`）
- prerequisites：accepted plan；shared repository set必须用于batch/state/source/blob/company wrappers；基线现有filing early-skip与SEC/CN/HK workflow tests为green contract。
- exact allowed changes：
  1. 新增§6.1 typed identity/state contract、§6.2 batch fresh read protocol及其storage owner实现、§6.4 conflict type/reason。
  2. 在`filing_upload_publication.py`只新增无I/O closed decision type与pure arbitration helper；不得新增或接通`execute_prepared_filing_publication()` batch lifecycle route。
  3. 在`docling_upload_service.py`新增filing prepared subtype/closed disposition与`describe/read/rebase/build-skip`窄helper；将不依赖`self`的 `_build_upsert_meta()` 提升为模块级私有唯一owner，让现有prepare继续调用它。S1不得让`prepare_upload()`产生filing subtype/disposition，不得删除现有filing early-skip或令identical filing继续conversion。
  4. 四个 existing fixture 文件均对全部 `FilingUploadPublishedState(...)` direct constructor 机械补 required `publication_identity=None`；其中仅 `tests/fins/test_fins_ingestion_runtime.py` 还必须同步两个既有 structural fakes：
     - `_FixedFilingUploadStateRepository` 新增独立于现有 `calls` 的 `batch_calls: list[tuple[BatchToken, str]]`；`read_filing_upload_state_in_batch(batch, document_id)` 使用 required protocol 精确签名，记录 `(batch, document_id)` 后返回初始化时传入的固定 `state`。
     - `_ForbiddenFilingUploadStateRepository` 同样新增独立 `batch_calls`；同签名方法先记录 `(batch, document_id)`，再明确抛出 `AssertionError`，固定 static admission 阶段禁止任何 filing state read（包括 batch state read）。
     - `_build_static_admission_guarded_runtime()` 的 fake 注入必须移除 `cast(FilingUploadStateRepositoryProtocol, ...)`，与 `_build_fixed_state_guarded_runtime()` 一样直接传入 structural fake，让 pyright 对两个 fake 真实执行 protocol conformance；不得新增替代 cast、default、optional method、`hasattr/getattr`、兼容 wrapper 或 runtime fallback。
     - 除上述 protocol-conformance 与精确调用边界断言外，不得改变两个 fake、既有 assertion 或 runtime prevalidation 业务语义；其余三个 fixture 文件仍只允许 required-field 机械变更。
  5. `tests/fins/test_fins_ingestion_tools.py` 只允许对既有 `_ForbiddenFilingUploadStateRepository` 做以下同型 protocol-conformance 修订：新增独立于现有 `calls` 的 `batch_calls: list[tuple[BatchToken, str]]`；`read_filing_upload_state_in_batch(batch, document_id)` 使用 required protocol 精确签名，先记录 `(batch, document_id)`，再明确抛出 `AssertionError`，固定 tool static admission 阶段禁止任何 filing state read。现有 static-admission cases 必须在 `calls == []` 旁精确断言 `batch_calls == []`；不得修改其它 fake、fixture、tool schema、既有 assertion 或业务语义，不得新增 cast、default、optional method、`hasattr/getattr`、兼容 wrapper 或 runtime fallback。
  6. 不得编辑SEC/CN/HK workflow、workflow tests或README；不得改变任何现有SEC/CN/HK/material terminal、event、stored count、conversion count、begin/commit/rollback行为。
- call/data path：S1 production的现有filing call path保持原样。新增batch reader与pure arbitration只由owner tests直接调用；新增Docling helpers通过typed test candidates验证，尚未成为workflow可达路径。
- invariants：现有 `prepare_upload()` filing identical仍early `skipped`且不继续conversion；现有SEC/CN/HK workflow byte-for-byte沿原begin/stage/commit路径；没有shared publication route activation；新增reader/helper无mutation、无global lock、无path/raw-meta leakage。
- non-goals：不接typed disposition、不改变filing identical preparation、不执行begin/recheck/stage/publish/rollback shared lifecycle、不做market event/runtime/direct integration、不改README。
- exact tests/assertions：
  1. published read与batch read对同一complete source产生exact相同identity；winner commit后第二batch读到winner，source/company来自同一staging view；spy证明batch read只调用`_read_company_meta_from_ticker_dir_unguarded(..., state.staging_ticker_dir)`，不调published locator且不重复parse。
  2. foreign core、wrong ticker、closed token、malformed document id fail fast且不mutation。
  3. prepared identity helper对单文件、多文件primary/companions、all original/derived metadata稳定；primary的`derived_from`精确命中original storage `name`，assets/companions两端按storage name排序且共用contract asset-source constants；primary flip、companion hash、derived bytes/content type任一变化不相等；不含绝对路径。
  4. pure arbitration helper对`MISSING -> MISSING`、stable/changed `COMPLETE`、repair、exact auto、explicit create/update、company keep/stage与identity mismatch返回§7.4唯一closed decision；测试不执行batch lifecycle或workflow terminal。
  5. `describe/read/rebase/build-skip` helper拒绝material/delete/result；material API与现有material prepare/skip/publication结果不变。
  6. 模块级 `_build_upsert_meta()` 是九字段唯一构造owner；现有prepare与rebase helper都调用它，无复制字段拼装。rebase candidate的`previous_meta`取fresh meta，`first_ingested_at/created_at`精确保持fresh值；same fingerprint保持fresh `document_version`，different fingerprint从fresh version递增。
  7. rebase helper的staging meta不自产revision；owner-level real storage publish断言storage source-document owner写入新revision，且新revision不同于fresh previous revision。该断言与version/meta断言分开，禁止把revision写入Docling meta owner。
  8. failure enum kind/code/to_json/from_json exact且240字符/path-free validator通过；未知code拒绝。
  9. repo中全部既有 `FilingUploadPublishedState(...)` direct constructor都显式提供 `publication_identity`；除 `tests/fins/test_fins_ingestion_runtime.py` 的两个 structural fake conformance 修订外，四个 fixture 文件的 diff 只有机械 `None` 参数。
  10. 为两个 fake 新增 exact contract signal：以 `BatchToken(transaction_id="fixture-batch", ticker="AAPL")` 直接调用 `_Fixed...read_filing_upload_state_in_batch()` 时，返回对象必须与固定 `state` 为同一对象，`batch_calls` 精确为 `[(batch, document_id)]` 且既有 `calls` 不变；直接调用 `_Forbidden...` 同方法时必须记录同一 tuple 后抛出明确 `AssertionError`，且既有 `calls` 不变。两个 runtime builder 的 protocol 参数均直接接收 fake、没有 cast，使 focused/full pyright 同时验证两个 fake 真实 conform。
  11. 现有 static admission tests 在断言 `state_repository.calls == []` 的同时精确断言 `batch_calls == []`；现有 runtime unsafe prevalidation 继续只产生两个 published-state `calls`，并精确断言 `batch_calls == []`。executor、runner、observation、job/workspace 零副作用断言保持不变，证明新增 required method 没有改变 static admission/runtime prevalidation 语义。
  12. 现有filing identical prepare测试继续断言early `skipped`、converter未执行；现有SEC/CN/HK workflow断言不修改且全量`tests/fins`全绿。S1禁止新增或修改任何断言来接受未来S2行为。
  13. tool static-admission fake 新增 exact contract signal：以显式 `BatchToken(transaction_id="fixture-batch", ticker="AAPL")` 直接调用其 `read_filing_upload_state_in_batch()` 时，必须先记录同一 `(batch, document_id)` 再抛出明确 `AssertionError`，且既有 `calls` 不变；仅在现有 filing static-admission cases 已有 `state_repository.calls == []` 的位置紧邻增加 `batch_calls == []`，使用同一 builder 但丢弃仓储且无既有 calls 断言的 material ticker-identity case不动。full pyright 必须直接验证该 fake conform，不得增加 cast。
- validation commands：
  - `source .venv/bin/activate && pytest tests/fins/test_filing_upload_publication.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py -q`
  - `source .venv/bin/activate && pytest tests/fins -q`
  - `source .venv/bin/activate && pytest tests/fins/test_filing_upload_publication.py tests/fins/test_docling_upload_service.py --cov=dayu.fins.pipelines.filing_upload_publication --cov=dayu.fins.pipelines.docling_upload_service --cov=dayu.fins.storage._fs_filing_upload_state_core --cov=dayu.fins.upload_failure --cov-report=term-missing --cov-fail-under=80 -q`
  - `source .venv/bin/activate && python -m pyright tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py`（exact structural signal：runtime 两个 builder 均无 cast，三个 fake 均不得出现 missing `read_filing_upload_state_in_batch` 或参数/返回值不兼容）
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- expected completion signal：owner tests与现有全量`tests/fins`全部通过，无expected red；目标模块单文件coverage目标>=80%；focused/full pyright均无新增/扩散且三个 fake 真实满足 protocol；`prepare_upload()` filing early-skip及全部SEC/CN/HK workflow行为未变；S2 workflow/semantic test/README files无diff；`test_fins_ingestion_runtime.py`除required-field机械diff外只含首次 amendment 明列的两个 fake conformance/独立调用记录/去 cast/零行为断言，`test_fins_ingestion_tools.py`只含第二次 amendment 明列的单一 fake conformance/独立调用记录/零行为断言。
- stop condition：若S1使任一现有Fins test变红、filing identical继续conversion、shared route可达、workflow observable改变，立即停止并回到plan review，不得声明expected red或提前修改S2文件；若三个静态可验证的 structural fake 不能在无 cast/default/getattr/兼容逃逸下满足 required protocol，或batch staging不能在protocol内形成company/source同版state、identity/meta owner不清，也停止且不得fallback读published/raw meta。`test_fins_service_runtime.py` 的动态 monkeypatch fake 不在本 work unit batch-read call path、无当前失败信号，不触发 S1/S2 scope 扩张；只有未来 work unit 使其 prevalidation 路径消费 batch read 或再次扩展 required protocol 时，才由该 fixture owner 同步 conform。

### 10.2 Slice S2 — atomic filing activation & terminal closure

- objective：在单一原子slice内启用完整新filing行为：filing identical继续conversion、typed disposition真实接线、shared publication route与SEC/CN/HK workflow/terminal/tests同步落地；任何一步都不得单独形成accepted checkpoint。
- allowed production files：
  - `dayu/fins/pipelines/docling_upload_service.py`
  - `dayu/fins/pipelines/filing_upload_publication.py`
  - `dayu/fins/pipelines/sec_upload_workflow.py`
  - `dayu/fins/pipelines/cn_pipeline.py`
- allowed tests/docs：
  - `tests/fins/test_docling_upload_service.py`
  - `tests/fins/test_filing_upload_publication.py`
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py`
  - `tests/fins/test_cn_pipeline.py`
  - `tests/fins/test_fins_ingestion_runtime.py`（在S1 contract fixture diff之上新增conflict/skipped fresh-action terminal断言；不得改production runtime）
  - `dayu/fins/README.md`
  - `tests/README.md`
- prerequisites：S1 implementation/code review/fix/re-review/accepted slice commit完成；S1 focused tests、完整`pytest tests/fins -q`与pyright均green；S1未改变filing early-skip或任何SEC/CN/HK workflow行为，且types/readers/helpers/meta owner contract已被owner tests固定。
- exact allowed changes：
  1. `prepare_upload()`在既有 `_can_skip_upload` 判定点为filing candidate接入required typed disposition；filing identical不再early terminal，继续conversion并形成strict prepared identity；material路径保持不变。
  2. 在`filing_upload_publication.py`把S1 pure arbitration接入`execute_prepared_filing_publication()`的begin/recheck/double-cancel-checkpoint/stage/publish/rollback lifecycle；不得复制裁决。
  3. 两个workflow删除begin/stage/commit的重复filing段并调用shared route；material段保持byte-for-byte；completed result使用outcome authoritative request的resolved action，raw requested action不变；existing typed handler消费conflict。
  4. 同步更新Docling/publication owner tests、SEC/CN/HK workflow tests与runtime terminal断言；不存在“生产接线完成但workflow tests尚未迁移”或反向的中间验收态。
- call path：market fresh/preparation（typed disposition + identical继续conversion） -> shared publication owner -> market file events/result event -> existing runtime typed pipeline/result summary。
- invariants：started event仍表示preparation采用的initial action；completed terminal使用batch authoritative action；failed terminal使用initial prepared action，因此explicit create的requested/resolved/filing均为create且无skip；一个stream唯一terminal；create-overwrite rebase继续复用S1唯一meta owner，storage write产生新revision。
- non-goals：不抽象market event builder、不改Service/CLI/tool、material、runtime状态enum；不把S2拆成expected-red子slice。
- exact concurrency tests（线程case用`ThreadPoolExecutor`/`Event`/`Barrier`，跨进程case用`multiprocessing.get_context("spawn")` + process-safe `Barrier/Queue`；全部禁止sleep、轮询时间窗口或只断言“不挂”）：
  1. SEC real FS exact auto single-file：两个request均在MISSING state prevalidated并在converter/batch barrier前完成prepare；结果multiset精确`{ok, skipped}`，counts为`{1,0}`，converter可执行两次但commit一次。
  2. SEC exact auto multi-file：primary+companions roles相同，winner存全部original且只转换primary；loser skipped events覆盖全部input，published role/assets/manifest与winner snapshot相同。
  3. SEC explicit create + `overwrite=False` same target：one ok/one failed，failure exact `SOURCE_PUBLICATION_CONFLICT`、requested/create保持、stored=0、不是skip或unexpected runtime；同一并发时序下explicit create + `overwrite=True`两个请求均publish ok，后writer走fresh rebase且不投影skip/conflict，并再次端到端断言fresh `first_ingested_at/created_at`保持、同fingerprint version保持/异fingerprint递增、storage owner写入新revision。
  4. SEC auto same target但两个converter产生不同derived bytes，及同source bytes但不同company alias requirement：winner ok，losertyped conflict；tree保持winner，不做第二版本。
  5. SEC same ticker different document IDs：两个ok，最终filing IDs/manifest/assets为exact union，company aliases按现有commit owner stable union，无lost update。
  6. SEC different ticker：两个publication owner可同时越过test barrier并各自ok，证明无global lock。
  7. CN real FS exact auto：one ok/one skipped，stored count/revision/version/tree不变量与SEC一致。
  8. HK route exact auto：one ok/one skipped，并断言HK canonical ticker与CN/HK facade wiring未旁路shared owner；不能只用CN测试替代HK。
  9. SEC 跨进程real FS exact auto single-file：两个spawned processes各自创建repository/workflow，用process-safe barrier确保两者在initial `MISSING`下完成prepare后才竞争同ticker writer；parent从bounded queue收到结果multiset exact `{ok, skipped}`、counts `{1,0}`，最终tree/manifest只有一次publication。该测试证明winner/skip可跨进程确定收敛，不以既有lock-only test代替。
  10. explicit `update` identical stable sequential重传保持skipped，stored=0且revision/version/tree不变；两个concurrent explicit update在source observation changed时后writer为typed conflict，不得按identity近似或action fallback收敛。
  11. typed conflict经pipeline JSON、`FinsUploadPipelineResult`、direct RESULT/durable failure summary保持同code/message；canonical skip被runtime接受为COMPLETED且stored=0；prepared conversion events不出现在skip terminal。
  12. 用writer barrier在等待期间取消原本会走SKIP/CONFLICT/PUBLISH的三类SEC candidate：均cancelled、rollback=1、fresh read与company/source mutation/commit/业务terminal为0；并覆盖第二checkpoint、rollback失败`STORAGE_IO`与进入existing commit ownership后的既有late-cancel边界。
  13. existing `SOURCE_REVISION_STALE`/`SOURCE_REPAIR_BLOCKED`、`SOURCE_INTEGRITY_UNSAFE`、path-free `STORAGE_IO`、cancel-before-commit、commit-after-cancel、company/source rollback、material regression继续通过。
- validation commands：
  - `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_ingestion_runtime.py -q`
  - `source .venv/bin/activate && pytest tests/fins/test_upload_failure.py tests/fins/test_docling_upload_service.py tests/fins/test_fins_storage_atomicity.py -q`
  - `source .venv/bin/activate && pytest tests/fins -q`
  - `source .venv/bin/activate && coverage erase && coverage run -m pytest tests/fins/test_filing_upload_publication.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_upload_failure.py && coverage report -m`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- expected assertions：modified production files的单文件coverage目标>=80%；focused tests与完整Fins suite全部通过，无expected red；pyright 0新增/扩散；README只写已实现事实；`git status`仅含approved S2 files before acceptance commit。
- completion signal：filing identical继续conversion、typed disposition、shared route、SEC/CN/HK workflow及其tests作为同一accepted diff闭环；US/CN/HK矩阵、same/different target、same/different ticker、typed terminal与README全部闭环，Fins suite全绿。
- stop condition：若S2无法在同一implementation/review slice同时完成prepare行为切换、shared route与全部workflow tests，停止并回到plan review，不接受部分接线或expected red；若共享owner无法被某market route直接调用而需要CLI/Service fallback或market-specific duplicate arbitration，同样停止且不新增兼容分支。

## 11. Validation exclusions 与 review focus

明确不运行：UF-PF10、UF-PF12、真实CLI/evidence、oracle/scenario regeneration。不得用真实evidence缺失阻塞deterministic implementation closure。

plan review/code review/deepreview必须重点检查：

- S1是否严格保持existing `prepare_upload()` filing early-skip与全部SEC/CN/HK workflow observable，`pytest tests/fins -q`是否全绿且无expected red；是否偷跑typed disposition接线、identical继续conversion或shared route activation。S2才检查这些行为是否在同一slice原子启用并同步更新workflow tests。
- fresh read是否确实发生在`begin_batch`之后、任一company/source mutation之前；是否误把pre-prepare recheck当closure。
- S2中filing pre-prepare identical是否仍被错误终结为skip；是否确实完成conversion、形成candidate并进入batch fresh arbitration；material是否未变。该要求不得反向用于S1。
- batch view是否由existing writer保证稳定，是否新增global lock、retry、sleep或directory fallback。
- staging company meta是否只由`_fs_company_meta_core.py` ticker-dir helper从`staging_ticker_dir`严格读取，是否偷读published path或在filing core重复parse。
- exact equality是否覆盖完整fingerprint、primary/companions、all assets、source requirements与company keep；是否只比较fingerprint字符串。
- asset source是否共用contract-owned alias/constants；primary是否命中storage name，assets/companions是否两端都按storage name稳定排序。
- typed initial disposition是否由Docling preparation基于现有 `_can_skip_upload` 同源产生且非bool/default；explicit update identical stable是否仍skip，changed explicit update是否typed conflict；explicit create-overwrite是否fresh rebase后publish且never skip。
- `_build_upsert_meta()`是否已成为`docling_upload_service.py`模块级唯一九字段owner，existing prepare与fresh rebase是否共同调用；fresh `first_ingested_at/created_at`、same/different fingerprint version规则是否精确，revision是否仍只由storage source-document owner新写。
- explicit create + `overwrite=False`是否可能进入skip；generic handler是否仍可吞掉competition为`UNEXPECTED_RUNTIME`。
- §6.4映射表是否完整实现；usage conflict、UNSAFE、I/O/corruption、repair revision/blocked是否保持各自唯一code和initial failed-action真源。
- skip是否commit空batch、更新时间/manifest/revision，或产生任何company/source mutation。
- token取得后fresh read前及arbitration后mutation/terminal前是否各观察cancel；等待writer取消的SKIP/CONFLICT/PUBLISH三类候选是否均cancelled且零mutation；prepared conversion event是否被误报为stored/processed；跨进程exact-auto test是否真正产生one winner/one skip。
- same ticker different filing是否使用fresh company decision并保留union。
- different ticker是否仍可并行。
- material、repair、cancel/commit boundary、old/new swap、path-free failure是否保持。
- 是否出现raw meta consumer、`FileExistsError`捕获、字符串匹配、`hasattr/getattr`、default/compat或测试夹具倒逼production fallback。

## 12. README decision

- `dayu/fins/README.md`：必须更新。命中`dayu/fins/`且属于developer stable contract；在现有writer/fresh validation/company-source batch段说明：prepare后在writer-owned batch view二次验证、stable identical sequential skip（含explicit update）、仅`MISSING -> COMPLETE` raw auto/no-overwrite exact convergence skip、changed explicit update与create/no-overwrite typed conflict、create-overwrite publish、双cancel checkpoint、skip零commit/零mutation、same ticker union与different ticker keyed并行。只在代码落地后写当前事实，不写UF-FIX10或文件流水账。
- `tests/README.md`：必须更新。记录新增focused命令和Event/barrier并发矩阵；不写未来计划。
- 根`README.md`：不更新。CLI参数、用户工作流、默认输出、安装/排障均未变化。
- `dayu/README.md`：不更新。UI/Service/Host/Agent分层和装配未变化。
- Host/Engine/Service/config README与`docs/host/design.md`、`docs/engine/design.md`：不更新；只作为对齐依据，职责未改变。

## 13. 风险、open questions 与 residual owners

### 13.1 Open questions

无blocking或non-blocking open question。Controller 接受的open questions已冻结为：

1. `primary_original_asset_name` 与docling `derived_from` 精确命中original asset descriptor的storage `name`，绝不是`original_filename`/用户basename；prepared/durable `assets` 与 companions 均按storage `name`排序。
2. staging company meta 由`_fs_company_meta_core.py::_read_company_meta_from_ticker_dir_unguarded()`唯一读取，传入`state.staging_ticker_dir`；不读published path，不在filing core重复parser。
3. stable retransmission只有typed `IDENTICAL_PUBLICATION` + fresh合法action + company keep + exact identity才能`SKIP`，并保留explicit update既有sequential语义；changed observation只有`MISSING -> COMPLETE` raw auto/no-overwrite exact equality可收敛`SKIP`。
4. `MISSING -> COMPLETE` explicit create + `overwrite=False`固定conflict；explicit create + `overwrite=True`固定由Docling owner按fresh previous meta rebase后`PUBLISH`，不改raw/resolved action。
5. publication owner在取得token后、fresh read前与closed arbitration后、任何mutation/terminal前各观察一次取消；命中则rollback-first cancelled，进入existing commit ownership后保持既有late-cancel边界。

failure code、identity字段、batch API、skip条件、terminal action与slice ownership均已在本plan冻结；实现者不得重新发明。

最终 review 的两个 Controller-accepted blockers 也已冻结并关闭：

6. C-F1：S1只做behavior-preserving owner contract/infrastructure，现有filing early-skip与任何SEC/CN/HK workflow行为都不改变，完整`tests/fins`必须全绿；filing identical继续conversion、typed disposition接线、shared publication route和workflow tests全部归S2同一原子slice，禁止expected red。
7. C-F2：staging meta九字段唯一owner为`docling_upload_service.py`模块级私有 `_build_upsert_meta()`；existing prepare与fresh rebase共同调用；fresh时间字段/version规则及storage owner新revision均有精确断言。

### 13.2 Risks / residual risks

C-R1/C-R2及最终C-F1/C-F2已作为accepted findings在本plan关闭，不再作为residual risk列入下表。DS最终review的R-1与C-F1同源，已由“重划slice且S1全量green”从根因消除，不保留expected-red或未分类residual。

| 风险 | 当前缓解 | 分类 / owner |
| --- | --- | --- |
| S1 structural implementer census 两次漏项：首次漏掉 `test_fins_ingestion_runtime.py` 的两个 fake，第二次 full pyright 又确认漏掉 `test_fins_ingestion_tools.py` 的 tool static-admission fake | 首次 amendment 保持 runtime 两个 fake 的 required method、独立 `batch_calls` 与去 cast；第二次 amendment 仅扩充 tool test 中第三个 fake 的同型 fail-fast method、独立记录及现有 filing cases 零行为断言，并以 focused/full pyright 固定；两路 re-review 均 pass，不得弱化 production protocol或增加兼容逃逸 | `fixed in accepted second amended S1 plan`：S1 implementation owner |
| `test_fins_service_runtime.py` 的 `_UnsafeFilingUploadStateRepository` 经动态 class monkeypatch 注入，静态 census 不可见且只实现 published read | Controller 依据两路 review 裁决：本 work unit 的 S1/S2 batch read route 均不经过该 prevalidation fake，无当前 pyright/runtime failure signal，不纳入 S1/S2；未来若该路径开始消费 batch read或协议再次扩展 required method，再由 fixture owner 同步 conform | `assigned to future triggering work unit`：该 fixture 语义 owner；当前非阻塞 residual |
| concurrent exact `auto` retransmission若initial已为`COMPLETE`，后writer observation changed时即使identity exact equal仍conflict而非skip | §7.3-§7.4明确只有`MISSING -> COMPLETE`可作changed convergence；S2 explicit/auto changed tests与README记录该fail-closed边界 | `fixed in current slice`（S2 route tests/docs）；DS final review R-2 |
| converter非确定性导致相同original产生不同derived；sequential重传可能因strict derived identity不等而publish，concurrent loser则conflict | prepared/durable asset metadata exact equality，不把近似结果误判skip；S1 identity tests、S2 route tests与README记录该tradeoff | `fixed in current slice`（S1 identity + S2 route tests/docs）；DS final review R-3 |
| SHA-256理论碰撞 | 同时比较role、name、size、content-type、source requirements；physical integrity owner重算hash | `assigned to later work unit`：storage integrity policy hardening；非当前goal |
| post-`COMMITTED` publication guard release failure可能让caller看到failure但durable winner已存在 | 保持现有commit truth；后续exact auto可基于fresh complete identity skip | `assigned to later work unit`：existing batch terminal-contract hardening；非当前goal |
| rollback自身失败 | 保持primary/secondary与recovery evidence；不得谎报skip/cancel | `fixed in current slice`（S2 shared-route lifecycle tests） |
| manual filesystem writer绕过repository locks | 本方案只承诺仓储协议内并发；integrity/commit validator继续fail closed | `assigned to later work unit`：storage operational hardening；非当前goal |
| fresh company warning/result表达 | skip要求company `keep`，但不新增warning | `assigned to later work unit`：`UF-FIX11` |
| material same-request concurrency | 本次只冻结filing publication identity/owner | `assigned to later work unit`：若需要则单独确认material work unit；非当前goal |
| oracle/scenario/frozen evidence仍未刷新或未跑UF-PF10/12 | 明确禁止本轮执行/修改 | `assigned to later work unit`：evidence/oracle work unit |

没有未分类residual risk。

## 14. 无过度设计与无 goal drift 说明

- 复用现有per-ticker writer、`BatchToken`、staging clone、source integrity inspector、repair revision、complete-tree validator、publication guard、backup/journal和old/new swap；没有新锁、重试、数据库、global registry或通用OCC。
- 只新增一个filing-specific publication identity、一个batch read方法和一个shared deterministic publication owner，分别对应fresh state、prepared/durable equivalence与market重复状态机三个真实语义；filing prepared subtype/disposition只承载既有skip事实，create-overwrite rebase只补齐fresh previous-meta真源，均不形成新framework/god object/glue facade。
- identity不保存raw bytes/path/URI/volatile timestamps，不扩展durable schema；只投影完成本次exact equality所需事实。
- 不把发现的material、UF-FIX11、manual writer或evidence风险纳入验收；均明确留在原owner，未扩大goal confirmation。
- 两个slice按observable activation boundary而非模块机械拆分：S1固定owner contract并证明零行为回归，S2原子启用全部filing语义与workflow证据；不存在半接线expected-red状态，gate成本与风险相称。
- staging meta只把既有无状态构造逻辑提升为模块级唯一owner，不增加builder/facade或第二套schema；fresh rebase复用同一helper，revision继续由storage owner产生，因此是最小语义收敛而非额外抽象。

## 15. Completion report format

后续每个implementation/fix artifact与最终closeout必须用中文明确报告：

1. 改了哪些owner、contract、state transition和allowed files；逐slice列出实际diff。
2. winner/loser、explicit/non-equivalent、same/different filing、same/different ticker、US/CN/HK的实际测试结果。
3. stored count、revision/version/assets/meta/manifest/tree no-mutation与typed/path-free failure证据。
4. focused tests、Fins suite、逐文件coverage、全仓pyright、`git diff --check`的实际命令与结果。
5. README实际更新与no-change decisions。
6. 明确未运行UF-PF10/UF-PF12、未改material/UF-FIX11/oracle/scenario/frozen evidence、未建通用OCC/global lock。
7. 所有findings状态、remaining risks及owner；若无则写“无未分类residual risk”。
8. 当前Gateflow gate、accepted commit（仅在后续授权gate）与下一入口；不得把plan完成写成implementation完成。
