# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Fins Financial / Read Contracts Plan

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Work-unit type: production semantic ownership / public tool-result contract fix
- Gate: `plan fix`
- Risk profile: `production-high`
- Status: `ready-for-plan-rereview`
- Plan owner: `AgentCodex`
- Expected artifact: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Implementation authorization: none；本 artifact 只定义 code-generation-ready plan，不实施、不 review、不 commit、不 push、不进入下一 gate。
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control truth:
  - `docs/host/issues-implementation-control.md`
  - `docs/phaseflow-umbrella-optimization-control.md`
- Source finding truth: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` 的 R3-D section
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-goal-confirmation.md`

## Preflight And Gate Position

- 当前分支：`phaseflow/host-issues-control`。
- plan-fix preflight 时 `git status --short` 只包含当前 plan 与三份 plan-review 输入 artifact；均属于本 gate 已声明 scope，无未知 ownership 冲突。
- 当前分支不是 `main` / `master` / `develop` / `release/*` 等受保护主干。
- `docs/host/issues-implementation-control.md` 当前状态明确：R3-C 已 local final-closeout-pass；R3-D goal confirmation 已接受；next gate 是 R3-D plan via AgentCodex；blocking open questions 为 0。
- Gateflow 固定顺序中的当前 gate 是 plan review 后的 `fix`；本 artifact 结束后只能交给 controller 进入 parallel plan re-review，不得自行进入 implementation。

## Goal / Motivation / Success Signal

### Goal

在 Fins owner boundary 内一次定义并保真传播财务报表、XBRL facts、文档读取与 source freshness 语义：

1. processor 产生 `periods`、`scale`、`data_quality`、`reason`；read runtime 只校验和投影，不重算、不补默认值、不丢字段；LLM-facing tool result 与 tool description 对这些字段自解释。
2. XBRL concept 查询区分合法空集、部分 concept 失败、全部 concept 失败和 XBRL 不可用；异常不再成为成功空集。
3. scale / fiscal-year / fiscal-period 无法从直接证据产生时，由 processor/domain owner 明确表达缺失或 degradation，不从日期、units、raw string 或下游 fallback 猜测。
4. 财期排序、财期解析、processor dataframe 可选字符串、SEC download version 和 upload ticker alias 各只有一个 owner helper。
5. 10-Q 正文扩展后，虚拟章节索引和 table assignment 与最终 section boundary 同源。
6. read runtime 只复用与当前 storage-owned source revision 一致的 processor/meta cache；source 变化期间不能返回旧 processor。
7. 非 UTF-8 source、section/index 构建和 search enrichment 异常成为 typed read failure，不被空文本、空索引或低质量成功结果掩盖。

### First-Principles Motivation Judgment

动机成立，严重性评估为 `production-high`，不是 style cleanup。

- 财务数值如果有 rows 却没有 scale，LLM 可能把 millions 当 units；这是数量级错误，不是展示瑕疵。
- XBRL dependency/query 异常与“公司确实没有该 fact”是两个不同事实；把前者返回为 `facts=[]` 会制造错误的成功事实。
- processor 已拥有 period/quality/reason，而 read runtime 删除这些字段，违反 producer/consumer 单一真源；下游无法可靠恢复。
- source mutation 后复用旧 processor，会让同一 document identity 同时对应新 storage state 和旧 read state。
- 10-Q section boundary 修改后仍使用旧 table mapping，会让 citation/section/table 三个面向 LLM 的事实不一致。
- decode/index/search 错误被吞后继续成功，会把“读取能力失败”伪装成“文档没有内容/没有命中”。

### Success Signals

- `get_financial_statement` 的 public result 对 `periods/scale/data_quality/reason` 逐字段 round-trip；`units` 不再承载 scale。
- `query_xbrl_facts` 的 valid empty、partial failure、all failure、XBRL unavailable 四类结果可由类型和字段唯一分辨。
- processor raw contract 缺少必填 financial/XBRL 字段或违反 quality/reason invariant 时 fail closed；read runtime 不生成 statement locator、period、scale、quality 或 reason fallback。
- BS 10-K/10-Q/20-F/6-K XBRL 路径调用同一 scale owner；scale/period semantics 缺失时返回 `partial` 和稳定 reason，不返回伪完整 `xbrl`。
- read runtime 不再把 ISO date 年份直接声明为 issuer fiscal year；缺失值保持显式 `None`，非法持久化值 fail closed。
- 两条 10-Q processor 路径在 expansion 后复用同一 reindex/reassign owner；`read_section.tables` 与 `list_tables.section_ref` 同源。
- cache hit 前比较 storage-owned source revision；revision 变化会原子 evict/rebuild，build 期间 revision 变化会 typed fail closed。
- `rg -n 'errors="ignore"' dayu/fins` 无匹配；search/index failure 产生 typed failed tool outcome。
- SEC legacy `download_version` 在 all-files-not-modified 路径不得 skip；upload ticker alias 使用 `try_normalize_ticker` canonical 值。
- 所有 focused tests、完整 `tests/fins`、pyright、coverage target、propagation scans 和 `git diff --check` 通过。

## Design And Control Alignment

- `docs/engine/design.md:3-26` 明确 Engine 不理解财报、ticker、XBRL 或 storage；本计划不在 Engine 增加 Fins 分支。Engine 继续只接受中性 tool outcome。
- `docs/engine/design.md:340-356` 固定 completed/failed tool outcome 与 LLM-facing tool message 边界；Fins owner 必须选择正确的 `ToolResultSuccess` 或 `ToolResultFailure`，不得把 failure 塞入 successful empty value 或 `meta`。
- `docs/host/design.md:3141-3145` 要求 LLM-facing evidence self-explaining；因此 financial result 字段和 tool description 必须说明业务含义，不能只暴露内部 type/schema 名。
- `docs/host/design.md:3481-3488` 把 source metadata 和财报业务事实交给业务工具/财报仓储，并要求 retrieval failure、evidence insufficient 与 stale 可解释；本计划把 semantics/freshness 修在 Fins，不让 Host 反推。
- `docs/host/design.md:3642-3652` 把业务层财报抽取列为 Host non-goal；本计划不修改 Host design/state machine。
- `docs/host/issues-implementation-control.md:127-151` 要求按语义闭环、依赖、失败/回滚风险与验证矩阵切 slice，而不是按文件/finding；本计划采用 3 个 owner-based slices。
- `docs/phaseflow-umbrella-optimization-control.md:42-60` 把生产行为、public contract 和 LLM-facing 变化归为 High Risk，要求 full gate 和 per-slice code review；本计划不采用 low-risk 合并 review。
- `docs/phaseflow-umbrella-optimization-control.md:95-120` 禁止 one-finding-per-slice，超过 3 slices 必须解释；本计划正好 3 slices，无需额外 gate 成本。

## Scope Adjudication And Owner Analysis

### Accepted Findings

