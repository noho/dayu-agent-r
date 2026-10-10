# 下载失败诊断：最小实现计划

- Work unit：download-failure-diagnostics-20261010
- 原 plan task label：dfdiag-plan-sol-20261010-01；本次 fix task label：dfdiag-plan-fix-sol-20261010-01。
- Gate：plan fix；按总控裁决修订 P1—P4，下一未完成 gate 为 re-review，不声明 plan 或 review gate 通过。
- Artifact：`docs/gateflow/download-failure-diagnostics-plan-20261010.md`
- Goal：`docs/gateflow/download-failure-diagnostics-goal-20261010.md`，2026-10-10 已确认。
- Branch：`fix/download-failure-diagnostics-20261010`
- 固定 base / 阅读时 HEAD：`c65c2aa28fae9c47ad947783d63f7559db7768c4`
- Design document、issue number、issue 关联：N/A。
- Fix preflight：branch / HEAD 与冻结输入一致；修改前 plan SHA256 为 `e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`。所有 download-failure-diagnostics-* 未提交文件归属已由总控核清：goal/state/old-evidence/adjudication 属总控，plan 属计划 Agent，review 属各 reviewer；没有未知 dirty。总控继续更新 state 不构成 ownership blocker。
- 本次只修改本 plan 并新增 `docs/gateflow/download-failure-diagnostics-plan-fix-20261010.md`；不实现、不改其它文件、不创建 commit/push/PR。
- RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6.1-sol（本轮 runner 配置；自报与配置名一致，未独立证明底层物理型号，不使用 Node 元数据或默认继承环境证明型号）。
- 本轮 canary 文件：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.p84mXh/canary.txt`
- CANARY=gpt-6-sol-1bbb6ea8
- 修订依据：`docs/gateflow/download-failure-diagnostics-plan-adjudication-20261010.md` 及两路本 unit plan review；其余有证据设计沿用原 plan。

## 1. 目标、动机与边界

动机成立。原运行确实结束，退出 0，但 53 个候选包含 34 个下载、11 个跳过、8 个失败；退出 0 表示当前 direct 调用完成，不表示每个候选都下载成功。原 stdout 未包含这 8 项的具体安全原因、来源日期和财期，当前有界摘要也无法取回所有失败。该缺陷必须在产生和投影下载结果的 owner 链上修复。

本次目标是：在 Dayu 下载职责内，使给定请求的成功、跳过、失败如实可核验；完整失败候选身份、上游已经提供的日期/表单/期间及安全原因都可取得，包括失败位于前 10 项之后、失败数量超过 10 的运行。来源未提供的信息保留显式未知。不把无界失败数组放进 LLM-facing wait/tool summary。

给定请求明确为 ticker=0700、2018-01-01 至 2026-10-10；真实安全原因保真修复限定于 CN/HK 共用 owner 链。通用完整 typed result 接口仍机械用于所有来源，但 SEC 仅验证完整性、身份和既有安全投影不变；现有 SEC adapter 会将原因说明改成通用文案，不能宣称已保真，也不纳入此次原因修复目标或 SEC 生产改动。

实际下载故障未被证明：不能把旧 8 项归因为 HTTP 404、网络、PDF 内容、转换、筛选窗口或来源缺口。现有 transport owner 的安全分类是本次原因精度上限；不为了“更详细”泄漏原始异常、URL、响应体、联系人或绝对路径。

非目标：不改 provider 获取/重试/selection/日期算法、下载资产或 publication 状态机；不设计 job/resume、历史诊断仓储、分页查询或自动重试框架；不改退出码政策；不作财务覆盖判断；不兼容旧 schema / 旧 constructor；不读取调用方 workflow、gate、审核包、范式；不改调用方产物、Raw、生产来源；不 overwrite、rediscover、直下 PDF、整批重跑。任何新观测或发现的实际下载缺陷，先由总控给巡检线报出范围和影响并确认，不能由 implementation 自行扩范围。

## 2. 直接证据与语义 owner

以下代码位置均基于固定 HEAD；实现后行号可变化。

| 事实 / 语义 | Owner 与直接代码证据 | 计划判断 |
| --- | --- | --- |
| 候选身份、来源披露日期、报告日期、身份/覆盖财期 | `cn_download_models.py: CnReportCandidate`；`cn_download_filing_workflow.py: _build_filing_result`；`cn_download_workflow.py: _build_candidate_failed_result` | 使用 workflow 结果，禁止从 document_id、标题、文件名或仓储偶然顺序反推日期和期间。 |
| 单候选安全原因 | `cn_download_filing_workflow.py:73 project_cn_filing_failure`；PDF 失败分支 `:259-290`；workflow 的单候选异常分支 `:402` | 已投影 provider 分类及 safe_message、storage 或 execution 分类；不需要另造原因体系。 |
| HK transport 安全分类 | `hkexnews_downloader.py:673 _hkexnews_http_failure`；协议异常 `HkexnewsProviderProtocolError` | HTTP 状态当前只承诺 `http_status` 和安全说明，没有具体状态数的 public contract；不能伪造更精细原因。 |
| CN/HK 对外 typed row | `cn_pipeline.py:1457 _project_cn_pipeline_summary`、`:1506 _project_cn_document_row`；`:1570-1590` 替换 skip/failure 原因，failure 使用 `reason_code or "cn_document_failed"` | 信息丢失发生在 adapter 投影边界；这里严格读取上游原因，不在 CLI 补原因。HK 与 CN 共用这一 adapter，无独立 `hk_pipeline.py`。 |
| SEC 既有安全投影限制 | `sec_pipeline.py:1933-1973` 调用 `_sec_safe_reason_message`，`:2092-2114` 按 disposition 生成通用文案；`sec_download_filing_workflow.py:314-325,614-623` 提供上游原因 | 原因说明并未保真。完整诊断机械保留现有 typed row；本轮不改 SEC 生产代码，不把上游原始异常直接透传。SEC 原因 owner 治理另定 work unit。 |
| 完整单调用结果、计数、正常终态 | `download_contract.py:412 FinsDownloadResultSummary`、`from_document_rows`、`:652 download_terminal_disposition_from_counts` | 完整 typed rows 已存在，owner `omitted_count` 为 0，计数从 rows / uncertain 集合派生；复用它。 |
| 部分中止的已处理快照 | `ingestion_runtime.py:623 FinsSourceDownloadAdapterFailure` 的 `persisted_summary`；`cn_pipeline.py: _summary_from_integrity_failed_pipeline_result` | 这是已验证的已处理候选快照，不等于中止后尚未处理候选的结果。 |
| 有界 public terminal | `direct_events.py: FinsDownloadPublicDocument / FinsDownloadPublicSummary`；`ingestion_runtime.py:6827 _public_download_summary` 在 `:6854` 截前 10 行 | 保持有界；将投影规则收敛到 public contract owner，完整结果成为 direct result 的唯一输入真源。 |
| direct 执行结果与取消裁决 | `ingestion_runtime.py:4321 _run_direct_stream_producer`、`:4377 _produce_direct_download`、`:6261 _emit_direct_result`、`:6544 _direct_result_event`；`direct_events.py: ValidatedFinsEventStream` | 复用终态 claim、完整性 typed failure 和 stream 最后唯一 RESULT；不新增事件种类或取消状态机。 |
| CLI 结果通道 | `cli/output.py: render_fins_direct_event`、`:401 _print_terminal_business_summary`；`cli/commands/fins.py` 消费 validated stream 并返回 `terminal_result.exit_code` | SUCCESS 写 stdout；FAILURE / CANCELLED 终态写 stderr；CLI 只序列化 owner 给出的对象。 |
| LLM 消费 | `service/fins_wait_adapter.py:519,593,624` 只序列化 `result.download.to_json_value()`，download tool 经 observation / wait | 保持该路径有界，不调用新的完整诊断方法；不改 tool schema / prompt。 |
| 默认日志生命周期 | `cli/main.py:109,130,189`，`_open_default_log_file()` 返回 TemporaryFile，finally 关闭 | 不依赖日志恢复完整结果；无需更改通用日志政策。显式 `--log-file` 仍只是 operator 诊断。 |
| published 来源与只读查询 | `storage/repository_protocols.py:1275 get_source_meta`；`fs_source_document_repository.py:229` 支持 `create_directories=False`；`_fs_repository_factory.py` 该模式不触发 recovery | 原来源仍只经公共 storage 仓储接口读；失败结果不是 published source，不把它塞进 source meta。 |

原 plan 已读取根 AGENTS.md、goal、gateflow plan 要求、上述 contract / adapter / workflow / downloader / runtime / direct events / Service / CLI / storage、相关测试及 README 职责。本次 fix 读取 AGENTS.md、goal、plan、裁决、两路 review 与 old-evidence JSON，并限定复核 SEC/CN 投影、mismatch 分支、runtime 终态 helper、direct contract、CLI 输出及对应现有测试。其余 owner 证据沿用原 plan，没有重新全仓探索或读取调用方其它 workflow / gate / 审核包 / 范式文件。

## 3. 明确的接口与数据流决定

### 3.1 不增加强制持久仓储

选择：完整失败结果通过现有 direct terminal Python 接口及 CLI 单行 JSON 公开；调用方捕获标准流即可保存。当前 goal 要求完整诊断可取得，没有要求重启进程后通过 Dayu 历史查询 API 找回任何未捕获结果。

理由是直接证据：完整 typed rows 已在 operation-local result 中；原调用方已经保存 stdout/stderr；丢失发生在 public projection 和 adapter。新建数据库、diagnostic repository、job id、artifact registry 或强制文件目录都不是修复该根因的必要条件。默认完整输出不依赖用户记得指定日志参数。过去未输出的原因无法由本次增加持久化追回。

本方案不承诺 SIGKILL、崩溃、未消费/提前关闭 stream 或未捕获标准流后的历史恢复。该限制明确报告，不扩成新增持久化需求。若总控 / plan review 判定 goal 必须包含这种承诺，先重新确认目标，本计划不把接口留给实现时临时选择。

### 3.2 完整结果是 direct result 的唯一下载输入

在 `FinsResultSummary` 中，以现有类型新增 constructor 字段：

```python
download_result: FinsDownloadResultSummary | None = None
```

删除现有 constructor 中可独立传入的 `download: FinsDownloadPublicSummary | None` dataclass 字段。保留对消费者有意义的 `download`，改为只读派生 property，返回 `FinsDownloadPublicSummary | None`。它从 `download_result` 派生，不接受另一个结果、更不从日志 / raw fields 重建事实。所有合法下载终态一律带非空 `download_result`，包括 direct RESULT 和未经过 event 构造的 observation terminal；`None` 只代表无下载结果的合法非下载 terminal，不能表示缺失结果的合法下载失败。启动前失败、activation submit 失败、prepare 取消均由持有 download request 的 runtime owner 明确提供 request-scoped typed 空结果，不靠消费者补默认结果。旧 `download=` constructor 使用点一次迁移到 `download_result=`，不保留兼容 constructor、wrapper 或 re-export，不新增 operation 字段。

public projection 的唯一接口放在 `FinsDownloadPublicSummary`：

```python
@classmethod
def from_result_summary(
    cls, summary: FinsDownloadResultSummary
) -> FinsDownloadPublicSummary:
    ...
