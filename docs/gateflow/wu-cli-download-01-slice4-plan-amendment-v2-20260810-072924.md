# WU-CLI-DOWNLOAD-01 Slice 4 Plan Amendment v2

## 1. 文档状态与裁决

- Work unit：`WU-CLI-DOWNLOAD-01`
- Slice：Slice 4 — Storage concurrency 与 integrity repair（DL-F08、DL-F10），以及 v1 已接受的 DL-F07/DL-F11 SEC transport/materialization amendment
- Gate：第二次 `plan fix`
- Timestamp：`2026-08-10 07:29:24 +0800`
- Baseline HEAD：`93eb073e597899b3c25234eaf50923ba1d6c0219`
- Base plan：`docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6、Slice 4、§9
- Amendment v1：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`
- 新 stop evidence：`docs/gateflow/wu-cli-download-01-slice4-stop-evidence-20260810-071524.md`
- Artifact path：`docs/gateflow/wu-cli-download-01-slice4-plan-amendment-v2-20260810-072924.md`
- Decision：stop evidence 的动机与严重性成立。strict validator 校验完整 ticker source tree；SEC/CN 在 single-filing Phase A 前提交 company-only batch，且 SEC SC13 selection 还会直接提交 rejected artifact，因此当前顺序无法让真实顶层 pipeline 修复既有 corruption。
- Completion：本文件形成 code-generation-ready 的唯一 v2 amendment；尚未经过原 AgentMiMo/AgentDS 双路 `$planreview` re-review，不授权恢复 implementation。

### 1.1 与 base plan / v1 的叠加与覆盖

本文件不是替代 base plan 或 v1 的独立方案。执行时按以下优先级解释：

1. 本 v2 明确覆盖 v1/base 中与“顶层 workflow mutation 顺序、完整 ticker integrity preflight、SC13 selection side effect、rejection registry publication”冲突的部分。
2. v1 的 storage-neutral SEC prefetch、private discriminated variants、single shared transport core、唯一 materializer、repair unconditional、Phase B identity-first、rejected prefetch-before-batch、200/304/empty/failure/cancel 测试与 static gate全部继续有效。
3. base §5.6 的 per-ticker reservation、blocking cross-process writer、recovery nonblocking try-lock、release/notify、三轮 target identity revalidation、strict validator与atomic swap全部继续有效。
4. 本 v2 不放宽 validator、不引入 operation-wide transaction、不改变 public terminal schema，不重启已删除的 prepared/replay/capability/compat 设计。

## 2. 第一性原理判断与 root cause

任一 ticker batch 都从最新 published ticker tree复制 staging，并在 commit 前调用完整 source-tree validator。故只要 published tree 中存在一个结构合法但物理文件 `REPAIR_REQUIRED` 的 source，任何只改 company、maintenance 或 rejected artifact 的 batch 都会复制该 corruption，并在 repair owner 得到 Phase A/Phase B 机会之前失败。

正确性约束不是“company batch 遇到 validator error 后重试”，而是：

```text
先完成最终 selection 与完整本地 integrity preflight
  -> 若存在唯一且最终 publication-eligible 的 selected filing corruption，先修它
  -> 再次证明整棵本地 source tree 无 REPAIR_REQUIRED
  -> 此后才允许 company / rejection / maintenance batch
```

原因：

- validator 是 source publication 完整性的最后防线，不能弱化为“只校验本轮改动”。
- provider/PDF/Docling I/O 不能在 writer lock 内，因此不能把 repair 塞进 company batch。
- `sec_pipeline.py` / `cn_pipeline.py` 只是 facade/composition owner；在 facade 捕获 commit error、重放 workflow 或复制顺序会形成 glue/fallback。
- multiple、unselected、最终 rejected corruption 没有本 WU 内合法的唯一 repair owner；让它们偶然在后续 validator 才失败会先泄漏 company/rejection side effect，必须在首个 ticker publication 前 typed fail closed。

## 3. SEC/CN ticker mutation 全量 inventory 与 owner

下表以当前 HEAD 的直接 `file:line` 为证据。这里的“mutation”指进入 storage ticker published tree 的 batch mutation；SEC HTTP cache 写入是 transport cache，不是 company/source/rejection durable fact，也不经过 ticker batch，继续由既有 cache owner管理且不作为 repair 绕路。

