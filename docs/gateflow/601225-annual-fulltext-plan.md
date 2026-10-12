# 601225.SH 年报全文普通增量：最小实施计划（plan fix r3）

- Work unit：`601225-annual-fulltext`；本文是 `plan review → fix` 修订稿，尚未复审通过、未实施。
- 分支 / 基线：`fix/601225-annual-fulltext` / `7637bb0b4fbca212a4db0f4cfc09655e66516695`。
- Binding scope：[目标确认](601225-annual-fulltext-goal-confirmation-20261012.md)；直接证据：[根因报告](601225-annual-fulltext-root-cause-evidence.md)；决定：[初轮裁决](601225-annual-fulltext-plan-review-adjudication.md)、[r1 总控裁决](601225-annual-fulltext-plan-rereview-r1-adjudication.md)、[r2 总控裁决](601225-annual-fulltext-plan-rereview-r2-adjudication.md)。无其它 design document。
- 本轮只修订本文并交付 [r3 fix artifact](601225-annual-fulltext-plan-fix-r3.md)，不实施生产代码/测试/依赖/README、不 commit/push/PR、不操作其它 Agent、不修改总控 state、原证据或其它 review artifact。
- r2 双路实际退出 0/completed（MiMo fail、DS pass），原四项 accepted 均已计划层修复并由总控保持闭环。本稿只补 MiMo-r2-01 的现有 JSON canonical 表示及两个非阻塞 OQ；总控裁决为低严重度规格缺口，原高严重性高估。已闭环的 HTTP observer、shared protocol、来源字段、grammar、原件读取/异常作用域/identity/GET 集合等保持；MiMo6 的 scope 扩张判断仍 rejected-with-reason，不拆市场协议、不新增 CLI provenance/schema。本稿不宣称复审通过。

## P0：目标、必要性与边界

普通公开 `dayu-cli download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12`，在独立 base、非 overwrite / 非 rebuild 下，发现、获取、转换并保留官方全文 1213161683 / 1219815158 / 1223301988，分别归属 2021 / 2023 / 2024 财年；独立摘要 1213161682 / 1223301999 不能冒充或阻挡全文。再增量对已经持久化的合法 COMPLETE 来源零 PDF GET、零转换，不以公司、公告 ID 或年份写生产特例。

动机成立且最小修复同时需要 selection 与 identity。当前真实原参数 FY 响应完整返回 19 条，三条全文在其中；现有选择把无年份全文投影为披露年并在跨年竞争中淘汰。两条隐藏摘要原文明确是摘要；CN 财期 ID 与 COMPLETE skip 又会独立阻挡已正确投影的全文。财年与全文性质只从官方原文首页证实，不按披露年减一、同日兄弟公告、页数、大小或分类数值猜测。历史 raw 和启动树未冻结，当前重现不冒充历史全链。

非目标：其它公告、一般日期/H1/Q 规则、OCR、财务提取、通用分类平台、调用方工程、历史迁移/自动清理/全面恢复、overwrite/rebuild 重设计、Host/Engine 架构。保持巨潮 category/分页请求、披露窗、默认 limit、原摘要文件和合法完整源。不新增候选持久缓存，不以 loose parsing、fallback、伪造 accepted/rejected 集合或放宽 storage 达到目标。

只有一个行为 slice **S1：官方 FY 原文确认 → 正确年度选择 → 独立来源增量保留**。它需要一次完整实施与审核，按模块拆分会留下“财年改对但仍被摘要挡住”的中间行为。下列实施顺序是 S1 内的验证顺序，不增加 gate/slice 或未授权提交。

| 决策 / 验证 | 已确认目标 / success signal |
| --- | --- |
| P2 原文 facts 与完整跨年选择 | 正确财年、摘要不冒充、同源根因；SS1/2/4 |
| P3 完整性前置拒绝、本地复用与 prepared handoff | 安全增量、零重复合法完整源获取；SS2/3/4 |
| P4 来源绑定、publication 连续性与 repair 边界 | 摘要不阻挡且保留、取消/失败不伪造成功；SS2/3/4 |
| P5 三条新 acquisition boundary matrix 与共享回归 | owner contract、现有合法行为；SS4 |
| P6 真正 bare CLI clean/seeded/repeat 与实际网络观察 | 三全文、摘要保留、零完整源 GET/转换；SS2/3 |

不变的官方取证与 432 测试 / pyright 基线不必重跑；它们不能充当本修复验证。必要性只覆盖上述行为，没有扩大 goal。

## P1：语义 owner 与精确文件边界

| owner | S1 allowed files / changes |
| --- | --- |
| PDF 首页业务事实 | 新 `dayu/fins/pipelines/cn_annual_report_facts.py`：纯提取/封闭 grammar，不做 HTTP、storage、Docling、OCR |
| 当前 snapshot 的 CN 年度原件投影/读取 | 新 `dayu/fins/pipelines/cn_annual_report_source.py`：P3.2 唯一声明角色投影与 exact revision PDF 读取，供 workflow/filing 直接复用；不解析年度 facts、不做远端刷新或写入 |
| typed acquisition/发现交付 | `dayu/fins/pipelines/cn_download_models.py`、`cn_download_protocols.py`：P2/P3 DTO、必填输入/结果、验证与作用域文档 |
| HTTP、raw provider 字段与实体校验 | `dayu/fins/downloaders/cninfo_downloader.py`：原请求保持；FY facts 获取、本地同源复用、同次 prepared 输出；真实 GET diagnostic |
| CN/HK selection | `dayu/fins/pipelines/cn_report_selection.py`：CN FY 原文年/类别与统一准入；H1/Q/HK 规则不改，仅接入必填结果/来源字段 |
| source integrity | `dayu/fins/storage/source_integrity.py`：P3.1 的窄纯 inventory 校验，完整 final classifier 复用它；无仓储读写/授权，无 schema 变化；直接从此模块导入，不加兼容 re-export |
| 请求编排与发布 | `dayu/fins/pipelines/cn_download_workflow.py`、`cn_download_filing_workflow.py`、`cn_download_source_upsert.py`：本地 snapshot 输入、prepared/witness 交接、A/B/repair、真实来源值持久化 |
| CN 来源 ID | `dayu/fins/pipelines/cn_download_identity.py`：仅 CNINFO FY 新来源绑定/碰撞；`cn_form_utils.py` 原财期 seed 不改 |
| shared protocol 实现迁移 | `dayu/fins/downloaders/hkexnews_downloader.py`：签名接收，CN tuple 必须为空，prepared/local witness 返回空；HK 不使用 gate，不改变发现/未知报告规则 |
| 依赖 | `pyproject.toml` 声明 `pypdf>=6.1.3,<7.0.0`；`constraints/lock-common-py311.txt` 固定 `pypdf==6.1.3`；**requirements.txt 不改**，平台 lock 继续继承公共 lock |
| owner tests | 新 `tests/fins/test_cn_annual_report_facts.py`、`test_cn_annual_report_source.py`、`test_source_integrity_preflight.py`；现有 `test_cninfo_downloader.py`、`test_cn_report_selection.py`、`test_cn_download_models.py`、`test_cn_download_identity.py`、`test_cn_download_workflow.py`、`test_cn_download_runtime.py`、`test_hkexnews_downloader.py`；`test_cn_pipeline.py`、`test_f5_workflow_rebuild.py` 必要协议/fixture 迁移；运行 `test_hk_period_rebuild.py` 共享 fake/helper 回归，不新增 HK 业务或改变其断言 |
| 有界 fixtures | 新 `tests/fins/fixtures/cninfo_annual_fulltext/`：原 19 条 raw、13 个首页派生 PDF、来源/hash 清单；不捏造年/raw；全量原件留在原证据根 |
| 独立验收辅助 | 新 `utils/validate_601225_annual_fulltext.py`（seed/verify/coverage/compare）、`utils/observe_601225_cli_http.py`（只观察所启动验证 CLI）；运行记录与临时 bootstrap 在 `workspace/tmp/` |
| 实施后的文档 | 根 `README.md`、`dayu/fins/README.md`、`tests/README.md`，按 P7 各自读者职责更新 |

禁止改 storage schema、repository protocol / Fs 实现、CLI / Service / Host / Engine / ingestion adapter、日期工具、调用方目录或总控 state。source_integrity 的新增 helper 是总控明确准许的 owner 修订，不授予仓储写权限。所有新增/修改函数与类提供中文 docstring、严格签名、模块级辅助函数；不引入 Any/object/kwargs/hasattr/getattr/lazy-import shim。协议调用点迁移已完整列在 P3.6；出现清单外真实调用点先交总控具体 blocker，不靠兼容默认值绕过。

## P2：FY facts、封闭首页 grammar 与 selection

### P2.1 typed 事实与来源

`cn_download_models.py` 新 frozen/slots `CnAnnualReportFacts(fiscal_year: int, kind: Literal['full','summary'])`：非 bool、1000..9999 四位财年，类别严格封闭，非法字段 TypeError/ValueError。它只表示原文事实。

`CnReportCandidate.fiscal_year_source: Literal['title_or_category_inferred','source_document']` 为必填字段。生产两处 candidate builder 与所有测试构造点显式迁移：CN FY selection 为 `source_document`；未变更的 H1/Q/HK 为 `title_or_category_inferred`。source upsert 消费 candidate 的该字段，不再写死旧常量；既有开放 meta 字段准确增加取值，无 DB/CLI 新字段、兼容读取或迁移。source_title 保留官方索引原文，report_date 继续 None。candidate、FILING_STARTED、source meta、runtime/CLI 中财年同源；snapshot witness 不持久化、不投影给 CLI/LLM。

### P2.2 精确 grammar

提供 `resolve_cn_annual_report_facts(pdf_bytes: bytes) -> CnAnnualReportFacts`。仅调用 `pypdf.PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()`；无零页/空页或加密无权限时失败。内部模块级 `_resolve_cn_annual_report_text_facts(text: str)` 负责以下规则，PDF 和文字 contract 测试均可直接检验。

1. 保留 `splitlines()` 的物理行边界；每行去掉 Unicode 空白字符（仅在该行内），**不得先把整页折叠成一个字符串**。这样 label 的行尾是明确定界，不把未知后缀截断。
2. 每行扫描 base pattern `(?<![0-9])(?P<year>[1-9][0-9]{3})年?(?:年度报告|年报)`。一行最多一个 base；其前缀允许原首页页眉中的公司全称，不从前缀得财年。超过一个 base、五位年内截取、非 ASCII 年份均拒绝。没有 base 的行不产生 facts。
3. base 到**该物理行尾的全部剩余文字**必须 fullmatch 以下 suffix：空串表示 full；`摘要`、`(摘要)`、`（摘要）`、`[摘要]`、`［摘要］`、`【摘要】` 表示 summary。summary 前可有一个 `:` 或 `：`，full 后不能单留冒号。可直接实现 summary pattern `(?:[:：])?(?:摘要|\(摘要\)|（摘要）|\[摘要\]|［摘要］|【摘要】)`。suffix 有任何其它文字或未匹配括号都拒绝，禁止 optional `摘要` 未匹配就默认 full。
4. 收集全部 label，要求唯一 `(fiscal_year,kind)`，同年同类重复页眉/封面允许，不选首个。每行剔除已消费的整个 label 后，剩余首页文字中若还含 `摘要`，也拒绝；因此 `年度报告\n摘要` / `年度报告\n（摘要）` 是不支持的跨行标签，显式失败而非 full。不为它们扩 OCR/泛化标签。
5. 无 label、不同财年、full/summary 混合、未知 suffix、PDF 提取失败均抛 `ValueError` 并保留 cause。提取函数只在包住 PdfReader/首页访问/extract_text 的同步 try 内捕获 Exception 并转 ValueError，grammar 本身直接 ValueError；checkpoint/gate/storage 不进入这个 try，BaseException 控制流不捕获。parser 不用披露年、meta 财年、页数、size、announcementType 或 sibling 公告补救。