```

将原 `_public_download_summary` 的现行算法移入该 owner：document rows 原顺序前 10；omitted 为完整 rows 长度减公开长度；uncertain 使用现有预算算法；filters、counts、missing_periods、terminal 均来自同一 typed summary。删除 runtime 原 helper，迁移其调用与测试引用，不保留透传 seam。

在 `download_contract.py` 增加唯一下载摘要预算常量 `FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS: Final[int] = 4096`。本次仅把现有 download 的 durable / public uncertain budget 调用统一使用它；runtime 的通用 `_MAX_SUMMARY_JSON_CHARS` 继续用于非下载摘要，不重构其它操作。上限 10、文本上限 240 保持原常量。无数据库 schema 改动，现有有界 JSON schema 保持不变。

在 `direct_events.py` 增加模块级 `_download_public_document(row: FinsDownloadDocumentResult) -> FinsDownloadPublicDocument`，机械投影全部现有业务字段、仅把 PurePosixPath 转为 relative string。有界 rows 和完整失败 rows 共用它及既有 `to_json_value()`，避免两套 JSON 字段/身份转义规则。

`FinsResultSummary.__post_init__` 保持现有 status/exit/failure/warning 不变量，并对 `download_result` 做严格 typed 检查，通过派生 `download` 校验原下载状态组合。`FinsEvent.__post_init__` 补 owner 级操作约束：DOWNLOAD 的 RESULT 必须有 `download_result`，其它 operation 的 RESULT 不得携带它；PROGRESS 仍无 result。fixture 必须构造真实合法 typed result，禁止 fake 默认补齐。

### 3.3 完整失败诊断的公共方法与 JSON

在 direct public result owner 增加：

```python
def to_download_diagnostics_json_value(self) -> dict[str, JsonValue]:
    ...