| ID | Current direct evidence | First-principles owner | Plan decision |
| --- | --- | --- | --- |
| R3-D-F01 financial projection loss | `dayu/fins/processors/financial_base.py:17-38` 声明 producer 字段；`dayu/fins/tools/read_runtime.py:236-249` 建 shadow payload；`:1639-1675` 只投影 rows/currency/units/locator；`dayu/fins/tools/result_types.py:246-316` public result 不含 periods/scale/quality/reason | Fins domain financial result contract 产生/校验；read runtime 只附加 ticker/document/citation；Fins tool description 自解释 | S1 删除 shadow contract 与 locator fallback，使用 validated domain contract并逐字段投影；public result 必填 owner fields |
| R3-D-F02 XBRL exception becomes empty success | `dayu/fins/processors/sec_xbrl_query.py:434-486` 对每个 `query_obj.execute()` 的任意异常 `continue`；`sec_processor.py:712-727` 和 `bs_report_form_common.py:317-332` 返回 `facts=[]/total=0` | `_query_facts_rows` 是 concept execution owner；processor result contract owns degradation；read runtime maps typed all-failure to tool failure | S1 用 typed execution summary/exception 区分 valid-empty、partial、all-failed；禁止 catch-and-continue without accounting |
| R3-D-F03 BS scale absent | `bs_report_form_common.py:376-387`、`bs_six_k_processor.py:922-940` 对有 rows 的 XBRL result 硬编码 `scale=None`；`sec_processor.py:634-646` 已调用 `_infer_scale_from_xbrl_query` | shared financial scale type/inference in domain/processor helper | S1 所有 BS/Sec XBRL statement producer消费同一 scale inference outcome；未知必须 partial+reason |
| R3-D-F04 period/year semantics inferred falsely or not at all | `sec_xbrl_query.py:204-222` 仅凭 `period_end[:4]` 声明 fiscal year，且只要日期合法就写 `FY`；`read_runtime_helpers.py:1017-1036` `_infer_fiscal_year` 丢弃参数后恒定返回 `None`；`read_runtime.py:2117-2127` 仍调用它 | processor owns statement periods；ingestion/domain owns filing fiscal fields；read runtime consumes validated storage values | S1 修 statement period type和quality；S3 删除 read-side fiscal inference，domain helper严格解析/排序，不从 report date猜 issuer fiscal year |
| R3-D-F05 fiscal-period sort drift | `read_runtime.py:160-168,432-463` 与 `read_runtime_helpers.py:142-149,372-411` 有不同 rank；后者无生产 caller | `dayu.fins.domain.filing_semantics` owns FiscalPeriod + recency rank | S3 增加 immutable rank helper，read runtime消费；删除两份 mutable map和dead recency/recommendation helpers |
| R3-D-F06 10-Q stale section/table indexes | `ten_q_processor.py:76-92`、`bs_ten_q_processor.py:87-103` expansion 后不 rebuild；10-K 路径 `ten_k_processor.py:70-90`、`bs_ten_k_processor.py:86-106` 手工 rebuild；base `sec_form_section_common.py:388-411` 已显示 index+assignment 必须同序 | `_VirtualSectionProcessorMixin` owns virtual section index/table maps | S2 在 mixin 提供唯一 refresh helper；base/10-K/10-Q 全部复用，10-Q expansion 后调用 |
| R3-D-F07 processor cache stale | `tools/cache.py:37-179` 只有 LRU/evict；`read_runtime.py:2468-2514` hit 后不读 storage；storage source update 在 `_fs_source_document_core.py:803-830` 产生新的 owner meta | storage owns source revision；read runtime owns cache reuse decision | S2 storage 增加 typed revision projection，cache value绑定 revision；hit/build前后校验，revision变化 evict processor+meta |
| R3-D-F08 silent non-UTF-8 loss | `sec_processor.py:845-858`、`sec_report_form_common.py:594-621`、`sec_6k_rules.py:155-182` 使用 `errors="ignore"` 或读失败返回空文本 | Fins source text decoder owns bytes-to-text semantics；read runtime/tool boundary owns failure projection | S2 strict UTF-8 owner helper，decode error带 source-neutral reason；禁止替换字符/ignore伪成功；tool failure code稳定 |
| R3-D-F09 search/index exception swallowed | `read_runtime.py:984-1026` 构建 sections/semantic/BM25F 后 `except Exception: pass`，随后使用空 index继续成功 | `FinsReadRuntime.search_document` owns search readiness；tool error contract owns public failure | S2 cancellation继续透传；其它 index/enrichment exception用 cause转成 `SEARCH_INDEX_FAILED`，不返回 degraded empty success |
| R3-D-F10 SEC not-modified skip ignores version | `sec_download_filing_workflow.py:529-558` 的 all-files-not-modified skip 无 version 条件；`sec_pipeline.py:1369-1425` fast/remote skip 已要求 current version | SEC download state/version helper owns equality | S3 抽取复用 current-version helper；所有 skip路径消费同一 helper；legacy version继续commit current version |
| R3-D-F11 upload ticker aliases bypass owner | `upload_company_meta.py:148-175` 只 `strip().upper()`；`ticker_normalization.py:84-147` 已定义 canonical owner | `try_normalize_ticker` owns alias normalization；upload company meta decides invalid-input policy | S3 每个非空 alias 调 owner；persist canonical，稳定去重；不可识别 alias抛 ValueError，不保留 raw uppercase |
| R3-D-F12 duplicated optional dataframe string normalization | `sec_section_build.py:896-911`、`sec_table_extraction.py:98-113`、`sec_xbrl_query.py:81-96` 三份相同 pandas-missing wrapper | Fins processor dataframe scalar adapter owns NaN/NaT/blank -> None | S3 建一个严格 typed helper并删除三份实现；不使用 `Any/object/getattr` 逃逸 |
| R3-D-F13 broad result/meta signatures on this path | `financial_base.py:14-38` 的 `Any` 深入 periods/rows/query；`result_types.py:246-316` 通过 shadow/cast；`document_models.py:33` 全局 `DocumentMeta=dict[str, Any]` | financial result domain contract + storage revision typed projection；不是每个 downstream consumer | S1 消除 financial/XBRL contract 的 `Any`；S2 为 freshness增加 typed storage revision；不做全仓 DocumentMeta god migration |

### Scope Corrections / Explicitly Not Planned

1. **6-K 双引擎 fallback 不在本 plan。** 来源 review 提到 `SecProcessor.supports()` 对 6-K 返回 false，但当前 `sec_processor.py:269-275` 有明确 BS-only 设计注释，且用户列出的 R3-D accepted correction / success signals 没有要求改变 6-K routing。R3-D 仍覆盖 `BsSixKFormProcessor` 的 financial scale/period/result correctness；不新增 SixK edgartools fallback，不改 registry priority。若 controller 要改变 6-K routing，必须作为独立 goal/design decision，而不能夹带在 financial contract fix 中。
2. **不做全量 `DocumentMeta` migration。** `document_models.py:33` 的 broad durable type 是真实技术债，但迁移所有 storage/pipeline consumers 是 broad god-file/schema cleanup，超出当前 accepted correction。S2 只增加 freshness 所需的 storage-owned typed revision；S1 关闭 LLM/durable boundary 上与 financial result 直接相关的 weak type。残余由 umbrella controller 决定后续 owner。
3. **不处理 creation-lock lifetime。** review 中 `_creation_locks` 单调增长未进入用户列出的 R3-D accepted scope；不得用 cache freshness slice顺带扩张。
4. **不改变 XBRL provider/API 的 query feature set。** 不新增 taxonomy service、remote lookup 或 cross-filing aggregation。

## Hard Non-Goals

- 不实现 R3-E Web/Documents egress、resource cap、diagnostic、oracle 或 smoke-oracle 修复。
- **tool-security 明确 out of scope，且本计划完全不安排：**
  - upload allowlist / user-file authority / symlink authority；
  - URL/TLS/redirect/SSRF/egress provenance；
  - remote wire/decoded byte budget；
  - LLM-facing upload/download security schema、description 或 prompt；
  - security capability token、sandbox、network policy。
- 不修改 Host/Engine tool state machine、accept barrier、memory、EventLog、wait、cancel、resume 或 durable schema。
- 不新增 compatibility re-export/wrapper/facade、old-field alias、loose parsing、default reason、successful-empty compatibility branch。
- 不做 broad processor god-file split、style/docstring sweep、全仓 `Any` cleanup、6-K registry redesign。
- 不从 logs、mtime、path string、偶然顺序或 processed output反推 source freshness。

## Contract And Implementation Decisions

所有后续实现必须遵守：新增/修改函数有完整中文 docstring（参数、返回、异常）；新/改 public/internal owner contract 不使用 `Any`、`object`、裸容器签名或 `hasattr/getattr`；不把显式 fields 放进 extra payload；复杂 quality/freshness/error ordering 用中文行内注释说明意图。

### 1. Financial Statement Domain Contract

新增 `dayu/fins/domain/financial_result_contract.py`，由它独占下列业务类型和 validator；`processors/financial_base.py` 只保留 processor protocol并直接 import这些类型，不 re-export旧路径。