当前 13 份官方原件正例（生产不写此表）：

| source_id | 财年 / kind | source_id | 财年 / kind |
| --- | --- | --- | --- |
| 1204545056 | 2017 / full | 1205110621 | 2017 / full |
| 1206005283 | 2018 / full | 1207678369 | 2019 / full |
| 1209875597 | 2020 / summary | 1209875598 | 2020 / full |
| 1213161682 | 2021 / summary | 1213161683 | 2021 / full |
| 1216619553 | 2022 / full | 1219815158 | 2023 / full |
| 1223301988 | 2024 / full | 1223301999 | 2024 / summary |
| 1225178190 | 2025 / full | — | — |

必须补语法正例：六种 summary suffix、普通/全角空白、冒号摘要、带公司前缀、重复同事实。必要反例：`年度报告摘要版`、`年度报告说明`、`年度报告补充`、`年度报告（未知）`、`年度报告（摘要]`、`年度报告：`、跨行摘要、同页两年/混类、一行两标签、五位/全角年份；再加空/损坏/零页/加密/无标签 PDF。合成反例只是 grammar 测试，不冒充官方证据。对其它布局的限制作为 residual，不用悄悄扩目标。

### P2.3 selection 真源

selection 公共窄 helper `is_cninfo_report_title_admissible(title: str) -> bool` 是现有 `_is_title_blocked` 的唯一准入判断（改名/迁移使用，不保留透传兼容 wrapper），downloader 与 selector 共用。显式标题摘要仍零 PDF GET。

`select_cninfo_report_candidates` 新必填 `annual_facts_by_source: Mapping[str,CnAnnualReportFacts]`。map 为本次 secCode/PDF 合法、请求 FY/window 内、标题准入 raw 的 source_id → 事实；缺事实或多余/重复身份为 contract 错误，不能旧年 fallback。FY summary 排除，full 以原文年分组；H1/Q 仍原 `_infer_cninfo_fiscal_year`。原 amended → filing date → 非正文 → source ID/URL 平手排序保持。完整 19 条任意顺序应选 2017–2025 九条 full，2017 修订胜原版，2020 隐藏摘要不能胜全文，三目标不再与后续财年竞争。

同次 FY raw 重复 source_id（无论同/不同 URL）在获取 PDF 前拒绝为不可重试 typed provider PROTOCOL，不覆盖 map 或重复 GET；不新增跨财期去重规则。raw 与日期工具保持原归一；准入 PDF 只限 query 披露窗，workflow 原分财期窗/limit 最终裁剪不变。

## P3：I/O 顺序、snapshot 关系与失败作用域

### P3.1 两次 integrity 检查，权限严格分离

在 source_integrity owner 新增 `validate_source_integrity_inventory(inventory: tuple[SourceIntegrityClassification,...]) -> None`，纯函数按既有优先序：任何 UNSAFE → `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`；否则多于一处 REPAIR_REQUIRED → `MULTIPLE_REPAIR_REQUIRED`；clean 或唯一 repair → 返回 None。它不返回 repair disposition、不接受候选集合、不认可唯一 repair。现有 `classify_source_integrity_preflight` 首先复用此 helper，随后原 selected/rejected/material 判断保持不变。

CN 且请求含 FY 时，workflow 在 resolve_company / discovery / 新本地年度原文读取之前，通过 `list_source_integrity(ticker)` 的现有同 guard inventory 调用此 helper（checkpoint 前后）。这使早已存在的 UNSAFE/多损坏优先于 PDF transport/parser 故障；不靠 accepted=全部 inventory 伪装选中。既有 inventory 自身可能为完整性 hash 读取文件，这是 storage 真源已有行为；本轮限制的是新增 facts snapshot/字节读取，不删改既有完整性检查。

discovery / 真实 selection 之后，保留原 final selected preflight：**新读**完整 inventory，用这次真实 selected 经新鲜 identity index 解析的 ID 建 `accepted_filing_ids`，`rejected_filing_ids` 仍为空。旧摘要未被选择就不能塞进 accepted/rejected。唯一 repair 到此才可能变成 SelectedSourceRepairRequired；发现期间新增 UNSAFE/多损坏仍可被新窗拒绝。两个 inventory 不是共享事务，不授予后续任何写入权。

### P3.2 完整本地原件输入、共享原件 owner 与 publication witness

models 新 frozen/slots：

- `CnAnnualReportPublication(provider: Literal['cninfo'], source_id: str, document_id: str, revision: SourceDocumentRevision)`：同源唯一键、exact 本地 ID、opaque revision；非空/严格类型。它是只读 witness，不是写 capability。
- `CnAnnualReportPdf(publication: CnAnnualReportPublication, source_url: str, pdf_bytes: bytes)`：同一 full snapshot 的实际 locator 与非空原件 bytes。provider/source_id 从 publication 取，不重复字段。URL 是 locator，不参与 source key。

workflow helper `_read_local_cn_annual_pdfs(ticker: str, period_windows: tuple[PeriodDownloadWindow,...], source_repository: SourceDocumentRepositoryProtocol, cancellation_checkpoint: Callable[[],None] | None) -> tuple[CnAnnualReportPdf,...]`：没有 FY 窗就立即空返回、零新增 snapshot/byte 读取。已有早期 inventory 只作安全拒绝；helper 新读 `read_source_meta_integrity_view(ticker,FILING,batch=None)`，对新观察分类也执行 P3.1 helper，避免已观察的 UNSAFE 被后续 parser 遮蔽。

discovery 预读只对该同窗 entry 的 COMPLETE 且 source_provider=cninfo、ingest_method=download、fiscal_period=FY、is_deleted 精确 False、filing_date 落请求 FY 有效窗内者调用 full snapshot。provider/来源/日期是严格 metadata 读取，非法 eligible 身份/日期拒绝，不根据旧 meta fiscal_year 选范围或认定 facts。此预读阶段的范围外、其它财期、非 COMPLETE 零新增 materialized snapshot、原文 open/read；不读取无关历史 PDF 来解析财年。P4 filing exact target 不受这项缓存 eligibility 豁免，读取范围仅为其当前 COMPLETE target。全量 metadata/integrity 枚举仍属既有 owner，不承诺全仓零物理 I/O。

在新窄模块 `cn_annual_report_source.py` 固定以下公开契约，workflow/filing 均直接导入，不在两个消费者分别解析 raw role，不依赖 filing 模块产生反向依赖：

- `CnAnnualReportSourceError(ValueError)`：唯一有界安全文本“本地年度报告缺少可信且唯一声明的 PDF 原件，无法确认原文”；表示 original 声明/descriptor/实际 bytes 无法建立所需关系，不是完整性调度类型，不持有路径或 raw metadata。
- `project_cn_annual_report_original(snapshot: SourceSnapshotProtocol) -> SourceSnapshotFileDescriptor`：纯投影，不 acquire/open/read。只从 `snapshot.source_meta['files']` 选择**唯一显式 `source='original'` 条目**，要求其 `content_type='application/pdf'`、非空 exact name；该 name 在 `snapshot.files` 唯一命中，媒体类型及存在的 size/SHA 与声明一致。无角色/零 original/多 original/非 PDF original/声明与 descriptor 不一致均抛上述 typed source error。缺省角色即使只有一个 PDF 也不猜；不从 filename、URI、URL、排序、primary 或 SDK 名称推断 original。Optional size/SHA 沿既有协议，不创造必填字段。
- `read_cn_annual_report_pdf(ticker: str, document_id: str, expected_publication: CnAnnualReportPublication, expected_meta: Mapping[str,JsonValue], source_repository: SourceDocumentRepositoryProtocol, cancellation_checkpoint: Callable[[],None] | None) -> CnAnnualReportPdf`：唯一新增 I/O owner。调用前的同窗分类须为 COMPLETE，expected_publication 从该分类的非 None revision、严格 provider/source_id、exact document_id 产生；expected_meta 必须为同 entry.source_meta。内部只 acquire `read_source_snapshot(ticker,document_id,FILING,materialize_files=True)`，在 `with` 内先核 ticker/kind/document_id、provider/source_id/revision 与 expected 完全相等，且 provider/source_id、ingest_method、is_deleted、filing_date、fiscal_year、fiscal_period、covered_fiscal_periods 与 expected_meta 的值严格相等；不等即 RevisionConflictError（这里验证同版而非用meta年推断facts）。通过后才用上述 projection 精确取得 original。snapshot 的 source_url 必须满足下述严格非空 string predicate；用 `snapshot.get_source(descriptor.name).open()` 读取，size/SHA 与声明/descriptor 存在值再核；成功返回同 snapshot 的 publication、实际 locator、不可变 bytes。无 facts/HTTP/写授权，不保留 Source/snapshot，正常、异常、取消均关闭 stream/snapshot。checkpoint 固定在 acquire 前/with 内成功 acquire 后、open 前/read 后、with 退出后。不提供 batch 参数，因为真实 snapshot API 只读 published。

同 snapshot 的 expected_meta 校验是 **raw JSON ↔ raw JSON**：两侧分别为同窗 entry.source_meta 与 snapshot.source_meta，`covered_fiscal_periods` 比较各自 JSON list 的原值，不与 candidate tuple 比较、不拼 candidate 投影、不转换或重排任一持久值。这里仅证明同版；P4 的 candidate 业务匹配另在 filing owner 进行。

本地 source_url predicate 精确为 `type(source_url) is str and source_url != ''`；缺失、非 string、空 string 抛 `CnAnnualReportSourceError`。满足 predicate 就原样保留实际取得原件时的 locator，包含空白也不 trim/normalize；不解析它来参与身份、发起 HTTP 或反推 source/year。远端 URL 仍由原 provider owner 产生/消费，不新增一般 URL parser、absolute-http(s) 校验框架或兼容转换。

helper 的 revision/身份变化（含 exact target 消失）抛 `SourceIntegrityRevisionConflictError`，不当 cache miss。snapshot acquire 若因 `ValueError` 拒绝 COMPLETE 读取，仅在该异常发生后用现有 exact `classify_source_integrity` **一次**核对原因：UNSAFE→PreflightError；否则 missing/revision 改变→RevisionConflictError；同 revision REPAIR_REQUIRED→RepairRequiredError；仍同 revision COMPLETE 则原 ValueError 透传。核对读取自身错误原样传播并保留原 cause；不从异常文本重判、不重取 snapshot。acquire 的 FileNotFoundError→RevisionConflictError；`SourceSnapshotConsistencyError`、其它 OSError/guard 错误原样传播。snapshot 成功后 projection/bytes 不一致仅为 CnAnnualReportSourceError，不伪造 storage 分类。checkpoint 不在这些 mapping try 内，原控制异常透传。