```

该方法直接检查唯一下载输入：`download_result is None` 时抛 `ValueError`，不尝试推断 operation，不补空结果；合法下载 terminal 因上述 owner 不变量不会进入该拒绝分支。存在结果时仅从 `download_result` 和既有公共失败对象产生下面的精确 schema，不设置行数/总字符上限，不增加持久化 ID。其 `summary` 仍是现有 bounded schema，完整列表单独命名为 `failed_documents`，不会让消费者误把 bounded documents 当作全量。

| 必填字段 | 类型 / 允许值 | 语义 |
| --- | --- | --- |
| `operation` | string，固定 `download` | 当前操作。 |
| `status` | `success` / `failure` / `cancelled` | direct 调用状态，沿用 owner。 |
| `exit_code` | int，分别 0 / 1 / 130 | product entrypoint 的终态退出码。 |
| `summary` | object | 现有 `FinsDownloadPublicSummary.to_json_value()` 全部字段，见下文；它是有界摘要。 |
| `failed_documents` | array of object，允许空 | 遍历完整 typed `document_rows`，按原顺序选 disposition=FAILED；完整、无 omission。每行复用 public document JSON。 |
| `failure` | object 或 null | 整体失败用现有 `FinsPublicFailure.to_json_value()`；正常 / 取消为 null。不伪造某候选原因。 |
| `scope_note` | string | 固定自解释说明：`诊断覆盖本次调用已返回结果的候选；取消或整体中止时，尚未返回结果的候选不作成功、跳过或失败判断。` |

`summary` 的必填字段全部保留：`source`（sec/cninfo/hkexnews）、`ticker`（canonical string）、`filters`（forms:string[]、start_date/end_date:string|null、overwrite/rebuild:bool）、`counts`（discovered/downloaded/skipped/rejected/failed/uncertain:非负 int）、`documents`（有界文档数组）、`uncertain_reports`（现有独立未知报告数组）、`omitted_uncertain_count`（非负 int）、`missing_periods`（string[]）、`omitted_count`（非负 int）、`terminal_disposition`（succeeded/partial_failure/failed/cancelled）。不改变 uncertain 的独立语义，它不属于 FAILED 文档，不并入 failed_documents。

`failed_documents` 每行所有字段必填：`document_id:string`、`form_or_period:string|null`、`filing_date:string|null`、`report_date:string|null`、`covered_fiscal_periods:string[]`、`disposition` 固定 `failed`、`reason_category:string`、`reason_message:string`、`artifact_locator` 固定 null。未知日期/期间为 null / 空 coverage，禁止拼日期、猜财年、以占位文本代替 null。原因必须满足既有 240 字与安全校验。`failure` 非空时保留现有必填六字段：classification、source、transport_category、message、retry_hint、reason_code。

最小合法 JSON 例（仅演示新的输出协议，不是旧运行原因证据）：

```json
{"operation":"download","status":"failure","exit_code":1,"summary":{"source":"hkexnews","ticker":"0700","filters":{"forms":["FY","H1"],"start_date":"2018-01-01","end_date":"2026-10-10","overwrite":false,"rebuild":false},"counts":{"discovered":1,"downloaded":0,"skipped":0,"rejected":0,"failed":1,"uncertain":0},"documents":[{"document_id":"example-report","form_or_period":null,"filing_date":null,"report_date":null,"covered_fiscal_periods":[],"disposition":"failed","reason_category":"provider_timeout","reason_message":"披露易来源请求超时","artifact_locator":null}],"uncertain_reports":[],"omitted_uncertain_count":0,"missing_periods":[],"omitted_count":0,"terminal_disposition":"failed"},"failed_documents":[{"document_id":"example-report","form_or_period":null,"filing_date":null,"report_date":null,"covered_fiscal_periods":[],"disposition":"failed","reason_category":"provider_timeout","reason_message":"披露易来源请求超时","artifact_locator":null}],"failure":{"classification":"execution","source":"hkexnews","transport_category":null,"message":"未取得可用来源文档","retry_hint":"请检查文档失败分类后重试。","reason_code":null},"scope_note":"诊断覆盖本次调用已返回结果的候选；取消或整体中止时，尚未返回结果的候选不作成功、跳过或失败判断。"}
```

不变量：`len(failed_documents) == download_result.failed_count == summary.counts.failed`；每个失败 row 的全部字段与来源 typed row 相等；没有 failures 时输出显式空数组。summary 的 omission 只描述 summary.documents，不描述 failed_documents。该方法是 operator / direct client 接口，LLM wait/tool 不调用它。

### 3.4 Adapter 与 CLI 的精确变更

`cn_pipeline._project_cn_document_row`：FAILED 严格使用 `_required_cn_text(item, "reason_code")` 和 `_required_cn_text(item, "reason_message")`；删除 `cn_document_failed` fallback 和通用失败说明。SKIPPED 同样原样保留 workflow 的 `reason_code` / `reason_message`，删除通用 skip 说明及该处原因猜测；normal、rebuild、typed integrity abort 三入口共用该投影。上游 workflow 已提供这些字段（例如 integrity_complete、period_metadata_mismatch、missing_form_type），缺字段、空字段、不安全字段即 contract violation，不能用 skip_reason 或下游默认值补偿。DOWNLOADED 仍无失败原因；不改来源执行逻辑。现有缺失业务字段的 rebuild 语义不在本次重新设计。

CLI 在每个合法下载 RESULT 的既有摘要之后，必定输出且只输出一行：

```text
Fins download diagnostics: <完整 JSON object>
```

前缀为模块级常量；用 `json.dumps(result.to_download_diagnostics_json_value(), ensure_ascii=True, sort_keys=True)`，不缩短身份，不调用 `_bounded_json_text` / 通用文本截断器，也不把它变成 FinsEventDetail。ASCII 转义保持引号、换行、反斜线、Unicode 行分隔符和 240 码点身份可逆，一份 JSON 不形成额外物理行。FAILED 文档可能同时出现在 bounded documents 和完整数组，两者是明确不同的投影，不去重改事实。

通道与退出码沿用现状：SUCCESS（含 partial_failure）终态和诊断在 stdout；FAILURE / CANCELLED 终态和诊断在 stderr；progress 在 stdout。CLI `Fins summary:` 增加 `terminal_disposition=<JSON string>`，使调用成功与候选 partial_failure 可直接区分。没有下载结果的其它命令不输出该行。标准流输出失败沿用 OSError 传播，不默默吞异常或宣称诊断已交付。

### 3.5 Runtime、异常与取消数据流

正常链：来源 workflow 完整结果 → CN/HK / SEC adapter 的 `FinsDownloadResultSummary` → `_execute_download_request` 身份与计数验证 → producer → `_emit_direct_result` / claim → `_direct_result_event` → `FinsResultSummary(download_result=...)` → validated stream（确认最后唯一 RESULT）→ Service 原样传递 → CLI；LLM wait 同一 result 的 `download` property → 有界 JSON。

runtime `_emit_direct_result`、`_emit_claimed_direct_result`、`_direct_result_event` 的参数由 bounded `download` 改为完整 typed `download_result`。所有下载调用点传原 typed summary；非下载传 None。`_produce_direct_download` 的正常 / 全失败、`_run_direct_stream_producer` 的 typed exception / 普通异常、`_emit_direct_cancelled_result`、observation prepare-cancel / failure helper 一次迁移；非下载 upload 使用 `_direct_result_event` 的调用只机械更名 None，不改业务行为。

activation submit 失败的 exact 改法（固定 HEAD `activate_observation:4005-4014` → `_mark_observation_failed:7486-7521`）：

1. `_observation_failure_result` 的 `download=` 改为 `download_result=`：有 request 时直接传 `_empty_download_summary_from_request(download_request, terminal_disposition=FAILED)`，删除此处 `_public_download_summary` 包装；无 request 时为 None。保留既有 whole failure：kind=EXECUTION、source=request.source、transport_category=None、safe_message=`下载执行未产生完整终态结果`、retry_hint=`请重新发起下载；若持续失败，请检查运行环境。`；不把 submit 原异常写进文档原因。
2. `_mark_observation_failed` 保留 `_safe_observation_message(message)`、`record.status=FAILED`、`record.message=safe_message`，把现有裸 `FinsResultSummary(...)` 构造整体替换为 `_observation_failure_result(operation_kind=record.handle.operation_kind, download_request=record.context.download_request)`。该 helper 已持有结果构造所需 request；不是下游补偿。当前唯一调用明确传 EXECUTION，复用 helper 的既有 EXECUTION 语义后删除 `_mark_observation_failed` 无需再使用的 `error_kind` 参数及 activation 唯一调用的该实参；不新增 wrapper、操作字段、分支或 fallback。
3. `activate_observation` 的锁、submitted 标记、异常后收口和裸 `raise` 保持原行为；submit 原异常以同一对象继续抛出。`_observation_cancelled_result` 同样直接构造 typed 空 CANCELLED 结果，failure=None。producer 缺 RESULT 的既有 `_observation_failure_result` 调用同步得到同一契约，不改变调度或治理状态机。

| 情况 | 完整结果 / 终态规则 | 必须保留的语义 |
| --- | --- | --- |
| 无失败且无 uncertain | 既有 typed summary；direct SUCCESS / 0；正常 terminal 沿用 owner | skipped 不等于 downloaded，空候选不是失败。 |
| 有成功下载且存在失败 | full rows；现有 SUCCESS / 0 与 partial_failure | 完整失败列表必须输出；不把 0 当成全候选成功。 |
| 全失败，或现有 uncertain 整体失败规则 | full rows；既有 FAILURE / 1、closed whole failure | 各文档原因与整体失败原因各在自己的字段。 |
| `FinsSourceDownloadAdapterFailure` | 原 `persisted_summary` 及原 typed cause；既有 FAILURE / 1 | 已处理前缀中的下载 / 失败全部保留；不能从最初发现数填造中止后的结果。 |
| adapter 启动前失败，尚无 typed snapshot | request-scoped typed 空结果，terminal FAILED；whole failure 是真实安全原因 | 空 failed_documents 表示未产生文档级结果，不表示没有整体错误。 |
| observation activation executor.submit 失败 | `_mark_observation_failed` 复用 `_observation_failure_result`；request-scoped typed 空 FAILED、direct FAILURE / 1、EXECUTION whole failure | 原异常同对象传播；download observation 的 poll result 有非空 download_result，完整诊断可调用；非下载 observation 仍有合法失败 result，其中 download_result=None，不凭缺失猜操作。 |
| workflow 取消返回结果，或终态 claim 时取消胜出 | 对完整 typed summary `replace(..., terminal_disposition=CANCELLED)`，然后派生有界摘要；direct CANCELLED / 130，whole failure=None | 已确认 downloaded/skipped/failed 行和原因不丢，不把取消候选算失败；取消发生在 claim 前后沿用既有裁决。 |
| prepare/开始前取消 | request-scoped typed 空 CANCELLED 结果 | 不造文档或未知原因。 |
| stream 不干净结束、重复 RESULT、RESULT 后事件、上游 BaseException | 保持 validated stream 原异常对象、关闭行为与协议错误 | 不输出未经验证的终态诊断；不新增第二个 RESULT 或强制持久化。 |

下载 durable job 的现有 bounded `to_json_summary` 字段、store validator 与 status 政策不变，仅下载预算常量同源。Host/EventLog/memory/trace 不新增完整数组；既有计数、terminal 和公开行仍从同一 typed owner 派生。不存在“CLI 原因正确但持久化另造原因”：durable 摘要本就不承诺逐文档原因，不能扩大该承诺或把 omission 冒充完整结果。

## 4. 一个行为 slice 与允许文件

### S1：任何合法下载终态都交付同源完整失败诊断

前提：总控完成 plan review / fix / re-review 与 accepted plan；固定 HEAD 是本计划阅读基准，implementation 进入时重新核对 branch、HEAD 的合法计划 commit 与 dirty ownership。其它 design_doc N/A。

预期行为增量：CN/HK 来源安全原因不丢失；direct client 可取得完整 typed result；CLI 默认完整失败 JSON 对数量与位置无截断；有界 wait 与 durable 摘要不扩容；错误/取消终态与已确认行守恒。将这些改动合成一个 slice，不能先交 CLI fallback 再补 owner，也无需按模块拆成多个 gates。

生产代码仅允许以下文件：

1. `dayu/fins/download_contract.py`：新增下载预算常量及 export；不改计数算法、来源 schema 或 repository。
2. `dayu/fins/direct_events.py`：完整 result 字段、派生 public property、public projection classmethod、共享 row projection、完整诊断方法、typed / operation 不变量和中文说明。
3. `dayu/fins/ingestion_runtime.py`：传递完整 result、取消覆盖同一完整结果、删除旧 public helper、下载预算常量调用迁移。只改上述下载收口调用链及非下载同签名 None 参数；不重构其它 runtime 功能。
4. `dayu/fins/pipelines/cn_pipeline.py`：strict 同源 reason 投影。
5. `dayu/cli/output.py`：机械完整诊断输出、摘要终态字段、前缀常量。

测试允许：

- `tests/fins/test_download_failure_diagnostics.py`（新增）：owner、公用 JSON 与超过 10 失败的主要契约断言。
- `tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`：CN/HK 实际 workflow / adapter 链原因保真及 isolated storage 验证。
- `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_direct_stream.py`：终态、取消、typed abort、完整 result、consumer close 与 fixture constructor 迁移。
- `tests/fins/test_f5_result_contract.py`：改 public projection 调用位置，保持未知 / durable 预算断言。
- `tests/fins/test_fins_ingestion_tools.py`：仅现有 constructor 迁移与 LLM-facing bounded 投影回归，不改工具行为。
- `tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`：各通道、JSON、CLI 主入口/真实固定 executable 的 isolated fixture 测试与 constructor 迁移。
- `tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`：仅受影响 fixture constructor 迁移、同对象完整 result 与 bounded wait 断言。

文档允许：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`（仅后续 implementation）。开发 artifacts 由总控按相应 gate 指定；本次 plan fix 仅写本 plan 与 plan-fix artifact。临时脚本仅 `workspace/tmp/`，分析辅助代码仅 `utils/`，本 slice 不新增常驻分析工具。不要顺手修改未经列出的代码、配置、schema、downloader、workflow 或 storage；fixture 违反 strict owner contract 时修 fixture。需要名单外生产改动、CN/HK 真实原因 owner 不足或新观测才能决定策略时停止报总控；SEC 已知原因泛化属于明确后续风险，不触发本轮跨来源修复。

