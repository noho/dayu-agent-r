# UF-FIX06 converter-capability-owner 实施计划

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：plan（第二轮 plan review fix 后修订）
- 日期：2026-08-15
- 基线提交：`a3d584fcf1444fcf5d633f2dd8bdb83eaf5adab9`
- 决策：`PLAN FIX COMPLETE / RE-REVIEW PENDING`
- Blocking finding：无
- 下一入口：`re-review`；本 agent 在此停止，不进入 implementation

## 1. 输入与证据边界

本计划只依据以下已读取输入，不把未验证推断写成能力承诺：

- 已确认 goal confirmation：`docs/gateflow/uf-fix06-converter-capability-owner-goal-confirmation-20260815.md`，SHA-256 `2e2729c31930ca2f3b645b3e08f1b87f1d2eee41b87c222fdc05bc9f37ea5929`。
- 项目约束：`AGENTS.md`。
- 架构边界：`docs/host/design.md`、`docs/engine/design.md`。
- Oracle：`docs/cli_ci_oracles.json` 的 `upload_filing.format-owner`；文件 SHA-256 `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。
- Scenario：`docs/cli_ci_scenarios.json` 的 `UF-FIX06`；文件 SHA-256 `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- 冻结 UF-O12 只读证据：
  - `oracle-adjudication.md`，SHA-256 `fe3029cda629d81ce812eb55d50dc414047068ba2bcbad386de46bb54a95b8ff`；
  - `observed-behavior.md`，SHA-256 `e2d3b58954576a2aa1cec3cbc3809134ad34c81d5147df778cef82e7173232c3`。
- 当前相关生产代码与测试，以及当前虚拟环境中 Docling 2.90.0 暴露的 `InputFormat`、`FormatToExtensions` 和 `DocumentConverter` 构造签名。
- 第一轮 plan review 修订输入：`docs/reviews/plan-review-20260815-135206.md`、
  `docs/reviews/plan-review-20260815-135414.md` 与 Controller 裁决
  `docs/reviews/uf-fix06-plan-review-adjudication-20260815.md`。
- 第二轮 plan re-review 修订输入：`docs/reviews/plan-re-review-mimo-20260815.md`、
  `docs/reviews/plan-re-review-ds-20260815.md` 与 Controller 裁决
  `docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`。第二轮 Controller accepted findings
  R1/R2/R3 是本次修订的唯一裁决来源，不重新扩展 goal。

实施不得修改 oracle/scenario registry、冻结 evidence、goal confirmation、Host/Engine 设计文档，不得运行 UF-PF06 或 UF-PF12。

## 2. 第一性原理判断与动机

问题真实存在，且严重性评估成立。

一个文件能否成为 filing primary，成立条件不是“扩展名出现在某个 allow-list”，而是：它属于本产品明确选择的转换能力，并且由实际构造出来的同一个 Docling converter 成功转换。companion 的业务语义不同：它只需被受控接纳并随同一批次原子保存，不应被误当成必须逐个转换的 primary。

当前根因由直接代码和冻结数据同源证明：