workflow `_read_local_cn_annual_pdfs` 的 eligible 判断仅使用上段 provider/ingest_method/FY/active/date/COMPLETE，**不以是否有 original 角色作静默过滤条件**。每项通过此 helper，expected_meta 显式传同窗 entry.source_meta；filing A 同样传当前 target entry.source_meta。只核同版范围字段，不使用旧 meta 财年判断 facts，不加入 callback/query/profile 或其它隐式读取。

projection 与读取分离、facts 仍只由 P2 pure owner 解析；workflow/downloader 本地 parser 前后 checkpoint，成功的本地 facts 只有经 selection 确认为 selected full/year 后才将 publication 作为结果 witness 交付。因此 witness 表示**该 revision 的实际 original 已确认 full/财年**，仅由这条 owner 链产生，不是从 COMPLETE/meta 年份裸造。eligible source 的角色不足在 workflow 映射为 P3.5 的 discovery PROTOCOL 原文失败，不能继续 GET 掩盖本地证据缺口；其他 storage/完整性异常仍原类型。

范围外/不同 ingest_method 源只是不进入 discovery 预读缓存，不能由此豁免后续 exact target COMPLETE 证明（P4.2）。snapshot 为既有全文件物化接口，会复制**所选范围内 source**的 PDF/Docling；不改 storage API。重复 `(provider,source_id)` 本地输入拒绝，不按 URL 去重。角色、日期、ingest_method 没有新持久 schema/历史迁移或远端刷新语义。

### P3.3 必填发现输入与显式 handoff

`list_report_candidates` 保留 query/profile/local_annual_ends/cancellation_checkpoint（已有 optional 取消参数不改），新增两个**必填 keyword-only** 参数：`local_cn_annual_pdfs: tuple[CnAnnualReportPdf,...]`、`pdf_download_gate: CnDownloadPdfGateProtocol`。HK 显式收空 CN tuple，不消费该 gate；CN local_annual_ends 仍空。公共CLI现装配为既有NoopCnDownloadPdfGate，本轮只沿原gate契约，不新增调度/限流能力。

downloader 完成原各财期 raw POST/分页后，对 FY 准入 raw 用 `(cninfo,announcement_id)` 查 local tuple，**不比较 URL**。命中用 snapshot 实际原件 facts；raw scheme/path/locator 变化不 GET、不改旧 locator。不命中才在原 gate 内调用 HTTP 实体读取与原 PDF magic/min-size 校验；抽取原校验窄 helper 由 discovery 和 download_report_pdf 共用，不另造 retry/throttle/PDF规则。GET 后同一 bytes 计算 SHA/size/取得时间、交 facts。发现内保留不可变同次 payload；无跨调用 cache、无提前持久化。

REPAIR_REQUIRED 不能提供可信 local 完整原件，故不进入 local tuple。索引标题未声明摘要的 raw FY，即使同 source 的历史原件损坏，也允许**必要 discovery facts GET**：正常单 attempt 无重定向/外部故障时该 raw 原件恰好 GET 一次、一次 gate lease，不做 HEAD/title/meta kind 推断；原 HTTP retry/redirect 契约不改，其实际次数须如实记录。确认 summary 后立即丢 bytes、不输出 prepared/witness、不转换；最终若是 unselected repair，仍按 P4.4 typed 零业务写入拒绝。“不重下摘要”只表示不作为 repair target 重提交、覆盖、删除或修旧资产，**不禁止这次只读 facts GET**。获取/校验/parser 失败走 P3.5 整次 discovery 失败，不预造 unselected summary、accepted/rejected 或 durable kind。

`CnReportDiscoveryResult` 必填增加：`prepared_assets: tuple[DownloadedReportAsset,...]`、`local_annual_publications: tuple[CnAnnualReportPublication,...]`。prepared 只包含**远端本次取得且最终选中** FY full；local witness 只包含**本地事实产生且最终选中** FY full。未选中的摘要/全文 payload 和 witness 在本次调用结束释放，不存库、不随结果返回。CN uncertain_reports 仍显式空；HK 两个新增结果均空。

result owner 在构造时校验：candidates source key 唯一；prepared 与 local witnesses 各自 source 唯一且互斥，准确命中 CN FY candidate；prepared.candidate 必须与最终 candidate 所有字段相等（生产直接使用同一选中实例），其中 ID/provider/URL/facts provenance一致；prepared SHA-256 与实际 bytes、content_length 与 len(bytes) 一致，downloaded_at 为取得时间，不能拿 HEAD 长度当 bytes 长度；local witness 与同源 selected 的绑定唯一。定义公开纯 contract helper `require_matching_cn_annual_asset(candidate: CnReportCandidate, asset: DownloadedReportAsset) -> None` 在 models 复用这些 prepared 字节/候选约束；不为旧 fake 留松校验。字节 magic/min-size 仍归 provider owner，FY事实仍归 facts owner。

workflow 在 `_select_candidates_for_a4` 裁窗/limit 后仅交付保留 candidate 的 asset/witness，按 source key 精确索引，显式传 `prepared_asset: DownloadedReportAsset | None`、`local_annual_publication: CnAnnualReportPublication | None` 给单 filing；禁止下游从日志/时间戳/顺序反推。两个入参必填、不可同存，不影响非 FY/HK的None路径。

### P3.4 checkpoint 与错误优先级

使用 workflow 已有 checkpoint（取消原对象透传），不能把 checkpoint 异常包进 parser/provider error。新增精确边界：

| 位置 | checkpoint / 保留行为 |
| --- | --- |
| 早期 inventory、metadata integrity view | 调用前/返回后；取消即停，无 snapshot/PDF GET/业务写入 |
| 每个 eligible source | full snapshot acquire 前/成功返回后、original open 前/read 后、with退出后；成功 acquire 后 checkpoint须在with内，保证取消也close |
| 本地 facts | parser 前/成功返回后；失败只映射 parser 本身，取消不映射 |
| 每个 raw POST/分页 | 保留已有请求前/响应后；所有 FY raw 收齐后、重复source检查后再取原文 |
| 远端原文 | gate acquire 前、lease 内 GET 前、HTTP每个重试 attempt 前/成功响应后、PDF校验前/后、parser前/后、lease退出后 |
| selected handoff | result返回后、final identity/preflight前后、每个FILING_STARTED前；之后沿原filing的转换/事务边界 |

gate bool cancel_checker 用模块级 `_check_cninfo_gate_cancellation(checkpoint: Callable[[],None] | None) -> bool` + partial：执行 checkpoint 后返回 False，异常原样抛出；不新增嵌套函数或把 callback 塞 query/profile。HTTP原循环新增可选内部checkpoint传递只供新发现读取使用，单 filing使用现有cancel_checker；不能在 except httpx.HTTPError 内捕获取消。parser仅捕获其提取/语法异常；storage、gate、cancel异常不误归provider。

优先序是阶段顺序：checkpoint命中先退出；已经观察到的 UNSAFE优先多损坏；早期安全通过后，storage读取故障/发现 HTTP或parser故障按实际发生传播；final新窗裁决新增完整性问题；不为取得“更优错误”在失败后继续I/O。无法在短 guard之外阻止并发损坏，因此 final/A/B仍必需，不能声称早期check冻结ticker。

### P3.5 失败作用域（明确修订原 protocol 文案）

CN FY 原文 facts 是**完整 discovery 所需的事实**。任意准入FY（即使后来可能落选）获取/校验/解析失败，`list_report_candidates` 整次抛错，不返回部分H1/Q/FY、不猜年、不静默排除、不新增partial/uncertain schema。parser失败映射 `FinsDownloadProviderError(CNINFO,PROTOCOL,retryable=False,safe_message='巨潮年度报告原文无法确认财年或全文性质')`，cause保留；magic/min-size为既有PDF协议安全文案；HTTP仍原typed category/retryable。无candidate失败行，因为此时尚未确定安全财年/文档ID。

protocol/方法文档准确区分：普通 selected candidate 的 `download_report_pdf` transport/PDF错误由单filing失败行隔离，既有selected repair失败仍终止其repair gate；discovery HTTP/JSON及CN FY facts完整性失败则整次发现失败。HEAD仍可选降级，不承诺FY facts GET具有candidate隔离。workflow/public runtime/CLI消费现有provider failure：kind=PROVIDER_TRANSPORT、source=CNINFO、transport_category=PROTOCOL、safe_message准确，无新结果字段。

必须端到端覆盖“一个坏非目标FY + 三正常目标 + H1/Q + 既有完整源”：workflow抛typed provider原因，未发FILING_STARTED；direct/runtime失败诊断非空，CN uncertain/partial不生成；公司/source/meta/revision/blob/processed全部零业务写入、无开放batch/半成品。该失败会暂停本请求其它财期维护，是明确可用性代价，README需说明。原件事实不足时无自动修复/overwrite/rebuild承诺。

### P3.6 完整迁移清单

当前 `rg` 核对调用/构造点如下，全部一次迁移，不拆CN/HK协议、不默认新入参/字段：

- 生产：protocol；CninfoDiscoveryClient、HkexnewsDiscoveryClient两实现；workflow唯一list调用；cninfo result构造、`select_hkexnews_report_candidates` 的result构造；selection CN/HK两candidate builder；workflow唯一single-filing调用及filing自身retry调用；tests/workflow当前1139/4178两处directsingle调用显式传prepared/local witness。Phase B函数若增加候选/来源检查仍在原参数内完成，当前2826处directcommit测试按该合同更新。
- tests list调用：`test_cninfo_downloader.py`、`test_hkexnews_downloader.py` 全部调用显式传 tuple/gate；`test_cn_report_selection.py` 的 CN selector 调用显式传 annual_facts_by_source（H1/Q为空）；fake实现 `_FakeDiscoveryClient`（workflow）、`_RuntimeFakeDiscoveryClient`、`_PipelineDownloadFakeDiscoveryClient`、`_PipelineDownloadFakeHkDiscoveryClient`、`_RawDiscovery`（F5）。不是原plan所称仅四处fake。
- tests result：workflow fake一处；pipeline两fake；runtime主fake及1669/1791/1922/2109/2307/2444处受控结果（位置仅为当前定位，按符号迁移）；F5经真实selector结果。所有结果显式prepared/local空或真实受控payload；models中新增DTO/contract helper准确维护本模块__all__及model测试，不为旧导入路径加转发。
- candidate构造：生产仅selection；tests为`test_cn_download_runtime.py`、`test_cn_pipeline.py`、`test_cn_download_identity.py`、`test_hkexnews_downloader.py`、`test_cn_download_workflow.py`、`test_cninfo_downloader.py`。其年度原文fixture迁移到新owner事实，不保留任意bytes冒充full；fake绝不作为兼容生产理由。
- `utils` 当前无list/result/candidate调用；本轮旧取证脚本在workspace/tmp中不迁移、不覆盖。实施完用同一`rg -n 'list_report_candidates\(|CnReportDiscoveryResult\(|CnReportCandidate\(' dayu tests utils`复核，并由pyright检查所有实现。

HK unchanged-contract：query/raw请求、年度截止日推导、unknown tuple、排序/candidate、HEAD/GET/gate调用数、失败/取消边界与此前一致；非空CN tuple拒绝，新增结果为空；没有分市场dispatch/facade/别名。existing provenance准确改值必要，不新增CLI输出字段。

## P4：来源身份、COMPLETE、A/B 与 repair

### P4.1 source identity 唯一真源