所有新增/修改函数严格类型、完整中文参数/返回/异常 docstring；不使用 Any/object、hasattr/getattr、lazy import、extra payload 或兼容分支。不得将原异常字符串透出。

完成信号：下节断言和验证完成、README 职责内更新完成、原证据逐项报告及固定 CLI 状态有证据、残余风险分类齐全，交总控 code review。本 Agent 不裁决 slice / gate pass。

## 5. 测试与验证：具体断言与命令

### 5.1 必须新增 / 更新的断言

1. owner / public projection：构造 11 个 skip + 1 个 downloaded + 12 个 FAILED，失败全部在前 10 项之后；len(full rows)=24，failed=12，bounded documents=10，omitted=14；完整 failed_documents 恰好 12，顺序、ID、form/date/coverage/reason 均等于 typed rows。再参数化 0 / 1 / 10 / 11 / 12 个失败、三 source、null 元数据与 240 码点特殊身份；全失败超过 10 同样完整。summary 的正常/取消不变量原样成立。在 `tests/fins/test_download_failure_diagnostics.py` 明确 owner 负例：构造不带 download_result 的 DOWNLOAD RESULT 必须抛 ValueError；参数化每个非 DOWNLOAD operation，其 RESULT 携带合法 typed download_result 必须抛 ValueError；合法非下载 terminal 的 download_result=None、download=None，调用诊断方法必须抛 ValueError。使用其它字段完全合法的 result/event，使失败只来自所断言的操作约束，不以非法 fixture 偶然失败替代契约验证。
2. CN/HK owner 真链：使用真实 isolated Fs repositories、existing workflow 与真实 CN adapter；只替换外部 discovery / HTTP transport / converter。提供明确不同的 candidate 日期/coverage、typed provider_timeout/provider_http_status/protocol 安全说明，以及 storage / execution 示例。assert workflow filing_result → typed row → bounded public row / 完整 diagnostics 逐字段相同；SKIPPED 的 integrity_complete（HK rebuild 的 period_metadata_current）原因不泛化。独立覆盖 period_metadata_mismatch：workflow status 必须是 failed，typed disposition 必须是 FAILED，其 reason_category/message 保真且该行进入 failed_documents；不得构造为 SKIPPED 或沿用 skip 断言。缺 reason_code、缺 reason_message、空字段、unsafe message 必须拒绝，不能落回通用文案。正常、rebuild、typed abort 三投影入口覆盖；上游未知保持 null，来源已有字段不能丢。
3. runtime 正常部分失败、全失败、empty success、provider 启动前失败、typed integrity abort：assert status/exit、terminal、whole failure 分类，确认前缀保留、len(failed_documents)=failed_count，不从发现进度猜未处理结果。adapter 启动前失败必须返回 request-scoped typed 空 FAILED：source/ticker/filters 等于原 request，counts 全零、rows/failed_documents 空，FAILURE/1 且 whole failure 非空并保持原安全分类；不能以 None 表示失败。SEC 仅断言完整 typed rows 的身份/顺序/字段机械进入 diagnostics，既有 adapter 安全文案及分类保持原值；不要求 SEC workflow reason_message 与 typed row 相等、不改 SEC 生产代码、不声称 SEC 原因保真。
   activation 专项在 `tests/fins/test_fins_ingestion_runtime.py` 更新 `test_activation_submit_failure_terminalizes_prepared_observation`：以 `_FailingSubmitExecutor` 分别抛 OSError / ValueError，prepare 真正的 download request 后 activate，assert 抛出的正是原异常对象；poll snapshot=FAILED、result=FAILURE/1、error_kind=EXECUTION、download_result 非空且 terminal=FAILED；source/ticker/所有 filters 对齐原 request，counts 全零、document_rows=()、diagnostics.failed_documents=[]，whole failure 与 §3.5 helper 既有安全投影逐字段一致，不能包含原异常文本。原非下载 upload activation 测试保留，并断言 download_result/download/failure 均 None、诊断方法 ValueError；不添加 event 来掩盖私有 record.result 的缺失。