1. `dayu/fins/upload_batch.py::FINS_UPLOAD_FILE_SUFFIXES`、`dayu/fins/pipelines/docling_upload_service.py::SUPPORTED_UPLOAD_SUFFIXES` 和真实 `DocumentConverter` 的能力来源相互独立。
2. `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 同时检查两个重复集合，导致 CLI/Fins 声明与真实 converter 漂移。
3. `dayu/fins/pipelines/docling_upload_service.py::_build_pending_assets` 当前转换每个 filing 文件；但 `_pick_primary_docling_file` 又以生成资产顺序选第一个 Docling 文件，已经形成“首文件隐式 primary”的事实，却没有强类型表达。
4. UF-O12 直接记录了 DOC/PPT/PPTX 被 CLI 预拒、XLS 被接受后真实转换失败，以及 CSV/JSON/XBRL/XHTML/XML/ZIP 与不同层声明不一致；HTML primary 加 XSD companion 也被错误预拒。

用户给定方向正确，但实现不应把 Docling 的全部默认格式动态暴露为产品承诺。更小且可维护的方案是：文档转换层声明受控的 typed capability，真实 converter 构造严格消费并验证同一声明；Fins 仅在其上叠加 filing primary/companion 角色与 material 全转换 selection。这样既消除多 owner，也避免无意开放图片、音频等未被本 work unit 证明的产品能力。

## 3. 目标、成功条件与非目标

### 3.1 目标与成功条件

1. converter capability 的唯一 owner 是 `dayu.documents.docling_runtime`：它同时负责声明受控 Docling 格式、投影归一化扩展名、在真实 Docling 导入后校验第三方元数据，以及用同一格式集合构造 `DocumentConverter`。
2. Fins 的唯一角色 owner 是新的 `dayu.fins.upload_format_contract`：它把 converter capability 投影为 immutable typed filing primary/companion selection 与 material selection，不复制 converter allow-list。
3. filing 保持现有公共行为：不新增显式 primary 参数；输入顺序中的首文件是隐式 primary，后续文件是 companions。
4. filing 只转换 primary；companions 读取并作为 raw originals 参与同一个原子发布批次。当前已证明的 companion-only 格式仅为 `.xsd`。
5. help、CLI/Fins 静态校验、batch scanner、Service、LLM-facing tool schema 使用同一 typed contract/projection；删除重复 allow-list，但保留 material 在 converter 前的 admission。
6. primary 转换失败、converter 构造失败、读取失败、取消或存储失败均保持 typed/bounded/atomic：不得产生半发布结果。
7. `requested_files`/`stored_files` 继续统计所有原始输入；primary 派生 Docling 资产不改变这两个用户可见计数语义。
8. material 上传在 CLI 与 tool/Service 入口都由同一 Fins owner 构造 typed selection 并完成 suffix admission；每个输入都是 converter-required，本 work unit 不改变其全转换语义。
9. 所有修改通过受影响测试、逐文件覆盖率目标和 pyright；按 README 触发规则同步文档。

### 3.2 非目标

- 不做 UF-FIX07：不新增显式 primary selector，不解决重复输入、同名文件或 primary 派生名与 companion 名的碰撞。
- 不运行或替代 UF-PF06、UF-PF12，不声称完成真实全格式矩阵或全量 mandatory scenario。
- 不修改日期、财年、ticker alias、company identity、action/state contract。
- 不修改原子发布协议、存储 schema、Host/Engine 生命周期、converter 子进程取消协议。
- 不做 MIME/content sniffing、插件注册、动态能力发现、旧接口兼容 shim。
- 不因为 Docling 默认支持某格式，就自动把该格式宣布为本产品能力。
- 不为 `upload_filings_from` 设计同目录 HTML/XBRL 与 `.xsd` 的自动关联/归组规则；该规则需要新的 identity/association contract，交由后续 batch association / UF-FIX07 类 work unit。

## 4. 架构与语义 owner 决策

| 语义 | 唯一 owner | 产生/校验/投影职责 | 禁止的重复实现 |
|---|---|---|---|
| 本产品选择的 Docling 格式及扩展名 | `dayu.documents.docling_runtime` 的 immutable converter capability | 以不 import Docling 的模块级静态声明产生受控 format id 与产品 suffix 子集；真实构造时 lazy 校验每个 suffix 受对应 `FormatToExtensions` 支持；向 `DocumentConverter(allowed_formats=...)` 传入同一 format id 集合 | CLI、Fins、Service 自建 converter suffix 集合，或把第三方新增 suffix 自动公开 |
| filing primary/companion 角色 | `dayu.fins.upload_format_contract` | 首文件建模为 primary；后续建模为 companions；按角色校验；保序输出 typed selection | consumer 从索引、文件名或生成资产反推角色 |
| companion-only 接纳 | `dayu.fins.upload_format_contract` | 在 converter primary suffix 集合上只增加已有目标/证据要求的 `.xsd` | Service 或 CLI 单独维护附件 allow-list |
| material 格式 admission 与全转换 selection | `dayu.fins.upload_format_contract` | 用 converter product suffix 子集校验每个 material path，产生 `FinsUploadMaterialFiles`；CLI 与 tool/Service 路径均在 converter 前消费该 selection | 仅 CLI 校验、Service raw list、或 Service-local suffix 常量 |
| 格式不受支持的 workflow failure 投影 | `dayu.fins.upload_failure` | 将 `FinsUploadFormatError` 唯一投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，产生 bounded、path-free 的稳定用户消息；SEC/CN workflow catch-all 只消费该投影 | 让异常逃逸既有 event/job failure contract，或由 workflow/Service 重写 kind、code、message |
| 实际转换成功 | 真实 `DocumentConverter` 调用路径 | suffix 只负责确定路由；成功必须以 converter 返回为准 | 用扩展名伪装内容能力或跳过 primary 转换 |
| filing primary_document | `DoclingUploadService` 的 typed preparation result | 直接携带首文件转换产物进入 store，不再扫描生成文件名决定 primary | `_pick_primary_docling_file` 式下游反推 |
| 原子发布、计数、取消 | 现有 upload service / storage batch / process converter owner | 保持现有 commit linearization、rollback、requested/stored、子进程清理 | 新建旁路存储、重算计数或兼容 fallback |

`dayu.host` 与 `dayu.engine` 不拥有财报文件格式或存储语义，本 work unit 不修改它们。`dayu.runtime` 也不承载 Fins 业务角色。

## 5. Contract 设计

### 5.1 Documents converter capability

在 `dayu/documents/docling_runtime.py` 增加严格类型、不可变的 capability（最终命名可在不改变语义的前提下调整），并冻结为静态产品声明与构造期第三方校验两阶段：

- `DoclingConverterFormat`：一个产品选择项，包含稳定的格式标识和该格式被当前产品承诺的归一化 suffix tuple。
- `DoclingConverterCapability`：包含非空 format tuple；提供去重、归一化、只读的 `primary_suffixes` 投影，以及按 suffix 判定的方法。
- `DOCLING_CONVERTER_CAPABILITY`：唯一模块级实例；它只包含稳定字符串 format id 与明确选定的归一化 suffix tuple，模块初始化不 import Docling。CLI help 与 tool schema 只读该静态对象。
- 私有解析/校验 helper：只在现有 converter construction path 被调用时 lazy import Docling，把稳定 format id 解析成 `InputFormat`，并逐项校验“产品声明 suffix ∈ 对应 `FormatToExtensions`”。第三方新增的 suffix 不是产品 contract，不进入 help/schema，也不导致构造失败。

静态产品声明必须直接使用以下模块级字面量 tuple；格式、suffix 成员和 tuple 顺序均已冻结，
implementation agent 不得现场增删或重排：

| 产品 format id | 冻结 suffix tuple |
|---|---|
| PDF | `(".pdf",)` |
| DOCX | `(".docx",)` |
| PPTX | `(".pptx",)` |
| HTML | `(".htm", ".html", ".xhtml")` |
| MD | `(".md", ".txt")` |
| CSV | `(".csv",)` |
| XLSX | `(".xlsx",)` |
| XML_XBRL | `(".xbrl", ".xml")` |
| JSON_DOCLING | `(".json",)` |

上述投影按表格顺序展平后恰为 13 个 suffix，全部小写且顺序稳定：
`.pdf, .docx, .pptx, .htm, .html, .xhtml, .md, .txt, .csv, .xlsx, .xbrl, .xml, .json`。
它是 help、schema 与 batch primary admission 的精确公共契约。第三方同一 format id 还映射的
`.text/.Rmd/.qmd/.xlsm/.potx` 等未选择扩展不进入产品声明；归一化比较后对应的
`.text/.rmd/.qmd/.xlsm/.potx` 也不得被 consumer 接纳。

特别约束：

- `.doc`、`.ppt`、`.xls` 是冻结证据证明不可靠的 legacy 声明，不得保留。
- `.zip` 未被真实 converter capability 证明，不得保留。
- help/schema/batch 只能投影上述 13 个 suffix；`.doc/.ppt/.xls/.zip`、`.xsd` standalone primary
  及第三方同 format 的所有未选择扩展均不得进入 primary projection。`.xsd` 只属于 Fins companion overlay。
- 图片、音频、VTT、LaTeX、JATS、USPTO XML、METS 等即使 Docling 默认枚举存在，也不在本 work unit 自动开放；它们属于 residual product-capability decision。
- `.xml` 的多格式歧义必须通过“本产品明确选择的 `XML_XBRL` + constructor allowed_formats”消除，不能依赖 Docling 默认枚举顺序。help/schema 投影 `.xml` 时必须明说“`.xml` 仅是 XBRL XML candidate，suffix 通过不代表任意 XML 或内容必然转换成功”。`.json` 同样只表示 Docling JSON candidate，不承诺任意 JSON 内容可转换。
- help/schema 投影只能读取上述模块级轻量静态 capability，不得在参数解析/模块导入阶段加载 Docling。
- `build_docling_pdf_converter` 保留现有名字以避免无收益的跨消费者重命名，但构造时必须显式传入由 capability 解析出的 `allowed_formats`。所有 fallback attempt 因调用该 builder 而自动同源。
- constructor `allowed_formats` 必须与静态产品声明中的 format id 精确同源，但 suffix 校验是单向子集校验。若第三方 format id 缺失或任一已声明 suffix 不再被对应映射支持，立即抛出已有 typed runtime initialization error；不得静默缩减、扩大或 fallback 到 Docling 默认全格式。

### 5.2 Fins primary/companion typed contract

新增 `dayu/fins/upload_format_contract.py`，建议包含：

- `FinsUploadFileRole`：`PRIMARY`、`COMPANION`。
- `FinsUploadFormatFailureKind`：`PRIMARY_SUFFIX_UNSUPPORTED`、`COMPANION_SUFFIX_UNSUPPORTED`、`MATERIAL_SUFFIX_UNSUPPORTED`。
- `FinsUploadFormatError`：只携带 failure kind 与安全 basename，不携带绝对路径。
- `FinsUploadFormatCapability`：持有 `DoclingConverterCapability`，另持有 `companion_only_suffixes=frozenset({".xsd"})`；primary 集合始终从 converter capability 投影，companion 集合为 primary 集合并 `.xsd`。
- `FinsUploadFilingFiles`：`frozen=True, slots=True`，字段为 `primary: Path | None` 与 `companions: tuple[Path, ...]`，提供保序 `ordered_files` 与 upsert-only `require_primary() -> Path`。`from_upsert_paths` 接收非空 path tuple，首项成为 primary，其余成为 companions，并逐角色校验；`for_delete` 唯一合法空状态是 `primary=None, companions=()`。
- `FinsUploadMaterialFiles`：`frozen=True, slots=True`，持有保序 `files: tuple[Path, ...]`；upsert 构造入口要求非空，用 converter product suffix 投影逐项校验，所有项均是 converter-required，不存在 material companion。
- 为保持现有 delete 不需文件的语义，两个 selection 均提供明确的 empty-for-delete 构造入口；只有 `prepare_upload` 在 `action=delete` 时可消费空 selection，create/update 必须消费非空 upsert selection。不用 raw list、`None`、默认值或双输入参数表示该状态。
- `FINS_UPLOAD_FORMAT_CAPABILITY`：唯一 Fins 实例。
- 一个稳定的 help/schema projection helper：自足说明 filing 首文件 primary、后续 raw companions、primary 必须实际转换成功、companions 不转换；material 每项都必须转换；并列出由 owner 投影的精确产品 suffix。对 `.xml` 使用 XBRL candidate 限定文案；不得泄漏内部 enum/id。

该模块只负责格式角色，不检查文件存在、regular file、内容、重复、碰撞、日期、ticker 或 storage。

`dayu/fins/upload_failure.py` 是 workflow failure 的唯一投影 owner，必须扩展现有 closed contract：

- `FinsUploadFailureKind` 增加 `USAGE`；
- `FinsUploadFailureCode` 增加唯一格式不受支持 code `UNSUPPORTED_UPLOAD_FORMAT`；
- `fins_upload_failure_from_exception` 显式匹配 `FinsUploadFormatError`，将三个 role-specific
  failure kind 都投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`；message 固定为
  `文件格式不受支持，请选择支持的文件后重试`，`file_label` 取 error 已校验的安全 basename，
  `retry_hint` 固定为 `请查看上传帮助中的支持格式后重试`；