```text
FinancialScale = Literal["units", "thousands", "millions", "billions"]
FinancialStatementReason = Literal[
  "unsupported_statement_type",
  "xbrl_not_available",
  "statement_method_missing",
  "statement_not_found",
  "statement_empty",
  "low_confidence_extraction",
  "scale_unavailable",
  "period_semantics_unavailable",
  "scale_and_period_semantics_unavailable",
]
FinancialPeriod = {
  period_end: str,
  fiscal_year: int | None,
  fiscal_period: FiscalPeriod | None,
}
FinancialStatementResult = {
  statement_type: str,
  periods: list[FinancialPeriod],
  rows: list[dict[str, JsonValue]],
  currency: str | None,
  units: str | None,
  scale: FinancialScale | None,
  data_quality: FinancialDataQuality,
  reason: FinancialStatementReason | None,
  statement_locator: StatementLocator,
}
```

Invariants:

- 上述字段全部 required；“没有 reason”用显式 `None`，不用字段缺失。
- `data_quality="partial"` 必须有非空 reason；`xbrl/extracted` 必须 `reason=None`。
- 对 `FinancialStatementResult`，`rows=[]` 不可声明完整 `xbrl/extracted`；该规则不外推为 XBRL concept query 的“零命中即失败”。后者由 `XbrlFactsResult.total` 与下文独立矩阵表达。
- `units` 只表达计量/货币单位，例如 `USD`、`shares`；scale 只表达倍率。不得再用 `units="millions"` 或 `USD in millions` 让同一事实出现两个 owner。
- 每个 period 必须有可校验 ISO `period_end`；fiscal year/period 只有直接 XBRL/表头证据时填写。不能用 `period_end[:4]` 或月份推断 issuer fiscal year/quarter。
- XBRL/HTML/OCR producer 无法得到 scale 或 fiscal semantics 时，保留 rows/period_end，但降级为 `partial`：只缺 scale -> `scale_unavailable`；只缺 period semantics -> `period_semantics_unavailable`；两者都缺 -> `scale_and_period_semantics_unavailable`。
- validator 必须校验 rows 与 periods 的 JSON shape、scale enum、quality/reason matrix和 locator；read runtime不得重建缺失 locator。

Scale truth:

- 同一 domain module提供 `infer_financial_scale_from_decimals(decimals)`，`sec_xbrl_query` 与 read fact normalization共用；删除 processor/read 各自的 `_DECIMALS_SCALE_MAP`。
- statement-level XBRL scale inference返回 typed outcome，至少包含 `scale` 与是否遇到 query/inference failure；辅助 scale probe failure不吞掉已有 statement rows，而是触发上述 partial reason。
- `bs_report_form_common`、`bs_six_k_processor`、`sec_processor` 全部消费同一 scale outcome。

HTML / OCR scale truth:

- HTML table 路径由 `html_financial_statement_common._infer_scale_from_caption()` 独占 caption/header 的 scale 提取；OCR 路径由 `six_k_form_common._extract_ocr_currency_and_scale()` 独占 OCR heading 的 scale 提取。两者只消费直接文本证据，不借 currency/units、金额绝对值或下游日期猜 scale。
- `_build_shared_statement_result_from_tables()`、`extract_statement_result_from_ocr_pages()` 与 OCR income-summary fallback 必须把上述 helper 的 `scale` 和 producer 已解析的 fiscal-period evidence 一并交给同一 financial quality/reason owner。存在 rows 但无直接 scale 证据时不得声明完整 `extracted`，而是 `data_quality=partial` + `scale_unavailable`；若 fiscal semantics 也缺失则使用 `scale_and_period_semantics_unavailable`。
- HTML/OCR `units` 只保留 currency/measurement unit；删除 `_build_units_label` / `_build_ocr_units_label` 把 `in millions` 等 scale 拼入 units 的行为。scale helper 未命中时保持 `scale=None`，不从旧 units 文本反解析。

### 2. XBRL Query Contract And Error State

扩展 `dayu/fins/domain/xbrl_result_contract.py`：

```text
XbrlQueryReason = Literal["xbrl_not_available", "query_partially_failed"]
XbrlFactsResult = {
  query_params: dict[str, JsonValue],
  facts: list[dict[str, JsonValue]],
  total: int,
  data_quality: FinancialDataQuality,
  reason: XbrlQueryReason | None,
}
```

`deduped_fact_count` **不属于**上述 producer/domain contract。`XbrlFactsResult.total` 是 producer 对 raw normalized facts 的 required count，必须始终等于 producer `facts` 长度；domain validator 遇到 raw payload 中的 `deduped_fact_count` 必须拒绝，且自身不得生成或覆盖 read-side dedup count。`deduped_fact_count: int` 由 read normalizer 在去重后产生，属于 `XbrlQueryResult` public read projection 的 required 字段，即使未删除任何 row 也必须显式等于 `len(public facts)`，不得放入 extra payload、不得设为 `NotRequired`，且必须满足 `0 <= deduped_fact_count <= total`。

`_query_facts_rows` 不再只返回 list，而返回 frozen typed execution summary：

```text
XbrlConceptQuerySummary(
  rows,
  attempted_concepts,
  successful_concepts,
  failed_concepts,
)
```

Edgartools API pre-check 与 bounded adapter contract：

1. 当前环境 edgartools `5.30.0` 的 `edgar.xbrl.facts.FactQuery.execute()` 直接调用 `_facts_view.get_facts()`、逐项执行 filters/transforms，最终返回 `list[dict]`；该方法没有 catch `get_facts`/filter/transform exception，且正常零命中返回空 list。这是本 plan 区分 exception 与 successful zero rows 的直接依赖证据。
2. S1 实现第一步先用 characterization tests 锁定当前 adapter 边界：query `execute()` 返回 `[]` 记为该 concept 成功；抛 sentinel exception 记为该 concept 失败；返回非 list 或 list 中存在非 mapping row 视为 edgartools contract violation，整项 concept 记失败并构造 typed adapter cause，不把 malformed rows 静默过滤成空成功。
3. `_query_facts_rows` 先规范 concepts；每个具有非空 local name、实际开始构造/执行 query 的 concept 进入 `attempted_concepts`。query chain 构造、filter 应用或 `execute()` 抛异常均进入 `failed_concepts`；`execute()` 返回合法 list（包括 `[]`），即进入 `successful_concepts`。本地 period/value/text/numeric 过滤把合法返回过滤到零 rows，仍属于 successful zero rows。
4. 每个 concept 只执行一次，不重试；failed identity 使用 bounded concept local name，summary不保存异常对象或raw message。helper只在all-failed抛错时以最后一个typed/caught exception作为`__cause__`，供日志和测试。若未来 edgartools 改为无法从 observable return/exception 区分内部失败与空 list，characterization test 必须在任何 producer 改动前失败并触发 S1 stop，不允许引入探测性重复 query、远程 taxonomy fallback 或 empty-success 兼容分支。

State matrix:

| Condition | Processor result / exception | Tool-visible result |
| --- | --- | --- |
| XBRL unavailable | `facts=[]`, `total=0`, `data_quality=partial`, `reason=xbrl_not_available` | successful degraded value，字段完整 |
| >=1 concept execute success, 0 rows, 0 failures | `facts=[]`, `total=0`, `data_quality=xbrl`, `reason=None` | legitimate empty success；`xbrl` 表示查询通过 XBRL 正常执行，不表示存在匹配 fact |
| >=1 success and >=1 execute failure | successful rows/empty, `data_quality=partial`, `reason=query_partially_failed` | successful degraded value，不隐藏 failure |
| all attempted executable concepts fail | raise `XbrlQueryExecutionError` with bounded failed concept identities and chained cause | read runtime maps to `ToolResultFailure(error="xbrl_query_failed")` |
| concepts normalize to empty | fail input contract (`ValueError` internally / public invalid_argument before processor) | failed，不是 empty success |

