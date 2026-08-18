# UF-FIX03 summary-and-bounded-errors — Code-generation-ready Plan

## 1. Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Gate：`accepted plan`
- Decision：**PASS — ACCEPTED FOR IMPLEMENTATION**
- Binding goal contract：
  `docs/gateflow/uf-fix03-summary-bounded-errors-goal-confirmation-20260813.md`
- Design inputs：`docs/host/design.md`、`docs/engine/design.md`
- Frozen read-only oracle inputs：
  - `docs/cli_ci_scenarios.json` 中 `UF-FIX03`
  - `upload_filing.irrelevant-and-repeated-options`
  - `upload_filing.direct-boundary-and-summary`
  - `upload_filing.malformed-and-empty-input`
- Branch：`codex/upload-filing-oracle`
- Baseline HEAD：`31817dc5da64126d1779fe276898f69488626a1a`
- Execution policy：本 artifact 只落实 controller accepted plan re-review findings N1–N3；不执行 implementation、UF-PF03、commit、
  push 或 PR。
- 本 gate 写入仅限本 plan 与 `docs/gateflow/uf-fix03-plan-rereview-fix-20260813.md`；goal-confirmation、此前 fix/adjudication、
  plan re-review adjudication、两份 re-review artifact、生产代码、测试、README、冻结 JSON 与 evidence 均为只读输入。

冻结 registry 基线 SHA-256：

