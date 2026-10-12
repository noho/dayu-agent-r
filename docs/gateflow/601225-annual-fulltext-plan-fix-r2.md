# 601225-annual-fulltext：plan fix r2 交付

- Gate / work unit：`plan re-review → fix（r2）` / `601225-annual-fulltext`；本轮只完成计划修订交付，不是 re-review pass / accepted plan，不推进总控 state。
- 仓库 / branch / HEAD / base：`/Users/leo/workspace/dayu-agent-r` / `fix/601225-annual-fulltext` / `7637bb0b4fbca212a4db0f4cfc09655e66516695`。
- Binding scope：[已确认目标](601225-annual-fulltext-goal-confirmation-20261012.md)，可靠官方原文财年、普通公开非 overwrite 入口三全文、摘要不挡/不冒充、合法增量；不伪造历史 raw，不扩日期/OCR/其它公告/历史恢复。
- 必读输入：AGENTS.md、binding goal、当前 plan、[r1 fix](601225-annual-fulltext-plan-fix-r1.md)、[MiMo r1 review](../reviews/plan-review-20261012-142347.md)、[DS r1 review](../reviews/plan-review-20261012-142348.md)、[r1 总控裁决](601225-annual-fulltext-plan-rereview-r1-adjudication.md)。两路实际 completed，MiMo fail、DS pass-with-risks，按总控裁决修四项 accepted，不按多数放行。
- 变更产物：[完整实施计划](601225-annual-fulltext-plan.md)与本文；临时探针/保护记录仅在 `workspace/tmp/601225-plan-fix-r2/`。
- 冻结输入 plan SHA256：`37663c068ee5d6b3f39fd60642ecf4c8c134ff760d0649a0fe12c8a0bef34855`；修订 plan SHA256：`5b506a9dca7af364e8b85f7ba3d12f38dc84b972bbb476f1c1150e420a4c4ae8`。
- 权限边界：未实施生产代码/测试/依赖/README、未 commit/push/PR、未改调用方目录/原证据/其它 review artifact/总控 state、未启动/clear/中止或操作其它 Agent。技能只使用 Gateflow 的当前 plan fix 约束，用户本轮限制覆盖技能的自动推进规则。

## 动机、直接证据与最小 owner 决策

原动机仍成立，未扩大严重性或目标：官方完整年报输入现有选择后财年偏移，旧摘要又占财期身份，影响本轮三全文与安全增量。r1 未闭合的是真实新路径的事实证明与异常生命周期，不能在调用方补三 ID、在消费者猜 kind 或用 prepared 修饰本地原件性质。

本轮直接核对以下基线事实：

- `cn_download_workflow.py:377` 的 per-filing 特殊 catch 只有 Preflight/RevisionConflict；RepairRequired 在此会落 generic 分支。`:437` 的 postrepair inventory catch 已有三类；postrepair company catch 原只有 Preflight。`_integrity_abort` 接受三类并保存已确认 filings 真源；普通失败由原计数投影，存在成功前缀时 summary 可为 partial_failure，而整体 public FAILURE / job FAILED。
- `source_integrity.py:281` 的 publication equality 只比较 target 与 revision，不比较 full/year，repair→complete 同 revision 可以相等。`repository_protocols.py:1426` 的 `read_source_snapshot` **没有 batch 参数**；`:1772` 的 blob read 也是 published 读取。不能在 B 期用这些 API 证明 staged 原件，更不能为本轮改 storage API。
- snapshot descriptor 没有 source role；`_fs_source_integrity.py:696` 的 role 是 optional，storage COMPLETE 并不等于年度 original/full 业务证明。角色 owner 是该 snapshot 的原 files 声明，年度事实 owner 是原文 parser。故新增窄 `cn_annual_report_source.py` 作为 workflow/filing 唯一共享 original projection/read，事实解析仍纯函数，禁止各自 raw role 解析。
- `cn_download_source_upsert.py:43` 的 download file entry 没有 derived_from；`:106` 已有公开 `build_content_fingerprint(pdf_bytes,docling_json_bytes)`。真实 converter 的 bytes/stream_name 输入、Docling 模型与 origin 行为见下文 probe，未引入 provenance/schema 新目标。