- 该投影不得包含绝对路径、traceback 或第三方异常文本，也不得落入
  `RUNTIME/UNEXPECTED_RUNTIME`；workflow 不得自行复制或重写该映射。

### 5.3 Validation 与错误 contract

`dayu/fins/ingestion_runtime.py` 的静态校验顺序保持逐文件且可预测：basename 安全校验 -> exists -> regular file -> 按位置进行 primary/companion suffix 校验。全部通过后才构造 typed `FinsUploadFilingFiles`。

- `ValidatedFinsUploadFilingRequest` 增加必需、非 Optional 的
  `file_selection: FinsUploadFilingFiles`；不存在 `None` 状态。
- validator 对 create/update 直接产生非空 `from_upsert_paths(...)` selection，对 delete 直接产生
  `FinsUploadFilingFiles.for_delete()`；workflow 只转交 authoritative selection，不再把 `None`
  转换成 delete selection。
- 原始 `request.files` 继续作为请求事实和 fresh validation 输入，不被 selection 替代。
- 旧的 `FILE_SUFFIX_NOT_ALLOWED` 与 `CONVERTER_SUFFIX_UNSUPPORTED` 合并替换为角色明确的 usage code；错误文本固定、中文、bounded、path-free，只显示安全 basename。
- usage failure 仍在 workspace/service mutation 前发生并映射为 CLI exit 2。
- converter 元数据漂移通过现有 construction failure 路径映射为 typed bounded content failure；primary 内容转换失败同样在批次构建前终止。
- material 不经 filing request validator，但不得因此绕过 admission：CLI `_validated_upload_files`
  与 tool/Service workflow 都必须在任何 converter call 前调用
  `FinsUploadMaterialFiles` 的同一 owner 构造入口。material create/update 在 SEC/CN workflow
  现有 `try` 内，且在任何 published-state 读取、company staging、其他业务 mutation、文件读取
  或 converter call 前构造 typed selection；material delete 在同一位置直接产生
  `FinsUploadMaterialFiles.for_delete()`。非法 suffix 必须留在既有 catch-all 与 event/job failure
  contract 内，并由 `fins_upload_failure_from_exception` 投影为上述
  `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，不得让异常逃逸绕过该契约；失败不进入 converter，
  不读取输入文件，不发布 company/source state。Service 保留现有
  exists/regular/empty-content 检查，但删除 Service-local suffix 常量与重复 suffix 规则。

### 5.4 Service 内部准备 contract

`DoclingUploadService.prepare_upload` 不新增 facade。现有其他关键字参数保持不变，只把
`files: list[Path]` 替换为单一 closed union 参数：

```python
selection: FinsUploadFilingFiles | FinsUploadMaterialFiles
```

禁止 raw list 与 role selection 双输入，禁止 `None`/default/fallback 分支。Service 入口首先校验
`source_kind is SourceKind.FILING` 必须对应 `FinsUploadFilingFiles`，
`source_kind is SourceKind.MATERIAL` 必须对应 `FinsUploadMaterialFiles`；不匹配立即抛
`ValueError`，不读文件、不调 converter、不开 batch。随后必须执行双向 action/emptiness
校验：create/update + empty selection 拒绝，delete + non-empty selection 也拒绝，二者均抛
`ValueError`，并且发生在文件读取、converter call 与 batch open 前。delete 只消费对应
source kind 的 empty-for-delete selection，并在读取文件前按现有 delete 分支返回。workflow
直接转交 filing fresh validation 的非 Optional `file_selection`；material workflow 从 raw request
paths 调用 owner 构造入口，delete 则直接使用 `FinsUploadMaterialFiles.for_delete()`。

Service 内部用一个私有严格类型 preparation value 表达：有序 originals、需转换的 inputs、filing 的明确 primary input。

- filing：`ordered_files=(primary, *companions)`，`converter_inputs=(primary,)`。
- material：有序 originals 与 converter inputs 都是全部文件。
- 所有 originals 仍先读取并参与现有空文件检查/source fingerprint；因此 companion 读取或空内容失败仍在发布前终止。
- `_build_pending_assets` 对 filing 只调用一次 converter，对 material 逐个调用。
- filing companion 不产生 `conversion_started` 或任何伪转换事件；它只沿现有 original publication 路径产生正常 `file_uploaded` 事件，事件的 source 保持 `original`，不新增 event type。
- `_PreparedAssetMutation` 增加明确的 `primary_document`（或等价的非可选 typed 字段/分支），由首文件转换结果直接产生并传入 `_store_upload_assets`。
- 删除 `_pick_primary_docling_file`，禁止从 stored entry 名称和偶然顺序反推业务角色。
- pending batch 仍包含全部 originals 和 filing primary 的单一 Docling 派生资产；companions 不生成 Docling 资产。
- 现有 `commit_prepared_upload_batch`、rollback、cancellation checkpoint 与
  `ProcessDoclingConverter` 不变；继续复用 closed failure mapping 机制，只按 §5.2 在其 owner
  增加格式 usage 映射。

## 6. 端到端 call path 与 data flow

### 6.1 Filing

```text
arg help / tool schema
  <- Fins help projection
  <- FinsUploadFormatCapability
  <- DoclingConverterCapability