source identity为 **`(provider,source_id)`**。source_url只是取得实际原件的locator；local匹配、identity匹配、COMPLETE断言统一用该键，不做URL归一/宽松匹配。非overwrite的合法同源COMPLETE不因raw scheme/path改变永久冲突、重新GET、转换、写metadata或更新locator；也**不承诺刷新相同source_id的远端内容**，即使远端bytes变更，仍保留已持实际原件及其旧locator。原remote_fingerprint可记录实际取得时的URL，但不得用于推翻该COMPLETE语义。

扩展`read_cn_download_identity_index` predicate为HK或CNINFO FY，仍通过read_source_meta_view；空/CN H1/Q零identity读取，index无写授权。`resolve_cn_download_ids` CN FY规则：ticker一致；同key唯一且internal ID可信则复用既有ID；missing internal/duplicate/read_error沿原owner优先序拒绝。新源原财期ID若未被任何在场source占用则用原seed；已占用则用`sha1(f'{ticker}|{provider}|{source_id}')`生成`fil_cn_<digest>`/`cn_<digest>`；fallback ID也被其它源占用就ValueError，不能覆盖/随机后缀。COMPLETE摘要与全文独立保留；同财年新版source_id同样独立。HK原身份/财期纠正行为不扩，H1/Q仍旧seed。

### P4.2 A期同窗事实、witness 与每次 COMPLETE 证明

CN FY单filing的A期从新`read_source_meta_integrity_view(ticker,FILING,batch=None)`取得目标entry，分类（entry.integrity）和meta同窗，不能沿旧`classify`+无绑定`get`拼接元数据。模块级 `_read_cn_annual_phase_a(ticker: str, document_id: str, source_repository: SourceDocumentRepositoryProtocol) -> tuple[SourceIntegrityClassification, Mapping[str,JsonValue] | None]`：有entry直接用同entry分类/meta；无entry再用原classify_source_integrity确认MISSING，若期间已出现目标则抛SourceIntegrityRevisionConflictError；不得用不存在的entry猜meta。HK/H1/Q保持旧A读法。

A 的检查顺序唯一：UNSAFE→PreflightError；有 `local_annual_publication` 时先检查 exact document_id/provider/source_id/presence/revision，变化→RevisionConflictError，同 revision REPAIR_REQUIRED→RepairRequiredError，必须仍 COMPLETE；然后对 existing target（含 repair）调用 filing 模块私有 `_require_matching_cn_annual_publication(meta: Mapping[str,JsonValue], candidate: CnReportCandidate) -> None` 比较 provider/source_id、fiscal_year、fiscal_period、covered_fiscal_periods。前两者缺/不符→`CnDownloadAnnualPublicationError('source_identity_conflict')`，后三者缺/不符→`period_metadata_mismatch`。URL 不比较；不依财期槽猜 source，不 reset 未知身份。该 helper 是 filing 内唯一业务匹配 owner，P3 原件投影不重复计算业务财年。

该 helper 对 `covered_fiscal_periods` 的唯一表示与现有 writer 一致：meta 必须有该字段，值必须是非空 **canonical JSON list**（`type(value) is list`），只含现有 canonical 期间字符串、顺序固定、无重复，且 **`meta['covered_fiscal_periods'] == list(candidate.period_projection.covered_periods)`** 完全相等。candidate 的已校验 period projection 是 canonical 内容/顺序真源；不重新设计 schema、枚举或投影 helper。缺失、非 list（包括 tuple）、空 list、重复、未知期间、乱序或值不一致统一抛 `CnDownloadAnnualPublicationError('period_metadata_mismatch')`；不得把持久侧 tuple 转为 list 后接受，不 sort/deduplicate 或 loose parsing。A/B 复用此 helper；P3 的 raw JSON 同版比较不承担这项 candidate 匹配。HK 保持既有 `list(candidate.period_projection.covered_periods)` 比较。

新增 `CnDownloadAnnualPublicationError(CnDownloadFilingError)` 的必填 `reason: Literal['source_identity_conflict','period_metadata_mismatch','source_document_facts_mismatch']` 严格封闭；`project_cn_filing_failure` 是唯一 projection，依次返回原 reason 与固定安全文本：“本地年度报告来源与所选公告不一致，无法复用”“本地年度报告财年或覆盖期间与原文不一致，需核对已有来源”“年度报告原文与本次已确认的财年或全文性质不一致，无法应用”。这些都是**单 filing 业务失败**，不升级为 request integrity-abort。没有从 reason 文本判断调度的分支，不在 adapter/CLI 重算，不推荐未证明的 rebuild 历史恢复。

每个 CN FY 非 overwrite COMPLETE skip 必须满足 **当前 A 同 revision 的实际本地 original 是 full 且年等于 candidate**：

1. 有由 P3 owner 链产生且经 A 核对相同的 local witness：复用已经确认的 full/year，不重复 snapshot/parse；元数据匹配成功后才 skip。witness 不匹配立即 integrity-abort，不走单 filing retry，也不能用旧事实 repair 新原件。
2. 无 witness（discovery 预读被 filing_date/ingest_method 排除、在 discovery 后新出现 COMPLETE、prepared 路径到 A 时已有 COMPLETE、直接 single filing、fresh retry）：filing 在任何 skip/消费 prepared 前从 **A exact target entry** 建 expected_publication、expected_meta，调用 P3.2 `read_cn_annual_report_pdf`，再调用 `resolve_cn_annual_report_facts`。必须 full/year 匹配；成功只对该 A revision 生效，prepared 丢弃，零远端 GET/转换/source 写入。这里不套 discovery 的日期/ingest_method 缓存 eligibility；只证明已解析到的 exact target，不扩大历史预读范围。
3. 原件角色缺省/多义/声明不一致（CnAnnualReportSourceError）、本地 parser ValueError、可解析但 summary/错年：filing 包 cause 转 `CnDownloadAnnualPublicationError('source_document_facts_mismatch')`，单 filing FAILED、零该目标业务写入。完整性变化三类型原样向 workflow 传播，不用远端 prepared 或 meta 财年替代本地 facts，也不通过 GET/覆盖补救。

`_require_current_cn_annual_complete_facts(ticker: str, document_id: str, classification: SourceIntegrityClassification, meta: Mapping[str,JsonValue], candidate: CnReportCandidate, local_annual_publication: CnAnnualReportPublication | None, source_repository: SourceDocumentRepositoryProtocol, cancellation_checkpoint: Callable[[],None] | None) -> None` 固定为 filing 模块私有 owner：调用前已完成上述 A 分类/witness 顺序及 metadata helper；仅 COMPLETE 可调用，按 1/2/3 执行，检查/读取/parser 前后 checkpoint。不返回 capability，不接受 prepared/远端 facts。其失败在任何 FILE_DOWNLOAD_STARTED、converter、batch/reset 之前发生。只有该 helper 成功才 emit `FILING_COMPLETED(status='skipped',reason_code='integrity_complete')`。source revision token 只比较相等，不从 token 派生年份/内容。

该 helper 中 source read 与 pure parser 使用独立 exception scope：只将 read 的 `CnAnnualReportSourceError` 包成业务facts mismatch；read 的原 storage ValueError/OSError/consistency及三integrity类型保持原样；只将 pure parser 自身的 ValueError 包成业务facts mismatch。checkpoint 在所有 mapping try 外，不能用一个 broad ValueError catch把storage/取消误归事实失败。

### P4.3 prepared / original GET / retry 的事实校验

A先于prepared消费；COMPLETE **经 P4.2 实际本地证明成功**才优先 skip，prepared 直接丢弃，不能为了“已有 payload”覆盖。MISSING或可信同源选中REPAIR_REQUIRED才acquire：有prepared就复用同次bytes，不再gate/GET；无prepared沿原gate/download。acquire前后checkpoint，使用P3 result contract helper校验candidate/provider/ID/实际locator/SHA/size。CN FY acquired原件再执行同facts owner，必须full且等于candidate财年（prepared再校验与initial discovery一致；retry/原GET不能偷偷使用不同事实）。解析失败为同PROTOCOL安全失败；可解析但年/kind改变为source_document_facts_mismatch，不重新分配年、不写错事实。prepared只一次lease取得，repair不重新GET。

沿原文件完成/转换事件、Docling复用判定、可取消converter、batch外转换与blob-first final meta；prepared失败的注入点在discovery payload或converter/result校验，不能仅在旧download_report_pdf打补丁。原GET的provider/conversion错误仍单candidate failed，选中repair failed仍break，不发布company/后续源。

B在原caller-ownedbatch内先classify_staged_source_integrity：UNSAFE rollback+typed失败；`has_same_source_publication_identity(A,B)`不相等先rollback并沿原最多三轮retry（0/1/2）。retry显式传 `prepared_asset=None, local_annual_publication=None`，丢弃PDF与Doclingpayload，重新identity/A，不重做discovery：fresh A COMPLETE 必须 P4.2 无 witness 的本地证明；fresh A MISSING/可信 selected repair 才重新 gate/GET/acquisition。重取bytes按上述年/kind校验，预算耗尽仍SourceIntegrityRevisionConflictError，不能接受旧facts作新原件成功。

A/B identity 相同后，对任何 existing CN FY 目标，用 `read_source_meta_integrity_view(...,batch=token)` 取 exact staged entry，其 classification 须与刚读 B 分类同 target/revision/status（否则 RevisionConflictError），调用同 metadata helper。它只验证 metadata，不能给 COMPLETE 提供 full/year。**CN FY 的 B COMPLETE + 非 overwrite 一律 rollback→retry，不直接 B skip**：到 B 的原 A 是 MISSING/REPAIR_REQUIRED，没有当前 COMPLETE 原件证明；即使 repair→complete 保持相同 revision，也须 fresh A 读 exact 当前 original。真实 `read_source_snapshot` 没有 batch 参数，禁止在 writer reservation 中借 published bytes 证明 staged target、增加 schema/仓储 API 或使用 acquired 远端 facts 顶替。HK/H1/Q 保持原 B skip。若没有更改 revision 但 B 已 complete，retry 仍计入原三轮预算；fresh A 证明后零新增 GET/转换，已进行且被丢弃的旧转换如实记事件。B metadata 业务 mismatch 走单 filing failed；B integrity 三类型走 request abort。写入/取消错误由原finally rollback保留主异常；commit_batch开始后token归storage，不二次rollback。

### P4.3a 唯一异常作用域、catch/结果与副作用矩阵

异常**类型**决定生命周期，reason 仅是有界业务说明。三类 integrity（PreflightError / RevisionConflictError / RepairRequiredError）永远属于 request integrity-abort；AnnualPublicationError 三个 reason 永远属于单 filing failed。取消使用既有控制类型优先捕获，不能映射为上述两组失败。具体调用/catch 固定：