4. cancellation：before-start / 已有 downloaded+failed 前缀 / terminal claim 的取消竞争；CANCELLED/130、完整前缀及原因保留、whole failure=null；未处理候选没有伪结果。在 `tests/fins/test_fins_ingestion_runtime.py` 增加 download prepare-cancel 用例（原 preprocess 用例保留）：`prepare_observed_download` → `cancel_observation` → `activate_observation` → `poll_observation`；assert executor.operations=[]，两个 snapshot 均 CANCELLED/130，download_result 非空、request filters 原样、counts 全零、rows=()、terminal=CANCELLED、failure=None，诊断方法成功且 failed_documents=[]。validated stream 最后唯一 RESULT、clean exhaustion 缓冲、重复/缺失/后续事件、取消和异常身份及 close 一次仍通过。
5. CLI render：每个下载 RESULT 在对应通道按固定前缀 `Fins download diagnostics: ` 筛选后恰有一条诊断物理行；去掉前缀后 `json.loads` 可完整恢复。不要求 stdout/stderr 总共只有一行，既有 progress、Fins summary/Fins document/Fins failure 行可同时存在。成功及 partial stdout、失败及取消 stderr，另一通道没有该前缀行，非下载两通道均无该前缀行。特殊身份/引号/换行/U+2028 可逆而不增加物理行；原因和空值不截断；human summary 显示 terminal_disposition。输出故障仍失败，不悄悄宣称保存。
6. LLM/durable：observation→wait 三终态只出现既有 bounded download JSON，documents <=10、uncertain 原有预算和 omission 仍守恒，不能出现 failed_documents / download_result 或完整诊断 wrapper。真实 job store 的 download bounded JSON 字段完全不变、预算 <=4096、原验证/取消规则通过。无需增加旧库读取或兼容 fixture。
7. 服务与入口：Service 返回同一个 validated stream、同一 terminal full result。CLI 主入口用 isolated factory fixture 证明 12 个失败即使日志 quiet / 默认临时日志仍公开完整诊断；factory 仅代替外部装配，不能由 fake 提供计算好的 diagnostics 替代 owner。
8. 固定 executable 离线验证：在 `tests/cli/test_fins_commands.py` 新增 `test_fixed_cli_download_diagnostics_on_empty_rebuild`，用 fresh `tmp_path`、仓库绝对 `.venv/bin/dayu-cli`、cwd 指向另一个临时空目录，执行 `download --base <fresh fixture root> --ticker 0700 --start 2018-01-01 --end 2026-10-10 --rebuild`，subprocess capture_output / timeout=60，check=False。该 rebuild 在 `cn_download_workflow.py` 首段直接进入 local rebuild、在任何 discovery/resolve_company 分支前返回，不触达原生产根；断言外层真实 returncode=0，从 stdout.splitlines() 按固定前缀 `Fins download diagnostics: ` 筛选后 len=1，stderr 同前缀行 len=0，剥离该前缀再 json.loads；允许 stdout 另有既有摘要、文档或进度行。解析对象断言 ticker=0700、rebuild=true、counts 全零、failed_documents=[]、terminal=succeeded。这是固定入口的新协议/装配验证，不冒充 12 失败的真实远端观测；12 失败由以上 real owner fixture 验证。若离线 fixture 意外触发远端请求或部署加载错误，停止修装配/测试设计并报出直接证据，不允许联网让测试通过。