CLI 或 upload tool 的原始 paths
  -> prevalidate/validate_fins_upload_filing_request
  -> 逐文件基础校验 + 首项 primary/后续 companion 格式校验
  -> ValidatedFinsUploadFilingRequest.file_selection
  -> Service / ProductionFinsUploadRunner
  -> SEC 或 CN/HK workflow fresh validation
  -> authoritative file_selection
  -> DoclingUploadService.prepare_upload(selection=FinsUploadFilingFiles)
  -> 读取全部 originals
  -> 仅 primary 调用 ProcessDoclingConverter
  -> 子进程 convert_pdf_bytes_with_docling
  -> fallback attempt
  -> build_docling_pdf_converter(allowed_formats=同一 capability)
  -> primary Docling 结果 + 全部 raw originals
  -> 单一 pending storage batch
  -> 原子 commit
```

SEC 与 CN/HK workflow 必须把 fresh authoritative validation 得到的非 Optional `file_selection`
原样交给 upload service，不再把 `list(raw_request.files)` 作为无角色输入，也不在 workflow 中把
`None` 转换为 selection。delete selection 已由 validator 直接产生。
`requested_files`/`stored_files` 仍从全部原始文件得到。

### 6.2 Batch、material 与 tool

- `upload_filings_from` 继续按单文件生成独立 upload 命令，每个候选只消费 owner 的
  `accepts_primary`。batch enter 集合精确等于以下 13 个 suffix：
  `.pdf, .docx, .pptx, .htm, .html, .xhtml, .md, .txt, .csv, .xlsx, .xbrl, .xml, .json`；
  每个 suffix 都生成 standalone command。`.doc/.ppt/.xls/.zip`、companion-only `.xsd` 与
  已知第三方未选择扩展 `.text/.rmd/.qmd/.xlsm/.potx` 必须稳定地以
  `unsupported_suffix` skip；其他不在精确 enter 集合中的 suffix 同样 skip。`.xsd` 不作为
  standalone candidate，也不自动与同目录 HTML/XBRL 归组。自动归组明确 deferred 到后续
  batch association / UF-FIX07 类 work unit。
- 本轮 XBRL companion 的产品目标入口是 direct `upload_filing --files primary companion...`；该路径将 companions 与 primary 置于同一原子 publication。
- CLI material 校验复用 `FinsUploadMaterialFiles` 的同一 owner 构造入口；tool/Service material
  workflow 在现有 `try` 内、所有 published-state read/file read/mutation 与 converter 前构造该
  selection，因为 material 的每一个输入都必须转换。failure owner 保证非法 suffix 经既有
  event/job failure contract 投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`。