| raise / catch 位置 | 唯一行为 / result |
| --- | --- |
| early inventory / local snapshot / final preflight，尚无 filing started | integrity 三类型原样传播至现有 adapter/runtime 完整性失败投影；没有 candidate failed 行/业务写入，整个请求 FAILED。snapshot 原错误及 provider discovery failure 保持各自现有投影，不借 reason 更改作用域 |
| A witness 的 presence/key/revision 变化；同 rev repair；A/B UNSAFE；B分类不一致；retry预算耗尽 | single filing 原类型 raise；workflow `run_cn_download_stream_impl` **现 per-filing特殊 catch 加入 SourceIntegrityRepairRequiredError**，catch tuple 准确为三类。当前 candidate 追加且只追加一条 FILING_FAILED（原 source_integrity_failed 投影），保留已确认 filings 前缀，以 `_integrity_abort(cause=exc,filings=...)` raise CnDownloadIntegrityAbort；不继续下一 candidate，不发普通 PIPELINE_COMPLETED |
| single filing download/acquisition 和 conversion 的现 broad catch | `except CnDownloadCancelledError: raise` 后、`except Exception` 前显式加入三类 integrity 的原样 re-raise；不由 project_cn_filing_failure 吞掉 request abort。年度 metadata/local COMPLETE 证明在 acquisition broad try 外；acquired facts 校验在该 acquisition try 内，业务/provider失败沿现 FILE_FAILED/FILING_FAILED/return，不再二次失败投影 |
| `_require_matching_cn_annual_publication`（A/B）及无witness本地证明的 AnnualPublicationError | A helper raise 至 workflow generic filing catch→project_cn_filing_failure→唯一 failed row/event；B先finally rollback再同链。三个 reason 不进 integrity tuple、不跑 source identity retry，不用 reason_message 字符串调度 |
| prepared/original GET acquired年/kind改变 | raise AnnualPublicationError(source_document_facts_mismatch)，由上述 acquisition catch 唯一 failed/return；不可解析为 FinsDownloadProviderError(PROTOCOL)，仍单 filing失败。与 discovery P3.5 整次失败区分 |
| postrepair inventory / company gate | postrepair inventory 原特殊 catch 已含三类，保留；复查仍 repair→RepairRequiredError→_integrity_abort，保修复已提交的真实前缀。postrepair company publication 的现特殊 catch 只有 PreflightError，扩为同三类再 `_integrity_abort`，不得漏掉带前缀的完整性错误；停止company/下一candidate。普通clean gate首候选前原类型传播、无filing前缀 |

workflow generic filing catch 与 stream 已 emit 的 failed 行互斥：return 后以 `filing_terminal_status='failed'` 进入原 repair gate，不再次 append。A/B 业务异常由 workflow 投影，acquisition/conversion failure由 stream 投影；各 raise 点与 catch 点不可重复生成行。`read_cn_download_identity_index`/resolve 的既有 ValueError/OSError 类型不重新定义；本轮三个业务 reason 只覆盖 publication helper 与实际原件事实不匹配。

| 终止类别 / 场景 | 后续 candidate、retry、mutation、公开终态 |
| --- | --- |
| integrity-abort发生在中途（普通candidate） | 当前目标 commit 前 batch rollback，无其 source/blob/processed新态；已确认前缀及其持久提交保留；无后续candidate mutation；原 company 若已按普通clean gate发布不回滚，不承诺整请求事务。CnDownloadIntegrityAbort私有status=integrity_failed；现 public/runtime 整体 FAILURE/FAILED、前缀真实、原typed原因 |
| AnnualPublicationError / provider / conversion 普通单filing失败 | 该目标不reset/commit或其 batch rollback；前缀及已发布company保留；继续下一candidate。只 A/B publication churn 走三轮retry，业务年/kind/metadata冲突不retry。存在failed row则既有公共结果status=FAILURE、job=FAILED；summary依既有counts可为failed或partial_failure，不改词表/adapter、不误报success |
| selected repair 任一单filingfailed（包括三个业务reason） | 原 repair gate 检查 **filing_terminal_status** 后 break，无下一candidate/company发布；旧损坏目标保留、未commit batch rollback，整体 FAILURE/FAILED。selected repair完整性异常直接integrity-abort，亦不发布company |
| 取消：discovery/local/prepared/A/B/convert/后续candidate边界 | 原 CnDownloadCancelledError / DoclingConversionCancelledError→CnDownloadCancelledError 控制链；协作取消按既有CANCELLED投影，prefix保留，不追加伪造业务failed；snapshot/lease关闭、commit前batch rollback，commit开始后token归storage。观察取消前已抛完整性/业务失败不为寻找取消更换主异常 |
| A→B publication churn | 先 rollback、丢旧prepared/witness/PDF/JSON，再fresh A；new COMPLETE exact original证明后skip，MISSING/repair重取；0/1/2预算耗尽为request integrity-abort。witness→A变化不属于此内部retry，须新请求重新完整discovery |

以上“整体 FAILED”指请求/运行/公开失败；已有成功下载前缀时 summary 的 partial_failure 是原 contract 对真实计数的投影，不是新增 partial discovery 或调度协议。保持 runtime/CLI/schema 原公共合同与失败退出码，无生产 adapter 改动。

### P4.4 repair 与状态表（不承诺全历史自愈）

| 场景 | 必须行为 / 写入界限 |
| --- | --- |
| MISSING目标 | prepared或GET事实/转换全部成功且A/B稳定才publish COMPLETE；否则目标无半成品 |
| 旧不同源COMPLETE摘要/全文占财期槽 | 分配新source ID；旧ID/meta/revision/files不变；新全文独立COMPLETE |
| 同key合法COMPLETE（raw locator可变） | A同rev witness可用或无witness读exact本地original并确认full/year，metadata正确才skip；不刷新远端或metadata |
| 旧隐藏摘要被新selection排除且REPAIR_REQUIRED | 正常单attempt允许一次gate内discovery facts GET，summary确认即丢payload/零转换；final preflight `UNSELECTED_REPAIR_REQUIRED`，整个请求typed失败，company/source/blob/processed/meta/revision零业务写入；不repair commit/覆盖/删除/修旧摘要、不塞accepted/rejected。GET失败先为discovery失败，不能猜kind |
| 可信同key selected全文REPAIR_REQUIRED | 不读损坏本地PDF；discovery远端取得原文facts+prepared；final原repair owner优先该目标，A/B/转换/commit稳定成功后新inventory复查clean，再允许company/其它候选 |
| selectedrepair的discovery GET/parser失败 | 发现尚未结束：整次provider typed失败；repair/company/其它源零写入 |
| selectedrepair的prepared conversion/commit失败 | 原filingfailed+repairgate终止；原损坏源/公司/其它源保持，batch回滚；不是继续下载其它源的partial成功 |
| 未知/损坏identity、UNSAFE、多repair | 保持typed拒绝；绝不依财期槽猜source或metadata-only修旧年 |
| localfacts读取后targetpublication实际变化 | witness变化→RevisionConflict，同revrepair→RepairRequired，unsafe→Preflight；workflow特殊catch三类，保真实前缀、停止下一candidate、整体FAILED；下一用户请求重新发现 |
| 无witness COMPLETE、prepared/acquired A→B变化 | 无witnessA必须当前snapshot full/year证明；B COMPLETE先rollback→freshA证明，其他churn freshA重取/校验；最多三轮，无陈旧skip/提交 |

未选中历史损坏摘要、未知旧identity、同源历史错财年/扫描首页自动恢复不在本次目标；不声称repair全历史保持不变，也不声称`--rebuild`可解决。COMPLETE摘要保留与可信selected全文repair属于本次正向契约，必须实际测试。

## P5：可直接实现的测试与验证

### P5.1 fixtures、基本owner和端到端失败

从已有`workspace/tmp/601225-evidence/current-002.response.bin`复制原19条raw；13原PDF用PdfWriter.add_page仅派生首页测试PDF，provenance记录官方URL、原件SHA、page_index=0、派生SHA、生成版本，原件不整批入Git。所有正例实际读取PDF，不能mock extract_text或伪造三个财年；语法合成文本/坏PDF明确标为反例。

- facts按P2全部13官方正例及语法/PDF反例；selector全19任意输入顺序、九年full/三目标、2017修订/2020隐藏摘要、日期/category/页数变化不改事实；H1/Q/HK原断言保留。
- model/result逐字段不一致（candidate、provider/source_id/URL、sha、实际size、空bytes、非FY、重复候选/asset/witness、local与prepared同时来源、unknownsource）明确ValueError/TypeError；资产正确happy路径。
- source owner `test_cn_annual_report_source.py`：真实 Fs current snapshot 原件 projection/read、Optional 声明 size/SHA、exact name 与 descriptor关系；无/缺省角色（即使唯一PDF）、多original、非PDF、SHA/size不一致typed source error。取expected同窗后publication变化/消失、同revrepair、unsafe分别为三integrity类型；acquire ValueError仍COMPLETE则原错误、consistency/OSError不误包parser。每一checkpoint/open/read/acquire/close故障释放资源且不补GET/写入；两消费者复用同模块，不导入彼此，也不让parser做I/O。
- 同 source owner 增补 P3 raw JSON 同版与 locator 断言：expected_meta/snapshot 的相同 `['FY']` 原值通过，任一侧 raw list 值/顺序变化为 RevisionConflictError，不输入 candidate 或转换持久值；source_url 缺失/非 string/空 string 为 CnAnnualReportSourceError，非空 locator（含空白或不符合 HTTP URL 的 string）精确保留，零 HTTP，不由 locator 推断 source/year。
- filing publication owner 直接负例覆盖 covered_fiscal_periods 缺失、非 list、空、重复、未知、乱序、额外/不同期间，均为 period_metadata_mismatch。tuple 仅作为 direct owner 的 runtime 非法输入反例，由测试参数表直接注入；不通过 Fs JSON serializer 变成 list 后冒充容器反例、不放宽 JsonValue 生产签名、使用类型抑制或增兼容支路，不制造持久 tuple schema。乱序/额外期间用合法 canonical 字符串组成的 list，candidate 保持合法 CN FY 投影，不改其校验器。
- inventoryhelper clean/单repair只返回None、unsafe优先multiple、material单repair暂不授selected；finalclassifier原unselected/rejected/material分支原样。同一tuple早期/最终复用同真源；早期falseaccepted不允许。
- identity纯查询+真实Fs：空槽、同源旧ID、different source占槽/fallback、fallback冲突/duplicate/missinginternal/read_error、空/H1Q零view；未知损坏source不猜；HK旧规则原样。
- discoveryfailure端到端用真实raw、三正常目标+一个坏FY及H1/Q、真实隔离Fs已有源，注入**新HTTP/事实边界**；断言P3.5typed诊断、未FILING_STARTED、零company/source/blob/processed业务mutation、无batch/半成品。runtime/direct失败不是空成功/缺报；CLI用现有runtime投影验证安全字段，不改CLI生产代码。

### P5.2 local acquisition boundary matrix

每项用真实Fs及snapshot资源，storage损坏/并发操作只在隔离fixture里；spy计数是owner级断言，不凭旧注入点推论。