### 5.2 执行命令

本 plan 没有代码修改，不运行测试/pyright，也不把计划命令报告成已验证。implementation 在激活 venv 后执行：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_download_failure_diagnostics.py \
  tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py \
  tests/fins/test_f5_result_contract.py tests/fins/test_fins_ingestion_tools.py \
  tests/cli/test_output.py tests/cli/test_fins_commands.py \
  tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py \
  tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_f5_workflow_rebuild.py -q
python -m pyright dayu/ tests/ utils/
```

预期：所有受影响 deterministic 测试通过；外部资源集成 skip 单列，不能当真实下载通过；pyright 无新增/扩散错误，触及文件内已有错误一并修复。先记录 implementation 前 pyright baseline，再记录修改后结果；不能 ignore 或降低类型检查。

单文件覆盖率必须实际报告 >=80%。用同一受影响集合（记为上述完整路径集合）加下面参数执行，不按新增行或排除生产行算覆盖率：

```bash
source .venv/bin/activate
python -m pytest tests/fins tests/cli tests/service -q \
  --cov=dayu.fins.download_contract --cov=dayu.fins.direct_events \
  --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.cn_pipeline \
  --cov=dayu.cli.output --cov-report=term-missing
python -m coverage report --include='dayu/fins/download_contract.py,dayu/fins/direct_events.py,dayu/fins/ingestion_runtime.py,dayu/fins/pipelines/cn_pipeline.py,dayu/cli/output.py' --fail-under=80
```

coverage report 的 fail-under 检查总数，因此必须另逐文件核对五个文件都 >=80，不能以总数代替。必要 coverage 扩大只为满足项目既有要求；不据此修未授权业务。真实外部集成缺资源、既有未覆盖路径或基线测试失败需单列给总控；不伪造 pass，不随手增加 unrelated 修复。

## 6. 旧运行证据的可恢复性：引用已完成核查

原 plan 已核验的原运行记录如下，本次 fix 沿用其证据，不重复访问调用方文件或执行仓储 query：

- stdout SHA256：`a9c8a3cc2babdd8c93313345e55f1638c27fea15b6b56c5d7f8d37b1ebd07f3a`；stderr 0 字节。
- download JSON SHA256：`788aa73c8c2de0039ae262c39f7737eb8ec277009572911a6fb2d85e4f1b1612`。
- terminal-check JSON SHA256：`6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7`。
- download 记录的 argv 为固定 CLI，base=`/Users/leo/workspace/portfolio-manager-v2/workspace`，ticker=0700、start/end 为目标窗口；started_at=`2026-10-10T08:26:26.843202+08:00`，completed_at=`2026-10-10T10:10:23.126594+08:00`，记录 exit_code=0。这里只核验记录，不冒充对旧进程的重新观察。
- stdout 的 8 条 `download.file_failed`、终态计数 53=34+11+8、前 10 个公开文档全为 skip，均与问题同源。总控随后已完成 owner-read 核查，现直接引用已归档证据，不再写“尚未独立核验”。

总控现有证据：`docs/gateflow/download-failure-diagnostics-old-evidence-20261010.json`，本次只读实测 SHA256=`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`。按总控已授权并完成的公共仓储核查：scope 为 existing published source metadata via Dayu repository only，create_directories=false，8 项 published_meta 均 missing，source_count=45，canonical_metadata_sha256=`d2010a1e5d30be536dd4f24b1cc53490ddeec68a875ad2e03d611e712b502b50`；record_sha256=`6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7` 关联既有 terminal-check。此证据不含新网络观测、discovery、download 或 recovery；本次 fix 只验证该归档文件及 hash，不冒充重新生产核查。

公共 reader 的常规 publication guard 可能获取/释放 `.dayu` 治理锁（`_fs_source_document_core.py:622` → `_fs_storage_infra.py:1813` → runtime FileLock）；create_directories=false 不等于绝对零治理写入。该锁不修改来源内容，本次已授权核查与保留 45 来源的结论沿用总控裁决，不再请求同一核查授权、不绕锁、不修改仓储，也不安排 implementation 重复查询。

逐项现阶段可恢复情况（下列日期、表单、期间、具体安全原因全部未知；相同不代表它们确实缺席，只代表当前证据未包含）：

| document_id | 旧 stdout 可恢复 | 来源日期 / form / report_date / coverage / reason | published meta 独立核查 |
| --- | --- | --- | --- |
| fil_cn_76fad62cd9ba3141f4cab67e8e2a0c220a93a27d | 身份、PDF file_failed 阶段 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_04fb4018812cf15ca633495dbd9fcac3cb033378 | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_307f1a281919204de1d3c3cb5f95322463819734 | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_2a0ebbf2c2935ee14a39fec8744d626853a68424 | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_d56f9cdc70daa5174522111629889cc74795448b | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_535e021474217e2750d6063d7046a72ead52f7b5 | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_a44583fc024459f5a22ee4eed537dea35e8882ac | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |
| fil_cn_4043a094cd9d2292c378e6b6c8f1856868291372 | 同上 | 未知，既有证据不可恢复 | 总控 owner-read 已完成：missing |

后续 evidence assessment / closeout 直接引用以上归档文件、hash 与逐 ID 结论，不重复 query 或重新等待授权：

1. 8 项身份与 PDF file_failed 阶段可恢复；原原因、URL、日期、form、report_date 与 coverage 不能由现有证据恢复，均明确未知。current published_meta missing 只代表核查时当前状态，不证明原失败时历史 snapshot，也不证明实际失败原因。
2. source_count=45 及 metadata digest 是总控 owner-read 的证据身份；不得推成 45 个全新下载或新业务覆盖结论。本轮保留全部 45 来源，不修复写入、不新增下载。
3. 不从相邻候选、document_id/hash、目录、历史临时日志或调用方其它包补造元数据，不增历史诊断仓储。实现验证使用 isolated fixture，与生产核查分开。
4. 需要新观测时报告拟观测的候选、输入窗口、是否 discovery/下载、网络与仓储影响及与旧证据的区别，等待巡检线另确认。禁止在本计划预先安排新远端观测或原命令重跑。实际下载 defect 若显现，单独报直接原因及最小修法，先裁决范围。

原证据内容缺失是明确的历史恢复限制，不是允许猜原因的 blocking question，也不是增加历史仓储的依据。

## 7. 固定 CLI 实际加载与部署可用性

原 plan 的直接核验及两路 review 的装配证据沿用：`.venv/bin/dayu-cli` shebang 是本仓库 `.venv/bin/python3.11`，entrypoint 是 `dayu.cli.__main__:exit_module`；venv Python=3.11.15。实际 site-packages 的 `dayu_agent-0.1.4.dist-info/direct_url.json` 是 editable=true、URL 指向本仓库；editable finder 映射 dayu 到 `/Users/leo/workspace/dayu-agent-r/dayu`。原 plan 从 `/private/tmp` 用该 venv Python `-B` import 时，cli.main 和 download_contract.__file__ 仍指向本仓库。本次 fix 未重新执行装配或 CLI smoke；版本号 0.1.4 不能单独证明修复是否加载，代码仍是固定旧 HEAD。

implementation / closeout 的验证必须留下命令、真实外层退出码、stdout/stderr、HEAD、关键模块路径和文件 digest；不用 `python -m dayu.cli` 或仓库 cwd 的隐式导入替代固定 binary 的检查：

```bash
git rev-parse HEAD
git status --short
cat /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli
cat /Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages/dayu_agent-0.1.4.dist-info/direct_url.json
shasum -a 256 dayu/fins/download_contract.py dayu/fins/direct_events.py \
  dayu/fins/ingestion_runtime.py dayu/fins/pipelines/cn_pipeline.py dayu/cli/output.py