- CLI `upload filing --help`、upload tool 的 LLM-facing schema 与根 README 三面必须使用一致的业务文案：首文件是 primary 且必须实际转换成功；后续文件是仅原样保存、不转换的 companions；`.xml` 仅是 XBRL XML candidate；suffix admission 不承诺内容转换成功。tool schema 还必须自足说明 material 每项均转换，create/update 与 delete 的 files 要求不变。
- tool runtime 仍构造 raw request；filing 进入同一 Fins validator，material 进入同一 Fins material selection owner，均不建立旁路。

## 7. 必须保持的 invariants

1. 首文件隐式 primary；本 work unit 不引入新参数或重排。
2. suffix 只证明路由资格，不证明内容转换成功。
3. filing primary 必须且只转换一次；companions 不进入 converter。
4. 全部 originals 与唯一 primary Docling 派生资产在同一 storage batch 发布。
5. 任一发布前失败均为零发布；commit 中取消继续遵循既有 linearization。
6. converter 子进程取消、terminate/kill/join 清理和 typed failure kind 不变。
7. 错误 bounded 且不泄漏绝对路径、traceback 或未受控第三方文本。
8. `requested_files == stored_files == 成功保存的原始输入数`；派生 Docling 文件不计入。
9. ticker alias、company identity、calendar date/fiscal period、action/state 校验顺序和语义不变。
10. material 多文件继续全部转换。
11. `prepare_upload` 只接收 filing/material closed typed union，selection 必须与 `SourceKind` 一致。
12. filing companions 无 `conversion_started`，只有 original `file_uploaded`；不伪造转换事实。
13. validated filing selection 永远非 Optional；create/update 只能配 non-empty selection，delete
    只能配 empty-for-delete selection，Service 双向拒绝 action/emptiness 不一致。
14. 不用 `hasattr/getattr`、loose parsing、默认 allow、consumer fallback 或兼容 wrapper 补偿 owner 错误。

## 8. 小 slice 实施计划

### Slice 1：建立真实 converter capability owner

**Allowed production files**

- `dayu/documents/docling_runtime.py`

**Allowed test files**

- `tests/documents/test_docling_runtime.py`

**Exact changes**

1. 增加 immutable typed capability、格式项与 suffix projection，补齐中文模块/类/函数 docstring。
2. 用模块级不可变对象和 §5.1 冻结的字面量 tuple 声明 9 个受控 format id、13 个产品
   suffix 及稳定顺序；该对象的构造与 help/schema 投影均不 import Docling，implementation
   agent 不得增删、重排或从第三方映射动态扩展。
3. 在 converter construction 中 lazy import Docling，解析 format ids，逐项校验每个已声明 suffix 属于对应第三方映射；第三方新增 suffix 不进入产品投影且不 fail。
4. `build_docling_pdf_converter` 显式使用同一 capability 的 `allowed_formats`；现有 PDF options、device/thread fallback、OCR/table 配置不变。
5. 保持 `convert_pdf_bytes_with_docling` 和 attempt/cancellation 调用结构不变。

**Tests / assertions**

- 每个被宣布格式的 format id 可解析，且产品 suffix tuple 逐格式精确等于 §5.1 的冻结声明；
  展平投影精确等于有序的 13 个 suffix，并且它是安装的 `FormatToExtensions` 对应映射的
  子集；断言未声明的第三方 suffix 不出现在静态投影。
- constructed converter 的 `allowed_formats` 与 capability 一致，不包含 legacy 或未选择格式。
- format id 缺失或已声明 suffix 被第三方删除均产生 typed `DoclingRuntimeInitializationError`，不 fallback；第三方新增 suffix 时构造继续成功且 help 不扩面。
- help 所需静态投影不触发 Docling import。
- 既有 fallback attempt、PDF options 和 convert result tests 通过。

**Stop condition**

- 若 §5.1 任一冻结 format id 或 suffix 无法由当前安装元数据和实际 constructor 限界共同证明，
  立即停止并交 Controller 裁决；不得由 implementation agent 移出、替换或扩展冻结 contract。