| 市场/阶段 | 当前 mutation | 直接证据 | 当前发生位置 | 唯一 owner | v2 裁决 |
|---|---|---|---|---|---|
| SEC / company resolve 后、selection 前 | company meta batch | `sec_download_workflow.py:457-469` | single-filing Phase A 前 | `sec_download_workflow.py` | 必须移到完整 preflight 与 repair-first gate 之后 |
| SEC / SC13 direction selection | rejected artifact 文件/meta batch | `sec_sc13_filtering.py:454-494` 调 `_persist_rejected_filing_artifact`；`sec_download_persistence.py:255-321` begin/store/upsert/commit | selection 内，早于顶层 filing loop | direction decision：`sec_sc13_filtering.py`；durable rejected artifact：`sec_download_persistence.py` | filtering 只返回 typed rejection intent；不得持久化或改 registry；顶层 repair gate 后交给 persistence owner |
| SEC / SC13 direction selection | in-memory rejection registry 写入 | `sec_sc13_filtering.py:503-511` | selection 内 | rejection decision：`sec_sc13_filtering.py`；entry construction：既有 `sec_download_state.py::_record_rejection` | selection 只返回 rejection facts；published registry 与 artifact 同一 rejection durable unit提交；artifact失败时保留既有 SC13 “registry-only”语义 |
| SEC / selected 6-K Phase A | rejected artifact 文件/meta batch | `sec_download_filing_workflow.py:341-414`，其中 `382-393` 调 persistence | single-filing Phase A 后、normal source batch 前 | 6-K policy：`sec_download_filing_workflow.py`；durable artifact：`sec_download_persistence.py` | 非 repair target 可在 repair gate 后按既有语义提交；designated repair target若最终被拒绝，typed fail closed且不提交 rejection |
| SEC / selected 6-K Phase A | in-memory rejection registry 写入 | `sec_download_filing_workflow.py:415-423` | rejected artifact成功后 | `sec_download_state.py::_record_rejection` 产生entry；workflow决定何时应用 | 先在副本构造 registry-after，artifact+registry同batch成功后才更新内存真值 |
| SEC / accepted filing Phase B | source blob、source meta/manifest、可能的processed marker | `sec_download_filing_workflow.py:445-617`；`587-613` upsert/processed，`617` commit | single-filing Phase B | `sec_download_filing_workflow.py` + source/blob/processed repositories | 保持 v1三轮 identity-first；repair target stable-partition 到首位 |
| SEC / pipeline 尾部 | rejection registry maintenance batch，即使 registry 未变也提交 | `sec_download_workflow.py:601-612` | 全部 filing 后；取消 break 后仍到达 | `sec_download_workflow.py` 调 `sec_download_state.py::_save_rejection_registry` | 删除无条件尾部 blind batch；每条 rejection 的 registry 变化在其 durable unit内提交，无变化则不写 |
| CN/HK / company resolve 后、candidate discovery 前 | company meta batch | `cn_download_workflow.py:193-205` | selection与single-filing Phase A 前 | `cn_download_workflow.py` | 移到完整 preflight 与 repair-first gate 后 |
| CN/HK / accepted filing Phase B | PDF、Docling JSON、source meta/manifest、processed marker | `cn_download_filing_workflow.py:386-408,487-586` | PDF/Docling锁外完成后 | `cn_download_filing_workflow.py` + repositories | 保持 v1 identity-first，repair target首位；外部I/O继续在begin前 |
| CN/HK / PDF digest reuse Phase B | source metadata/processed batch | `cn_download_filing_workflow.py:240-271,646-680` | PDF下载后 | `cn_download_filing_workflow.py` | 同样受完整 preflight与target identity-first约束 |

storage root cause证据：

- `dayu/fins/storage/_fs_storage_infra.py:568-595`：每次 commit 在 publication guard 前调用 `_validate_complete_source_tree`。
- `dayu/fins/storage/_fs_storage_infra.py:682-710`：validator遍历 filing 与 material 两棵完整 source tree。
- `dayu/fins/storage/_fs_storage_infra.py:943-991`：逐文件 strict检查 physical existence、size与digest。
- `dayu/fins/storage/repository_protocols.py:682-697`、`fs_source_document_repository.py:642-658`、`_fs_source_document_core.py:756-817`：repository 已拥有 public source ID enumeration；v1 classification属于同一个 source owner，足以形成整树 query，不需要新 capability。

### 3.1 `sec_sc13_filtering.py` 必须加入 allowlist的证明

若不修改该 owner，`run_download_stream_impl` 即使移走 company batch，`_filter_filings` 仍会经 `should_keep_sc13_direction` 在完整 preflight 前提交 rejected artifact并修改 registry。顶层 workflow无法在事后撤销已发布事实；在 facade 拦截也无法阻止 owner 内 batch。因此该文件是最小充分新增项，不是可选重构。

`sec_download_state.py` 不加入 allowlist：现有 `_record_rejection` 与 `_save_rejection_registry` 已能构造/写入 typed registry；v2只改变调用时序与batch归属，没有证据要求修改其规则。`sec_pipeline.py`/`cn_pipeline.py` 仅按 base allowlist机械适配 host/typed签名，不拥有新顺序。

## 4. Scope 与 effective allowlist

### 4.1 v2 production allowlist 增量

- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`

### 4.2 v2 test allowlist 增量

- 无。禁止新增测试文件。

### 4.3 effective production allowlist（base + v1 + v2）

- `dayu/fins/storage/source_integrity.py`（new）
- `dayu/fins/storage/__init__.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/downloaders/sec_downloader.py`（v1）
- `dayu/fins/pipelines/sec_download_persistence.py`（v1）
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`（v2）
- `dayu/fins/pipelines/cn_download_workflow.py`（v2）
- `dayu/fins/pipelines/sec_sc13_filtering.py`（v2）

### 4.4 effective test allowlist（base + v1；无新增文件）

- `tests/fins/test_sec_downloader.py`（v1）
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_docling_upload_service.py`

### 4.5 forbidden boundary

- 不修改 README（四 slices 后 documentation closeout再处理）、base plan、v1、任何 evidence/review artifact、Oracle/registry、真实 CLI/provider、Host/Engine、PR190、production timing hook。
- 不修改 `sec_download_state.py`、`sec_download_company_meta.py`、`cn_download_company_meta.py`、`_fs_maintenance_core.py`；现有owner接口足够。
- 不新增 Protocol/capability/factory/compat/glue/fallback、operation-wide transaction、timeout、sleep、spool backend或第二套transport core。
- 任何实现若需要本节之外的新文件，先命中 §12 stop condition，不得顺手扩 scope。

## 5. Typed contract 与 owner boundary

### 5.1 完整 ticker integrity inventory

v1 的单target published/staged classification保留，并在同一个 `SourceDocumentRepositoryProtocol` 增加一个朴素public query：

```python
def list_source_integrity(
    self,
    ticker: str,
) -> tuple[SourceIntegrityClassification, ...]:
    ...
```

契约：

- wrapper/core在一个短 publication guard 内枚举 filing + material 的全部published source ID并逐项调用同一 unguarded classification core；按 `(source_kind.value, document_id)` 排序返回。
- 不返回 path/raw meta/bytes，不做provider I/O，不取得writer，不制造snapshot capability。
- inventory只含实际存在的source目录；目标不存在仍由单target `classify_source_integrity` 返回 `MISSING`。
- identity/meta/manifest结构错误（包括 malformed sha256）立即从storage owner严格抛出；不得包装成repair reason。
- 同一guard消除“先list、后逐项classify”跨publication混合视图；这只是现有source facts的整树查询，不是新repository或兼容能力。

### 5.2 Cross-provider preflight disposition

`dayu/fins/storage/source_integrity.py` 继续是 typed integrity 真源，并增加封闭的跨provider disposition；不用一个含多个 optional 字段的god bag：

```python
@dataclass(frozen=True, slots=True)
class NoSourceRepairRequired:
    kind: Literal["clean"]

@dataclass(frozen=True, slots=True)
class SelectedSourceRepairRequired:
    kind: Literal["repair_selected"]
    target: SourceIntegrityClassification

SourceIntegrityPreflightDisposition: TypeAlias = (
    NoSourceRepairRequired | SelectedSourceRepairRequired
)

class SourceIntegrityPreflightReason(str, Enum):
    MULTIPLE_REPAIR_REQUIRED = "multiple_repair_required"
    UNSELECTED_REPAIR_REQUIRED = "unselected_repair_required"
    SELECTED_REJECTED_REPAIR_REQUIRED = "selected_rejected_repair_required"

class SourceIntegrityPreflightError(RuntimeError):
    reason: SourceIntegrityPreflightReason