| 输入/注入点 | 必须断言 |
| --- | --- |
| 请求不含FY；FY窗外/其它财期且不是selected exact target的历史源 | 新fullsnapshot/originalread/parse为0；窗口内COMPLETE discovery预读有界，P4 selected exact target证明单独断言，identity必要读取与原finalinventory允许 |
| 同keyCOMPLETE、URLscheme/path变化；远端预置same/differentbytes | eligible本地actual full/year→selected同revwitness→A skip；HTTP transport GET为0、converter0、旧locator/meta/revision/PDF/JSONSHA不变；remote响应不得被消费；A不重复snapshot/parse |
| 真实 Fs 合法 COMPLETE `covered_fiscal_periods=['FY']`，candidate.covered_periods=('FY',) | 经真实仓储持久化/读回确认为 JSON list，P4 metadata helper 通过，沿既有 full/year 证明成功 skip；实际 GET/转换/source 写入为 0，meta/revision/两文件 SHA 不变。不能用同容器 fake 代替这个正例 |
| COMPLETE摘要+新全文 | 本地摘要facts=summary、只为全文新identity发布；摘要全部bytes/revision不变 |
| inventoryUNSAFE/多repair + 远端配置必失败 | 先sourceintegrity typed原因；新snapshot/PDFGET/converter/companysource写0；不伪造accepted |
| metadata读、snapshot acquire/open/read/close失败 | 原storage/consistency异常，不变成provider/parser；资源释放、无业务写入 |
| checkpoint逐边界取消/异常 | 原异常对象/类型透传；已读bytes释放、snapshotclose；未发生后续GET/写入 |
| parserfail（空/坏/无label） | 同discoveryPROTOCOL范围，零发布，不用meta年补判 |
| entry→fullsnapshot revision/source/range改变 | SourceIntegrityRevisionConflictError，禁止陈旧或范围外原文read/事实成功 |
| snapshot→finalpreflight/A target消失、换revision/源；同rev修复必需 | unsafe优先；否则revisionconflict/repairrequired；零目标GET/转换/写入，不带旧factsretry |
| eligibility 内缺original角色/角色歧义 | P3共享投影typed拒绝→discovery PROTOCOL，未FILING_STARTED，零远端factsGET/转换/公司源业务写入；不靠唯一PDF/name/URL猜 |
| 同keyCOMPLETE旧filing_date在FY窗外；非download ingest_method | discovery预读为0而raw仍准入，远端facts可GET；filing A无witness必须exact当前snapshot actual full/year。local full/year匹配则skip（filingGET/conversion/write0）；local summary/错年则业务facts mismatch failed；远端prepared full不能证明旧local full。日期/ingest_method不得成为目标豁免 |
| 无witness的原件角色缺省/歧义、不可解析PDF | metadata相等也不能skip；CnAnnualReportSourceError/纯parser ValueError的cause保留，project为source_document_facts_mismatch单filingFAILED；filing段GET/convert/commit为0（此前discovery GET如实计数），按P4.3a普通继续/repair停止 |
| discovery后newCOMPLETE；直接singlefiling / freshretryCOMPLETE | 必调共享read+samefacts owner，snapshot revision精确等A；wrongyear/summary拒绝，full/year合法0GET/convert/commit；取消/变化类型与资源释放按P4.2，不能metadata-only成功 |

### P5.3 prepared acquisition boundary matrix

| 输入/注入点 | 必须断言 |
| --- | --- |
| 原HTTP真实raw+13首页payload | 请求category/secCode/分页不变，显式标题摘要0GET；准入13各≤1实际GET；selected9同次filing不再GET、实际bytes/SHA/size/候选一致 |
| repeatedrawsource / invalidresultpayload | PDFGET前重复拒绝；candidateID/provider/locator/sha/size各错拒绝；不构造假accepted、不写source |
| discovery HTTP/PDF/parser failure（含落选source） | 原typed类别/retryable、安全文案及整次discovery作用域；company/source零业务写入 |
| 每GETattempt/gate/parse/handoff处取消 | checkpoint异常原样、lease释放、无converter/发布；HTTPretry不吞取消 |
| prepared+MISSING；可信selected全文repair | GET=1（discovery），filingGET=0；payload校验、conversion和commit原owner；repairfirst、postrepairfreshinventoryclean后company发布 |
| repairconversion/provider/commit/cancel失败 | providerfail在discovery时整次零写；转换/事务失败原repairgate阻后续、旧company/source保留、无半成品；各边界分别注入 |
| hidden摘要REPAIR_REQUIRED、旧title/meta不含kind（与COMPLETE摘要对照） | 不读取损坏localPDF；正常单attemptdiscovery恰好1GET/1lease、samefacts确认为summary、payload/witness/prepared不返回、converter0；finalUNSELECTED_REPAIR_REQUIRED，真实accepted不含该摘要且rejected为空；company/source/meta/revision/oldbytes/blob/processed全零业务写入，无batch。GET/parse失败则discovery typed失败、未到finalpreflight/未FILING_STARTED；不用title/meta猜summary。COMPLETE摘要本地事实0GET，全文独立成功 |
| acquire前target已COMPLETE/unsafe | 必须A同revision本地full/year证明和metadata检查后skip并丢prepared；unsafe拒绝；wrongsource/错年/summary/缺original不能skip/reset |
| A→B missing变complete/repair→新revision/unsafe、3轮churn | 每次rollback、旧prepared/Docling丢弃；freshidentity/A；newCOMPLETE共享snapshot本地证明后skip（新GET0、新converter0），否则按新A acquire核FY；耗尽typed conflict |
| A repair→B complete同revision | has_same_source_publication_identity=True仍不可B skip；CNFY先rollback→retry，freshA无witness共享读原件，full/year正确才skip；错年/summary业务FAILED，不能以已acquired full/year顶替；HK/H1/Q原B skip不变 |
| B同identity但错provider/id/财期metadata；B写入/rollback异常 | 共用publicationfailure；rollback保主错误，无半发布；旧源/未selected源保持 |
| A/B covered_fiscal_periods 缺失/非list/空/重复/未知/乱序/值不一致 | 共用 P4 publication owner 为 period_metadata_mismatch；A 在消费 prepared 前失败，B 经 finally rollback 后失败，作用域按 P4.3a，不 retry/normalize、不接受 tuple 兼容；direct owner 非法容器与 Fs 可持久化 JSON list 反例分开，零该目标发布 |
| retry重GET原文变year/kind/不可解析 | source_document_facts_mismatch或原parserPROTOCOL；不提交旧candidate财年、不再使用prepared |

### P5.4 original-GET acquisition boundary matrix

这是no-prepared路径（H1/Q/HK及CNFY在freshretry/直接singlefiling测试中），必须独立测试，不能视为prepared矩阵的附带覆盖。

| 输入/注入点 | 必须断言 |
| --- | --- |
| MISSING/noasset | gate一次、真实GET实际payload；CNFY再解析一致facts，converter/commit成功；H1/Q/HK行为不改 |
| 合法COMPLETE/A无witness | 先exact当前snapshot original+samefacts full/year证明；GET/converter/sourcewrite0；URL变化不影响CNFYskip；缺原件/summary/错年failed不能成功 |
| HTTP/magic/size/parser失败 | selectedcandidate typed安全failed；其它正常candidate隔离；repairtarget失败停止repairgate |
| asset candidate/ID/URL/SHA/size不一致 | CNFYmodelcontract拒绝，无convert/write，不能复用错误原件 |
| checkpoint/gate/GET/convert/批内取消 | 与原异常/取消结果一致、lease/token释放、batchrollback；保已处理真实结果 |
| selected全文repair、unsafe、A/B变化/预算、rollback | 原repair及publicationowner；freshretry重新GET，不复用旧PDF/JSON，三轮上限；不能把旧test绿等同newprepared/local绿 |

真实runtime结果核对source_id、财年、source meta、PDFSHA、Docling原件一致；COMPLETE不同source FY旧测试改为两源独立保留，同源测试仍零传输。既有legal行为与新边界测试都必须pass，fixtures跟owner迁移，禁止生产兼容分支。

HK 回归在既有 `test_cn_download_workflow.py` / `test_hk_period_rebuild.py` 对合法 JSON list 与 candidate canonical tuple 明确断言原 `list(...)` 比较仍可 skip/复用；财期、财年或覆盖 list 不一致保留原 period_metadata_mismatch 行为。复用既有 HK 合法 candidate/helper，不因 CN 规范澄清改变 HK 业务、重写旧断言或新增转换兼容。

P4.3a作用域须在 `test_cn_download_workflow.py` / `test_cn_download_runtime.py` 实测同版组合：先成功或skipped前缀→第二candidate注入三integrity类型（尤其RepairRequired）→第三candidate spy，应只有前缀+当前唯一failed row，第三无FILING_STARTED/GET/转换/source写；typed原因与CnDownloadIntegrityAbort私有快照/public FAILED、既有前缀资产一致。再对三个AnnualPublicationError reason分别做普通/selectedrepair两行：普通继续第三candidate、整体FAILURE/jobFAILED（summary依既有counts），当前源零写/旧源保留；selectedrepair先排序，gate按failed status停止第三且company不发布。覆盖A/B raise、acquisition失败return、postrepair复查和companycatch三类型，失败行不重复；取消独立注入CANCELLED、prefix不丢、lease/snapshot/token释放；reason文案改动不影响这些transition。三轮churn/rollback失败保主异常与P4矩阵一致。

### P5.5 实施顺序、命令与停止条件

S1内依次完成：facts/DTO及依赖→selection/identity→inventory/local/prepared/A-B→上述矩阵/真实CLI/docs。每步只做本slice已定义行为，先对应owner tests再下一步；没有额外commit要求。若当前官方13首页无法按本grammar确认、owner/API与此规格不可实现、外部变化阻断CLI三目标，向总控具体blocker，不能擅改scope或验收。

实施建`workspace/tmp/601225-validation/`，激活venv后执行：

```bash
source .venv/bin/activate
python -m pip install -e '.[test,dev,browser]' -c constraints/lock-macos-arm64-py311.txt
python -m pip check
python -c 'import pypdf; assert pypdf.__version__ == "6.1.3"'
pytest -q tests/fins/test_cn_annual_report_facts.py tests/fins/test_cn_annual_report_source.py tests/fins/test_source_integrity_preflight.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_models.py tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_pipeline.py tests/fins/test_f5_workflow_rebuild.py tests/fins/test_hk_period_rebuild.py --cov=dayu.fins.pipelines.cn_annual_report_facts --cov=dayu.fins.pipelines.cn_annual_report_source --cov=dayu.fins.storage.source_integrity --cov=dayu.fins.downloaders.cninfo_downloader --cov=dayu.fins.downloaders.hkexnews_downloader --cov=dayu.fins.pipelines.cn_download_models --cov=dayu.fins.pipelines.cn_download_protocols --cov=dayu.fins.pipelines.cn_report_selection --cov=dayu.fins.pipelines.cn_download_identity --cov=dayu.fins.pipelines.cn_download_workflow --cov=dayu.fins.pipelines.cn_download_filing_workflow --cov=dayu.fins.pipelines.cn_download_source_upsert --cov=tests.fins --cov-report=term-missing --cov-report=json:workspace/tmp/601225-validation/coverage.json
python utils/validate_601225_annual_fulltext.py coverage --coverage workspace/tmp/601225-validation/coverage.json
pyright
```

coverage子命令固定核对上述12个生产文件（新增窄source owner计入）和**实际修改/新增**测试文件逐文件≥80%，报告path/num_statements/percent；缺JSONentry失败，只有num_statements=0可记录无分母；不能以总体覆盖率或排除生产行替代。coverage.json 的 `files` 键按路径 resolve 后相对于repo root精确匹配 `dayu/...py` / `tests/...py`，不得模糊按basename匹配；新增/修改测试清单由实施实际diff冻结于validation run，不把只加跑而未改的HK测试强制当修改文件。utils按项目免测试/coverage但仍pyright。新增 source/integrity helper对应owner tests不得遗漏。P5所列文件以外的既有pyright问题不因文档修订重跑；实施触及报错必须一并修，不新增/掩盖错误。

## P6：真正公开 CLI 与独立实际 GET 验收

### P6.1 选定方案：仅验证 CLI 进程的 scoped HTTP observer