- 若任一 consumer 要求 help/schema 通过 import Docling 动态产生 suffix，停止并回到 owner 设计；正确路径已冻结为“静态产品声明 + construction-time lazy 子集校验”，实现 agent 不得另行选择。

### Slice 2：建立 Fins role contract 并迁移所有静态消费者

**Allowed production files**

- `dayu/fins/upload_format_contract.py`（新增）
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_batch.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/fins/tools/upload_tools.py`

**Allowed test files**

- `tests/fins/test_upload_format_contract.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_upload_batch.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`

**Exact changes**

1. 实现 Fins typed capability、角色、role-specific failure、`FinsUploadFilingFiles` 与 `FinsUploadMaterialFiles`；两类 selection 均有 upsert 与 empty-for-delete 的明确构造入口。
2. 删除 `FINS_UPLOAD_FILE_SUFFIXES`；batch 改用 owner 的 `accepts_primary`，material CLI 改为构造 owner-owned `FinsUploadMaterialFiles`。
3. ingestion static validation 删除两个 allow-list 的连续检查，按位置建立 selection 并写入
   validated request；`file_selection` 是必需、非 Optional 字段，delete 由 validator 直接写入
   `FinsUploadFilingFiles.for_delete()`。
4. CLI `upload filing --files` help 与 upload tool schema 从同一 projection 生成业务可读文本；两者都要明说首文件 primary、后续 raw companions、companion 不转换、`.xml` 仅是 XBRL XML candidate 以及 suffix 不承诺内容成功。
5. 当前 filing CLI 已通过 Fins request validator 做预校验，不再人为增加一层 CLI filing suffix validation；只迁移仍存在的 material helper。

**Tests / assertions**

- filing `from_upsert_paths` 拒绝空输入，`for_delete` 是唯一空状态；单 primary、多 companion 的构造保序，`.xsd` 仅 companion 可用。
- material 非空 typed construction 保序并逐项执行 converter-required suffix admission；任一非法 suffix 产生 `MATERIAL_SUFFIX_UNSUPPORTED` 且不返回部分 selection。
- legacy DOC/PPT/XLS、ZIP 作为 primary 被 role-specific usage error 拒绝；错误 bounded/path-free。
- 只有 Slice 1 已证明并宣布的 primary suffix 可通过；测试不得为未证明候选硬编码成功预期。
- HTML primary + XSD companion 静态校验成功，XSD 作为首文件失败。
- batch 参数化覆盖 §5.1 每个格式：13 个冻结 suffix 的文件都 enter 并分别生成 standalone
  command；`.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx` 都稳定
  `unsupported_suffix` skip，不生成 command、不自动归组；断言 enter 集合与 13 个 suffix
  精确相等，且 batch 不再引用旧 allow-list。
- validated filing request 的 create/update 直接携带 non-empty selection，delete 直接携带
  `for_delete()` typed empty；所有 action 下字段均非 Optional，workflow 无需二次翻译。
- `--help` 和 LLM-facing schema 自足说明角色、实际转换要求、raw companion 与静态产品投影的确切 suffix；`.xml` 文案不得宣称任意 XML。
- date/ticker/action/state 既有测试原样通过。

**Stop condition**

- 若需要支持 `.xsd` 以外、但当前目标与证据无法证明的 companion-only 格式，停止并交 Controller 扩 scope；不得猜测扩表。
- 若 role contract 被迫承担文件内容、存储或显式 primary selector 语义，停止并重新划分 owner。
- 若 batch 实现需要将 companion 与 primary 自动关联，停止并记入后续 batch association / UF-FIX07 类 work unit；本 slice 必须保持 `.xsd` 稳定 skip。

### Slice 3：让 Service 与 workflows 消费 typed roles

**Allowed production files**

- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/upload_failure.py`

**Allowed test files**

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`（仅在签名/集成断言受影响时）
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_upload_failure.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`（仅直接集成段）
- `tests/fins/test_fins_ingestion_tools.py`（仅 material tool 端到端 admission 断言）

**Exact changes**

1. 删除 `SUPPORTED_UPLOAD_SUFFIXES` 及其重复规则，但不删除 material 前置 admission。将 `prepare_upload` 的 `files: list[Path]` 精确替换为 `selection: FinsUploadFilingFiles | FinsUploadMaterialFiles`，其他关键字参数不变；入口校验 selection 具体类型与 `SourceKind` 一致，禁止 raw list/双输入。
2. SEC、CN/HK filing workflows 在 fresh validation 后原样传递非 Optional authoritative
   `FinsUploadFilingFiles`；material workflows 在现有 `try` 内、任何 published-state read、
   company staging、其他 mutation、file read 或 converter call 前从 raw paths 构造
   `FinsUploadMaterialFiles` 并传入。filing delete selection 由 validator 直接产生，material
   delete 直接使用 `FinsUploadMaterialFiles.for_delete()`，workflow 不做 `None` 转换。
3. Service 保留 exists/regular/empty-content 检查，读取所有 originals；filing 只转换 primary，material selection 中全部文件逐个转换。
4. preparation result 显式携带 primary Docling document；删除 `_pick_primary_docling_file`。
5. companions 仅作为 originals 进入同一 pending batch；不对 companion 发 `conversion_started`，只保留 source=`original` 的正常 `file_uploaded`，不新增 event type。保持现有 source fingerprint、commit/rollback/cancellation 和结果计数 owner。
6. failure owner 增加 `USAGE/UNSUPPORTED_UPLOAD_FORMAT` closed contract，并由
   `fins_upload_failure_from_exception` 将 `FinsUploadFormatError` 投影为 §5.2 的固定 bounded、
   path-free message；同步扩展 `upload_failure_reason_from_json` 的 kind/code 一致性推导，使
   `UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`，同时保持未知 code 与错配 kind/code 拒绝；
   SEC/CN catch-all 继续走既有 event/job failure contract，不允许格式异常逃逸。