```

纯函数接收完整inventory、最终accepted filing IDs与已知rejected filing IDs，按固定优先级裁决：

1. storage结构错误已在构造inventory时直接失败，优先级最高。
2. `REPAIR_REQUIRED` 数量大于1：`MULTIPLE_REPAIR_REQUIRED`，不因其中某个selected而降级。
3. 恰好1个且为material或不在accepted/rejected集合：`UNSELECTED_REPAIR_REQUIRED`。
4. 恰好1个且在rejected集合：`SELECTED_REJECTED_REPAIR_REQUIRED`。
5. 恰好1个且是accepted filing：返回`SelectedSourceRepairRequired`。
6. 零个：返回`NoSourceRepairRequired`。

SEC/CN workflow拥有“哪些ID最终accepted/rejected”的业务事实；`source_integrity.py`只拥有相同输入如何形成封闭preflight disposition的跨provider不变量。两个workflow不得各自从raw meta或validator字符串重算。

### 5.3 SC13 selection typed decision

`sec_sc13_filtering.py` 把当前“bool + durable side effect”拆为typed decision。精确variant至少为：

- `Sc13DirectionAccepted`：只携带accepted filing identity。
- `Sc13DirectionRejectedWithArtifact`：携带filing、archive CIK、remote descriptors、source fingerprint、selected primary、rejection reason/category等构造既有artifact/registry所需且互不矛盾的facts。
- `Sc13DirectionRejectedRegistryOnly`：表达现有“artifact remote listing失败但仍记录direction rejection”语义；只携带registry entry所需facts与safe diagnostic，不伪造remote files。
- `Sc13DirectionRejectedAlreadyRegistered`：表达`overwrite=False`命中既有同version registry的纯skip；它属于最终rejected ID集合，但不产生新artifact/registry mutation。

若一个variant需要互斥optional字段，必须继续拆variant。selection/direction cache缓存typed decision而非`Optional[bool]`；重复筛选同一accession只复用decision，不重复生成intent。`filter_sc13_by_direction`、browse-edgar extension与retry返回accepted filings和按首次发现顺序去重的rejection intents；它们不得：

- 调 `_persist_rejected_filing_artifact`；
- 调 `begin_batch/commit_batch/rollback_batch`；
- 调 `_record_rejection` 或修改caller registry；
- 把batch/repository/callback塞进intent。

SEC HTTP角色解析、remote listing与cache仍由原owner负责，且没有writer/publication guard。

### 5.4 Rejection durable unit

v1 `persist_rejected_filing_artifact` 的“完整prefetch在begin前、真实batch materialize”不变；v2补充同一条rejection的atomic事实边界：

```text
caller以既有_record_rejection在registry副本构造registry_after
  -> persistence完整prefetch（无batch）
  -> cancellation checkpoint
  -> begin_batch
  -> materialize rejected files + upsert rejected meta
  -> save registry_after（同一真实batch）
  -> commit
  -> caller才把in-memory registry替换为registry_after
```

- 6-K artifact/prefetch失败沿用现有语义：filing failure，不增加registry entry。
- SC13 artifact listing/prefetch失败沿用现有语义：以独立registry-only batch提交typed rejection entry；不伪造artifact。registry-only batch也只能发生在repair gate之后。
- artifact成功时artifact+对应registry entry不可分离；任一store/meta/registry/validator/cancel失败都rollback，二者published facts均保持old。
- 删除 `sec_download_workflow.py:601-612` 的无条件尾部registry batch。无新rejection则registry不写；每个已提交rejection已带registry真值。
- 这不是operation-wide transaction：每个filing source与每条rejection仍是独立atomic batch；batch之间不跨provider I/O持锁。

## 6. 单一可执行顺序与状态机

### 6.1 共同不变量

```text
READ_ONLY_DISCOVERY_AND_FINAL_SELECTION
  -> WHOLE_TICKER_INTEGRITY_PREFLIGHT
  -> STABLE_PARTITION(REPAIR_TARGET_FIRST)
  -> OPTIONAL_REPAIR_FIRST_THREE_ROUND_PHASE_A/B
  -> WHOLE_TICKER_POST_REPAIR_PREFLIGHT
  -> COMPANY_PUBLICATION
  -> DEFERRED_REJECTIONS / REMAINING_FILINGS
  -> TERMINAL