- 单个异常不把 raw exception message放进 LLM result；typed error保留 `__cause__` 供日志/test，public message只说明查询执行失败和可重试动作。
- `sec_processor.py` 与 `bs_report_form_common.py` 的 caller 必须按同一映射消费 summary：`facts = normalize(summary.rows)`，`total = len(facts)`；`summary.failed_concepts` 非空且仍有 successful concept时使用 `partial/query_partially_failed`；failed 数为零时使用 `xbrl/None`，即使 `total=0`；all attempted failed由 `_query_facts_rows` 直接抛 `XbrlQueryExecutionError`，caller不得构造 result；XBRL unavailable在调用 helper 前保持 `partial/xbrl_not_available`。
- `validate_xbrl_facts_result_payload()` 要求 `data_quality/reason` required并校验 matrix；`total` 继续严格等于 raw facts count。
- `_normalize_xbrl_query_payload()` 只能规范 facts/去重；必须从 validated result复制 quality/reason，不从 facts count重算，并始终写 required `deduped_fact_count=len(deduped public facts)`。
- `XbrlQueryResult` public type required quality/reason/deduped_fact_count；raw `total` 原样复制 producer count，dedup count不能覆盖它。

### 3. Read Projection And LLM-Facing Contract

- 删除 `read_runtime.py` 的 `_ProcessorFinancialStatementPayload` shadow TypedDict；`_FinancialStatementReadProcessor` 直接返回 domain `FinancialStatementResult`。
- `get_financial_statement()` 先调用 domain validator，再只添加 `ticker/document_id/citation`；periods/rows/currency/units/scale/quality/reason/locator 原样复制。
- 删除 `statement_locator` missing fallback；processor contract非法即 `ValueError` fail closed。
- `query_xbrl_facts()` 捕获 `XbrlQueryExecutionError` 并映射为 typed `FinsReadBusinessError(ErrorCode.XBRL_QUERY_FAILED)`；其它 contract invalidity继续 fail closed，不能转空。
- `result_types.py` 的 financial/XBRL public types不再 total=False/cast bag；核心字段全部 required且复用 domain literal/TypedDict component。
- `fins_tools.py` 两个 tool description 必须在当前 schema文字内自足说明：
  - `periods` 是 array，元素含 `period_end:string`、`fiscal_year:int|null`、`fiscal_period:FY|H1|Q1|Q2|Q3|Q4|null`；
  - `scale` 是 `units|thousands|millions|billions|null`，与 `units` 不同；
  - `data_quality` 是 `xbrl|extracted|partial`；`partial` 必须读取 `reason`；
  - XBRL `total` 是 producer raw fact count，required `deduped_fact_count` 是展示去重数；
  - 不暴露 Python type、Host/Engine、event id、digest、cursor或治理术语。
- `get_financial_statement` description 使用以下简洁模板（允许实现时只做不改变语义的措辞润色）：`读取标准财务报表。返回 periods（period_end、fiscal_year、fiscal_period）、rows、currency、units、scale、data_quality 和 reason；scale 取 units/thousands/millions/billions/null，表示数值倍率，units 表示货币或计量单位。data_quality 取 xbrl/extracted/partial；partial 时 reason 说明缺失或降级原因。`
- `query_xbrl_facts` description 使用以下简洁模板（允许实现时只做不改变语义的措辞润色）：`查询结构化 XBRL 数值 facts。返回 query_params、facts、total、deduped_fact_count、data_quality 和 reason；total 是去重前的原始 fact 数，deduped_fact_count 是返回 facts 的去重后数量。data_quality=xbrl 表示 XBRL 查询正常执行，total=0 表示没有匹配 fact；partial 时 reason 说明 XBRL 不可用或部分概念查询失败。`
- 本 slice只改 financial/read tool descriptions；不改 upload/download schema或 security text。

### 4. Source Revision And Cache Freshness

Storage owner新增 frozen `SourceDocumentRevision` 和 `SourceDocumentRepositoryProtocol.get_source_revision(ticker, document_id, source_kind)`：

- revision token由 storage 对会影响 processor选择/内容的 canonical source meta字段计算：`document_version`、`source_fingerprint`、`form_type`、`primary_document`、`ingest_complete`、`is_deleted` 以及按稳定顺序规范化的 `files` identity/content字段（name/uri/etag/last_modified/size/sha256）。
- 使用标准库 canonical JSON + SHA-256；不读取 log、mtime或下游 processed meta；不把 digest投影给 LLM。
- raw meta缺字段/类型非法时 storage method fail closed，不返回默认 revision。

Read cache contract:

```text
CachedProcessor(processor, source_kind, revision)
CachedSourceDocumentMeta(meta, source_kind, revision)
```

- processor/meta cache hit 前均读取当前 storage revision；相等才复用。
- `_get_source_meta_cached_by_kind()` 或实现时固定的等价 owner 必须独立完成 revision comparison，不能假设 `_get_or_create_processor()` 已运行。`list_documents`、document identity/info 和 citation 路径即使完全不构建 processor，也统一经过该 owner。`_get_document_meta_cached()` 必须先 resolve source kind 后委托同一 revision-aware owner；不得保留一条不比较 revision 的 no-kind positive cache 快路。
- mismatch 时在 document creation lock 内 evict processor cache和该 document的 kind/no-kind meta cache，再从 repository重建。meta rebuild 使用 `M1 = current revision -> read/parse meta -> M2 = current revision`；`M1 != M2` 时不缓存、不返回 meta。
- processor build 前读 `R1`，构建后读 `R2`；`R1 != R2` 时不缓存、不返回可能混合状态的 processor。processor race 与 meta race 均**立即**抛 `source_changed_during_read` typed failure，本次 read path 固定为零次自动重试；调用者若需要重试只能发起新的显式 read，不得在 owner 内 loop/backoff。
- pure preprocess 只更新 processed output而不改变 source；`FinsReadRuntime` 类契约 `read_runtime.py:543-550` 明确它实时读取 source、不消费 processed JSON。因此本计划选择“reuse前验证 source freshness”，不把 ingestion callback耦合进 read runtime。任何 source mutation/reprocess如果改变 processor输入，必须先由 storage revision变化表达。
- meta cache也绑定同一 revision，避免 citation/list result在source mutation后继续使用旧 meta。

### 5. Virtual Section/Table State Owner

`_VirtualSectionProcessorMixin` 新增一个 protected refresh method（最终命名在实现中固定并由 source scan锁定），原子执行：

1. 以最终 `self._virtual_sections` 重建 `self._virtual_section_by_ref`；重复 ref立即抛 ValueError。
2. 清理/重建 `self._table_ref_to_virtual_ref` 和每个 section的 `table_refs`，调用现有 `_assign_tables_to_virtual_sections()`。
3. 完成后验证所有 table->section ref和section->table ref双向一致；悬挂 ref fail closed。

- `_initialize_virtual_sections()` 初始建表、10-K postprocess、BS 10-K postprocess、10-Q postprocess、BS 10-Q postprocess全部复用该 helper。
- 当前 `expand_ten_q_virtual_sections_content()` 的直接代码证据是：它只原地修改既有 section 的 `start/end/content/preview` 并按 `(start, level, ref)` 重排，不 append/insert section，也不创建 child ref。因此 S2 不设计新 ref schema；调用前后的 section object/ref multiset必须相同，且输入/输出 refs 均唯一。
- 10-Q expansion完成并排序后立即 refresh；不得在 `read_section` / `list_tables` 下游临时重算。若实现时发现 expansion 已能创建 child section/ref，必须停止并回 plan/re-review 明确由 expansion owner生成的唯一规则，禁止在 refresh helper 用后缀补救冲突。

### 6. Read Failure / Decode Contract

- 新增 `dayu/fins/processors/source_text.py` 作为 Fins processor source text decode owner，提供严格 typed bytes/path UTF-8 decode helper和 `FinsSourceDecodeError`。
- 允许 ASCII/UTF-8/BOM-normalized UTF-8；非法 byte sequence不得 ignore、replace或返回空串，必须以 `UnicodeDecodeError` 为 cause抛 typed error。
- `sec_processor._load_text`、`sec_report_form_common._extract_source_text_preserving_lines`、`sec_6k_rules._preview_payload` 复用；materialize/read失败也不得转 `""`。
- `read_runtime._create_processor()` 把 `FinsSourceDecodeError` 映射为 `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)`；public失败文本说明 source无法可靠解码，不包含绝对路径/raw bytes。
- `search_document` index readiness是搜索成功前置条件。保留 `FinsReadCancelledError` 直通；任何其它 section enumeration/semantic enrichment/BM25F/profile exception统一 chain为 `ErrorCode.SEARCH_INDEX_FAILED`。不保留空 BM25F fallback。
- `ErrorCode` 增加 `XBRL_QUERY_FAILED`、`SOURCE_DECODE_FAILED`、`SEARCH_INDEX_FAILED`、`SOURCE_CHANGED_DURING_READ`；`FinsReadBusinessError.code` 使用该 enum而不是裸 string，tool boundary只投影 `.value`。