- `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
- `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`

## 2. Goal / motivation / success signals

### 2.1 Goal

业务 scope 严格为 `upload_filing`。下列 failure、atomicity、stderr、label 与 direct-boundary目标只约束 filing；material 仅因共享
count/result type breaking change做机械迁移与回归，不成为本 WU 的业务目标。

1. 上传终态的唯一公开摘要同时表达：
   - `requested_file_count`：validated request 中本次用户输入文件数；
   - `stored_file_count`：本次 batch 成功 commit 后发布的用户输入 original 文件数。
2. `stored_file_count` 不计派生 Docling JSON/manifest/其它转换资产；`deleted`、`skipped`、`cancelled`、`failed`
   一律为 `0`，成功 `ok` 必须等于 `requested_file_count`。
3. 删除 `uploaded_files` 字段及其所有生产/测试依赖，不保留 alias、兼容 reader、兼容 writer、wrapper 或 fallback。
4. `dayu.fins.upload_failure` 继续作为唯一 closed public failure reason owner；`dayu.fins.direct_events` 是 public display file label
   的唯一 canonicalization/validation owner。filing pipeline、runtime、durable summary、direct event、CLI 只消费同一个 canonical label
   并做 typed projection，不按字符串、路径或异常 `repr` 二次分类。
5. 仅对 `upload_filing`：空文件在 Docling converter 与 `begin_batch` 前失败；损坏 PDF、损坏 DOCX、有效+损坏混合输入整批失败，
   且不发布 filing、company/source state 或任何非零 stored count。
6. 普通 stderr 只包含有界、业务可读错误和必要的 basename 标签；不包含第三方 traceback、绝对路径、异常 `repr` 或原始无界文本。
   operator log 使用异常链保留完整 traceback/cause。
7. 维持现有 direct Fins 边界：不创建 Host/Engine/legacy job，不写 Host/runtime durable artifact；用先有成功 publication positive
   control 的回归护栏检查该边界，不声称形式化证明，也不新增第二套 runtime。

### 2.2 First-principles motivation judgment

问题真实且严重性评估成立。summary 是对外业务事实，不是展示装饰：把 request basename 列表写成“已上传文件”会让
delete-with-files、skip、cancel 和 failure 对外承诺不存在的 publication。普通 stderr 直接渲染未知异常字符串则绕过 closed failure
owner，可能泄露路径、第三方 traceback 或无界内容。两者都必须在事实 owner 与公开错误 owner 处修复。

当前原子 publication 机制不需要重构。SEC 与 CN/HK `upload_filing` workflow 已在 `prepare_upload(...)` 完成后才
`begin_batch(...)`，company meta、blob、source meta 进入同一 caller-owned batch，失败走既有 rollback。正确方案是让内容 admission
在 prepare 阶段 fail closed，并从既有 commit 成功路径投影 stored count；新增事务、补偿队列或 Host job 反而会制造第二真源。

### 2.3 Success signals

- owner-level contract tests 证明 request count 与 commit 后 original publication count 同源，派生 Docling 资产不计数。
- `ok` 终态为 `requested == stored >= 1`；delete/skip/cancelled/failed 为 `stored == 0`。
- terminal summary、durable summary 与 direct RESULT details 使用相同 counts；started/preparing/completed progress 保留既有
  `file_count` 作为 requested progress unit；全仓生产/测试 Python 源码无 `uploaded_files`。
- filing 空文件：converter call `0`、batch begin `0`、workspace business tree不变、typed code 为 `empty_input_file`、label 为 owner
  产生的 canonical public display label。
- 损坏 PDF/DOCX：public kind/code 固定在 closed content 集合，stderr 显示 basename 与有界原因；operator log 保留完整内部 cause。
- filing 有效+损坏混合输入：首个 conversion failure 后 fail-fast；此前允许产生内存/临时转换结果，但 Fins publication batch `0`，
  company/source/blob published tree不变，
  terminal stored count `0`。
- direct test 先断言 success terminal 与真实 Fins source/blob publication，再断言 `.dayu/fins_ingestion/jobs` 无 JSON/JSONL record，
  且不存在 Host Run/Attempt/EventLog/Memory/ToolTrace/runtime SQLite artifact；Service public API 仍不暴露 job handle。
- 受影响测试通过；修改生产文件 coverage 目标 `>=80%`；完整 pyright 无新增或扩散错误；README 与 no-touch audit 通过。

## 3. Non-goals / frozen boundary

### 3.1 明确不做

- 不执行或登记 UF-PF03，不生成真实 post-fix CLI evidence。
- 不修改 `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json` 或任何第一轮冻结 evidence。
- 不处理日期/年份、ticker alias、format capability、multi-file primary/collision、existing-source repair、并发、company warning。
- 不改变 repeated action/ticker 的 argparse last-wins，也不借本 WU 改写 delete-with-files 的 accept/ignore 决策；本 WU 只保证其
  requested/stored summary 不再把请求误报为 publication。
- 不新增 Host Run/Attempt/EventLog/Memory/ToolTrace、Engine run、legacy ingestion job、durable operation ledger、workflow engine、
  补偿队列或自动重试。
- 不修改 Host/Engine/runtime/config/tool schema/prompt，不让 Host/Engine 理解财报上传业务事实。
- 不保留 `uploaded_files` 兼容字段、兼容 parser、re-export、wrapper、facade 或下游 fallback。
- 不按异常文本、时间、日志、目录扫描或文件名反推 stored count/failure kind；不在 CLI/Service 重算 Fins owner 语义。
- scope 严格为 `upload_filing`。`upload_material` 只因共享 count/result breaking contract 机械补齐
  `stored_file_count` producer/consumer/test，并运行既有 material 回归；不修改 material generic failure 分类、raw `message`/
  `payload.error`、operator log、company-first publication 顺序或任何 material public behavior。
- 不对 material 增加 empty/corrupt/mixed zero-publication、typed failure、safe label 或 bounded stderr 验收；这些风险归后续 material
  work unit，不能借共享 service 顺手修复。

### 3.2 为何没有 goal drift

计数只需要扩展现有 `UploadOperationResult -> FinsUploadPipelineResult -> FinsUploadResultSummary` 链；filing failure 只需要扩展现有
`FinsUploadFailureReason` 链；filing 原子性继续复用现有 `prepare -> begin_batch -> stage -> commit/rollback`。Service direct 继续原样透传
`ValidatedFinsEventStream`，CLI 继续机械渲染 typed terminal。没有理由创建新层、新数据库、新 job 类型、新 transaction protocol 或
通用错误框架。

## 4. Direct root-cause evidence and owner adjudication

| 语义 | 直接代码/测试证据 | 唯一 owner | 本 WU 决策 |
| --- | --- | --- | --- |
| requested count | `service_runtime._upload_summary_from_result(...)` 当前从 `request.files` 构造 basename tuple；该数据只证明请求，不证明 publication | validated `FinsUploadRequest` | 只取 `len(request.files)`，命名为 `requested_file_count` |
| stored count | `DoclingUploadService._store_upload_assets(...)` 在每次 `blob_repository.store_file(...)` 成功后掌握 asset provenance；`commit_prepared_upload_batch(...)` 只在 `commit_batch(...)` 返回后向 workflow 返回 result | Docling publication result | 只计成功写入且 provenance 为 user-input original 的资产；workflow 仅消费 commit 后 result |
| 当前错报根因 | `_upload_summary_from_result(...)` 无视 pipeline publication，直接把所有 request basename 填入 `uploaded_files`；durable/direct 都复用该 summary | `FinsUploadResultSummary` terminal projection | 删除 basename 列表，接收 request owner count + pipeline owner count |
| 派生资产误计风险 | `_store_upload_assets(...)` 的 payload 当前使用 `len(stored_entries)`，该集合同时含 original 与 Docling derived assets | typed asset provenance + publication result | 删除 payload `uploaded_files`；显式维护 original-success count |
| empty admission | `_validate_source_files(...)` 只检查存在、普通文件、suffix；`_build_original_assets(...)` 接受 `read_bytes()==b""` | `DoclingUploadService._build_original_assets(...)` 的内容读取边界 | 读到空 bytes 立即抛 owner-classified content failure；不进 converter/batch |
| corrupt input label | converter 的 `DoclingConversionError` 是 closed kind，但不携带 source basename；`_build_pending_assets(...)` 正好持有当前 `file_path.name` | `direct_events` canonicalize/validate display label；upload failure owner将其写入reason | 在filing逐文件conversion catch中fail-fast包装typed upload failure，带同一canonical `file_label`，保留原异常为cause |
| public failure | `upload_failure.py` 已拥有 kind/code/message/retry_hint exact-key parser 与 Docling/OSError/runtime 映射 | `dayu.fins.upload_failure` | 增加 `empty_input_file`、optional `file_label` 和携带 reason 的 typed exception；禁止其它层自造 code/message |
| public display file label | `direct_events._validate_safe_text(...)` 会拒绝 `job_id`、`财报正文` 等 fragment，现有 failure text 校验又未覆盖 Unicode `Cc/Cf`；合法但超过 public label 上限的 basename 若被 canonicalizer 拒绝，还会让 known content failure 降级；这些接受集差异可让 typed filing failure 在 reason/detail 构造前崩塌 | `dayu.fins.direct_events` 中单一 label canonicalizer/validator；`FinsUploadFailureReason.__post_init__()` 强制调用该 validator | 普通安全 basename 原样保留；合法超长 basename、命中 fragment/URL/job/path 等既有 detail guard或含 Unicode `Cc/Cf` 时统一返回固定标签 `输入文件（文件名已隐藏）`；pathful 输入仍拒绝；reason/durable/direct/CLI消费该同一值，raw basename只进operator log |
| stderr 泄漏 | `run_fins_direct_command(...)` generic `except Exception` 直接渲染 `str(exc)` | CLI 只拥有 transport/render；未知业务分类仍不归 CLI | `_LOGGER.exception(...)` 留 operator traceback；stderr 使用固定 bounded unknown message |
| atomic publication | SEC/CN filing workflow 都先 await `prepare_upload`，之后才 `begin_batch`；stage/commit failure tests 已断言 single rollback 与 published tree SHA不变 | existing batching repository + `commit_prepared_upload_batch(...)` | 保持事务 owner，不新增补偿；扩充 empty/corrupt/mixed zero-publication assertions |
| direct boundary | `FinsDirectCommandService` 只取得 `DefaultFinsRuntime.get_ingestion_runtime()`；`FsFinsIngestionJobStore.from_workspace_root(...)` 仅计算 lazy path，只有 `create_job(...)` 首写 | Fins direct runtime + Service identity pass-through | 不改 Service/Host/Engine；新增 upload direct no-artifact/no-job 负断言 |
| architecture | Host design 不拥有财报业务语义；Engine design 禁止访问 Fins/storage，且 Engine run 不持久化 | frozen Host/Engine design | `dayu/host/**`、`dayu/engine/**` 全部 no-touch |
| material scope boundary | SEC/CN material 在 prepare 前先 commit company meta，generic catch 公开 `str(exc)`；这与 filing workflow 的状态机不同 | Fins material workflow（后续 work unit） | 本 WU 不重排、不修 generic failure；仅迁移共享 count 字段并用 material 回归锁定既有行为 |

三个 accepted predicates 的落地：

- `irrelevant-and-repeated-options`：不改变 last-wins/delete ignore 决策；只保证 summary 的 stored fact 来自 publication，不再由 request 猜测。
- `direct-boundary-and-summary`：summary 同时含 requested/stored，error 由 typed owner 投影，direct 不产生 Host/runtime durable/job artifact。
- `malformed-and-empty-input`：`upload_filing` 的 empty/corrupt/mixed 在 publication 前整批失败；stderr 使用同一 canonical display label +
  bounded reason，第三方 traceback与无法原样展示的 raw basename只进 operator log。

## 5. Exact contract changes

### 5.1 Publication result contract

`UploadOperationResult` 新增必填 `stored_file_count: int`。所有构造点必须显式赋值，不给兼容默认值：

- `uploaded`：成功 staged 并最终由 `commit_prepared_upload_batch(...)` 在 commit 返回后交付的 user-input original 数；
- `deleted` / `skipped` / `cancelled`：`0`；
- failure 不返回 `UploadOperationResult`，workflow failure terminal 必须显式写 `stored_file_count=0`。

`_PendingFileAsset.source` 不继续作为松散任意字符串。最小方案固定选择私有
`Literal["original", "docling"]` 加 `_ASSET_SOURCE_ORIGINAL = "original"`、`_ASSET_SOURCE_DOCLING = "docling"` 两个模块常量；
不引入 enum、registry 或第二套 provenance 类型。运行期值必须仍为 exact `original` / `docling`，在每个 successful
`store_file(...)` 之后只对 `original` 增加计数。不得使用 `len(stored_entries)`，不得按后缀、文件名或 manifest 反推 original。

provenance 收紧仅是类型化，不改变 `_build_upload_source_fingerprint(...)` 的 canonical payload、排序、JSON 序列化或 bytes。现有
`a.pdf`/`b.pdf` fixture 的 canonical bytes 必须保持
`[{"name":"a.pdf","sha256":"sha-a","size":1,"source":"original"},{"name":"b.pdf","sha256":"sha-b","size":1,"source":"original"}]`
且 SHA-256 必须仍为 `099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd`；不得借本 WU 改 fingerprint schema。

`UploadOperationResult.payload` 删除 `uploaded_files`；count 是显式字段，不放入 extra payload。`publish_prepared_upload(...)` 的内部结果
在 commit 前只代表 staged writes；生产 workflow 只能从 `commit_prepared_upload_batch(...)` 的成功返回消费它。commit 抛错时不得投影
stored count。

### 5.2 Pipeline terminal JSON contract

`FinsUploadPipelineResult` 新增无 default 的必填 `stored_file_count: int`。count contract 的唯一 typed owner 是
`FinsUploadPipelineResult.__post_init__()`；`from_pipeline_json(...)` 只做 exact 取值/类型读取后调用 constructor，不复制状态矩阵。
pipeline status 闭集固定为 `ok/skipped/deleted/failed/cancelled`；`__post_init__()` 必须拒绝缺失、bool、负数或非 int，并拥有以下
完整状态矩阵：

| pipeline status | `stored_file_count` |
| --- | --- |
| `ok` | `>= 1` |
| `skipped` | `0` |
| `deleted` | `0` |
| `failed` | `0` |
| `cancelled` | `0` |

同时保持 failed 必须有 typed failure、非 failed 禁止 failure 的现有 exact contract。不得把 `cancelled` 留给
`FinsUploadResultSummary`、renderer 或其它下游兜底。owner tests 必须分别通过 direct constructor 与 JSON parser 证明
`cancelled+0` 被接受、`cancelled+positive` 被拒绝；parser 不复制该矩阵。

SEC/CN/HK filing 的全部 success/no-op/failure terminal result builder，以及 shared service 的 cancelled result，都必须显式写顶层
`stored_file_count`。SEC/CN material 只在既有 success/cancel/failure result producer/consumer 上机械补齐该 required count；不触碰
material failure object、message、logging或publication顺序。

### 5.3 Runtime terminal/durable contract

`FinsUploadResultSummary` 删除：

```text
uploaded_files: tuple[str, ...]
```

新增两个无兼容默认值的必填字段：

```text
requested_file_count: int
stored_file_count: int
```

terminal count contract 的唯一 owner 是 `FinsUploadResultSummary.__post_init__()`；所有 producer 必须先完成 constructor 迁移，
renderer/progress/durable consumer 不再校验或重算。`__post_init__` 固定不变量：

| status | requested | stored |
| --- | --- | --- |
| `ok` | `>= 1` | `stored == requested` |
| `skipped` | `>= 1` | `0` |
| `deleted` | `>= 0`（保留 validated request 事实） | `0` |
| `cancelled` | `>= 0` | `0` |
| `failed` | `>= 0` | `0` |

全部 count 拒绝 bool/负数。`_upload_summary_from_result(...)` 只允许：

```text
requested_file_count = len(validated request.files)
stored_file_count = typed pipeline result.stored_file_count
```

不得从 request basename、source manifest、workspace tree 或 payload 重建 stored count。runner unavailable、early cancelled、legacy upload
job 与 direct upload 的内部 summary 构造点也必须传入 request count 和 stored `0`。

`to_json_summary()` 用 `requested_file_count` / `stored_file_count` 替换 `uploaded_files`。这是 fresh breaking schema：不兼容读取旧
durable record，不提供 migration、default、alias、reader/writer或parser shim；旧 record 不在本 WU 读取契约内。Direct result details
固定输出 `requested files`、`stored files`。started/preparing/completed progress 的既有 `file_count` 完整保留，继续表示 requested
progress unit；本 WU 不改 `_PAYLOAD_FILE_COUNT`、不在 progress 双写/rename count key。

当前四个 production `FinsUploadResultSummary(...)` constructor 必须全部显式传入两个 required counts，且不得新增 default：

1. `dayu/fins/service_runtime.py::ProductionFinsUploadRunner.run_upload(...)` 的 early-cancelled 分支：requested=`len(raw_request.files)`，stored=`0`；
2. `dayu/fins/service_runtime.py::_upload_summary_from_result(...)`：requested=`len(request.files)`，stored=`result.stored_file_count`；
3. `dayu/fins/ingestion_runtime.py::FinsIngestionRuntime._produce_direct_upload(...)` 的 runner-unavailable 分支：requested=当前 validated request files数，stored=`0`；
4. `dayu/fins/ingestion_runtime.py::FinsIngestionRuntime._run_upload_job(...)` 的 runner-unavailable 分支：requested=当前 validated request files数，stored=`0`。

实现后用 production-only static constructor audit 断言恰好审计上述四点；测试 constructor 随 required schema 机械迁移，不得倒逼 production
增加 default。

### 5.4 Closed failure contract

`FinsUploadFailureReason` exact JSON object 从四字段变为五字段；五个 key 全部 required，`file_label` 的值允许为 `null`：

```json
{
  "kind": "content | storage | runtime",
  "code": "closed enum value",
  "message": "bounded path-free text",
  "retry_hint": "bounded path-free text or null",
  "file_label": "validated basename or null"
}
```

新增 closed code：

```text
empty_input_file -> kind=content
message="文件为空，无法上传"
retry_hint="请提供非空文件后重试"
```

这是 intentional fresh breaking schema：`FinsUploadFailureReason.file_label: str | None` 本身也无 default；owner 内现有 Docling、OSError、
runtime、prevalidation factories 与 parser constructor 全部显式传 `None` 或 canonical label。JSON parser 只接受五个 exact keys，明确拒绝
旧四字段、missing/unknown key；不迁移、不删除旧 record、不提供 default、兼容 parser、alias或dual writer。旧 durable failure record 不在
本 WU 的读取契约内。

`FinsUploadFailureReason.__post_init__()` 是 reason-level label 接受集的唯一强制边界：`file_label is not None` 时必须调用唯一
`validate_fins_public_file_label(...)`。`upload_failure_reason_from_json(...)` 只负责 five-field exact key/type 读取并调用 constructor，
不得自己调用 validator、复制长度/fragment/control/path规则或维护第二套接受集。owner tests 必须直接构造合法、`None` 与非法 label 的
reason，证明任何 factory、parser 或未来 direct constructor 都受同一 invariant 约束。

public display file label 采用一个最小且唯一的 owner 方案：

- 在 `dayu/fins/direct_events.py` 增加 `canonicalize_fins_public_file_label(raw_basename: str) -> str` 与
  `validate_fins_public_file_label(value: str) -> None`；二者共享一个私有判定实现并复用该模块现有 `_validate_safe_text(...)` 及
  `_DISALLOWED_TEXT_FRAGMENTS`，没有重复validator。不得新建模块、value type、registry，也不得放宽所有 `FinsEventDetail` 的通用安全守卫。
- 依赖方向固定为 `upload_failure -> direct_events` 使用validator、`docling_upload_service -> direct_events` 使用canonicalizer；
  `direct_events`不得反向import `upload_failure`，从而保持单向依赖且不引入lazy import/glue seam。
- canonicalizer 输入必须是单个 raw basename：非空、无 `/`、`\\`，且不是 `.`/`..`；pathful 输入仍直接拒绝。源文件存在性、
  filesystem basename 合法性继续由既有 upload input validation owner 负责，canonicalizer 不做路径解析。
- 普通且能通过既有 detail safe-text guard 的 basename 原样返回。若 basename 含 Unicode category `Cc` 或 `Cf`（覆盖换行、DEL类
  控制与双向/格式控制），命中既有 fragment/URL/job/path public guard，或虽为合法 basename 但长度超过 public label 上限 `240`，
  则 owner 确定性返回固定业务标签
  `输入文件（文件名已隐藏）`；不做 silent strip、`Path.resolve()`、loose normalization或字符级猜测。
- validator 只接受 canonicalizer 已可能产生的 public label；five-field parser 的 raw `job_id_notes.pdf`、`财报正文.pdf`、含 `Cc/Cf`、
  pathful 或超出 `240` 的未 canonicalize label 必须经 reason constructor 拒绝，防止绕过 producer 直接注入。parser 本身不复制这些规则。
  filing producer 对上述无法原样公开的合法 raw basename 先 canonicalize，再把同一个固定 canonical value 写入 reason；超长合法 basename
  的 empty/conversion failure 必须保留原 closed content kind/code，绝不能因 label 处理降级为 runtime/unknown failure。
- failure reason、pipeline JSON、durable summary、direct detail 与 CLI 只消费 reason 中的 canonical value；任何 downstream consumer 禁止
  按 fragment/control内容分支、二次 validate+fallback或重算。无法原样展示的 raw basename只允许进入 operator log。

这比给 `FinsEventDetail` 增加 file 特例、放宽全局 fragment 守卫或在 runtime/CLI 重复 sanitizer 更小：只增加一个 owner helper，
普通 label 与所有投影仍走既有 contract。

新增一个 owner-defined typed exception（命名为 `FinsUploadFailureError`），只携带已经校验的 `FinsUploadFailureReason`：

- `prepare_upload(...)` 把已有 `source_kind` 作为显式参数直接传给 `_build_original_assets(...)` 与 `_build_pending_assets(...)`；
  不使用callback/factory/extra payload。`_build_original_assets(...)` 仅在 `source_kind is FILING` 时对空 bytes抛该异常；material保持
  既有generic failure行为；
- `_build_pending_assets(...)` 仅对 filing 在逐文件 `DoclingConversionError` catch 中，用当前 `file_path.name` 调唯一 label owner，
  operator log用 `%r`/等价转义形式记录raw basename与cause以防日志换行注入，再由failure owner产生reason并 `raise ... from exc`；
  material原样重新抛既有异常；
- filing conversion 顺序固定为 sequential fail-fast：首个失败立即包装并终止，后续 converter call 必须为 `0`；失败前已产生的内容只在
  内存/临时对象中，不得 `begin_batch`，不形成 stored/publication fact；
- SEC/CN/HK `upload_filing` workflow 在 `DoclingConversionError`/`OSError`/generic 之前穷尽显式 catch
  `FinsUploadFailureError`，operator log 使用 `_LOGGER.exception(...)`，pipeline 直接投影 `exc.failure`；material catch不修改；
- raw third-party error 只保留在 exception chain/operator log，不进入 public reason。

`EMPTY_INPUT_FILE` 必须加入 `_CONTENT_FAILURE_CODES`，并由 kind/code一致性 owner test锁定为 `content`。转换失败沿用现有 Docling
closed code 与固定 message/retry_hint，只增加当前 original 的 canonical display label。storage/runtime failure 的 constructor 显式传
`file_label=None`；本 WU 不猜测哪个 derived asset 应映射为用户输入文件。

filing 两个 workflow 的 typed catch 是 `FinsUploadFailureError` 的穷尽边界；owner test 必须注入该异常并断言 generic catch及 runtime
`_classify_direct_error(...)` / `_safe_direct_error_message(...)` 不被调用。若实现发现另有 filing 入口可绕过这两个 catch，必须停止并在
runtime增加直接读取 `exc.failure` 的 typed defense；绝对禁止通过 `str(exc)` 重新分类。

### 5.5 CLI projection contract

Typed pipeline failure 的 direct RESULT：

- `error_message = failure_reason.message`；
- details 包含 failure kind/code/message，非空时再包含 `retry hint` 与 `file`；
- CLI renderer 继续机械输出 RESULT，不读取 exception/string/path 重新分类。

`run_fins_direct_command(...)` 的 generic `except Exception` 改为：

1. `_LOGGER.exception("Fins direct command failed; command=%s", args.command_name)` 记录完整 operator traceback；
2. stderr 只输出固定文案：`dayu-cli <command>: 命令执行失败，请查看日志后重试`；
3. 退出码保持 `EXIT_FAILURE`；禁止拼接 `str(exc)`、`repr(exc)` 或 `__cause__`。

Known usage/prevalidation/protocol/typed terminal 分支保持既有 owner 和退出码。本 WU 不把 generic unknown 伪装成已知 content/storage code。

### 5.6 Data flow and invariants

```text
validated upload_filing request
  -> requested_file_count = len(request.files)
  -> DoclingUploadService.prepare_upload
       -> read every original
       -> empty: typed content failure(canonical file_label), no converter, no batch
       -> convert every original
       -> corrupt: typed content failure(canonical file_label), fail-fast, no batch
  -> begin one caller-owned batch only after all prepare succeeds
       -> stage company decision + original/derived blobs + final source
       -> count each successful original store only
       -> cancel/failure: rollback, no terminal stored fact
       -> commit succeeds
  -> pipeline stored_file_count
  -> FinsUploadResultSummary(requested, stored)
       -> same source for direct RESULT and durable summary；progress继续使用既有file_count
       -> CLI mechanical rendering
```

必须始终成立：

- derived Docling assets 永不增加 `stored_file_count`；
- non-`ok` 终态 stored 永远为 `0`；
- filing content failure 发生在 `begin_batch` 前；filing storage stage failure 走既有 single rollback；
- mixed input 不做 per-file partial publication；先转换成功的临时/内存产物不构成 Fins stored fact；
- displayed/durable/direct counts 与 failure 来自同一 summary/reason，不允许各层重算；progress `file_count` 继续来自validated request；
- normal stderr 和 public event 无绝对路径、traceback、exception repr、raw provider/Docling 文本；canonical label只由唯一owner产生；
- direct path 不调用 `start_upload/create_job/read_job/request_cancel`，不产生 Host/Engine artifact。

## 6. Exact affected files and symbols

### 6.1 Production files

1. `dayu/fins/pipelines/docling_upload_service.py`
   - `UploadOperationResult`：新增 required `stored_file_count`。
   - `_PendingFileAsset`：把 `source` 收敛为 closed provenance。
   - `DoclingUploadService.prepare_upload(...)`：no-op/cancel result stored `0`；保持 delete 既有 admission 次序。
   - `DoclingUploadService.publish_prepared_upload(...)`：delete stored `0`；日志使用 typed count，不读 payload旧字段。
   - `DoclingUploadService._store_upload_assets(...)`：逐个 successful original store 计数；删除 payload `uploaded_files`。
   - `DoclingUploadService._build_original_assets(...)`：filing 空 bytes 抛 typed upload failure；material行为不变。
   - `DoclingUploadService._build_pending_assets(...)`：filing逐文件转换错误fail-fast包装canonical label + closed reason，保留cause；
     material原样抛既有异常。
   - `_build_cancelled_result(...)`：stored `0`。

2. `dayu/fins/pipelines/sec_upload_workflow.py`
   - `run_upload_filing_stream(...)`、`_build_sec_filing_failure_event(...)`：所有 terminal result 显式 stored count；catch typed owner error。
   - `run_upload_material_stream(...)`：仅在既有 success/cancel/failure result construction机械补齐 shared `stored_file_count`；不改
     generic failure、日志或company publication。

3. `dayu/fins/pipelines/cn_pipeline.py`
   - `CnPipeline.upload_filing_stream(...)`、`_build_cn_filing_failure_event(...)`：同 SEC。
   - `CnPipeline.upload_material_stream(...)`：同SEC，仅机械补齐shared count。

4. `dayu/fins/upload_failure.py`
   - `FinsUploadFailureCode`：新增 `EMPTY_INPUT_FILE`。
   - `FinsUploadFailureReason.__post_init__()` / `to_json()` / `upload_failure_reason_from_json(...)`：fresh breaking五字段exact contract；
     constructor 对非空 label 调用唯一 validator，parser 只做 exact key/type 读取，不自建或复制fragment/control/path/长度规则。
   - 新增 `FinsUploadFailureError` 与 empty failure factory。
   - `fins_upload_failure_from_exception(...)`：允许 caller 显式传入 validated `file_label`；不读取异常文本。

5. `dayu/fins/ingestion_runtime.py`
   - `FinsUploadPipelineResult` / `from_pipeline_json(...)`：required stored count及状态不变量。
   - `FinsUploadResultSummary` / `__post_init__()` / `to_json_summary()`：breaking count contract，删除 old field。
   - `_produce_direct_upload(...)`、`_run_upload_job(...)` runner-unavailable constructor：显式 counts；与service_runtime两点合计四个。
   - `_upload_result_details(...)`：requested/stored + typed failure label/retry projection。
   - `_upload_context_request_progress_payload(...)` / `_upload_context_summary_progress_payload(...)`：no-change audit，保留既有
     `_PAYLOAD_FILE_COUNT == "file_count"`，不迁移。

6. `dayu/fins/service_runtime.py`
   - `ProductionFinsUploadRunner.run_upload(...)`：early cancelled summary 显式 request/stored counts。
   - `_upload_summary_from_result(...)`：request owner与pipeline owner的唯一汇合点；删除 basename projection。

7. `dayu/cli/commands/fins.py`
   - `run_fins_direct_command(...)` generic catch：operator traceback + fixed bounded stderr，禁止原始异常字符串。

8. `dayu/fins/direct_events.py`
   - 增加唯一 public display file label canonicalizer/validator；复用现有safe-text guard，覆盖fragment、Unicode `Cc/Cf`与合法超长
     basename的固定隐藏标签投影；pathful仍拒绝，不改`FinsEventDetail`通用contract。

Production constructor inventory（实现时全部机械迁移，禁止靠default兜底）：

- `UploadOperationResult(...)` 当前六点：
  1. `DoclingUploadService.prepare_upload(...)` skipped；
  2. `DoclingUploadService.publish_prepared_upload(...)` deleted；
  3. `DoclingUploadService._store_upload_assets(...)` uploaded；
  4. `docling_upload_service._build_cancelled_result(...)` cancelled；
  5. `sec_upload_workflow.run_upload_filing_stream(...)` conversion-cancelled；
  6. `CnPipeline.upload_filing_stream(...)` conversion-cancelled。
- `FinsUploadPipelineResult(...)` production只由 `FinsUploadPipelineResult.from_pipeline_json(...)` 的 `cls(...)` 构造；
  constructor必须经过新 `__post_init__()` owner校验。
- `FinsUploadResultSummary(...)` production四点就是§5.3列出的 early-cancelled、service汇合、direct runner-unavailable、job
  runner-unavailable；不得遗漏或新增隐式default路径。
- `FinsUploadFailureReason(...)` production均在 `dayu/fins/upload_failure.py` owner 内：Docling/OSError/runtime mapper三分支、两个
  prevalidation factory、five-field parser，以及本WU新增empty factory；每点显式传required `file_label`。

### 6.2 Test files

1. `tests/fins/test_docling_upload_service.py`
   - original/derived 计数、delete/skip/cancel `0`；filing empty 与 PDF/DOCX conversion failure pre-batch；filing mixed
     no-publication；commit/rollback不变量。
2. `tests/fins/test_sec_pipeline_upload_filing_stream.py`
   - SEC filing terminal count传播、typed label/reason、mixed zero batch/company/source publication；保留现有 rollback SHA assertions。
3. `tests/fins/test_cn_pipeline.py`
   - CN/HK 同形 contract/atomicity parity。
4. `tests/fins/test_sec_pipeline_upload_material_stream.py`
   - 只迁移shared count schema并回归既有material generic failure/company-first publication行为；不新增filing语义断言。
5. `tests/fins/test_fins_ingestion_runtime.py`
   - pipeline parser、summary状态矩阵、direct/durable同源 counts、no old key、failure exact JSON/details、direct no job artifact。
6. `tests/fins/test_fins_service_runtime.py`
   - `_upload_summary_from_result` request/publication count汇合；delete/skip/cancel/failure zero；derived资产不由 request重建。
7. `tests/cli/test_fins_commands.py`
   - filing empty/corrupt PDF/corrupt DOCX/mixed bounded stderr；canonical label可见、绝对路径/traceback/repr/raw cause不可见；
     generic catch的 caplog/stderr分离。
8. `tests/service/test_fins_direct.py`
   - direct stream identity/API no-job contract回归；不修改 Service production。

### 6.3 README decision

本 plan-fix gate 不修改 README；以下是未来 implementation 命中触发后的预定 decision，届时必须先读取各 README 自身更新约束：

- `dayu/fins/README.md`：**更新**。`dayu/fins/**` production contract 变化命中职责；记录 requested/stored 真源、original-only count、
  closed failure label、empty/corrupt pre-publication与现有 atomic batch复用。
- `tests/README.md`：**更新**。测试文件变化命中职责；只记录已落地测试能力与 focused/coverage 命令，不写 work-unit 过程。
- 根 `README.md`：**更新**。用户可见上传 summary/stderr/empty behavior 变化命中最终用户手册职责；只写用户能看到的两个 count、
  bounded basename错误与整批失败，不写 owner/module/internal schema。
- `dayu/service/README.md`：**不更新**。Service production API、identity pass-through 与 no-job边界均不变，现有说明准确；只跑回归证明。
- `dayu/host/README.md`、`dayu/engine/README.md`、`dayu/README.md`、`docs/host/design.md`、`docs/engine/design.md`：**不更新**。
  没有分层、装配、Host/Engine contract变化。

### 6.4 Explicit no-touch

- `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`、全部冻结 evidence、UF-PF03 artifact。
- `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/ui/**`。
- `dayu/service/fins_direct.py` 及其它 Service production；direct boundary已正确。
- `dayu/fins/storage/**`；现有仓储协议与 batch足够，不新增 count API或扫描接口。
- 日期/年份、alias、format capability、primary/collision、repair、concurrency、company warning相关文件与测试。

## 7. Small implementation slices

共 3 个可独立 review/验证的 vertical slice。每个 slice 只允许修改列出的文件；需要越界时必须停止并回到 plan gate，不得顺手扩 scope。

### S1 — Publication-owned requested/stored count contract

- Slice ID：`UF-FIX03-S1`
- Objective：删除 request-basename伪 publication，贯通 original-only stored count到pipeline/runtime/direct/durable。
- Prerequisite：当前 baseline；不得先引入 failure label或CLI generic行为变化。
- Expected outcome：所有 producer/consumer编译通过；direct/durable使用同一 `FinsUploadResultSummary` counts；old field零命中。
- Allowed production files/functions：
  - `dayu/fins/pipelines/docling_upload_service.py`：`UploadOperationResult`、`_PendingFileAsset` provenance、
    `prepare_upload`/`publish_prepared_upload`/`_store_upload_assets`/`_build_cancelled_result`。
  - `dayu/fins/pipelines/sec_upload_workflow.py`：filing/material terminal result construction。
  - `dayu/fins/pipelines/cn_pipeline.py`：filing/material terminal result construction。
  - `dayu/fins/ingestion_runtime.py`：两个 upload result types、所有内部 summary构造、JSON/details/progress projection。
  - `dayu/fins/service_runtime.py`：`ProductionFinsUploadRunner.run_upload`、`_upload_summary_from_result`。
- Allowed test files：
  `tests/fins/test_docling_upload_service.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、
  `tests/fins/test_cn_pipeline.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、
  `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_service_runtime.py`。
- Tests first / exact assertions：
  1. 两个输入文件成功时，storage实际写入 original+derived 多个 asset，但 pipeline/runtime `requested=2, stored=2`。
  2. delete-with-files：requested保留validated request数，stored `0`；skip/cancel/failed同为 `0`。
  3. `FinsUploadPipelineResult.__post_init__` 直接constructor与parser入口都拒绝缺失/bool/negative count、`ok+0`、non-ok+positive；
     状态矩阵显式逐项覆盖`skipped/deleted/failed/cancelled`，其中constructor与parser都接受`cancelled+0`并拒绝
     `cancelled+positive`，不得靠summary兜底；
     `FinsUploadResultSummary.__post_init__`拒绝`stored>requested`、`ok stored!=requested`、non-ok stored非零。
  4. production static constructor audit覆盖§5.3四个summary点、§6.1六个operation result点及pipeline唯一`cls(...)`点；没有default。
  5. durable JSON与direct RESULT details分别含两个 exact key/value，均不含旧字段或文件basename。
  6. started/preparing/completed progress继续只有既有`file_count`请求单位，不出现`requested_file_count`/`stored_file_count`；terminal
     summary/durable/direct details才使用两个新count。
  7. closed provenance仍为exact `original`/`docling`；上述fingerprint fixture canonical bytes与digest保持§5.1字面值不变。
  8. filing `commit_batch` 分别抛 `OSError` 与 `RuntimeError`：terminal均为failed、stored=`0`；failure kind/code保持既有
     `storage/storage_io`与`runtime/unexpected_runtime`分类，published tree SHA不变且single rollback断言仍成立。
  9. material success/cancel/failure只新增required count；existing raw generic failure message/error与company-first publication回归保持，
     不增加zero-publication或typed failure预期。
- Data flow：successful `store_file(original)` -> `UploadOperationResult.stored_file_count` -> workflow top-level result ->
  `FinsUploadPipelineResult` -> `_upload_summary_from_result(requested, stored)` -> direct/durable projections。
- Invariants：count不进extra payload；不按`len(stored_entries)`；commit失败terminal显式stored=0但不消费staged count；non-ok stored为0；
  provenance/fingerprint不变；material仅机械迁移；无路径/文件列表。
- Focused validation：
  `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py`
- Static stop check：
  `rg -n '\buploaded_files\b' dayu/fins tests/fins --glob '*.py'` 应零命中；`_PAYLOAD_FILE_COUNT`与progress `file_count`必须仍命中并由
  progress regression覆盖。其它workflow内部`file_count`若明确表示请求或候选数量，不做全局盲删。
- Stop condition：若 workflow 可在 `commit_batch` 返回前向 runtime交付 result，或无法从 typed asset provenance识别 original，停止并
  重新澄清 publication owner；不得退回 request count或目录扫描。
- Non-goals：不实现 empty/corrupt label，不改CLI，不改事务协议，不新增material业务规则。

### S2 — Pre-publication content admission and closed bounded failure

- Slice ID：`UF-FIX03-S2`
- Objective：`upload_filing` empty/corrupt/mixed输入在prepare阶段形成带canonical display label的typed failure，整批zero publication。
- Prerequisite：S1 accepted；S1 count/schema不在本 slice重定义。
- Expected outcome：fresh closed reason五字段贯通SEC/CN filing与direct/durable summary；第三方cause及无法原样展示的raw basename只在
  operator log；material failure行为不变。
- Allowed production files/functions：
  - `dayu/fins/upload_failure.py`：failure enum/reason/parser/mapper/typed exception/label validator/empty factory。
  - `dayu/fins/direct_events.py`：唯一display file label canonicalizer/validator；不得修改通用detail guard接受集。
  - `dayu/fins/pipelines/docling_upload_service.py`：`_build_original_assets`、`_build_pending_assets`及必要docstring/import。
  - `dayu/fins/pipelines/sec_upload_workflow.py`：filing typed catch与failure terminal构造；material no-touch。
  - `dayu/fins/pipelines/cn_pipeline.py`：filing typed catch与failure terminal构造；material no-touch。
  - `dayu/fins/ingestion_runtime.py`：pipeline failure parse、upload direct details/error_message投影。
- Allowed test files：
  `tests/fins/test_docling_upload_service.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、
  `tests/fins/test_cn_pipeline.py`、`tests/fins/test_fins_ingestion_runtime.py`。
- Tests first / exact assertions：
  1. zero-byte `.pdf`/`.docx`：code=`empty_input_file`、kind=`content`、exact message/retry_hint、file_label=basename；converter calls `0`、
     batch begin/commit/rollback均 `0`、published tree为空/保持旧SHA。
  2. deterministic fake converter分别对 `.pdf`/`.docx` 抛每个代表性closed Docling failure：kind/code/label映射稳定，reason不含
     底层exception文本、绝对路径或repr；`__cause__`身份保留。已有真实corrupt sample只断言稳定public contract，不依赖第三方原始
     exception subtype/text，且禁止因平台差异加无条件`xfail`/`skip`。
  3. fail-fast顺序：bad-first时后续converter call=`0`；valid-before-bad时只调用到首个bad，bad后的文件不转换。两种都不begin batch；
     SEC与CN至少各一条mixed workflow测试断言batch begin `0`、
     company/source stage `0`、repository tree无partial state、terminal stored `0`。
  4. exact JSON parser拒绝旧四字段、missing/未知字段、pathful/oversized raw label、raw fragment label、含Unicode `Cc/Cf` label、
     kind/code不匹配；五个key required但允许`file_label=null`。这些 label rejection 来自 reason constructor 调唯一 validator，parser只做
     exact key/type读取；`empty_input_file`仅允许`content` kind。
  5. raw basename `report.pdf`原样canonical；`job_id_notes.pdf`、`财报正文.pdf`、含换行/U+202E等`Cc/Cf` basename均产生
     exact `输入文件（文件名已隐藏）`；合法且超过`240`字符的basename也产生同一固定标签，pathful输入仍拒绝。上述每个合法basename
     场景仍保持原empty/conversion closed content kind/code，reason/durable/direct detail/CLI消费同一label，stderr单行有界，下游无
     fragment/control/长度分支或fallback，known typed failure不得降级。
  6. 直接构造`FinsUploadFailureReason`：`file_label=None`与canonical label接受；raw fragment、`Cc/Cf`、pathful及超长未canonicalize
     label均由`__post_init__()`拒绝。parser delegation test替换constructor为受控入口，断言five-field值原样传入constructor；label接受集
     只在上述direct constructor参数化测试覆盖，不在parser测试复制同一规则表。
  7. operator `caplog`含注入的private cause和typed catch marker；public pipeline/direct repr不含它。
  8. SEC/CN filing显式catch `FinsUploadFailureError`并直接投影`exc.failure`；generic catch、`_classify_direct_error`、
     `_safe_direct_error_message`均未调用，证明typed exception不穿透到字符串分类边界。
- Data flow：original read/conversion catch -> display label owner canonicalizes -> failure owner builds reason -> typed exception -> workflow log full cause + pipeline exact JSON ->
  runtime typed parse -> direct result。
- Invariants：仅filing内容失败发生在begin_batch前；label只来自当前`Path.name`并由单一owner canonicalize/validate；unknown text不参与分类；
  conversion fail-fast；stored始终0；material不进入本slice行为变更。
- Focused validation：
  `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py`
- Stop condition：若filing converter错误无法在逐文件边界关联唯一basename，停止并重新请求owner裁决；不得静默退为`None`或从异常文本
  loose parse文件名。若任一filing内容失败已发生在begin_batch后，停止并修正filing prepare/publication顺序，不加补偿删除；不得
  因此重排material company publication。
- Non-goals：不处理material generic failure/company publication、format capability/primary/collision/repair，不改CLI generic catch，
  不执行真实UF-PF03。

### S3 — CLI unknown boundary, direct no-artifact regression guard, and documentation

- Slice ID：`UF-FIX03-S3`
- Objective：封闭CLI最后一个raw exception stderr出口，并以有success positive control的回归护栏检查direct不创建
  Host/Engine/legacy job；同步当前文档。
- Prerequisite：S1、S2 accepted；typed terminal渲染已携带counts/label。
- Expected outcome：known typed failure可行动，unknown failure固定安全；operator log有完整cause；direct无durable side effect。
- Allowed production file/function：
  - `dayu/cli/commands/fins.py::run_fins_direct_command(...)` generic catch及必要模块常量/helper；不得修改参数解析或Service factory语义。
- Allowed test files：
  - `tests/cli/test_fins_commands.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/service/test_fins_direct.py`
- Allowed docs：`README.md`、`dayu/fins/README.md`、`tests/README.md`。
- Tests first / exact assertions：
  1. 注入 `RuntimeError("private /absolute/path traceback marker")`：exit `1`；stderr exact fixed message，无marker/path/Traceback/repr；
     caplog含marker与 traceback。
  2. real CLI corrupt PDF与corrupt DOCX：exit `1`，stderr包含各自canonical label、closed content kind/code与bounded reason，长度受
     既有renderer上限约束；无repo/temp绝对路径、`Traceback`、第三方logger/raw cause。
  3. empty与mixed CLI/pipeline integration：requested为输入数、stored `0`、无partial filing/company/source；不把第一个valid文件误报stored。
  4. direct runtime no-artifact test先断言terminal=`success`、requested=stored，并从Fins repository读取真实source meta、original blob与
     derived Docling asset作为positive control；随后才断言jobs目录无`*.json`/`*.jsonl`、workspace `.dayu`树无Host/runtime SQLite、
     EventLog/Memory/ToolTrace、holding executor无legacy operation、Service public API仍无job handle/wait/request_cancel。该测试只称
     regression guard，不称完整证明。
  5. success/delete/skip/failure CLI摘要分别显示正确requested/stored；不显示`uploaded_files`。
- Data flow：typed RESULT -> existing CLI renderer；unknown exception -> operator logger + fixed CLI text。Service/direct stream identity不变。
- Invariants：CLI不分类业务错误、不扫描workspace、不调用job API；测试先证明真实upload成功，再观察public filesystem/API负事实，
  不mock Host、不声称形式化证明。
- Focused validation：
  `pytest -q tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py`
- Documentation assertions：root只写用户行为；Fins README写owner contract；tests README写测试层级/命令；不写未来UF-PF03或work-unit状态。
- Stop condition：若real Docling损坏样本在受支持环境不稳定，保留deterministic owner/integration tests并把real样本风险明确交UF-PF03；
  不放宽public assertions、不匹配第三方原始文本、不在production加测试分支。
- Non-goals：不改Service/Host/Engine/runtime production，不创建job-free facade，不执行UF-PF03。

## 8. Test and validation matrix

### 8.1 Required assertions by behavior

| Behavior | Owner-level assertion | Integration/public assertion |
| --- | --- | --- |
| success count | original successful stores N；derived stores不计 | direct/durable/CLI requested=N, stored=N |
| delete/skip/cancel/fail | pipeline与summary constructor owner各自完整矩阵；`cancelled+0`接受、`cancelled+positive`拒绝 | terminal summary/durable/direct均为0，无old field；progress仍用file_count |
| filing empty | read后立刻typed failure，converter/batch 0 | stderr canonical label+empty reason；workspace无mutation |
| filing corrupt PDF/DOCX | deterministic mapper+per-file catch保留cause、closed reason+label | exit1；无traceback/path/raw text；stored0；real sample无xfail/skip |
| filing mixed valid+bad | sequential fail-fast，bad后converter 0 | no company/source/blob publication；第一个valid不计stored |
| filing storage failure | commit OSError/RuntimeError保持typed分类，stored0 | single rollback；published tree SHA不变 |
| label safety | canonicalizer覆盖fragment、Unicode Cc/Cf及合法超长basename；pathful拒绝；reason constructor调用唯一validator，parser不复制规则 | known content kind/code不降级；reason/durable/direct/CLI同一canonical label；无下游特例 |
| material shared count | 仅机械迁移required stored count | existing generic failure/company-first行为保持，无filing断言 |
| unknown CLI error | no business classification | fixed stderr，full operator log |
| direct boundary | success terminal+真实Fins publication positive control | 随后no job/Host/runtime artifacts；Service API无job handle |
| schema break | parser拒绝old/missing/invalid counts/failure keys | `rg`生产/测试无`uploaded_files` |

### 8.2 Focused pytest

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
```

### 8.3 Coverage

```bash
source .venv/bin/activate
coverage erase
coverage run -m pytest \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py
coverage report --include='dayu/fins/pipelines/docling_upload_service.py,dayu/fins/pipelines/sec_upload_workflow.py,dayu/fins/pipelines/cn_pipeline.py,dayu/fins/upload_failure.py,dayu/fins/direct_events.py,dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py,dayu/cli/commands/fins.py'
```

判定：每个修改生产文件目标 `>=80%`；若大型既有文件低于目标，必须报告具体 uncovered branches并补owner行为测试，不得用
`pragma: no cover`、降低阈值或移除正确断言掩盖。

### 8.4 Type check

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

判定：零新增/扩散错误；所有新增/修改函数具有完整中文 docstring（参数、返回、异常），无 `Any`/`object`/untyped payload seam。

### 8.5 Static/no-touch audits

```bash
rg -n '\buploaded_files\b' dayu tests --glob '*.py'
rg -n 'requested_file_count|stored_file_count' \
  dayu/fins tests/fins tests/cli tests/service --glob '*.py'
rg -n '_PAYLOAD_FILE_COUNT|"file_count"' dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py
rg -n 'FinsUploadResultSummary\(' dayu/fins --glob '*.py'
git diff --name-only
shasum -a 256 docs/cli_ci_scenarios.json docs/cli_ci_oracles.json
```

判定：

- 第一条零命中；不得保留兼容字段。
- 第二条所有生产终态构造点都有明确counts，测试覆盖success与四个stored-zero类别。
- 第三条确认progress `file_count`仍存在且有回归；第四条production summary constructor审计恰好覆盖§5.3四点。
- diff只包含§6允许文件；无Host/Engine/runtime/config/storage/Service production/冻结registry/evidence。
- 两个SHA与§1完全一致。

### 8.6 Broader regression

```bash
source .venv/bin/activate
pytest -q tests/fins tests/service/test_fins_direct.py tests/cli/test_fins_commands.py
```

UF-PF03 明确不在任何上述命令或completion report中执行/伪报。

## 9. Risk classification and stop rules

### 9.1 Covered by implementation/tests

- **Count drift（高）**：pipeline/runtime/durable/direct多处构造可能漏字段。用required无默认字段、状态矩阵与零旧字段audit关闭。
- **Derived asset overcount（高）**：用closed provenance和successful original store计数关闭，不以总stored entries测试替代。
- **Filing mixed partial publication（高）**：SEC/CN tracking batch/company/source/blob + published tree SHA直接断言关闭。
- **Public leakage（高）**：fresh reason exact parser、reason constructor调用单一label validator、合法超长basename固定投影、CLI exact
  stderr、caplog cause分离关闭。
- **Material shared-contract regression（中）**：只做机械producer补齐和现有material回归，不扩scope。
- **Direct durable side effect（中）**：filesystem/API/holding-executor负断言关闭，不新增runtime。

### 9.2 Residual but acceptable

- **真实Docling对损坏样本的底层异常差异（中）**：public只承诺closed upload code/reason，不承诺第三方文本；deterministic owner tests
  覆盖映射，已有真实sample保留稳定contract测试且不加无条件xfail/skip；真实多平台evidence归UF-PF03。
- **旧durable summary/failure不可读（显式fresh breaking，低）**：项目schema规则要求全新schema；不迁移、不删除、不兼容旧job record。
- **generic CLI固定文案降低内部细节（低）**：这是预期安全边界，完整细节仍在operator log。
- **Material generic raw failure/company-first publication（中）**：`assigned to later work unit`，owner为Fins material workflow；本次
  shared count迁移不得改变该行为。

### 9.3 Explicitly excluded later work

- UF-PF03真实CLI evidence与冻结状态刷新。
- 日期/年份、alias、format capability、primary/collision、repair、concurrency、company warning对应后续finding。
- material generic failure、bounded stderr与company publication state-machine修订，交后续material work unit。

### 9.4 Open questions

无。用户已确认 `stored_file_count` 为成功发布的用户输入 original 数且derived不计；所有non-ok终态为0。若实施时发现无法从
publication owner取得该事实，必须停止回到goal/plan澄清，不得用request或storage scan补偿。

## 10. Why this is not over-designed

- 只增加两个整数、一个required-key/nullable canonical label、一个empty closed code和一个携带既有reason的typed exception。
- 复用现有validated request、asset provenance、publication result、batch commit、failure reason、direct summary和CLI renderer。
- 不增加数据库/schema migration、storage协议、Host/Engine状态、job、event bus、补偿事务、错误注册表或通用middleware。
- count在唯一生产链传递，failure reason在closed owner产生并由其constructor调用`direct_events`唯一label validator，display label由
  `direct_events`唯一owner canonicalize；parser与下游没有fallback、重复validator、目录扫描、异常字符串解析或consumer特例。
- 三个slice按可验证业务增量拆分：事实count、内容failure、CLI/no-artifact closeout；不是按文件机械拆分，也没有God change。

## 11. Completion report template

实施完成时必须按以下模板报告；任一必填项缺失不得宣称complete：

```text
UF-FIX03 completion report

1. Contract changes
   - requested_file_count owner/value:
   - stored_file_count owner/value and original-only proof:
   - uploaded_files removal audit:
   - progress file_count preservation:
   - failure exact contract / empty code / file_label:
   - provenance strings / fingerprint equivalence:
   - CLI unknown stderr vs operator log:

2. Modified files
   - production:
   - tests:
   - README:
   - explicit no-touch confirmation:

3. Slice results
   - S1:
   - S2:
   - S3:

4. Validation
   - focused pytest command/result:
   - broader regression command/result:
   - per-file coverage result:
   - pyright command/result:
   - static old-field audit:
   - frozen JSON SHA audit:

5. Behavioral evidence
   - success original vs derived count:
   - delete/skip/cancelled/failed stored=0:
   - filing empty pre-converter/pre-batch:
   - filing corrupt PDF/DOCX bounded reason / fail-fast:
   - fragment / Unicode-control / overlength label projection and typed-code preservation:
   - filing mixed input zero publication:
   - commit failure stored=0 / typed classification:
   - material mechanical count regression / unchanged behavior:
   - direct success publication positive control + no Host/Engine/legacy job artifact:

6. Documentation decision
   - root README:
   - dayu/fins README:
   - tests README:
   - Service/Host/Engine no-update reason:

7. Residual risks / not covered
   - UF-PF03 not executed:
   - real Docling platform variance:
   - other frozen findings untouched:
```

## 12. Plan re-review fix gate completion

- 本轮 controller accepted findings N1–N3 已逐项落实：pipeline `cancelled -> stored_file_count == 0` 纳入 constructor owner完整矩阵并有
  constructor/parser tests；合法超长 basename统一canonicalize为固定隐藏标签、pathful仍拒绝且known content kind/code不降级；
  `FinsUploadFailureReason.__post_init__()`调用唯一label validator，parser不复制规则并有direct constructor tests。
- 此前 accepted findings继续保持已修复；旧fix artifact C4关于pipeline不存在`cancelled`的事实错误只在本轮新fix artifact中勘误，
  既有artifact保持只读。
- 当前gate不修改生产代码、测试、README、冻结JSON或evidence，不执行UF-PF03。
- Plan re-review fix status：**PASS**。AgentMiMo 与 AgentDS 定向复核 N1–N3 均通过，artifact 分别为
  `docs/reviews/plan-review-20260813-211608.md` 与 `docs/reviews/plan-review-20260813-211627.md`。
- Next entry point：`implementation S1`；必须按 S1 → review → fix/re-review → accepted slice commit 的 gate 顺序推进。

## Artifact path

`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