```

- stable partition只把唯一repair target移到accepted序列首位；其余accepted filing保持原相对顺序，rejected intents保持首次发现顺序。
- repair-first目标使用v1完整三轮：published classify → 锁外prefetch → begin/latest-copy → staged identity-first → apply/rollback/retry。SEC repair unconditional；CN PDF/Docling锁外。
- repair-first成功也必须再跑一次whole-ticker inventory；只有零 `REPAIR_REQUIRED` 才能进入company batch。
- concurrent writer若先修好target，当前请求可在重新classification后按原`overwrite=False` skip，但post-repair inventory必须strict clean；这是“repair已由并发owner完成”，不是用旧prefetch覆盖。
- publication guard只覆盖短query或swap；writer只覆盖staging/validation/publication。provider/PDF/Docling、SEC prefetch、6-K/SC13 remote classification均不在锁内。

### 6.2 SEC 精确顺序

1. resolve company、fetch submissions、加载published registry；全部只读。
2. 完成form/window selection。SC13 direction只产生typed accepted/rejected decisions；不得产生ticker batch或修改registry。对全部SEC候选统一应用既有rejection-registry policy：`overwrite=False`命中同version entry的document ID进入最终rejected/non-publication集合，不能留到single-filing内部成为隐藏skip；`overwrite=True`仍按既有规则忽略registry。
3. 构造accepted filing IDs与SC13 rejected IDs，调用`list_source_integrity`并执行§5.2 preflight。
4. 若multiple/unselected/SC13-rejected corruption，立即抛typed preflight error；company/artifact/registry/source batch调用数均为0。
5. 若有唯一accepted repair target，stable-partition到首位并只执行该filing。顶层workflow必须观察其真实terminal：
   - downloaded，或因并发owner已修好而strict COMPLETE skip：继续；
   - provider/prefetch/Phase B/validator失败或三轮耗尽：中止，不提交company/rejection；
   - cancel：canonical cancelled收口，不提交company/rejection；
   - 该target为6-K且Phase A最终判为rejected：在调用rejected persistence前抛`SELECTED_REJECTED_REPAIR_REQUIRED`，不把损坏source重写成被policy拒绝的新source，也不发布rejection；命中既有registry的target已在步骤2进入rejected集合，不会走到此处。
6. 再次whole-ticker preflight；非clean即typed fail closed。然后执行cancel checkpoint。
7. 提交company meta batch。此时所有已知初始corruption已被修复或在任何ticker mutation前失败。
8. 按稳定顺序处理deferred SC13 rejection intents；每条使用§5.4 durable unit。随后处理其余accepted filings；普通6-K rejection同样使用§5.4。
9. 不执行无条件尾部maintenance batch；warnings/summary从已提交的registry真值与filing results派生。

### 6.3 CN/HK 精确顺序

1. resolve profile、list candidates、完成A4/period selection；不得提交company。
2. 以selected document IDs调用whole-ticker preflight。CN无rejected集合；任一material/unselected corruption或multiple corruption均typed fail closed。
3. 唯一selected repair target stable-partition到首位，执行v1三轮Phase A → 锁外PDF/Docling → Phase B；失败/cancel时company保持old。
4. post-repair whole-ticker preflight必须clean，随后cancel checkpoint与company meta batch。
5. 处理其余candidate。每个filing继续独立atomic commit；different-target基于latest staging形成union。
6. no-filing且inventory clean时仍提交company，保留现有company-resolved durable语义；no-filing但存在任一corruption时在company前以`UNSELECTED_REPAIR_REQUIRED`失败。

### 6.4 明确不做的“修复”

- 不让company/rejection batch捕获validator error后再调用provider。
- 不把company与全部filing放进一个operation-wide batch；禁止跨网络/Docling持writer。
- 不修multiple或unselected corruption；本WU只允许唯一、最终accepted filing target repair。
- 不为selected-then-rejected source发布正常source replacement；其业务语义不再publication-eligible，必须typed fail closed。
- 不以delete、prune、loose sha parsing、validator exception字符串或CLI retry推断integrity。

## 7. Durable facts / error owner 矩阵

“old”表示调用前exact bytes/meta/manifest/company/rejected artifact/registry facts；每个batch仍受storage atomic swap保护。

| 场景 | 首个ticker mutation前裁决 | 结束后的durable facts | 唯一error owner |
|---|---|---|---|
| SEC/CN唯一selected size mismatch | repair-first unconditional | target新bytes/meta/manifest；post-repair strict snapshot可读；随后才可能更新company | source classification + single-filing workflow |
| SEC/CN唯一selected digest mismatch | 同上 | 同上 | 同上 |
| SEC/CN唯一selected physical missing | 同上；这是带revision的`REPAIR_REQUIRED/PHYSICAL_FILE_MISSING`，不是`MISSING` target | 同上 | 同上 |
| selected target真正不存在 | 普通`MISSING` create，不计corruption | 成功后新source；overwrite policy不被repair transport替代 | single-target Phase A/B |
| multiple corruption | company/rejection/source batch均0 | 全部old精确保留 | `SourceIntegrityPreflightError(MULTIPLE_REPAIR_REQUIRED)` |
| unselected filing或material corruption | company/rejection/source batch均0 | 全部old精确保留 | `SourceIntegrityPreflightError(UNSELECTED_REPAIR_REQUIRED)` |
| designated 6-K Phase A后rejected | rejected persistence前失败 | 损坏source、company、artifact、registry全部old | `SourceIntegrityPreflightError(SELECTED_REJECTED_REPAIR_REQUIRED)` |
| SC13 rejected target本身corrupt | SC13 intent已形成但尚未发布；preflight失败 | company/artifact/registry/source全部old | 同上 |
| SC13 rejected、artifact成功 | 仅在repair/post-check/company gate后执行 | artifact+registry entry同batch完整发布；无半个rejection fact | persistence owner；storage commit error原样 |
| SC13 rejected、artifact listing/prefetch失败 | repair gate后执行registry-only语义 | artifact保持old/不存在；registry typed entry单batch发布 | SEC transport owner给safe failure；workflow决定registry-only policy |
| 6-K rejected、artifact失败 | repair gate后执行 | artifact与registry均old；filing terminal failure | persistence/transport owner |
| no-filing、clean | 无repair | company meta可提交；SEC deferred SC13 intents仍按其完整durable unit处理 | SEC/CN top workflow |
| no-filing、有corruption | company前fail closed | 全部old | preflight owner |
| repair prefetch/provider/PDF/Docling failure | company/rejection前中止 | target old bytes/meta/manifest、company、所有rejection facts精确保留 | 各transport owner + single-filing projection |
| Phase B identity churn 1–2轮 | rollback并释放，丢弃旧prefetch | latest并发published facts保留；下一轮重新prefetch | single-filing identity-first owner |
| Phase B churn第3轮耗尽 | company/rejection前中止 | latest tree精确保留 | typed integrity conflict owner（v1） |
| cancel在discovery/selection/preflight/repair/begin前 | fail/取消收口 | company/rejection均old；open target batch rollback | canonical SEC/CN cancellation owner |
| cancel或普通filing失败发生在company已成功之后 | 不伪造operation-wide rollback | company是完整已提交新fact；此前成功的独立source/rejection batch保留，当前open batch回滚，后续不执行 | canonical cancellation或当前filing owner |
| company/rejection commit pre-swap失败 | atomic rollback | 该batch全部old | storage commit owner |
| storage post-commit release/cleanup失败 | 不谎称rollback已提交tree | durable tree可能已完整新发布，异常保留storage primary/post-commit语义 | storage owner；implementation artifact单列 |

上表明确区分“能在副作用前发现”的初始integrity/policy/repair失败与“独立batch已成功后才发生”的后续失败。前者一律在company/rejection publication前fail closed；后者不通过禁止的operation-wide transaction假装回滚已提交事实。

## 8. Deterministic tests 与 barrier placement

不新增测试文件。所有thread/process/race只用`threading.Event`、`multiprocessing.Event`、`Barrier`与bounded test deadline；timeout只诊断test hang，禁止进入production；禁止`sleep`猜时序。

### 8.1 Storage owner tests

在`tests/fins/test_fins_storage_atomicity.py`与`test_fins_storage_provider.py`覆盖：

- `list_source_integrity` 在单publication guard返回filing+material排序inventory；并发swap前后只能观察old或new整套inventory。
- size/digest/physical missing分别返回closed reason；malformed sha256（非字符串、空、非canonical 64 hex）strict结构错误。
- per-ticker condition/reservation、blocking process writer、recovery try-lock nonblocking、release/notify、same/different ticker行为继续按base/v1矩阵。

### 8.2 SEC真实顶层矩阵

全部落在既有`tests/fins/test_sec_pipeline_download.py`与`test_sec_pipeline_download_stream.py`：

- 用真实Fs storage public contract建立完整source，再分别制造size、same-size digest、physical missing corruption；调用真实`SecPipeline.download/download_stream(overwrite=False)`，断言repair成功、company commit发生在repair commit后、`read_source_snapshot(..., materialize_files=True)`可读。
- `SpyBatchingRepository`记录`begin/commit/rollback/release`序号；`SpyCompanyMetaRepository`、`SpyFilingMaintenanceRepository`、v1 `SpyStoreFile`记录首次mutation与batch token。统一断言：`selection_complete < inventory_complete < repair_phase_a < prefetch_complete < repair_begin < staged_classify < repair_commit < company_begin`。
- **SC13 hidden mutation**：`sc13_decision_ready` Event阻塞selection返回；此时company/rejected/registry begin均为0。释放后由preflight/repair gate决定；clean路径才允许rejection durable unit。
- **既有registry skip**：`overwrite=False`命中同version entry时在final selection进入rejected集合；其source若corrupt则typed fail且batch为0，其source clean则不重复写artifact/registry。
- **selected-then-rejected 6-K**：在designated target的`precheck_6k_returned_reject` Event处阻塞；断言company/rejected/registry mutation为0；释放后得到typed preflight error且facts全old。
- **multiple/unselected/material/no-filing**：直接断言provider selection可完成，但首个ticker batch为0，error reason精确。
- **repair failure/cancel**：在v1 prefetch-returned/begin-before Event、Phase B staged classify Event与commit Event分别触发；断言old target/company/rejection精确。
- **SC13 artifact/registry atomicity**：store/meta/registry/validator各阶段注入失败，断言artifact与registry同old或同new；artifact transport failure只产生既有registry-only结果。
- runtime/top-level只断言端到端结果与durable顺序，不重复断言provider helper调用次数。

### 8.3 CN/HK真实顶层矩阵

全部落在`tests/fins/test_cn_download_runtime.py`与`test_cn_download_workflow.py`：

- CN与HK至少各一条真实top-level path；CN完整覆盖size/digest/physical missing + overwrite False，HK覆盖共享workflow顺序回归。
- `profile_resolved`、`selection_complete`、`inventory_complete`、`pdf_returned`、`docling_completed`、`repair_begin`、`repair_commit`、`company_begin`使用Event/barrier控制；断言无PDF/Docling I/O在writer内。
- no-filing clean提交company；no-filing+unselected corruption首batch为0。
- repair失败/cancel保留old company与old target；repair成功后strict snapshot可读。

### 8.4 既有 race 矩阵继续有效

- 同target双overwrite：`phase_a_classified` Barrier → `prefetch_complete` Barrier → writer A commit Event → writer B观察revision变化、旧payload callback为0、重新prefetch；两者success，last writer获胜。
- different-target：双方prefetch Barrier → A commit Event → B从latest复制并提交；最终union。
- revision churn三轮：每轮`round_n_prefetched`与`round_n_published`成对控制，旧prefetch不materialize。
- 同一矩阵10次repeat；process writer/recovery subset另跑10次。禁止概率循环或production hook。

## 9. Static call graph gate

implementation必须创建且只创建临时脚本`workspace/tmp/wu_cli_download_01_slice4_static_gate.py`；artifact记录脚本sha256与输出，但临时脚本不进入production/tests/commit。证据组合是`rg`全调用点枚举 + Python AST syntax gate + full pyright + 人工call-graph review，不声称形式化不可达。

可执行枚举：

```bash
rg -n "begin_batch\(|commit_batch\(|rollback_batch\(" dayu/fins/pipelines dayu/fins/storage tests/fins
rg -n "_persist_rejected_filing_artifact|persist_rejected_filing_artifact|_record_rejection|save_rejection_registry" dayu/fins/pipelines tests/fins
rg -n "def (download_files_stream|prefetch_files_stream)|\.(download_files_stream|prefetch_files_stream)\(" dayu tests
rg -n "_http_download(_if_modified)?\(|_execute_sec_request\(|download_report_pdf\(|convert_pdf_to_docling_json\(" dayu/fins tests/fins
rg -n "SourceDocumentRepositoryProtocol|class .*SourceDocumentRepository|list_source_integrity|classify_(staged_)?source_integrity" dayu tests
rg -n "BatchToken\(|getattr\(|hasattr\(|prepared|replay|compat" dayu/fins/downloaders/sec_downloader.py dayu/fins/pipelines/sec_download_persistence.py dayu/fins/pipelines/sec_download_filing_workflow.py dayu/fins/pipelines/sec_download_workflow.py dayu/fins/pipelines/cn_download_workflow.py dayu/fins/pipelines/sec_sc13_filtering.py
python workspace/tmp/wu_cli_download_01_slice4_static_gate.py
python -m pyright dayu/ tests/ utils/
```

AST脚本至少检查：

- `sec_sc13_filtering.py` 不调用persistence、batch lifecycle或registry mutation helper；其direction结果为typed variants。
- SEC/CN top workflow中company `begin_batch` 的语法位置在whole-inventory preflight、optional repair dispatch与post-repair check之后。
- SEC无无条件尾部maintenance batch；所有registry save调用点被枚举并归类为artifact+registry或registry-only durable unit。
- `persist_rejected_filing_artifact` 的所有provider/prefetch调用在其`begin_batch`前；batch内只可达materializer、artifact meta、registry save、validator/publication。
- single-filing Phase B第一条target operation是staged classification；identity变化分支在store/reset/upsert前rollback。
- CN PDF/Docling调用点在filing `begin_batch`前。
- `list_source_integrity` Protocol/wrapper/core签名一致；core只取得一个短publication guard并使用unguarded list/classification core。
- v1 shared transport、无fake BatchToken/prepared/replay/capability/compat/getattr/hasattr/新增timeout规则继续检查。
- production文件变更集合严格等于effective allowlist子集。

人工review必须逐条展开并记录`file:line`：SEC clean、SEC repair-first、SC13 rejection、6-K rejection、CN assets、CN metadata reuse、company、registry-only、artifact+registry、rollback/cancel。动态dispatch或独立Protocol implementer若使任一路径无法可信展开，触发stop，不把AST结果写成形式化proof。

## 10. Validation commands

implementation恢复后先激活环境并运行owner tests：

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q
pytest tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py -q
```