source .venv/bin/activate
python -m pytest tests/cli/test_fins_commands.py -k fixed_cli_download_diagnostics_on_empty_rebuild -q
```

再在仓库外空 cwd（tool 的 workdir 参数，不设置 PYTHONPATH）执行固定 venv Python `-B -c`：import cli.main、cli.output、fins.direct_events、fins.download_contract，输出 sys.executable / sys.version / 各 __file__ / SHA256；检查新 property 与诊断方法存在，不能只看 dist.version。对应真实固定 CLI fixture 必须已通过上一节 subprocess 验证。若路径指向别的安装、editable 指向别的工作树、方法缺席或 binary 无法启动，停止交付“已可用”，由总控处理实际部署阻断；不能临时 PYTHONPATH、wrapper、修改生产工作区或声称重新安装已经做过。

当前 editable 装配意味着源码修复并经这些验证后无需额外部署拷贝/安装；本 Agent 不安装、发布或合并。根 README 只写此能力的用户操作，不把 commit 当作安装版本。最终应给出：固定入口实测加载的 HEAD/路径及诊断能力状态、调用方如何捕获标准流、旧 8 项限制、需要巡检线裁决的继续动作。不能把“源码改完”单独当入口可用。

允许说明但禁止自行执行的后续捕获方式：在巡检线批准的新运行范围内，把固定 CLI 的 stdout 和 stderr 分别保存到全新唯一文件（shell noclobber 或 runner 的 create-exclusive capture），从两通道读取完整诊断行。保留 raw 文件和 exit_code；partial_failure 不能按 0 误判全成功。`--log-file` 可另加来捕获 operator 日志，但不是完整失败诊断的必要参数。此计划不提供一个可被误执行的原整批下载命令。

## 8. Goal alignment、文档与最小性

| 已确认成功信号 | 设计 / 验证对应 |
| --- | --- |
| 后 10 项失败与 >10 失败完整可取得 | S1 完整 typed direct result + 默认 CLI failed_documents；测试 1/5/7。 |
| CN/HK 真实安全原因与来源身份、日期/覆盖同源；未知明确 | CN/HK strict adapter、shared row projection、完整诊断 null；测试 2/3。SEC 只验证完整性、身份及既有安全投影不变，不承诺其 upstream 原因保真。 |
| 不给有界 LLM 摘要无界结果 | `download` property 有界、wait 只调用既有 JSON；测试 6。 |
| 成功/跳过/失败可核验，取消不造事实 | count owner 不变，human terminal_disposition，whole failure 与文档失败分离；测试 1/3/4。 |
| 原 8 项恢复性、保留 45 份、无未授权重跑 | 第 6 节引用总控已完成 owner-read JSON/hash 和逐项 missing/未知；不重复 query 或重问授权；isolated fixtures 不触达生产。 |
| 固定入口实际可用、必要操作与剩余问题 | 第 7 节源码外 import/hash + 实际 binary isolated subprocess；不冒充真实下载。 |
| 受影响测试、pyright 与职责内文档 | 第 5 节命令、coverage 单文件核对、下表。 |
| 后续 draft PR/review/final closeout | 仅由总控按既有 gates 推进；本计划给 completion report，未自行进入后续 gate。 |

文档职责判定（沿用原 plan 已读各 README 开头约束的决定；本次 fix 仅改开发 artifacts，不触发 README 修改）：

- 根 README：更新。用户输出多一条完整诊断、两通道捕获方法、0 与 partial_failure 的区别、默认临时日志不用于历史恢复，属于下载/排障用户手册。不能写内部字段迁移或 gate。
- `dayu/fins/README.md`：更新。说明完整 operation-local/direct result 与 bounded LLM/public projection 的稳定接口、原因 owner 与取消快照边界；不写安装命令、测试清单或 work unit 流水账。
- `tests/README.md`：更新。记录新增 contract / runtime / CLI isolated 验证、超 10 失败、bounded wait、固定 binary smoke 的运行方式与证据限制。
- `dayu/README.md`：已检查，不更新。本次保持 UI→Service→Fins direct 装配与 Host/Engine/runtime 边界；变化是 Fins 内部具体投影协议，按总览约束交给 Fins README。
- Host/Engine/Config/Service README：无对应代码变更或边界变化，不触发；不机械同步。

这是一个必要的端到端行为修复，新增 API 只让现有完整 typed result 可用，只有一个 slice、五个生产文件，没有强制持久化、job、配置、下载重试或来源算法扩展。constructor 一次迁移是保证唯一真源所必需，既有消费者的 bounded `download` property 有有效投影语义，不是兼容 re-export/wrapper。所有新规则都映射已确认信号或必要 contract/cancel 正确性，没有 future slice 或 goal drift。

## 9. 风险分类、未覆盖项与停止条件

| 风险 / 未覆盖项 | Gateflow 分类 | Owner / destination 与理由 |
| --- | --- | --- |
| CN/HK adapter 丢真实原因、后 10 / >10 失败不可取得 | fixed in current slice（计划处理，尚未实现） | S1；此次已证实产品缺陷。 |
| SEC 既有原因说明泛化及 upstream 原始异常安全治理 | assigned to later work unit | Dayu 维护侧；后续 SEC 原因 owner work unit 需另定范围，不自行建 issue、不透传 raw exception；本次通用接口只保留既有 typed 安全投影。 |
| full/bounded 不一致、取消丢前缀、LLM 膨胀 | fixed in current slice（计划防回归，尚未验证） | S1 owner/property 与测试；不是新增独立架构目标。 |
| 旧 8 项原原因 / URL / 日期 / form / coverage 不可由现有证据恢复 | requiring explicit user decision（如需新观测） | 巡检线已授权如实未知，现有 evidence assessment 直接引用总控完成的 owner-read；不等待新确认、不以未知阻塞接口。未来新观测另确认范围。 |
| 公共 reader 的 publication 治理锁与当前 metadata 的历史证明边界 | fixed in current slice（本次 plan fix 已更新证据说明，非生产修复） | 总控现有 JSON/hash 已引用：8 missing、45 来源；常规锁不修改来源，当前查询不证明历史原因；本轮不重复 query 或改 storage。 |
| 实际失败原因、来源业务影响、覆盖判断 | assigned to later work unit | 调用方巡检线；当前未证实，不含于 S1。实际 Dayu 下载 defect 需先重做范围裁决。 |
| 未捕获终态、进程崩溃/SIGKILL/提前关闭导致历史不可追回 | requiring new issue or explicit user decision | 如将来要求 durable 历史诊断，由用户/总控另定 work unit；当前只承诺合法被消费 RESULT，已由目标允许最小接口。 |
| 无界失败数组使 operator 输出长度随失败数增长 | fixed in current slice（正确输出行为，非消除增长） | 单次已有 typed rows 无二次真源；逐项安全上限和转义，tests >10；极端规模性能未单独压力测试，不增加流式/分页框架。 |
| 完整 typed result 在 observation 内保存到既有生命周期结束 | fixed in current slice（正确性与生命周期回归，非新增管理框架） | 复用原 immutable tuple、既有 observation abandon/取消路径；不把它序列化给 LLM。极端规模内存压力属于前项未覆盖。 |
| 极端结果规模性能、完整 repr 可能扩大日志 | assigned to later work unit | Dayu 维护侧；真实扩展压力出现时另定性能 work unit。当前 S1 验证 LLM/durable 不含完整数组，不增加分页/日志框架，无单独规模压测。 |
| 固定 binary 部署漂移 / 真实网络生产验证 | requiring explicit user decision | 总控处理路径/权限阻断；生产观测需巡检线范围确认。现有 editable 直接证据仅保证当前指向，并非修复已加载。 |
| merge、approve、ready、reviewer、外部 comment | requiring explicit user decision | 用户；draft PR 已授权由后续总控执行，不推导其它授权。 |

没有 later approved slice、没有 existing issue，不能用这两个分类隐藏未完成工作。除明确标注本次文档修订的证据说明外，此表的 fixed 表示 S1 计划处理，完成报告必须替换为实证状态；未通过检查、未经 review 裁决不能写生产缺陷“已修复”。

阻塞停止：输入 branch/HEAD/未知 dirty ownership 不符、必要文件不可读、新 owner 不清、CN/HK strict workflow 合同实际不能满足且必须扩大来源执行修复、真实下载故障要扩范围/新观察才能决定策略、指定之外生产文件必须修改、测试/type 失败需未授权业务改动。记录具体缺项与证据给总控。本次接口设计无阻塞开放问题；原 plan 收尾 ownership blocked 已由总控核清并解除，交接内 state 等文件更新不构成新 blocker。历史未知、SEC 后续原因治理、没有生产新观测均为已分类限制，不猜原因、不借此扩范围。

## 10. 完成报告格式与本轮状态

后续 implementation 报告至少包含：

1. Work unit / slice / branch / 实际 HEAD / changed files / artifact path，明确做了什么。
2. owner contract、错误和取消行为、完整失败数与 bounded omission 的对齐证据；不得把退出 0 写成全部成功。
3. 原始测试/pyright/coverage 命令、真实外层退出码、结果和 skip/未覆盖项；逐文件覆盖率、基线错误及修复证据。
4. 引用第 6 节总控现有 JSON/hash：旧 8 项逐 ID 可恢复身份 / 当前 published_meta missing / 不可恢复字段，保留 45 来源；不重复生产查询，不把本轮未重新 query 写成总控尚未核查。
5. fixed CLI shebang、源码外 import 路径/hash、editable metadata、实际 binary fixture 外层结果、新诊断协议可用性；无需安装的理由或实际阻断。
6. README 更新与职责判定、残余风险分类/owner/destination、accepted finding 修复状态或待总控裁决状态。
7. 后续需要巡检线确认的具体观测范围（若有），不自行运行；交总控下一 gate，不自行声明整个 work unit 或 draft PR 已完成。

原 plan 生成时的代码 owner、原证据和 CLI 装配证据继续沿用；其 postflight ownership blocked 已由总控核清，不再保留为未解决项。本次完成 P1—P4 的计划修订及 plan-fix artifact，只读复核冻结身份、关键代码和现有 old-evidence JSON/hash；没有实现、生产 query、新观测/下载、测试或 pyright 执行，没有 commit/push/PR，未改 goal/state/adjudication/reviews。Completion status：plan fix 修订完成，P1—P4 文档修复证据待总控双路 re-review 验证；没有已知 blocking open question，不声明任何 gate 已 pass。下一未完成 gate / 交接入口：re-review。本 Agent 到此停止。