新增`utils/observe_601225_cli_http.py`，子命令`run --run-dir PATH -- COMMAND...`。采用**scoped sitecustomize透明观察**，不用监听外部任务、不起全局代理、不改CLI生产实现。run-dir须新建且位于本仓workspace/tmp；已有输出拒绝覆盖；command首项必须当前venv的真实`dayu-cli`，参数必须独立base与本目标bare download（允许`download --help`自检）。父进程写只含观察逻辑的bootstrap，`subprocess.Popen`执行原argv；设置PYTHONPATH仅注入该bootstrap，保留真实cwd/业务参数/HTTPorigin/响应/网络配置。**不得调用Python替代下载函数或换业务返回**，不传`--forms FY`、overwrite/rebuild或三ID下载。

bootstrap只在首次验证CLI解释器装载时记录PID并把observer PID写入child env；后代PID不同立即不装hook，父进程不扫描任何其它PID。安装失败必须显式`observer_error`并令验收失败（Python可吞sitecustomize异常，不能靠CLI退出0当装载成功）。hooks仅只读观察固定依赖版本：`httpx==0.28.1`、`httpcore==1.0.9`。版本/签名不同是验收blocker，不能无声降级计数。

执行算法与输出固定如下（均为辅助验证schema，不进入生产）：

1. 包装`httpx.HTTPTransport.handle_request(self,request)->httpx.Response`，以thread-safe递增seq记录实际transport尝试的method/URL/UTC，调用**原方法**，返回**同一Response**，异常原对象重抛。记录response status/transport error；任何retry/redirect均单独记attempt，不只记高层downloader入口。
2. 同时包装已锁`httpcore.HTTP11Connection._send_request_headers(self,request)->None`，先调原方法，成功后记录`wire_sent`的seq/method/host/target。用`ContextVar[int|None]`关联外层transport seq，非全局“最近请求”；这是实际发送请求头完成的独立网络证据。当前production httpx.Client默认HTTP/1.1；出现未关联发送、HTTP2、hook被替换或完整性缺项直接验收失败，不能推论0GET。观察私有httpcore方法只在辅助工具内、带pin/签名校验，不成为生产seam。
3. 包装`httpx.Response.read(self)->bytes`，**先调用原read**再返回同一bytes；只对该CLI的巨潮query POST按Response去重保存应用实际读取的request form、完整raw response bytes/hash（通过public response.request/content），不主动额外read/GET，不消费/替换业务载荷。由raw解析真实FY集合、hasMore/分页/参数，验证它与冻结官方集合不变；若raw变化保存原bytes并报`official_set_changed`给总控，不拿旧固定集合硬套。
4. `http.jsonl`：observer_started(pid/argv/versions/hooks)、transport_request/response/error(seq)、wire_sent(seq)、query_body(filename/SHA)、observer_finished(pid/seqcounts/hooks_intact/error_count)。只保存巨潮相关必要请求/表单/raw，不录cookie/secret/header全包、不记录其它任务。可观察非PDF公司GET但不计入PDF集合。原CLIstdout/stderr单独保留，原退出码写`run.json`。
5. 父进程待CLI**实际退出**后生成`http-summary.json`：startup/finish完整性、每seq闭合、transport与wire一致、raw分页完整、PDF GET attempts/sends的source_id→count、未知PDF URL、nonPDF请求、capture错误。PDF ID由**本次raw精确locator表**映射，无来源猜测/looseURL身份规则；重定向按同seq链/Location精确证据归属，另输出每hop。每source≤1是按PDF transport尝试与实际发送两表核对；非预期redirect/retry导致次数超限则失败记录成本，由总控裁决，不隐去。
6. observer失败输出exit2；CLI非0透传原exit且observer状态仍存；只有CLI0且observer完整才run0。结束/信号仅管理自己spawn的验证进程及其正常资源，不操作其它Agent/监听。全部函数严格typed，锁住httpcore私有签名/版本是证据必要性，禁止生产debug计数/schema扩展。

机制已在 r1 隔离probe验证（见 fix-r1，r2未重跑）：实际loopback origin返回原bytes，transport与真实send headers都观测到；POST原bytes不变；探针grandchild另一次真实GET未被观察；bare `.venv/bin/dayu-cli download --help`实际退出0且bootstrap装载。**此probe不是官方download/repeat证据**，S1必须用同方案跑下面真实origin命令。原计划的新增debug `巨潮年度原文获取: source_id=<ID>`明确保留为HTTP owner diagnostic：仅在FY远端acquisition入口（checkpoint通过后、HTTP调用前）记录，local复用不记录，不进LLM/summary；它描述获取动作而非逐retry的网络计数。只有observer记录能证明实际attempt/send数量，debug可辅助定位，缺debug不能单独证明零GET。

### P6.2 命令、脚本输入/输出与失败判定

成本：此前原下载约57分钟；计划阶段不重做34件转换。实施必须真正clean一次、seeded一次及两次repeat。新独立日志，不能使用调用方base。每命令退出码由observer/run.json或验收runner单独记录，遇到非0立即停止依赖步骤，不用流水线/`|| true`掩盖。

```bash
source .venv/bin/activate
VALIDATION_ROOT="$(mktemp -d "$PWD/workspace/tmp/601225-cli-XXXXXX")"
mkdir -p "$VALIDATION_ROOT/clean" "$VALIDATION_ROOT/seeded"
python utils/observe_601225_cli_http.py run --run-dir "$VALIDATION_ROOT/clean-01" -- "$PWD/.venv/bin/dayu-cli" --base "$VALIDATION_ROOT/clean" --debug --log-file "$VALIDATION_ROOT/clean-01.log" download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12
python utils/validate_601225_annual_fulltext.py verify --base "$VALIDATION_ROOT/clean" --evidence-root "$PWD/workspace/tmp/601225-evidence" --run-dir "$VALIDATION_ROOT/clean-01" --output "$VALIDATION_ROOT/clean-01.verify.json"
python utils/observe_601225_cli_http.py run --run-dir "$VALIDATION_ROOT/clean-02" -- "$PWD/.venv/bin/dayu-cli" --base "$VALIDATION_ROOT/clean" --debug --log-file "$VALIDATION_ROOT/clean-02.log" download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12
python utils/validate_601225_annual_fulltext.py verify --base "$VALIDATION_ROOT/clean" --evidence-root "$PWD/workspace/tmp/601225-evidence" --run-dir "$VALIDATION_ROOT/clean-02" --output "$VALIDATION_ROOT/clean-02.verify.json"
python utils/validate_601225_annual_fulltext.py compare --scenario clean-repeat --before "$VALIDATION_ROOT/clean-01.verify.json" --after "$VALIDATION_ROOT/clean-02.verify.json" --output "$VALIDATION_ROOT/clean-repeat.compare.json"
python utils/validate_601225_annual_fulltext.py seed --base "$VALIDATION_ROOT/seeded" --evidence-root "$PWD/workspace/tmp/601225-evidence" --output "$VALIDATION_ROOT/seed.verify.json"
python utils/observe_601225_cli_http.py run --run-dir "$VALIDATION_ROOT/seeded-01" -- "$PWD/.venv/bin/dayu-cli" --base "$VALIDATION_ROOT/seeded" --debug --log-file "$VALIDATION_ROOT/seeded-01.log" download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12
python utils/validate_601225_annual_fulltext.py verify --base "$VALIDATION_ROOT/seeded" --evidence-root "$PWD/workspace/tmp/601225-evidence" --run-dir "$VALIDATION_ROOT/seeded-01" --output "$VALIDATION_ROOT/seeded-01.verify.json"
python utils/validate_601225_annual_fulltext.py compare --scenario seeded-first --before "$VALIDATION_ROOT/seed.verify.json" --after "$VALIDATION_ROOT/seeded-01.verify.json" --output "$VALIDATION_ROOT/seeded-first.compare.json"
python utils/observe_601225_cli_http.py run --run-dir "$VALIDATION_ROOT/seeded-02" -- "$PWD/.venv/bin/dayu-cli" --base "$VALIDATION_ROOT/seeded" --debug --log-file "$VALIDATION_ROOT/seeded-02.log" download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12
python utils/validate_601225_annual_fulltext.py verify --base "$VALIDATION_ROOT/seeded" --evidence-root "$PWD/workspace/tmp/601225-evidence" --run-dir "$VALIDATION_ROOT/seeded-02" --output "$VALIDATION_ROOT/seeded-02.verify.json"
python utils/validate_601225_annual_fulltext.py compare --scenario seeded-repeat --before "$VALIDATION_ROOT/seeded-01.verify.json" --after "$VALIDATION_ROOT/seeded-02.verify.json" --output "$VALIDATION_ROOT/seeded-repeat.compare.json"
```

这些实施命令目前**未执行**，utils生产验收辅助尚未编写。本轮只写规格及workspace/tmp机制probe。无需init，真实入口用DefaultFinsRuntime及原production converter factory/config，不替代Docling。

`validate_601225_annual_fulltext.py` contract：

- `seed`只接受空、独立workspace/tmp base；读取两份官方摘要1213161682/1223301999实际PDF并重核证据SHA及same facts summary，以production Docling产生真实JSON；经共享storage仓储集合、build_cn_file_entry/commit_cn_filing_source_document的caller-ownedbatch提交两原财期seed ID，provider/source_id/actualURL真实，ingest_method=download。converter失败不发source、只在成功commit后写seed.verify。seed绕selection仅为历史占槽fixture，不是network发现证据。所有document读写经storage。
- `verify`使用FsSourceDocumentRepository/snapshot接口读取**全部已持源**的documentID、sourcekey、opaque revision、完整metadata、PDF/JSON SHA及完整性；三目标唯一存在、FY分别2021/2023/2024、active/ingest_complete、storage COMPLETE、PDFSHA与官方证据一致、primary为有效Docling。实际PDF调用same facts owner，不只看meta。run-dir读取observer/run/publicdiagnostics及conversion进度输出；按本次raw及仓储记录构造精确sourceID→URL→documentID表。现有`dayu/cli/output.py::_fins_event_line`把进度写成`Fins progress: operation="download" ... document="<document_id>_docling.json" stage="download.conversion_started|download.conversion_completed" ...`；脚本只对这个前缀用`json.JSONDecoder.raw_decode`逐个解码现有key=JSON值（不是split含空格message），要求operation=download、精确匹配stage与已读source.files中的Docling文件名，得到started/completed per-source counts。缺/重复/unknown文档映射失败；first三目标各started/completed=1，repeat全部started/completed=0。终态要求唯一`Fins download diagnostics: `行解析JSON，`status="success"`、`exit_code=0`、`failure=null`、`failed_documents=[]`，`summary.terminal_disposition="succeeded"`且`summary.counts.failed/rejected/uncertain=0`、`summary.uncertain_reports=[]`、`summary.omitted_uncertain_count=0`；不通过有界summary.documents反推全集。两套转换进度必须闭合且与实际持久资产一致；这是既有公开进度证据，不新增计数字段或通过productiondebug当零GET证据。
- 输出包含`validation_status`、三目标事实/资产、全source records、`pdf_get_attempt_counts`、`pdf_get_wire_counts`、observed/expected集合、conversion counts、raw_set/observer完整性、diagnostics及比较差异。辅助schema自足，允许ID只在验证程序/开发artifact；不增加生产public字段。
- `compare clean-repeat / seeded-repeat`逐个已持source比较文档ID、meta、revision、PDF/JSONSHA与COMPLETE；新source不应出现；核对P6.3精确允许GET集合、每项≤1且三目标/其余已持完整源0GET/0conversion。`seeded-first`校验两摘要仍原ID/meta/revision/两文件SHA、新全文分配独立ID且三目标转换成功。任一diff、非0CLI、缺observer、原集变化、未知PDF/多次GET、诊断失败/转换缺失均脚本非0；外部差异保存真实证据交总控，不接受未核hash的替代内容。