affected union：

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
```

10次deterministic repeat：

```bash
for run in 1 2 3 4 5 6 7 8 9 10; do
  pytest tests/fins/test_sec_pipeline_download.py \
    tests/fins/test_sec_pipeline_download_stream.py \
    tests/fins/test_cn_download_workflow.py \
    tests/fins/test_fins_storage_atomicity.py -q || exit 1
done
```

随后运行base plan §9 aggregate union，以及：

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

使用同一affected union生成coverage data，并对每个实际修改production文件逐一执行：

```bash
coverage report --include=<单个production文件> --fail-under=80
```

implementation artifact必须列出：命令原文、exit code、测试数、10次repeat逐轮结果、process/thread/barrier矩阵、所有Protocol implementer与`DownloadFilesStream` references、async generator finalization、static脚本位置/sha256/output、人工call graph、逐production文件coverage与git diff/static结果。

## 11. Risk adjudication

| 风险 | 裁决 | Owner / destination | Gate影响 |
|---|---|---|---|
| company-only batch先于repair | `fixed by v2 design` | SEC/CN top workflow移序 | top-level corruption矩阵blocking |
| SC13 selection隐藏artifact/registry mutation | `fixed by v2 design` | `sec_sc13_filtering.py` typed decision；persistence owner延后提交 | 必须新增该production allowlist |
| multiple corruption | 本WU不修；`typed fail closed` | preflight disposition owner | 首batch必须为0，否则blocking |
| unselected/material corruption | 本WU不修；`typed fail closed` | 同上 | 首batch必须为0，否则blocking |
| selected-then-rejected 6-K/SC13 | 不发布语义冲突的source或rejection；`typed fail closed` | policy workflow + preflight error | company/rejection必须old |
| artifact与registry半发布 | `fixed in v2` | 每条rejection durable unit同batch；SC13 registry-only为显式既有语义 | failure injection matrixblocking |
| no-filing仍被company batch validator偶然拦截 | `fixed in v2` | no-filing也先whole-tree preflight | clean/company与corrupt/fail矩阵blocking |
| repair失败改变company/rejection | `fixed in v2` | repair-first gate在二者之前 | exact old-facts assertionblocking |
| 后续filing失败时已有独立batch保留 | `accepted, explicitly bounded` | per-filing atomic publication；禁止operation-wide transaction | artifact记录，不伪造rollback |
| whole-tree query混合revision | `fixed in v2` | repository单guard `list_source_integrity` | storage concurrency testblocking |
| out-of-band physical corruption恰在post-check后发生 | `assigned to later storage reliability WU` | strict commit validator仍为最后防线；本WU不持全程writer | classified residual，不放宽validator |
| malformed sha256误入repair | `fixed by v1 + v2 gate` | storage strict structure owner | provider/batch调用必须0 |
| Python动态call graph不能形式化证明 | `accepted with controls` | rg+AST+pyright+人工+barrier | 证据不可信即stop |
| OS/file lock永久I/O卡死 | `assigned to later runtime/storage reliability WU` | 不新增业务timeout | 非本slice blocker，继续记录 |
| SEC rejected prefetch持有多文件bytes | `bounded by existing per-filing artifact` | v1 persistence一次只处理一条rejection；不做operation-wide聚合/spool | coverage/large-file行为沿既有owner |

无未分类residual risk；v1其余risk table继续有效。

## 12. Stop conditions

implementation出现任一项立即回滚本轮production/test试改、产新evidence并回plan review：

- 需要effective allowlist之外的新production/test文件，尤其是把顺序塞进facade、修改`sec_download_state.py`/maintenance core或新增shared glue module；
- SC13 selection仍可达batch/persistence/registry mutation，或typed decision无法封闭而退回optional god bag；
- whole-tree inventory不能在一个短publication guard得到一致filing+material classifications，或必须新增capability/compat/default/getattr/hasattr；
- multiple/unselected/material/selected-rejected/no-filing-corrupt在任何company/rejection/source batch之后才失败；
- designated repair target未先于company/maintenance/rejected batch完成，repair失败后任一old bytes/meta/manifest/company/rejection fact变化；
- selected-rejected 6-K被强行写成正常source，或SC13 rejected corruption绕过typed fail closed；
- artifact与registry出现一新一旧，或删除SC13现有registry-only语义；
- malformed sha256变成repair/UNKNOWN，或strict snapshot/complete-tree validator被放宽；
- provider/PDF/Docling I/O在writer/publication guard内，recovery try-lock变blocking，writer增加timeout，release/notify/lost-update不成立；
- identity变化后旧prefetch materialize、overwrite=True变skip、repair接受304、same-target任一stable writer失败或different-target丢union；
- deterministic test需要sleep/概率时序/production hook，async generator finalization无法证明；
- `rg + AST + pyright + 人工review`无法建立可信call graph，发现未清点独立Protocol implementer或`DownloadFilesStream` consumer；
- affected/aggregate/repeat/pyright/Ruff/format/compileall/diff失败，或任一修改production文件coverage低于80%。

## 13. Docs、completion signal 与下一入口

- README：本plan-fix不修改；继续留到四slices完成后的documentation closeout。
- Base plan、v1、stop evidence、review artifacts：零修改。
- Oracle/registry、真实CLI/provider、Host/Engine、PR190：零修改。
- Completion signal：本artifact包含完整mutation inventory、直接owner证据、最小allowlist增量、single executable order、typed fail-closed disposition、rejection durable unit、真实top-level矩阵、deterministic barriers、static/validation/coverage gates、stop conditions与已分类risk table；`git diff --check`通过，workspace除既有stop evidence与本artifact外无变化。
- 当前gate：第二次`plan fix`完成待re-review。
- Next entry point：原 AgentMiMo/AgentDS 分别以base plan + v1 + 新stop evidence + 本v2执行双路`$planreview` re-review；两路均PASS且总控接受前不得恢复implementation。
- 禁止commit、push、PR。