P0、P2 grammar/selection、P3.6 shared protocol 迁移、P4.1 source identity、P6.3 repeat 集合与冻结 r1 **逐字相同**（`document-check-preartifact.json`）。HTTP observer 保持原机制/版本/计数合同，仅更正 probe 归属为 r1；来源字段维持既有必填与准确取值，不重开已闭环项。

## 四项 accepted 的具体修订位置

本表只报告提交的规格与待执行验证，不回写总控裁决或 reviewer 最终 finding 状态；当前四项仍以未修改裁决为准，须双路同版 re-review 验证后由总控回写。

| r1 accepted finding | r2 plan 具体位置 | 唯一决定、状态机与边界测试 |
| --- | --- | --- |
| MiMo-r1-01：不重下摘要与 facts GET 冲突 | P3.3 `:131`；P4.4 `:244`；P5.3 `:297` | “不重下摘要”限定不 repair commit/覆盖/删除/修旧资产。REPAIR_REQUIRED 不读作完整 local 输入，hidden raw FY 在 gate 内正常单 attempt 恰好一次 discovery GET；same facts 确认 summary 后丢 bytes/prepared/witness，零转换。final unselected repair 原 typed拒绝、真实 accepted 不含该摘要/rejected为空、company/source/meta/revision/old bytes/blob/processed零业务写。GET/校验/parser失败先为 discovery失败，未到selection/finalpreflight，不从旧title/meta猜kind。原HTTP retry/redirect规则不改，真实次数照录。 |
| MiMo-r1-02：exception作用域不唯一 | P4.2 `:188`；P4.3a `:212`；P5.4后作用域组合 `:319` | 三类 integrity永远 request abort；per-filing特殊catch补RepairRequired，postrepair company特殊catch也收为三类，stream acquisition/conversion broad catch前原样re-raise。当前唯一failed行+已确认前缀→_integrity_abort→整体FAILED，停止下一candidate。AnnualPublicationError三个reason只为单filingfailed，普通继续/整体FAILURE-jobFAILED，selected repair按failed status停止、不发company。A/B raise、acquisition return、postrepair/取消/retry/rollback及业务mutation矩阵固定，不以reason文本调度。 |
| MiMo-r1-03：无witness COMPLETE metadata-only skip | P1 `:34`；P3.2 `:100`；P4.2 `:184`；P4.3 `:208`；P5.1/P5.2/P5.3/P5.4 | 同rev已有witness只复用成功local facts→selected full/year的证明；无witness从A exact target同窗entry读当前snapshot声明original，经samefacts full/year后才skip。日期/ingestMethod缓存过滤、新出现COMPLETE、prepared、freshretry、directsingle都不能豁免。共享函数/输入输出/错误/资源/checkpoint/revision唯一；缺role即使唯一PDF也typed拒绝，不能以远端prepared证明旧local。B CNFY COMPLETE必须rollback→freshA证明（无batch snapshot API），同revision repair→complete同样执行；合法同源缓存0GET/转换、不刷新/覆盖/迁移。测试覆盖role缺省/歧义、日期/ingestMethod过滤、sameID远端改变、A-B-retry、取消与资源。 |
| DS-r1-01：漏HK共享fake/helper回归 | P1 owner tests `:43`；P5.5 `:332` | pytest命令新增 `tests/fins/test_hk_period_rebuild.py`，仅验证复用迁移fake/helper的现有HK行为。新窄source owner/test也加入固定测试/coverage清单；不改HK业务目标或该文件原断言。 |