### P6.2a 真实 Docling 模型、原件关系与逐字段验收

上文“有效 Docling / 原件一致”具体执行以下步骤，均在辅助验证程序内，经当前 Fs source snapshot 读取实际 bytes，不新增生产 schema/转换功能：

1. 同一 full snapshot 调用 P3.2 `project_cn_annual_report_original` 定位明确 original PDF；`source_meta.primary_document` 必须等于 `snapshot.primary_filename` 且精确命中唯一声明 `source='docling',content_type='application/json'` 的文件名及 descriptor。从 snapshot exact 名称读 PDF/JSON；不按 `_docling.json` 后缀、唯一 JSON、URL/URI 或文档 name 推断角色。下载 owner 当前 `build_cn_file_entry` 的 fields 是 name/uri/etag/last_modified/size/content_type/sha256/source/ingested_at，**没有 derived_from**；不用验收需求创造该字段，也不把 upload 专用声明带入 download。
2. 对实际 PDF 与实际 JSON 分别 `hashlib.sha256(bytes).hexdigest()`、`len(bytes)`，逐项核 `files[].sha256/size` 与 descriptor 中存在值。三新全文及本次真实 seed 的两文件由 production blob/file-entry owner 产生，实际声明须有 SHA/size，不可留空后声称验收已核。PDF 实际 SHA 另核 `source_meta.pdf_sha256`，三目标核官方冻结 evidence SHA；`source_meta.source_fingerprint` 只用既有公开 `build_content_fingerprint(pdf_bytes=...,docling_json_bytes=...)` 复算，不手写组合公式。其意义是当前两资产内容一致，不是历史转换因果签名。
3. 原 JSON bytes 直接调用已安装 `docling_core.types.doc.document.DoclingDocument.model_validate_json(json_bytes)`，失败保存有界验证原因并非0退出，不仅 `json.loads` 成功就通过。需非空 `origin` 与非空 `pages`（这三份实际PDF均有页，空模型不能代替有效转换）。三份真实完整年报在 schema-valid 之外还须最小内容 sanity：`bool(doc.body.children)` 为真，且 `any(item.text.strip() != '' for item in doc.texts)` 为真；空 body、无 text item、text 全空/只有空白均非0退出。这使用真实 SDK 的 body.children / texts[].text 字段，仅确认已有正文引用及至少一项非空文本，不要求财务表/数字提取、覆盖率或准确性研究，不改变产品/来源 schema。不转存/规范化 JSON 后比较 hash，不mock SDK，不重新转换已持资产。声明中的 primary、model 验证与三目标内容 sanity 必须同时成功。
4. 输入链已核实：filing 调用 production `convert_to_json_bytes(pdf_bytes,pdf_filename,config=DEFAULT_FINS_DOCLING_CONVERSION_CONFIG)`；shared worker调用 `convert_pdf_bytes_with_docling`，Dayu以 `DocumentStream(name=stream_name,stream=BytesIO(raw_bytes))` 输入 SDK，`InputDocument` 的 `file.name` 来自该 stream 名。当前标准 PDF reading-order API 用 input.file.name / input.document_hash 产生 `DocumentOrigin`，URI 未传。因此验收用当前 SDK 的公开 `docling.utils.utils.create_file_hash(BytesIO(actual_pdf_bytes))` 及 `DocumentOrigin.model_validate({'mimetype':'application/pdf','filename': original_descriptor.name,'binary_hash': sdk_hash})` 构造 expected origin（model_validate 接受 SDK hex 输入并按真实模型规则转为 Uint64；不要在 typed constructor 给 int 字段硬传 str）。核实际 doc.origin.mimetype/filename/binary_hash/uri 与 expected 相等；**不假设 binary_hash 是 SHA256字符串/自行截断算法，不假设 filename 的命名形态，也不要求 origin.uri 等于远端 locator**。原件 exact 声明名称与 production converter 实际 stream_name 一致，由当前owner传同一个pdf_filename给转换与file entry的调用链、owner测试核实；公开CLI进度只暴露转换文件name映射后的document标签，未输出source_name，不把内部payload当额外公开证据，也不从SDK文件名反推来源ID。
5. 三新全文 `source_meta.fiscal_year_source='source_document'`；实际 original 经同 facts owner 验证 kind=full、年=2021/2023/2024，持久 meta、候选/结果/CLI字段同源。seed摘要 actual facts=summary，其原身份/来源字段不改为全文，不为此追补历史 provenance。
6. verify 每个 source 输出 declared原件/primary名、实际两SHA/size、source_meta.pdf_sha256、fingerprint expected/actual、model验证状态、origin expected/actual及三目标fiscal_year_source；三目标另输出 body.children 数量、非空 text item 数量与 content sanity 状态，有 mismatch 或 sanity 失败即非0。已有 conversion_started/completed 与实际产物/hash/origin一并证明本次真实输入/转换/发布链；SDK origin.binary_hash 是其模型有损Uint64投影，不是独立完整hash/不可伪造审计链。当前 download files 无持久 derived-from关系，不能从旧 JSON origin单独证明历史转换因果；如需这种审计须另work unit，不扩大本次scope。

本轮 r2 **实际只读 probe**：激活 venv后运行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python workspace/tmp/601225-plan-fix-r2/probe_docling_contract.py`，实际退出0。当前锁与运行均 Docling2.127.0 / core2.96.0 / Pydantic2.13.2；三个官方PDF以真实 InputDocument/backend输入有效（287/297/294页），SDK输入hash与实际bytes对应、origin采用实际input.file.name且uri=null，真实模型export→model_validate_json roundtrip成功，非Docling/损坏JSON均拒绝。记录 `docling-contract-probe.json/.log`；该roundtrip是模型/API探针，**未做真实PDF转换、未证明四次CLI产物**。SDK/backends源码只读核对了上述输入链；不以探针模型代替production Docling输出。若实施环境与pin/API不符，记录具体blocker交总控，不增加算法fallback或改验收标准。

### P6.3 repeat的精确允许集合

仅在本次官方FY集合与当前19条不变、无外部故障/并发变化时：

| 场景 | 允许且预期出现的PDF GET source_id集合（每项≤1） | 必须0GET/0conversion |
| --- | --- | --- |
| clean repeat | `{1204545056,1209875597,1213161682,1223301999}` | 三目标及全部已持久化合法COMPLETE源；其它PDF来源也无额外GET |
| seeded repeat | `{1204545056,1209875597}` | 三目标、已持久化完整源、两seed摘要 |

verify/compare输出**真实transport与wire集合**及各count，并与此集合逐项相等比较，不只检查子集/目标debug缺席。1204545056是2017落选的275页全文，另外三项是摘要；不是“只有摘要可能GET”。没有持久化的落选全文/摘要每次需要原文facts，成本如实保留，优化交后续按需性能任务，不纳入新缓存。两次repeat所有conversion count应0。

## P7：README决定、风险与交付

已读根README/ Fins README的Agent更新约束及tests README当前事实边界；本轮仅文档plan fix，不修改这三份README。实施后：

- `dayu/fins/README.md`按现有选择/身份/下载机制职责说明FY原文事实、sourcekey/locator、local-witness/prepared与早期/最终完整性权限、无witness的exact原件证明、两组类型的失败作用域、selectedrepair及unselected损坏摘要只读factsGET后拒绝；不写ID/测试/work-unit记录。
- `tests/README.md`只记录已落地的facts13正例、三种acquisition矩阵、source/integrity helper、protocol迁移/fixture来源、HK共享helper回归与真实验收方法，不写未来计划。
- 根`README.md`用户下载/排障：FY完整报告与独立摘要各自保留，区分现有Q1/Q3正文覆盖行为；说明FY原文无法确认会使本次下载失败且不写财报，检查来源原件后重试；损坏历史摘要/未知身份需先核对工作区，不承诺repeat/rebuild自行修复；合法完整同source缓存不因URL变更自动刷新，需刷新才使用既有显式overwrite。保留现有完整诊断/安全操作路径，不加内部schema/三ID或未经验证的恢复建议。

无分层、装配、入口参数/日志位置变化，`dayu/README.md`、Engine/Host/Config README无触发。inventory helper仍在既有Fins storage纯contract，新snapshot original projection/read owner在既有Fins pipelines内，无新层/反向依赖。

| residual / 未覆盖 | 分类 | owner / destination | 是否阻塞 |
| --- | --- | --- | --- |
| MiMo-r2-01 canonical JSON 表示及两个非阻塞 OQ 的规格修订有效性 | fixed in current slice（plan fix/re-review责任） | 本轮Sol/总控 / 本plan、fix-r3、后续两路同hash聚焦 re-review | 原四accepted保持r2已闭环；新accepted须复审验证，不自放行实施 |
| S1代码/owner矩阵/依赖安装/类型与coverage/README | fixed in current slice（implementation尚未执行） | 实施Agent / S1 checks及code review artifacts | 实施必须完成 |
| 四次真实CLI/真实Docling、observer正式辅助完整性 | fixed in current slice（验收未执行） | 实施/验收Agent / clean/seeded/repeat artifacts | 无真实证据不pass |
| 历史启动树/raw缺失 | assigned to later work unit | 总控 / 原根因历史证据边界及后续可追溯任务 | 不补造；当前同源链已证 |
| 被排除损坏摘要/未知旧identity/同源错年自动恢复 | assigned to later work unit | Fins完整性维护者/总控 / 独立历史完整性任务 | 本轮仅安全失败+零写入；未扩恢复承诺 |
| OCR/扫描/跨行或未知标签、其它公司/公告失败布局 | assigned to later work unit | Fins年度事实维护者/总控 / 独立发现任务 | 当前13可解；事实不足整次失败；影响目标即blocker |
| 落选275页全文/摘要repeatGET成本 | assigned to later work unit | Fins维护者 / 后续按需性能任务 | 本轮如实验证允许集合，不加cache |
| UTC/本地披露日偏差 | assigned to later work unit | Fins日期维护者/总控 / 独立日期任务 | 当前目标远离窗口边界 |
| origin集合/内容或锁定HTTP版本变化、不可用 | fixed in current slice（验收责任） | 实施/验收Agent与总控 / 真实差异记录、裁决 | 无真实对账不能pass |
| SDK origin仅有损binary_hash/当前download声明无derived_from，不能单独证历史转换因果 | assigned to later work unit | Fins转换/审计维护者与总控 / 如有需求的独立来源审计任务 | 本次以真实转换进度+完整两资产SHA/fingerprint+模型origin核对，不扩审计schema |

只有S1，无later approved slice/既有issue；不创建新issue。分类是责任归属，不能冒充已修复或复审通过。

S1完成报告必须记录changed files、P2–P4实际行为、accepted findings复审状态、pytest退出/数量/逐文件coverage、pyright/pipcheck、README决定、四个bareCLI原argv/真实exit、三目标财年/source/locator/PDF/Docling/COMPLETE、两个摘要保留、实际transport/wireGET与conversion集合/count、observer装载/闭合、所有残余risk/owner/destination。修订交付后由总控核对实际退出，再同时派MiMo/DS审核同版；本Agent不更新state、不自判accepted已复审通过。