### 7. Fiscal / Optional String / SEC Version / Ticker Owners

Fiscal:

- `filing_semantics.py` 提供 `normalize_fiscal_year(value)` 和 `fiscal_period_recency_rank(period)`；fiscal year只接受非bool正整数，`None`表示缺失，其它非空值均抛`ValueError`。rank固定为`None/unknown=0, Q1=1, Q2=2, H1=3, Q3=4, Q4=5, FY=6`，由immutable owner detail持有，不向consumer暴露mutable dict。
- `_parse_source_document_meta` 使用 domain fiscal year/period parser；非法非空值 fail closed，不 loose-parse为 None。
- 删除 read-side `_infer_fiscal_year`、`_infer_fiscal_period`、`_resolve_*_with_fallback` 及 dead `build_document_recency_sort_key/_build_recommended_documents`。source meta缺 fiscal字段就显式 `None`；read runtime不从 form/date补偿。
- source producer（SEC/CN/HK/upload）继续负责写 fiscal semantics；本 slice不新增 calendar/issuer fiscal calendar service。

Processor optional strings:

- 新增 `dayu/fins/processors/value_normalization.py` 的 `normalize_optional_dataframe_string(value: StringConvertible | None) -> str | None`；用显式 protocol/closed scalar types处理 `None`、blank、float NaN、`pd.NA`、`pd.NaT`，不使用 `Any/object/getattr`。
- 三个 consumer删除同名私有 wrapper并直接调用 owner；普通 `0/False` 保留为文本，不被当空。

SEC version:

- `sec_download_state.py` 提供 `has_current_download_version(meta, expected_version)`；`SecPipeline._can_skip_fast/_can_skip` 和 workflow all-not-modified condition都调用它。
- legacy/missing version即使所有 HTTP file result为 not_modified，也不能发 `not_modified` terminal；继续通过现有 source batch写入 current `download_version`，成功后才能 completed。

Ticker aliases:

- `_normalize_ticker_aliases` 对 canonical和每个非空 alias调用 `try_normalize_ticker`，使用 `.canonical` 去重并保持 canonical首项。
- 非空但无法识别的 alias抛 ValueError，整个 company-meta upsert不发生；不得保留 raw uppercase或静默丢弃。

## Implementation Slices

### S1 — Financial Result, XBRL Execution, And LLM Projection Contracts

#### Objective / Expected Outcome

建立 producer-owned financial/XBRL强类型contract，修复scale/period/quality/reason，并让read/tool projection无损传播；XBRL failure不再empty-success。

#### Prerequisites

- R3-D plan已通过 MiMo/DS plan review、必要fix/re-review并accepted commit。
- 不依赖S2/S3。

#### Allowed Production Files

- 新增 `dayu/fins/domain/financial_result_contract.py`
- `dayu/fins/domain/xbrl_result_contract.py`
- `dayu/fins/domain/filing_semantics.py`（S1仅增加financial scale/reason关联类型或复用导入；fiscal rank/parser留给S3）
- `dayu/fins/processors/financial_base.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/bs_six_k_processor.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/processors/html_financial_statement_common.py`
- `dayu/fins/processors/six_k_form_common.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`（S1仅XBRL normalize/scale consumer）
- `dayu/fins/tools/result_types.py`
- `dayu/fins/tools/error_contract.py`（S1仅XBRL code）
- `dayu/fins/tools/fins_tools.py`（只改两个financial tool descriptions和failure mapping）

#### Allowed Test Files

- 新增 `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_fins_storage_provider.py`（只改/加financial spawned-child、tool schema/outcome断言）

#### Exact Allowed Changes

1. 实现上文FinancialStatement/XBRL types、validators、quality/reason matrix与scale truth；更新所有真实producer返回必填 reason；domain XBRL result明确不含read-side dedup字段。
2. 先完成 edgartools `execute()` characterization tests，再让 `_query_facts_rows`按“exception/malformed=failed、合法空list=successful zero rows”返回execution summary；partial/all failure按矩阵投影；新增typed exception，不保留catch-all continue。
3. `sec_processor.py` 与 `bs_report_form_common.py` 显式解构 `XbrlConceptQuerySummary.rows/successful_concepts/failed_concepts`，按同一 caller mapping 构造 `XbrlFactsResult`，不得把 summary 当 list 或丢弃failed accounting。
4. BS/Sec/HTML/OCR producer把period/scale evidence输入统一quality helper；HTML caption与OCR heading helper分别拥有其scale evidence；无证据时partial+scale reason；units与scale拆分。
5. 删除read shadow protocol/fallback/cast bag；validated fields逐字段copy；read projection始终生成required `deduped_fact_count`，并保留producer `total`。
6. 按上文模板更新两个tool description为自解释output contract；不得触碰security、upload/download schema。
7. 删除旧result type import/export路径；所有caller直接import domain owner，不做compat re-export。

#### Required Assertions

- financial success round-trip：periods含明确 period_end/fiscal fields、scale=millions、units=USD、quality=xbrl、reason=None，public result逐字段相等。
- partial matrix参数化：missing scale、missing fiscal semantics、两者都缺；每类 reason唯一且tool result保留。
- financial statement validator拒绝缺 periods/scale/data_quality/reason/locator、非法scale、partial+None reason、xbrl+non-None reason、empty statement rows+xbrl；该断言不得错误拒绝successful zero-row XBRL concept query。
- units/scale guard：fixture不能再用 `units="millions"`；HTML/OCR result中scale不拼入units。
- edgartools characterization/matrix：`execute()->[]` 进入successful；sentinel exception进入failed并保留cause；非list/含非mapping row进入failed；all failed raises typed error；one success/one failure -> partial；successful zero rows -> `xbrl/None` legitimate empty；XBRL absent -> partial unavailable；本地filter导致空集仍是valid empty。
- `sec_processor` 与 `bs_report_form_common` caller tests逐项断言 summary rows/failed count 到 facts/quality/reason 的映射相同；all-failed caller不产生payload。
- raw total与raw facts count不一致继续fail closed；raw producer payload夹带`deduped_fact_count`也fail closed；public `deduped_fact_count` 在有/无去重两种情况都required并等于public facts长度，raw total原样保留且不能被dedup覆盖。
- BS common与BsSixK scale probe命中 -6时返回millions；probe无证据/失败返回partial+reason。
- HTML caption与OCR heading含 `in millions`/等价直接证据时scale=millions且units不含scale；无scale证据但有rows时partial+`scale_unavailable`；同时无fiscal semantics时partial+`scale_and_period_semantics_unavailable`；OCR income-summary fallback消费同一scale owner。
- direct callable和process-backed代表性tool path对all-failed均为failed outcome，不是success value。
- 两个tool description分别与上文模板字段/语义一致；XBRL description明确`xbrl + total=0`是正常零命中，并解释raw total与required dedup count；均无内部治理/security术语。