**Tests / assertions**

- HTML primary + XSD companion：converter 只收到 HTML；两个 originals 均存储；只有一个 Docling 派生资产；primary_document 指向首文件转换结果；requested/stored 都为 2；XSD 没有 `conversion_started`，仅有 source=`original` 的 `file_uploaded`。
- DOCX + XLSX + DOCX：converter 只收到首个 DOCX；XLSX 与第二个 DOCX 作为 raw companions 原样存储；只有首项的一个 Docling 派生资产；`primary_document` 指向首项转换结果；requested/stored 都为 3，该两个 companion 均无 `conversion_started`。
- corrupt primary + valid companion：typed content failure、converter 只调用一次、零 storage publication。
- companion 读取/空内容失败：发生在 batch commit 前并零发布。
- material 两文件仍转换两次并保持既有 primary/result 行为。CLI 与“LLM upload tool raw
  request -> `ProductionFinsUploadRunner` -> material workflow -> Service”端到端路径上的非法
  suffix 必须在现有 `try` 内被 catch-all 捕获，并经 failure owner 投影为
  `kind=USAGE`、`code=UNSUPPORTED_UPLOAD_FORMAT`、
  `message=文件格式不受支持，请选择支持的文件后重试`、`file_label=safe_basename`；同时断言
  published-state read、company/source
  mutation、文件读取、converter call 与 batch open 均为 0，且既有 event/job failure contract
  收到该投影，异常没有逃逸。
- `USAGE/UNSUPPORTED_UPLOAD_FORMAT` failure reason 的 `to_json()` 结果经
  `upload_failure_reason_from_json` 恢复后与原值相等；未知 code 与已知 code 配错 kind
  继续被拒绝，不得因新增 `USAGE` 放宽 closed contract。
- `source_kind=filing` + material selection 与 `source_kind=material` + filing selection 都在
  Service 入口以 `ValueError` 拒绝。另对 filing/material 两类 selection 分别覆盖
  create/update + empty 与 delete + non-empty 两个方向，全部在 Service 入口以 `ValueError`
  拒绝；所有非法组合均断言零文件读取、零 converter、零 batch。合法 delete typed empty 的
  类型一致性与既有无文件 delete 行为同时回归。
- SEC 与 CN/HK fresh validation 的 selection 被实际消费，不从 raw list 重建隐式规则。
- commit 期间取消、converter interrupt cleanup、storage rollback 的既有 regression 通过。

**Stop condition**

- 若实现需要改变 storage schema、原子 batch 协议或 public explicit-primary contract，停止并交 Controller；不得用文件名扫描或 fallback 绕过。
- 若发现同名/派生名碰撞，记录为 UF-FIX07 residual，不在本 slice 修复。

### Slice 4：文档、全局审计与验证收口

**Allowed documentation files**

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`

**Exact changes**

1. 先遵守各 README 的更新约束。
2. 根 README 更新最终用户可见行为：首文件隐式 primary、后续 raw companions 且不转换、primary 实际转换门槛、`.xml` 仅为 XBRL XML candidate、suffix 不保证内容成功、原子失败；格式清单以 `--help` 为即时真源，不写无法证明的承诺。
3. Fins README 更新开发者 owner/data flow：documents capability、Fins role overlay、首文件一次转换、全部 originals 原子保存、计数与取消不变。
4. tests README 更新本 work unit 的 owner-level 回归范围和命令。
5. `dayu/README.md` 不更新：分层与装配未变化。Host/Engine/config README 均不触发。

**Tests / assertions**

- 运行下节全部 focused tests、静态 owner audit、逐文件 coverage 与 pyright。
- 逐面对照 CLI `upload filing --help`、LLM-facing upload tool schema 与根 README，断言三者一致承诺“首文件 primary、后续 raw companions、companions 不转换、`.xml` 仅为 XBRL candidate、suffix 不保证内容成功”。
- README 不宣称未进入 typed capability 的格式，也不写内部 enum/迁移术语给最终用户。

**Stop condition**

- 任一旧 allow-list、consumer-side suffix set、per-file filing conversion或生成名 primary 推断仍存在，即本 work unit 不得判定完成。
- 任一 changed production file 覆盖率低于 80%、pyright 新增/扩散错误或保护性 regression 失败，停止 closeout 并修复当前 slice。

## 9. 验证计划

实现后先激活 Python 3.11 虚拟环境：

```bash
source .venv/bin/activate
python -m pytest \
  tests/documents/test_docling_runtime.py \
  tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_upload_batch.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_upload_failure.py \
  tests/fins/test_docling_process_converter.py -q