行号来自本稿 plan，仅作定位；P3/P4/P5 section与符号是实施依据。新增 source 模块固定两个共享入口 `project_cn_annual_report_original(snapshot)->SourceSnapshotFileDescriptor`、`read_cn_annual_report_pdf(ticker,document_id,expected_publication,expected_meta,source_repository,cancellation_checkpoint)->CnAnnualReportPdf` 及 `CnAnnualReportSourceError`；签名与职责已写全，不交 implementation 重新选策略。private COMPLETE helper只接受同窗classification/meta/candidate及witness，不接受prepared。source读取I/O与facts纯parser分离，没有新增协议/DB/CLI或Fs owner修改。

## Open question 的收束与真实 Docling probe

P6.2a `:389` 将“有效Docling/原件一致”写成实际字段/API步骤：

- primary_document = snapshot.primary_filename = 唯一声明 source=docling 的exact JSON名；original同共享projection。两实际bytes分别核SHA/size与files/descriptor声明，PDF另核source_meta.pdf_sha256与官方证据；fingerprint只调用现有公开build_content_fingerprint。download声明没有derived_from，不为验收创造schema。
- 实际JSON用当前 `DoclingDocument.model_validate_json` 验证，要求origin及非空pages；不以json.loads或假Docling通过。真实API输入是不可变PDF bytes + stream_name，原件file entry与converter使用同一个pdf_filename由owner调用链/测试证明。公开CLI进度没有source_name，不能把内部payload冒充公开运行证据。
- expected origin用当前SDK公开 `create_file_hash(BytesIO(actual_pdf_bytes))` 和真实 `DocumentOrigin.model_validate` 构造，核mimetype/filename/binary_hash/uri；不手写SDK hash截断、不按文件名形态反推来源、不要求origin.uri是远端URL。三新全文fiscal_year_source=source_document，实际PDF经same facts owner确认正确财年/full；两历史摘要不追补为新来源。
- coverage按**实际修改生产/测试**逐文件≥80%；新增source owner计入12个生产文件，路径相对于repo root精确匹配；utils免tests/coverage但仍pyright，不降低/掩盖类型门槛。仅加跑未改的HK文件不算“修改测试”。

本轮执行与真实边界：

| 实际动作 / 记录 | 实际退出、观测 | 不证明什么 |
| --- | --- | --- |
| 激活venv；`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python workspace/tmp/601225-plan-fix-r2/probe_docling_contract.py`；`docling-contract-probe.log/.json` | **0，实际进程退出**。Docling2.127.0/core2.96.0/Pydantic2.13.2与当前lock一致。三官方PDF实际InputDocument/backend均valid，287/297/294页；input.document_hash来自真实bytes，origin采用实际input.file.name、uri=null。真实模型export→model_validate_json roundtrip成功，非Docling与损坏JSON拒绝。 | roundtrip模型是明确探针，没有运行PDF→Docling转换，没有新public CLI或修复owner回归；不把模型当三真实转换产物。 |
| 激活venv后inline只读SDK probe；`origin-model-validate-probe.json` | **0**。三份实际PDF通过公开create_file_hash + DocumentOrigin.model_validate得到与上述真实输入相同origin；真实API而非推测算法。 | 没有追加转换或持久资产写入。 |
| 当前Dayu/SDK源码、方法签名与locks只读核对 | InputDocument / standard reading-order origin / export与JSON读取API；filing→shared worker→DocumentStream链；snapshot仅published；业务counts与catch链；README读者约束。 | 静态读取不等于实现、tests、pyright通过。 |
| plan对冻结副本的diff/文档检查、保护性hash | `plan-r1-to-r2.diff`、`document-check-preartifact.json`、最终`document-check.json`、`protected-before.json`/`protected-after.json`；保护检查只允许plan原文件变化。 | 不等于planreview/re-review pass，不替代总控冻结复审。 |

**未运行项**：生产facts/source/DTO/acquisition/identity/A-B/catch代码与测试实现；依赖安装/pipcheck；受影响pytest、新矩阵、逐文件coverage、pyright复跑；正式utils/observer；四次真实bareCLI clean/seeded/repeat、真实Docling与仓储读回/hash/网络对账；实施后README；双路r2复审。未重做官方HTTP取证、历史raw、r1observer、已闭环grammar探针或432测试/pyright未变基线。临时probe在workspace下，不修改utils/venv依赖。