#### Validation Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
pytest tests/fins/test_fins_storage_provider.py -q -k 'financial_statement or xbrl_query or financial_tool'
coverage run -m pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py -q
coverage report --include='dayu/fins/domain/financial_result_contract.py,dayu/fins/domain/xbrl_result_contract.py' --fail-under=80
python -m pyright dayu/ tests/ utils/
git diff --check
```

#### Propagation Scans

```bash
rg -n '_ProcessorFinancialStatementPayload|data_quality: NotRequired|reason: NotRequired' dayu/fins tests/fins
rg -n 'FinancialStatementResult|XbrlFactsResult|ValidatedXbrlFactsResult|XbrlQueryResult' dayu/fins tests/fins
rg -n -U 'query_obj\.execute\(\)\n\s*except Exception:\n\s*continue' dayu/fins/processors/sec_xbrl_query.py
rg -n '_DECIMALS_SCALE_MAP|units.*millions|units.*thousands|units.*billions' dayu/fins tests/fins
rg -n 'periods|scale|data_quality|reason' dayu/fins/tools/read_runtime.py dayu/fins/tools/result_types.py dayu/fins/tools/fins_tools.py
rg -n 'deduped_fact_count' dayu/fins/domain dayu/fins/processors
```

Expected scan decision:

- shadow payload、NotRequired quality/reason、query catch-and-continue和duplicate scale map为零匹配。
- type consumer scan的每个命中必须直接import/consume domain owner，无旧re-export。
- units+scale scan只允许LLM description解释“二者不同”，不允许producer把scale写入units。
- domain/processor dedup count scan零匹配；该字段只允许出现在read normalizer/public projection、LLM description、tests和README。

#### README Decision

- S1暂不单独改README；在S3 aggregate docs step统一更新 `dayu/fins/README.md` 当前financial/XBRL contract，避免中间slice写future state。
- 不更新root `README.md`、`dayu/README.md`、`tests/README.md`：本slice不改变最终用户命令、分层关系、测试层级/运行方式。

#### Completion Signal

S1实现/test/review证明processor contract能区分完整、partial、unavailable、valid empty和failure，且LLM-facing result保留全部owner fields。

#### Stop Conditions

- 如果implementation-start characterization证明当前edgartools query API与已取证的5.30.0边界不同，或无法从observable return/exception区分“execute成功无rows”和“execute失败”，在修改producer前停止并回plan/re-review；不得回退empty success、重复远程probe或扩展taxonomy能力。
- 如果financial period/scale需要无直接证据的issuer calendar猜测，停止该推断并保留typed degradation；不得从日期或units反推。
- 如果实现需要Host/Engine分支、upload/download security schema或R3-E文件，停止并报告scope blocker。
- 如果移除旧type路径发现外部public consumer不在当前allowed files，停止并让controller裁决；不得加compat re-export。

### S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts

#### Objective / Expected Outcome

让10-Q最终section/table state同源，让processor/meta cache只复用storage revision匹配内容，并把decode/search/index失败投影为typed read failure。

#### Prerequisites

- S1 accepted；S2复用S1 financial/tool failure contract和error mapping。

#### Allowed Production Files

- `dayu/fins/domain/document_models.py`（只新增`SourceDocumentRevision`）
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- 新增 `dayu/fins/processors/source_text.py`
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/fins/processors/ten_k_processor.py`
- `dayu/fins/processors/bs_ten_k_processor.py`
- `dayu/fins/processors/ten_q_processor.py`
- `dayu/fins/processors/bs_ten_q_processor.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/pipelines/sec_6k_rules.py`
- `dayu/fins/tools/cache.py`（只允许cache value/type/docstring所需改动，不新增TTL/background invalidator）
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`（只允许FinsReadBusinessError enum typing）
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/tools/fins_tools.py`（只允许新增read failure code到existing failed outcome mapping；不改schema）

#### Allowed Test Files

- 新增 `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_sec_pipeline_download.py`（只覆盖6-K preview decode failure；不改download policy）

#### Exact Allowed Changes

1. storage owner实现canonical source revision typed projection；protocol/facade只暴露该typed fact。
2. processor/meta cache entry绑定revision；`_get_or_create_processor()` 与 independent `_get_source_meta_cached_by_kind()`/no-kind delegate都在各自call path比较revision，mismatch清两类cache；processor/meta rebuild race固定零自动重试并立即typed fail。
3. mixin新增唯一refresh helper；10-K/10-Q两种engine path迁移到helper并删除手写重复；锁定10-Q expansion只修改既有section boundary/order、不创建ref。
4. strict source decoder替换所有Fins `errors="ignore"`；decode/read失败不返回空文本。
5. search index readiness exception转typed business failure；不保留empty BM25F fallback。
6. 不把processor cache invalidation callback注入ingestion runtime，不以mtime/processed meta为freshness。

#### Required Freshness / State Matrix

| Case | Expected behavior |
| --- | --- |
| cache hit, revision equal | same processor instance reused；registry create count不增加 |
| source revision changes before next read | old processor/meta evicted；new processor built；result/citation来自new meta |
| source revision changes, meta cache accessed independently | 不调用processor build也必须比较revision；old meta与同文档old processor一并evict；list/info/citation从storage重建new meta |
| source deleted/invalid meta after cache | cached processor不得返回；FileNotFound/typed storage failure |
| revision changes during processor build | processor不cache/不return；零retry，立即`source_changed_during_read` failed outcome |
| revision changes during independent meta read | meta不cache/不return；零retry，立即`source_changed_during_read` failed outcome |
| only processed output changes, source revision equal | processor可复用；capability flags仍从processed repository当前值读取 |
| two concurrent reads after one revision change | document lock内只构建一次new processor；两者都不见old processor |

#### Required Assertions

- 10-Q expansion改变start/end/order后，在调用table assignment前先断言调用前后section object/ref multiset相同且ref唯一；refresh后`_virtual_section_by_ref` object identity指向最终sections，table双向map一致，无stale/悬挂ref。
- edgartools和BS 10-Q都覆盖；10-K迁移helper后行为不变。
- duplicate section ref和unassignable dangling table ref fail closed，不以最后写 wins。
- source revision digest对影响processor的任一meta/file字段变化而变化，对JSON key顺序变化稳定。
- independent meta tests不调用processor registry：warm list/info/citation meta后修改storage source revision，下一次独立meta read必须重读new meta并evict old processor；不出现“processor新、citation旧”。
- processor build与meta read各自注入一次R1/M1 != R2/M2；断言每条路径repository/build调用次数固定为一次、无第二次尝试，且cache无race产物。
- invalid UTF-8 bytes在Sec processor、report fallback、6-K preview分别抛typed error，原始非法bytes不进入message；无空文本success。
- search list_sections/enrichment/BM25F/profile任一注入异常，read runtime抛`SEARCH_INDEX_FAILED`且cause为注入异常；tool outcome `ok=False`。
- cancellation在相同位置仍优先为cancelled，不被search failure mapping改写。