```

保护现有 public/architecture contracts 的追加 regression 应包括现有 storage atomicity、service direct、ticker/date 与 import-boundary tests；实现 agent 只从已有测试文件中选择对应 node，不创建 PF 替代品。

静态 owner audit：

```bash
rg -n 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES' dayu tests -g '*.py'
rg -n '_pick_primary_docling_file' dayu tests -g '*.py'
```

两条命令预期均无结果。另需检查没有新增 consumer-local suffix literal set、`hasattr/getattr`、`Any/object` 签名、兼容 wrapper 或下游 fallback。

覆盖率使用临时目录中的 coverage data，避免污染 workspace；报告必须逐行确认每个 changed production file `>=80%`，不能只看 aggregate：

```bash
source .venv/bin/activate
UF_FIX06_COVERAGE_DIR="$(mktemp -d)"
export COVERAGE_FILE="$UF_FIX06_COVERAGE_DIR/coverage"
coverage run -m pytest <上述 focused tests>
coverage report --include='dayu/documents/docling_runtime.py,dayu/fins/upload_format_contract.py,dayu/fins/ingestion_runtime.py,dayu/fins/upload_batch.py,dayu/cli/commands/fins.py,dayu/cli/arg_parsing.py,dayu/fins/tools/upload_tools.py,dayu/fins/upload_failure.py,dayu/fins/pipelines/docling_upload_service.py,dayu/fins/pipelines/sec_upload_workflow.py,dayu/fins/pipelines/cn_pipeline.py'
```

类型检查：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

最终只读变更审计：

```bash
git diff --check
git status --short
git diff -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md
```

最后一条预期为空；冻结 evidence 位于 workspace 外，必须以本计划记录的 SHA-256 复核保持不变。不得运行 UF-PF06/UF-PF12。

## 10. 风险、残留项与测试断言

| 分类 | 风险/残留 | 本 work unit 的处理 |
|---|---|---|
| Blocking | 无 | 当前 owner、scope 和最小 companion 集合均可由目标与直接证据确定 |
| Capability residual | Docling 默认枚举中的图片、音频、VTT、LaTeX、JATS、USPTO XML、METS 等不是已证明的产品能力 | 不纳入 contract；测试断言 constructed converter 不包含它们；未来需独立产品需求与真实 fixture 证明 |
| Capability residual | 第三方可能删除产品已声明 suffix 或 format id | Slice 1 构造期对“产品 suffix ⊆ 第三方映射”做 fail-fast；第三方新增 suffix 不公开也不失败；由 pinned dependency 与 owner test 管理 |
| Content residual | suffix 合法不代表 DOCX/PPTX/XLSX/JSON/XBRL 等内容一定可转换 | 明确作为实际 converter success gate；失败保持 typed bounded、零发布；真实全矩阵留给 UF-PF06 |
| Companion residual | 当前只证明 `.xsd` 是 companion-only；其他 XBRL 附件类型未知 | 只接纳 `.xsd`；测试明确拒绝未声明 companion，不猜测扩展 |
| Batch association residual | `upload_filings_from` 不会自动把同目录 `.xsd` 归入 HTML/XBRL filing | 本 work unit 稳定 skip `.xsd`；分类为 assigned to later work unit，owner/destination 为后续 batch association / UF-FIX07 类 work unit |
| UF-FIX07 | 显式 primary、重复输入、basename/derived-name collision 未解决 | 保持现有首文件语义；遇到碰撞不加 fallback，留给 UF-FIX07 |
| PF residual | 当前 work unit 不重跑真实 CLI fixture 矩阵与 137 mandatory scenario | 不运行 UF-PF06/UF-PF12；只做本地 owner-level tests，后续由对应 PF adjudicate |
| Regression | material 可能被 filing 的“只转首项”误伤或 tool 路径绕过 admission | 独立 `FinsUploadMaterialFiles` 与 closed union branch；CLI/tool/Service invalid-suffix 回归与多文件全转换测试覆盖 |
| Regression | 改变 validated request 可能误伤 ticker/date/action/state | 不改其 owner与顺序；运行既有 contract tests |
| Operational | 产品已声明 suffix 被第三方删除时，help 仍展示静态声明但运行 fail-fast | 这是有意的安全失败；错误保持 typed/bounded；第三方仅新增 suffix 不会导致该失败；部署兼容性由 pinned dependency 与测试负责 |

没有未分类风险，没有需要实现 agent 自行猜测的 open question。

## 11. 为什么不过度设计

- 核心 domain owner 仍只有两个：documents 管 converter capability，Fins 管 filing/material
  业务角色与 selection；格式失败复用既有 `dayu.fins.upload_failure` 投影 owner，不新增
  registry、plugin、factory 层或 runtime service。
- 复用现有 converter builder、fallback、子进程、storage batch 和 workflow，只收紧它们之间的 typed handoff。
- 继续采用首文件隐式 primary，不提前实现 UF-FIX07 的公共选择协议。
- companion-only 集合只包含当前目标与证据明确要求的 `.xsd`，不做 MIME 推断或附件生态设计。
- 保留现有函数名和调用结构，只删除重复 allow-list 与下游反推；避免无语义价值的重命名和 facade。
- 产品 suffix 只是第三方映射的受控最小子集；构造期只做 lazy 支持性校验，help 只读轻量静态投影，避免把依赖升级变成产品自动扩面。

## 12. Plan gate 完成报告

- 完成内容：基于确认目标、架构、oracle/scenario、冻结 UF-O12、当前代码/测试及两轮
  Controller accepted findings，修订为 4 个 code-generation-ready slices。
- 第二轮 R1：`已修复`。failure owner 冻结
  `USAGE/UNSUPPORTED_UPLOAD_FORMAT` 与固定 bounded/path-free message/file label 投影；
  `upload_failure.py` 及新增 owner test 已纳入 Slice 3；material selection 构造点固定在 workflow
  现有 `try` 内且位于所有 external read/mutation 前；端到端测试断言投影和零副作用。
- 第二轮 R2：`已修复`。逐格式冻结 9 个 format id、13 个小写有序 suffix；help/schema/batch
  只能精确投影该集合，batch enter/skip 集合与测试已钉死。
- 第二轮 R3：`已修复`。validated filing selection 改为必需非 Optional；validator 直接产生 delete
  typed empty；workflow 不再翻译 `None`；Service 双向拒绝 action/emptiness 不一致并测试零副作用。
- 允许的下一动作：`re-review`。
- 未执行：生产代码、测试、README、registry/evidence 修改；UF-PF06、UF-PF12；commit。
- Gate 结论：`PLAN FIX COMPLETE / RE-REVIEW PENDING`，blocking finding 为 0；当前 fix 不等于 review 通过，下一入口是 `re-review`。