## Hash保护与docs决定

`protected-before.json`在任何plan写入前保护 **10,272个文件**：所有当时Git tracked文件、gateflow/reviews全部既有文档、本仓原`workspace/tmp/601225-evidence/`与r1临时证据、调用方原只读证据根 `/Users/leo/workspace/portfolio-manager-v2/orch/jobs/20261012-601225.SH-01/`。原plan另保 `plan-before.md`，输入hash与总控冻结相等。`protected-after.json`逐个复算，唯一允许变化是本plan，任何其它变化/缺失都会报错；HEAD/branch也复核，无新增tracked代码变更。r2新产物与探针不覆盖任何原记录。

本轮docs决定：只改plan并创建本文，不改root-cause-evidence或其它review/state。已读根README/Fins README的Agent更新约束及tests README事实边界；能力尚未落地，README保持原样。P7只规定实施后按三份README读者职责记录实际FY原文/增量/失败机制、无witness原件证明与已落地测试；无分层/装配/入口变化，不扩dayu/Engine/Host/Config README。

## 分类 residual risk / owner / destination

| 风险 / 未覆盖 | 分类 | owner / destination | 阻塞及处置 |
| --- | --- | --- | --- |
| 四accepted及Docling规格的文档修订尚未复审验证 | fixed in current slice（plan fix/re-review责任） | Sol/总控 / 本plan、本文、双路同hash re-review | 不自放行，正式finding状态由总控待复审回写。 |
| S1生产实现/owner矩阵/类型/逐文件coverage/依赖与README未执行 | fixed in current slice（S1未来验证） | 实施Agent/总控 / implementation、checks、code-review artifacts | 后续实施gate必须完成，不用本文/探针替代。 |
| 四次真实CLI、真实转换、正式observer/verify/compare未执行；外部内容/网络/pin变化 | fixed in current slice（验收责任） | 实施/验收Agent/总控 / P6原argv/exit/raw/http/model/hash/compare证据与差异裁决 | 无真实对账不能pass；保存差异，不改binding标准。 |
| 隐藏坏摘要/未知identity/同源历史错年自动恢复 | assigned to later work unit | Fins完整性维护者/总控 / 独立历史完整性任务 | 本轮只读factsGET+typed安全失败/零业务写，不扩恢复。 |
| SDK origin有损Uint64、download无derived_from，不能单独证明历史转换因果 | assigned to later work unit | Fins转换/审计维护者/总控 / 如有需要的独立来源审计任务 | 当前以真实转换进度+完整两SHA/fingerprint+模型origin核对，不创造schema；非本目标blocker。 |
| 历史启动树/raw缺失 | assigned to later work unit | 总控 / 原根因证据边界及后续可追溯任务 | 不补造历史事实。 |
| OCR/扫描/未知/跨行布局、其它公司/公告 | assigned to later work unit | Fins年度事实维护者/总控 / 独立发现任务 | 无可靠facts整次失败，影响本目标才给具体blocker。 |
| 落选全文/摘要repeatGET成本 | assigned to later work unit | Fins维护者 / 后续按需性能任务 | 既有精确允许集合不变，不增cache。 |
| UTC/本地披露日偏差 | assigned to later work unit | Fins日期维护者/总控 / 独立日期任务 | 本目标远离窗口边界，不扩一般日期。 |

只有S1，无later approved slice/既有issue；不创建issue或把风险分类冒充已解决。未发现必须改变binding boundary的具体blocker：B缺batch snapshot以原rollback/freshA路径收束，Docling真实API与现有声明可支持本次可核关系，历史因果审计局限明确归后续任务。

## 交付状态与总控接手点

计划修订交付已完成；没有 implementation、re-review pass、accepted commit 或state转移。总控应在确认本次runner实际退出与保护hash后，再冻结本文plan hash并同时派MiMo/DS复审同版；本Agent未派发/操作其他Agent。若复审发现accepted未闭合，仍由总控裁决plan fix，不以本文自行推进。