#### Validation Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
pytest tests/fins/test_fins_storage_provider.py -q -k 'search_document or processor_cache or source_meta_cache or source_revision'
pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q
coverage run -m pytest tests/fins/test_processor_read_consistency.py -q
coverage report --include='dayu/fins/processors/source_text.py' --fail-under=80
python -m pyright dayu/ tests/ utils/
git diff --check
```

#### Propagation Scans

```bash
rg -n 'errors="ignore"' dayu/fins
rg -n -U 'except Exception:\n\s+pass' dayu/fins/tools/read_runtime.py
rg -n '_virtual_section_by_ref\s*=|_assign_tables_to_virtual_sections\(' dayu/fins/processors
rg -n '_processor_cache\.(get|put|evict)|_meta_cache\.(get|put|evict)|get_source_revision' dayu/fins tests/fins
rg -n 'SourceDocumentRevision|source_changed_during_read|search_index_failed|source_decode_failed' dayu/fins tests/fins
rg -n 'mtime|stat\(' dayu/fins/tools/read_runtime.py
```

Expected scan decision:

- `errors="ignore"` 和read-runtime swallow block零匹配。
- virtual assignment只在mixin owner内部直接调用；form processors只调用refresh helper。
- every cache get必须同一call path有revision comparison；mtime/stat zero match。
- named 6-K preview decode test必须被pytest按node id收集并执行；不存在该test时命令直接失败，禁止使用可能0 selected的`-k`表达式。

#### README Decision

- S2不单独落README；S3统一更新Fins README当前read cache/source revision和failure contract。
- storage protocol新增revision method属于Fins内部稳定契约，必须进入 `dayu/fins/README.md`；不触发root/dayu README。

#### Completion Signal

S2测试证明最终section/table map一致、cache无stale reuse、decode/search/index error不可伪装成功，且所有状态均由storage/processor/read owner直接产生。

#### Stop Conditions

- 如果storage owner无法从canonical source meta确定processor input revision，停止；不得用mtime、path、cache age或ingestion callback猜freshness。
- 如果processor还读取未进入storage revision的其它mutable source，停止并先扩展revision owner；不得仅清cache碰运气。
- 如果合法生产source必须支持非UTF-8 charset而当前没有明确encoding owner/policy，停止并请求charset contract；不得恢复ignore/replace。
- 如果section refresh需要下游read/list临时重算，停止并回到mixin owner修复。
- 如果10-Q expansion实现已创建或需要创建child section/ref，停止并回plan/re-review定义expansion owner的唯一ref规则；不得在refresh consumer追加后缀消歧。
- 任何tool-security/R3-E需求立即stop并报告，不并入S2。

### S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure

#### Objective / Expected Outcome

收敛fiscal排序/解析、dataframe optional string、SEC skip version和upload ticker alias真源；完成README、aggregate scans和production-high验证。

#### Prerequisites

- S1、S2均accepted；S3不得回改其contract，除非review finding明确进入fix/re-review。

#### Allowed Production Files

- `dayu/fins/domain/filing_semantics.py`
- 新增 `dayu/fins/processors/value_normalization.py`
- `dayu/fins/processors/sec_section_build.py`
- `dayu/fins/processors/sec_table_extraction.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/README.md`

#### Allowed Test Files

- 新增 `tests/fins/test_fiscal_normalization_contracts.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_sec_pipeline_upload_material_stream.py`
- `tests/fins/test_cn_pipeline.py`（只更新共享upload company-meta alias assertion）

#### Exact Allowed Changes

1. domain fiscal year/parser/rank helper成为唯一真源；read runtime删除inference/fallback/dead duplicate。
2. dataframe optional string helper替换三份wrapper；锁定NaN/NaT/blank/0/False语义。
3. SEC current-version helper被fast/remote/not-modified三类skip复用；legacy version走commit current version。
4. upload aliases全部走`try_normalize_ticker`，invalid fail before repository write。
5. 更新Fins README当前事实：financial/XBRL result invariants、source revision cache、typed read degradation、fiscal/normalization owners；不写work-unit流水账或测试命令。
6. 执行S1-S3 aggregate validation和propagation audit；不顺手清理其它pipeline style/Any。

#### Required Assertions

- fiscal rank固定业务顺序并通过helper消费；read/runtime不存在第二份map。
- `fiscal_year` missing -> None；bool/zero/negative/non-integer fail closed；不从report_date/filing_date产生year。
- annual form缺fiscal_period不被read runtime补FY；producer显式值会canonical为FY；非法period fail closed。
- optional string matrix：None/blank/float nan/pd.NA/pd.NaT -> None；`0` -> `"0"`；False -> `"False"`；普通text trim。
- SEC meta为legacy/missing version且remote files all not-modified时，不产生`skip_reason=not_modified`；成功commit后meta版本=current。
- current version下existing not-modified skip行为保持。
- ticker alias examples：`700.HK -> 0700`、`BRK.B -> BRK-B`、case/market suffix去重；invalid alias抛ValueError且spy repository零写入。
- canonical ticker始终首项；相同canonical的不同raw alias只保存一次。
- README只描述已落地current contract，无R3-D/gate/future/security文本。

#### Validation Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
pytest tests/fins/test_sec_pipeline_download.py -q -k 'skip or not_modified or download_version'
pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q -k 'company_meta or ticker_alias'
coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py -q
coverage report --include='dayu/fins/processors/value_normalization.py' --fail-under=80
pytest tests/fins -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

#### Propagation Scans

```bash
rg -n '_FISCAL_PERIOD_SORT_ORDER|def _infer_fiscal_year|def _infer_fiscal_period|_resolve_fiscal_.*fallback|build_document_recency_sort_key|_build_recommended_documents' dayu/fins/tools
rg -n 'def _normalize_optional_string' dayu/fins/processors/sec_section_build.py dayu/fins/processors/sec_table_extraction.py dayu/fins/processors/sec_xbrl_query.py
rg -n 'normalize_optional_dataframe_string' dayu/fins/processors tests/fins
rg -n 'download_version|not_modified|_can_skip_fast|_can_skip\(' dayu/fins/pipelines/sec_download_state.py dayu/fins/pipelines/sec_download_filing_workflow.py dayu/fins/pipelines/sec_pipeline.py tests/fins/test_sec_pipeline_download.py
rg -n 'strip\(\)\.upper\(\)|try_normalize_ticker|_normalize_ticker_aliases' dayu/fins/pipelines/upload_company_meta.py tests/fins
rg -n 'R3-D|plan gate|future|tool-security|SSRF|allowlist' dayu/fins/README.md
```

Expected scan decision:

- read/tool duplicate fiscal/inference/dead helpers和三份optional wrapper零匹配。
- every SEC skip branch可追到current-version helper；upload alias无local uppercase normalization。
- README work-unit/future/security terms零匹配。

#### README Decision

- **更新 `dayu/fins/README.md`：是。** 触发原因：Fins result public contract、storage revision protocol、read failure/freshness和processor owner机制变化，属于该README开发者稳定边界。
- **更新 `tests/README.md`：否。** 新测试仍属于现有 `tests/fins` 层级，未改变测试运行方式/维护规则。
- **更新根 `README.md`：否。** 无安装、CLI、workspace位置、用户工作流变化。
- **更新 `dayu/README.md`：否。** `UI -> Service -> Host -> Engine` 和Fins装配边界不变。
- **更新 `docs/host/design.md` / `docs/engine/design.md`：否。** 设计真源已明确财报语义属于Fins外部工具；本计划不改变Host/Engine contract。若实现发现必须改变这些边界，按stop condition停止而不是直接改design。

#### Completion Signal

S3及aggregate验证证明所有accepted R3-D semantics关闭、无旧owner/fallback传播、README与current code一致；sub-WU可交controller进入aggregate deepreview，不能由implementation agent自行进入。

#### Stop Conditions

- 如果fiscal year需要issuer-specific calendar但当前storage/processor没有直接事实，保持None/partial并停止新增推断；不得从date year补偿。
- 如果ticker alias允许非ticker company-name alias，必须由controller澄清CompanyMeta字段语义；不得一边canonical一边保留raw fallback。
- 如果SEC legacy-version all-not-modified路径无法在不引入remote/security策略的情况下重建current meta，停止并报告；不得skip旧版本。
- 如果README所需内容超出当前已实现事实，删除future文本；不得写计划状态。
- 任何R3-E/tool-security扩张立即stop。

## Slice Count And Gate-Cost Justification

计划包含 **3 个 implementation slices**，符合 umbrella production-high 默认边界；没有 one-finding-per-slice。

1. S1 是 financial/XBRL public/LLM contract 原子闭环：如果拆成“types”和“projection”会产生 contract-only 半成品；如果并入其它slice会让review同时承担public schema和cache/state风险。
2. S2 是 processor/read consistency闭环：virtual section state、source revision cache、decode/search failure共享“读取结果必须对应当前可信source”的失败矩阵和review专长。
3. S3 是 domain/pipeline normalization闭环：fiscal、optional scalar、version、ticker都是owner helper迁移，风险低于S1/S2，但需要在前两slice稳定后做aggregate propagation/docs closure。

增加第4个slice只会为单个helper/README重复implementation artifact、双路review、controller adjudication和validation；合并到2个slice则会让public financial contract与source freshness/section state互相掩盖失败。3个是最小稳定闭环。

所有3个slice都修改生产代码；按 `production-high` 必须 per-slice code review，不合并到aggregate-only review。

## Aggregate Validation Profile

### Required Focused Profiles

- Fins result projection tests：S1 financial raw -> validated -> read -> tool round-trip。
- XBRL exception tests：all failed / partial / valid empty / filter empty / unavailable。
- BS scale tests：BS common + BS SixK命中与缺失/exception degradation。
- 10-Q virtual section/table tests：edgartools + BS双路线，index与双向table mapping。
- processor cache invalidation/freshness tests：equal/mismatch/during-build/concurrent/meta alignment。
- read-runtime degradation tests：search/index/decode/source-change typed failed outcomes和cancellation priority。
- SEC skip/version test：legacy/missing/current version × all-not-modified。
- ticker normalization test：HK/CN/US alias canonical/dedupe/invalid no-write。
- fiscal/optional normalization tests：strict absence/invalid/rank/NaN/NaT。

### Final Aggregate Commands

```bash
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_processor_read_consistency.py tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
pytest tests/fins/test_fins_storage_provider.py -q -k 'financial_statement or xbrl_query or search_document or processor_cache or source_revision'
pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q
pytest tests/fins/test_sec_pipeline_download.py -q -k 'xbrl or 6k or skip or not_modified or download_version'
pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q -k 'company_meta or ticker_alias'
pytest tests/fins -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

### Final Propagation / Source Audit

```bash
rg -n 'errors="ignore"' dayu/fins
rg -n -U 'except Exception:\n\s+(pass|continue)' dayu/fins/tools/read_runtime.py dayu/fins/processors/sec_xbrl_query.py
rg -n '_ProcessorFinancialStatementPayload|data_quality: NotRequired|reason: NotRequired|_DECIMALS_SCALE_MAP' dayu/fins
rg -n '_FISCAL_PERIOD_SORT_ORDER|def _infer_fiscal_year|def _infer_fiscal_period|_resolve_fiscal_.*fallback' dayu/fins/tools
rg -n 'FinancialStatementResult|XbrlFactsResult|SourceDocumentRevision|ErrorCode\.' dayu/fins tests/fins
rg -n '_virtual_section_by_ref\s*=|_assign_tables_to_virtual_sections\(' dayu/fins/processors
rg -n 'not_modified|download_version|try_normalize_ticker|normalize_optional_dataframe_string' dayu/fins tests/fins
rg -n '(^|\s)(from|import) dayu\.(host|engine)' dayu/fins --glob '*.py'
git diff --name-only
git diff --check
```

Audit rules:

- 任何 unexpected match先分类为current owner、legitimate third-party adapter或stale path；不得用ignore comment/allowlist掩盖。
- `git diff --name-only` 必须是S1-S3 allowed files、tests和`dayu/fins/README.md`；出现R3-E、Host/Engine、config prompt、upload/download security文件立即stop。
- pre-existing test failure必须按umbrella baseline registry复跑最小命令并用baseline commit/artifact证明；不得把本轮owner failure登记为baseline。
- 新增contract/helper file单文件coverage >=80%；既有大文件使用focused branch matrix并在implementation artifact记录uncovered areas。

## Plan Re-Review Checklist For AgentMiMo / AgentDS

### Shared Mandatory Checklist

- [ ] 目标/动机与current code direct evidence一致，没有把style/god-file问题伪装成R3-D blocker。
- [ ] 每个 accepted correction有唯一owner；没有read/tool/fixture fallback修补processor/storage错误语义。
- [ ] financial quality/reason matrix能唯一分辨complete、partial、unavailable、valid empty、all failure。
- [ ] `periods/scale/data_quality/reason` 从producer到LLM result逐字段同源；units不承载scale。
- [ ] XBRL all/partial/empty异常矩阵无catch-empty loophole；validator与public result一致。
- [ ] edgartools pre-check与bounded adapter明确：empty list成功、exception/malformed失败、每concept一次执行；两个caller按summary同一映射消费。
- [ ] `xbrl + total=0`只表示XBRL查询正常零命中，未与empty financial statement混淆；LLM description/test一致。
- [ ] raw `total`只由producer拥有；required `deduped_fact_count`只由read projection拥有，二者没有extra/NotRequired/覆盖路径。
- [ ] source revision由storage canonical fact产生，不依赖mtime/log/processed state/timestamp猜测；build race fail closed。
- [ ] independent meta read自己比较revision；processor/meta race均零自动retry且不会cache混合结果。
- [ ] 10-Q expansion后index/table双向状态原子refresh，无downstream重算。
- [ ] 10-Q expansion ref集合不变且唯一；若出现child ref需求会stop而非consumer消歧。
- [ ] strict decode/search failure不会泄露path/raw bytes，也不会吞cancel。
- [ ] fiscal year没有从calendar date伪推；财期排序和optional string各一个owner。
- [ ] SEC version/ticker alias消费现有owner helper，无raw fallback。
- [ ] 3 slices按owner/validation/blast radius切分，没有one-finding-per-slice，也没有不必要第4 slice。
- [ ] 每个slice allowed files、test assertions、commands、README decision、propagation scans和stop conditions足够code generation，不需要实现者再发明contract。
- [ ] tool-security和R3-E明确out of scope；没有修改upload/download security schema/prompt。
- [ ] 无compat shim/re-export/wrapper、loose parsing、`Any/object/getattr/hasattr`新签名或旧empty-success保留。

### AgentMiMo Focus

- [ ] 沿 processor -> domain validator -> read normalizer -> result type -> ToolResultSuccess/Failure -> LLM description 做字段级data-flow audit。
- [ ] 检查S1 types是否存在total=False/cast/extra bag暗门，quality/reason invariant是否所有producer都满足。
- [ ] 检查两个LLM-facing description是否符合模板，自足说明字段、类型、allowed values、scale-vs-units、raw/dedup count和partial reason，不暴露内部治理。
- [ ] 检查DocumentMeta残余裁决是否窄到revision所需，而非遗漏当前financial/read weak boundary。
- [ ] 检查README decision与`dayu/fins/README.md` Agent更新约束一致。

### AgentDS Focus

- [ ] adversarial执行XBRL all-fail/partial-fail/filter-empty/malformed-return反例，确认没有exception count或reason丢失。
- [ ] adversarial执行cache ABA/source-change-during-build/concurrent rebuild/independent meta-stale反例，并确认race没有隐式第二次重试。
- [ ] 检查10-Q section reorder/duplicate ref/unmapped table/child section反例和双向不变量。
- [ ] 检查UTF-8失败、materialize/read失败、search enrichment各exception branch及cancellation ordering。
- [ ] 检查legacy version 304/not-modified与alias invalid/no-write反例。
- [ ] 检查source scans是否覆盖所有producer/consumer，特别是HTML/OCR/BS SixK和三份optional wrapper。

## Risks / Residuals / Blocking Questions

### Known Implementation Risks With Owner

- edgartools动态rows仍在最窄adapter边界；已由5.30.0源码取证与characterization/malformed fallback限定，S1 validator必须立即收窄为JsonValue typed contract；依赖升级漂移由命名tests fail closed。Owner: S1 financial contract。
- source revision计算增加cache hit storage read；correctness优先，性能数据只可在后续profiling优化，不得跳过revision。Owner: S2 storage/read cache。
- strict UTF-8可能暴露历史非UTF-8 source；当前安全行为是typed fail closed。若业务需要其它charset，destination是独立Fins encoding-policy decision，不是R3-E/tool-security。
- full `DocumentMeta` broad type仍存在；destination由umbrella controller另行裁决，不能在R3-D final closeout写成已修复。
- 6-K BS-only routing保持；destination只有controller明确创建的独立6-K routing WU。

### Blocking Questions

无。

正确owner已经清楚，计划不需要tool-security或R3-E工作；因此不触发用户要求的artifact blocker stop。

## Implementation Completion Report Format

每个后续implementation slice只允许按以下格式返回controller：

```text
SLICE <S1|S2|S3> COMPLETE
changed files: <exact paths>
contract changes: <owner-level summary>
tests: <commands and results>
pyright: <result>
coverage: <new/small owner files result>
README decision: <updated path or no-update reason>
propagation scans: <expected/unexpected matches and classification>
residual risks: <owner/destination or none>
blocking questions: <none or blocker>
```

禁止implementation agent commit、push、PR、merge或进入review/next slice；controller按Gateflow推进。

## Plan-Fix Gate Completion Status

- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Implementation slices: 3
- Controller plan-fix findings: PF-01 through PF-06 addressed in this artifact；pending independent re-review。
- Gate decision: `ready-for-plan-rereview`
- Blocking questions: none
- Next allowed gate owner action: controller派发AgentMiMo/AgentDS执行R3-D parallel plan re-review；AgentCodex在本次任务中停止，不进入implementation。
