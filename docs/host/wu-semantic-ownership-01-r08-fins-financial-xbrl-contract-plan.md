# WU-SEMANTIC-OWNERSHIP-01 / R08 Financial/XBRL 最小契约实施计划

## 0. Gate 与结论

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| sub-WU | 既有 remediation `R08`；不是新 WU、feature 或 issue |
| gate | plan review fix 后的 code-generation-ready plan；完成后停回 Controller validation |
| base / transition HEAD | `8d9bf63b3ab56f9ba3d5355d75af4ee002548c9c` |
| R07 completion commit | `28b6fc1956bd3832489a471fa29bfe354b319860` |
| 固定 slices | S1 producer domain contracts + all actual processors；S2 read/tool/LLM single projection |
| 本 gate 授权 | 只修改本计划并新增一个 plan-fix artifact；不实施、不 stage、不 commit、不 push、不建 PR |

R08 只落实 umbrella remediation plan §15 已裁决的 Topic 6.4：收窄 financial/XBRL 的 LLM-facing contract，并建立单一 public typed projection。R06 transaction/publication owner 与 R07 identity/revision/snapshot/citation/provenance owner 已完成，本计划只消费它们，不回改。

## 1. 第一性原理判断

问题真实存在，且不是命名或文案问题：

1. Financial producer 将财务事实与 `statement_locator`、`statement_method_missing`、`statement_empty` 等处理器诊断混在同一 contract，read 又原样公开，使内部调用路径变成 LLM 业务事实。
2. XBRL producer 用 `len(facts)`生成 `total`，read 再公开 `deduped_fact_count`。模型实际消费的是已去重 facts，双计数没有独立业务动作，却形成两个 owner。
3. Producer 当前将可选 XBRL filters 放在 `query_params.filters_applied`，read 却从 `query_params` 顶层读取同名键并补 `None`，已经形成直接可证的 shape drift。
4. Tool description 手写第三份字段定义，公开 raw total / dedupe diagnostic，且没有自足说明必填性、完整枚举和最小示例。
5. `dayu/fins/pipelines/sec_fiscal_fields.py::_build_financials_payload` 没有 production caller，却作为替代 owner 发明 `processor_error:<message>` 与 `invalid_statement_result` reason；它不能以“兼容”名义保留。

所以正确路径是先在 producer owner 收紧 contract，再由一个 typed public projection 机械投影。只改 tool 文案、在 read 补默认、保留双 contract 或给旧测试加 shim 都不是 root-cause 修复。

## 2. 完成定义与非目标

### 2.1 R08 完成定义

- Financial producer 只承诺 `statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`、可选业务可行动 `reason`。
- 所有实际 producer 在 owner terminal 将 method 不存在、method 返回空、空表、空 rows 统一为 `statement_not_found`；read 不猜 reason。
- XBRL processor-internal result 只承诺 `query_params`、raw `facts`、`data_quality`、可选 `reason`。
- Provider raw total 只有在明确 internal validation/diagnostic owner 中才可存在；它不进入 producer result、public result、tool/schema/serializer/LLM。
- Read 不原地修改 raw facts；独立复制、规范化、稳定去重，再构造 public typed result。
- Public XBRL 只有一个 `fact_count`，且唯一赋值 owner 执行 `len(returned_facts)`。
- Tool description、result serializer 与 LLM-facing 字段说明从同一 typed projection/helper 派生，自足说明字段、类型、必填性、枚举与最小示例。
- 真实 AAPL XBRL fixture、真实 HTML 财务表 smoke、owner tests、逐文件 coverage、pyright、Ruff、diff/source/propagation scans 全部通过。
- S1 完整 review/fix/re-review 关闭后才进入 S2；R08 后仍需 R09-R12 与 umbrella aggregate deepreview。

### 2.2 不可回改的 owner

| 语义 | 唯一 owner | R08 边界 |
|---|---|---|
| opaque ticker/document identity 与 storage mapping | R07 storage | 不解析 ID、不从路径或前缀猜 provider |
| revision、稳定 snapshot、borrow/retire/cache 生命周期 | R07 storage/read snapshot boundary | 不改 cache key、revision、borrow/release、retry |
| provenance 与 citation | R07 snapshot/citation projection | 只机械接收同一 borrowed snapshot 的 ticker/document/citation |
| transaction authority 与完整 source publication | R06 storage transaction | 不改 batch/commit/rollback/staging/publication |
| financial producer result | `dayu.fins.domain.financial_result_contract` + actual processor | S1 唯一业务 owner |
| XBRL raw query result | `dayu.fins.domain.xbrl_result_contract` + actual processor | S1 唯一业务 owner |
| public financial/XBRL result | `dayu.fins.tools.result_types` 的 typed projection/helper | S2 唯一 public owner |

### 2.3 明确 out-of-scope

- R09 direct-stream validator；R10 HKEX；R11 upload/placeholders；R12 init/reset；
- Issues 142、151、175、177、178；统一 authorization；
- Host generic truncation/cursor/fetch_more、Engine、Service、UI；
- R07 identity/snapshot/revision/citation/provenance owner；
- financial/XBRL 之外的 error codes、ingestion、download/upload、storage contract；
- compatibility re-export/wrapper、fallback、shim、双写字段、loose parsing、`getattr/hasattr` 补偿、默认 reason、历史 payload 分支；
- 无关 dead-code 清理、全仓 Ruff 清理或 README 扩写。

若实现必须修改上述 owner 才能满足 R08，停止该 slice 并回 Controller；不得自行扩 allowlist。

## 3. 当前字段与 owner inventory

### 3.1 Financial producer contract

当前 owner 是 `dayu/fins/domain/financial_result_contract.py`。

| 当前字段/值 | 裁决 |
|---|---|
| `statement_type` | 保留，required、非空 |
| `periods` | 保留，required typed list |
| `rows` | 保留，required JSON rows |
| `currency` | 保留，required nullable |
| `units` | 保留，required nullable |
| `scale` | 保留，required nullable；当前唯一真源 `FinancialScale` 闭集为 `units|thousands|millions|billions` |
| `data_quality` | 保留，required、闭集枚举 |
| `reason` | 改为 optional；只允许业务可行动闭集 |
| `statement_locator` / `StatementLocator` | 删除，不是财务事实或当前动作依据 |
| `statement_method_missing` | 删除；producer terminal 归一为 `statement_not_found` |
| `statement_empty` | 删除；producer terminal 归一为 `statement_not_found` |

Financial reason 闭集固定为：

```text
unsupported_statement_type
xbrl_not_available
statement_not_found
low_confidence_extraction
scale_unavailable
period_semantics_unavailable
scale_and_period_semantics_unavailable
```

`data_quality=xbrl|extracted` 时 `reason` 必须缺席；`data_quality=partial` 时必须存在且属于该七值闭集。序列化结果不以 `reason: null` 代替 optional。异常消息、method 名称、空表实现细节都不能变成 reason。

### 3.2 XBRL processor-internal contract

当前 owner 是 `dayu/fins/domain/xbrl_result_contract.py`。

| 当前字段/值 | 裁决 |
|---|---|
| `query_params` | 保留且 typed，required |
| raw `facts` | 保留，required；read 不原地改写 |
| `data_quality` | 保留，required；只允许 `xbrl|partial` |
| `reason` | optional；只允许 `xbrl_not_available|query_partially_failed` |
| `total` | 从 processor result 删除；当前值是本地 `len(facts)`重复派生，不是 provider raw validation fact |
| `deduped_fact_count` | 删除 |
| `fact_count` | 不属于 producer；只在 S2 public projection 产生一次 |

当前审计未发现需要保留的真实 provider raw-total validation owner，因此 initial positive inventory 预期为零。若实施扫描发现真实 provider response total，只有同时满足下列条件才可保留：

1. 位于明确命名的 processor/provider internal typed validation/diagnostic owner；
2. 只核验 provider 响应完整性或生成内部诊断；
3. 有 matching/mismatching owner tests；
4. 不进入 `XbrlFactsResult`、public result、tool/schema/serializer/LLM；
5. review evidence 逐条记录文件、symbol、provider input、校验动作与无传播证明。

本地 `len(facts)`形成的 total 不具备保留资格，也不能改名为 `raw_total`。

### 3.3 Actual producer inventory

| 文件 / owner symbol | 当前偏差 | S1 动作 |
|---|---|---|
| `dayu/fins/processors/sec_processor.py` financial method | locator、method/empty internal reasons | 删除 locator；归一为 `statement_not_found` |
| `dayu/fins/processors/sec_processor.py` XBRL method | `total=len(facts)` | 删除 count；输出 typed flat query params |
| `dayu/fins/processors/bs_report_form_common.py` | locator、method/empty reasons、XBRL total | 收窄为目标 contract |
| `dayu/fins/processors/bs_six_k_processor.py` | locator；helper以 `None`表达 method/empty；XBRL total | terminal 形成 `statement_not_found`；删除 count |
| `dayu/fins/processors/html_financial_statement_common.py` | HTML result 含 locator | 删除 locator，保留表格业务字段 |
| `dayu/fins/processors/six_k_form_common.py` | HTML/OCR 两处 locator | 删除 locator，保留 quality/period/scale语义 |
| `dayu/fins/processors/report_form_financial_statement_common.py` | fallback reason 集含两个内部 reason | 只消费收窄后的业务 reason |
| `dayu/fins/processors/sec_report_form_common.py` | 消费 common fallback/quality | 只做必要类型传播；无字段构造则零 diff |
| `dayu/fins/processors/sec_xbrl_query.py::build_statement_locator` | locator 唯一 helper | 删除 helper及引用，不保留 wrapper |
| `dayu/fins/processors/financial_base.py` | Protocol引用producer types | 只做必要签名/docstring传播 |

Registry 的 BS 10-K/10-Q/20-F/6-K、SEC 10-K/10-Q/20-F 与 generic `SecProcessor` 均由上述 concrete/common owner 覆盖。只继承而不构造目标 payload 的表单类只跑 propagation/registry tests，不做空改动。

### 3.4 Consumers、alternate owner 与 tests

| 文件 | 当前行为 | R08 动作 |
|---|---|---|
| `dayu/fins/tools/result_types.py` | tools public `FinancialStatementResult` 含 locator，`XbrlQueryResult` 含 total+dedup count，且与 domain producer 类型命名边界不清 | S2建立唯一 typed public contract/helper，精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`，删除两个旧 tools 类型名且不保留 alias |
| `dayu/fins/tools/read_runtime_helpers.py` | 复制/清洗/去重后仍返回双count | S2只交付独立facts给public builder |
| `dayu/fins/tools/read_runtime.py` | 手工拼结果与query params | S2机械消费projection；不补默认/猜reason |
| `dayu/fins/tools/fins_tools.py` | 手写LLM字段contract | S2消费owner metadata/helper |
| `dayu/fins/pipelines/sec_fiscal_fields.py::_build_financials_payload` | 无production caller，发明alternate reasons | S1删除该owner及只固化它的测试 |
| `dayu/fins/pipelines/sec_fiscal_fields.py::_extract_fiscal_from_xbrl_query` | 消费旧total validator | S1只传播新validator，不新建owner |
| `dayu/config/prompts/**` | 当前没有目标字段 | 不改；纳入public/LLM negative scan |

测试迁移 inventory：

- `tests/fins/test_financial_read_contracts.py`：S1 owner contract、SEC/BS/6-K/HTML/OCR actual producers。
- `tests/fins/test_sec_pipeline_download.py`：S1删除alternate reasons与invalid-total旧断言，保留真实fiscal语义。
- `tests/fins/test_fins_read_runtime.py`：S1 只迁移 `_extract_fiscal_from_xbrl_query` 直接消费的 XBRL producer-contract fixture/node；S2 再迁移同文件的 read normalize/dedup/query params/唯一 count nodes，具体 symbol 边界见§5.1。
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`：S2 exact projection与R07 citation/snapshot guards。
- `tests/fins/test_processor_read_consistency.py`：S2同snapshot processor/result/citation一致性。
- `tests/fins/test_fins_storage_provider.py`：S2真实HTML、AAPL fixture、tool description、process outcome。
- `tests/fins/test_processor_registry.py`、`tests/fins/test_fins_ingestion_tools.py`：必跑回归，除直接旧fixture证据外预期零diff。

## 4. 目标 contracts（代码生成真源）

### 4.1 Financial producer typed contract

`dayu/fins/domain/financial_result_contract.py` 继续拥有 producer result与terminal validator。目标shape：

```python
class FinancialStatementResult(TypedDict):
    statement_type: str
    periods: list[FinancialPeriod]
    rows: list[dict[str, JsonValue]]
    currency: str | None
    units: str | None
    scale: FinancialScale | None
    data_quality: FinancialDataQuality
    reason: NotRequired[FinancialStatementReason]
```

字段规则：

- `statement_type`非空，使用调用的canonical statement type，不另建alias。
- `periods`逐项由现有typed period contract校验；日期、财年、财期不由read重建。
- `rows`每项为独立JSON mapping；complete结果至少一行，partial/not-found允许空列表。
- `currency`、`units`、`scale`是required nullable业务事实；producer明确给出`None`，read不补。
- `scale`非空时只允许当前唯一真源 `FinancialScale` 的 `units|thousands|millions|billions`；不得引入 `ones` 或其它新值。
- `data_quality`只允许`xbrl|extracted|partial`。
- `reason` complete时缺席；partial时必填且属于七值闭集。
- 缺essential field、未知键、非法枚举、complete+reason、partial无reason均由terminal validator fail closed；不得宽松读取。

失败语义：

| Producer观测 | 唯一输出 |
|---|---|
| statement type不支持 | partial + `unsupported_statement_type` |
| XBRL source/能力不可用且下一步应改用抽取 | partial + `xbrl_not_available` |
| method absent、method返回None、空DataFrame、空rows、无目标表 | partial + `statement_not_found` |
| 抽取低置信度 | partial + `low_confidence_extraction` |
| multiplier不可靠 | partial + `scale_unavailable` |
| 财期语义不可靠 | partial + `period_semantics_unavailable` |
| multiplier与财期均不可靠 | partial + `scale_and_period_semantics_unavailable` |

禁止输出locator、method/empty内部原因、异常字符串reason、unknown reason、`reason: null`，也禁止read根据rows或异常消息重建这些事实。

### 4.2 XBRL processor-internal typed contract

`dayu/fins/domain/xbrl_result_contract.py` 继续拥有 raw query result、query params与terminal validator：

```python
class XbrlQueryParams(TypedDict):
    concepts: list[str]
    statement_type: NotRequired[str]
    period_end: NotRequired[str]
    fiscal_year: NotRequired[int]
    fiscal_period: NotRequired[FiscalPeriod]
    min_value: NotRequired[int | float]
    max_value: NotRequired[int | float]

class XbrlFactsResult(TypedDict):
    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    data_quality: XbrlDataQuality
    reason: NotRequired[XbrlQueryReason]
```

规则：

- `concepts` required、非空、保持实际执行顺序；可选filters只有调用方明确提供时才出现。
- `fiscal_period` 的类型与运行时值集只消费 `dayu.fins.domain.filing_semantics` 已有 `FiscalPeriod` / `FISCAL_PERIODS` 真源，闭集精确为 `FY|H1|Q1|Q2|Q3|Q4`。S1 validator 不另写 literal 集合；输入未提供时保持字段缺席，不补 `None`。
- `min_value`、`max_value`直接使用可实现的朴素类型`int | float`；`bool`虽然是`int`子类，但不属于本业务数值，S1 `xbrl_result_contract.py` validator 必须先显式拒绝 `bool`，再接受 `int | float`，owner tests 分别覆盖 `True`、`False`、`int`、`float`和字段缺席。仓库当前没有`JsonNumber`，不得在计划中引用不存在的类型；除非实现证明多个owner确需共享且在现有domain owner内定义，否则不新增alias。
- 删除当前`filters_applied`嵌套shape；producer直接输出flat typed params，read只复制，不补`None`。
- raw facts逐项校验为JSON mapping；validator不加入任何count。
- `data_quality=xbrl`包括合法zero-hit，省略reason。
- `data_quality=partial`必须带`xbrl_not_available|query_partially_failed`。
- 全部concept失败继续抛既有typed `XbrlQueryExecutionError`，不降级成内部消息result。
- Unknown keys统一失败；不为`total|raw_total|deduped_fact_count|fact_count`分别写兼容分支。

### 4.3 单一 public typed projection

`dayu/fins/tools/result_types.py` 是唯一public result projection owner。只建立两个小型、直接、严格typed helper，不引入generic builder、god bag、reflection或新schema framework：

```text
project_financial_statement_result(
    *, ticker, document_id, citation, producer_result
) -> PublicFinancialStatementResult

project_xbrl_query_result(
    *, ticker, document_id, citation, query_params,
       returned_facts, data_quality, optional_reason
) -> PublicXbrlQueryResult
```

Tools projection types 的公开名称精确为 `PublicFinancialStatementResult` 与 `PublicXbrlQueryResult`。S2 必须删除 `dayu.fins.tools.result_types` 中旧 `FinancialStatementResult` / `XbrlQueryResult` 定义，并同步所有 direct imports、return annotations 与 tests；不保留 re-export、alias、wrapper 或其它 compatibility path。Domain producer `dayu.fins.domain.financial_result_contract.FinancialStatementResult` 与 `dayu.fins.domain.xbrl_result_contract.XbrlFactsResult` 保持原名，不在 R08 重命名。

`PublicFinancialStatementResult` exact字段：

```text
required: ticker, document_id, citation: dict[str, JsonValue],
          statement_type, periods, rows, currency, units, scale, data_quality
optional: reason
```

`PublicXbrlQueryResult` exact字段：

```text
required: ticker, document_id, citation: dict[str, JsonValue],
          query_params, facts, fact_count, data_quality
optional: reason
```

投影规则：

- `ticker`、`document_id`、`citation`只由当前R07 borrowed snapshot context传入；helper不读storage、不解析ID、不生成citation。
- 两个 builder 的 `citation` 入参精确使用 `Mapping[str, JsonValue]`，进入 builder 后立即以 `dict(citation)` 形成不与输入 alias 的独立 `dict[str, JsonValue]`，并把该独立 dict 作为两个 public result 的 `citation`。不修改 `Citation` frozen dataclass 或其 `to_dict()`，不重新枚举、校验、推断或子集投影 citation keys，不建第二个 citation schema，不使用 `dict[str, Any]`、cast、alias 或 shim。R07 `_build_citation`、snapshot/citation 字段语义与生成路径保持 no-touch。
- Financial business字段逐项机械复制；reason存在才复制。
- XBRL `facts`是read完成规范化与稳定去重后的独立list，每个fact也是独立mapping。
- Builder先固定最终`returned_facts_copy`，再且只在这一处写`fact_count=len(returned_facts_copy)`。
- Serializer就是该typed JSON-safe mapping；read/tool callable不得再手写第二份result mapping。
- `fact_count`不表示provider total、去重前命中量或diagnostic，只表示同一public result中返回facts的长度。

### 4.4 Tool schema、description与LLM文本

`result_types.py`邻接拥有两个无状态description metadata/helper，分别描述financial与XBRL public contract；`fins_tools.py`只消费它们。禁止从`TypedDict` runtime introspection、`Any`、反射或另一registry猜字段。

两份description在当前文本中均自足满足第1-5与第7项，financial description 额外满足第6项：

1. 全部返回字段及业务含义；
2. JSON类型；
3. required/optional；
4. `data_quality`、`scale`、`reason`、`fiscal_period`允许值；
5. reason只在partial时出现；
6. financial 七个 reason 的简洁业务含义与安全下一动作；
7. 一个最小JSON示例。

`result_types.py` 中的同源 description metadata/helper 必须完整拥有下列 reason→下一动作矩阵；`fins_tools.py` 只机械消费，不重写：

| reason | 业务含义 | LLM-safe 下一动作 |
|---|---|---|
| `unsupported_statement_type` | 当前 actual processor 无法服务该全局合法报表类型 | 不重复同一请求；选择其它合法 statement type 或其它 document |
| `xbrl_not_available` | 当前来源无可用 XBRL 业务结果 | 不重复同一 XBRL 请求；改用可用的财务报表抽取结果或其它 filing，并谨慎核验 |
| `statement_not_found` | 当前 document 没有可用的目标报表 | 不重复同一请求；选择其它合法 statement type 或其它 document |
| `low_confidence_extraction` | 抽取结果置信度不足 | 不直接作确定性结论；用其它报表或来源交叉验证 |
| `scale_unavailable` | 数值倍率不可靠 | 禁止数量级判断或依赖倍率的比较，先核验 scale |
| `period_semantics_unavailable` | 财期语义不可靠 | 禁止跨期比较，先核验期间归属 |
| `scale_and_period_semantics_unavailable` | 数值倍率与财期语义均不可靠 | 禁止数量级判断与跨期比较，分别核验 scale 与 period |

该 metadata/helper 只暴露业务含义与下一动作，不暴露 processor method、fallback branch、异常消息或 Host 治理状态。`unsupported_statement_type` 不是未来扩展占位：它表达 actual processor 无法服务一个全局合法 statement type 的当前业务结果，七值闭集保持不变。

`query_xbrl_facts` 输入 schema 的 `fiscal_period.enum` 必须使用 `sorted(FISCAL_PERIODS)` 从同一 owner 派生确定性 `FY|H1|Q1|Q2|Q3|Q4` 值序列，不只在 description 中举例，不手写第二份 literal enum；输入缺席时不补 `None`。`min_value` / `max_value` 的 schema 继续使用 JSON Schema `type: number`，并与 S1 domain validator 的显式 bool 拒绝共同受 callable/schema tests 约束。

最小XBRL示例必须只有一个count并满足等式：

```json
{
  "ticker": "AAPL",
  "document_id": "opaque-document-id",
  "citation": {
    "source_type": "SEC_EDGAR",
    "document_id": "opaque-document-id",
    "ticker": "AAPL",
    "source_provider": "SEC_EDGAR"
  },
  "query_params": {"concepts": ["Revenue"]},
  "facts": [{"concept": "Revenue", "value": 100}],
  "fact_count": 1,
  "data_quality": "xbrl"
}
```

示例中的document ID只是引用标签，不能暗示provider/revision。不得暴露processor类名、method状态、raw count、dedupe diagnostic、revision、snapshot key或内部错误消息。
示例与 description tests 必须消费当前 owner metadata/helper，断言 `source_type` 为 `SEC_EDGAR`、保留同一示例的 `document_id`、`ticker`、`source_provider`，且 LLM-facing 文本不存在 `sec_filing`；不为示例新建 source mapping。

## 5. R08-S1 — producer contracts + all actual processors

### 5.1 依赖与 exact allowlist

进入条件：base lineage仍包含给定R07 completion；除accepted plan/review artifacts外无未知改动；R07 owners未获修改授权。

S1 production diff闭集：

```text
dayu/fins/domain/financial_result_contract.py
dayu/fins/domain/xbrl_result_contract.py
dayu/fins/processors/financial_base.py
dayu/fins/processors/html_financial_statement_common.py
dayu/fins/processors/report_form_financial_statement_common.py
dayu/fins/processors/sec_report_form_common.py
dayu/fins/processors/bs_report_form_common.py
dayu/fins/processors/six_k_form_common.py
dayu/fins/processors/sec_processor.py
dayu/fins/processors/bs_six_k_processor.py
dayu/fins/processors/sec_xbrl_query.py
dayu/fins/pipelines/sec_fiscal_fields.py
```

`financial_base.py`、`sec_report_form_common.py`只有严格类型传播或真实旧字段引用时可改，否则零diff。`sec_fiscal_fields.py`只删除alternate financial owner并传播新XBRL validator，禁止顺手清理其它dead helpers。

S1 tests diff闭集：

```text
tests/fins/test_financial_read_contracts.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_fins_read_runtime.py
```

`tests/fins/test_processor_registry.py`必跑但预期零diff；如其fixture直接构造旧payload，须先由Controller扩allowlist。S1不改README，current public surface在S2定型后一次更新。

`tests/fins/test_fins_read_runtime.py` 是 S1/S2 共享文件，symbol 边界固定如下：

- S1 只允许迁移 `_extract_fiscal_from_xbrl_query` 的 import、专用 fixture `_FiscalXbrlProcessor` 与当前 node `test_sec_fiscal_inference_rejects_invalid_xbrl_total`；该 node 改为 `test_sec_fiscal_inference_consumes_countless_xbrl_contract`，直接证明 fiscal consumer 接受无 count 的新 producer contract。
- S2 只允许迁移 `_normalize_xbrl_query_payload` 的 import 与当前 `test_xbrl_query_payload_missing_total_fails_closed`、`test_xbrl_query_payload_non_int_total_fails_closed`、`test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup`、`test_xbrl_query_payload_preserves_processor_total_after_dedup`、`test_xbrl_query_payload_always_projects_dedup_count_and_owner_quality`、`test_xbrl_query_payload_rejects_producer_dedup_count` 这组 read normalize/dedup nodes。
- 两个 slice 都不得修改该文件的 generic LRU、form matching nodes；共享 import 行只能作与上述各自 symbols 直接相关的机械调整。S1 Controller validation 与两路 review 必须按 symbol 而非整文件授权核对 diff。六个 normalize/dedup nodes 仍由 S2 完整迁移、运行和验收；S1 不运行它们，也不得对它们加 `skip` / `xfail`、兼容 fixture 或 production shim 伪造绿色。

### 5.2 实施顺序

1. Financial owner删除locator类型/字段和两个内部reason；reason改为optional并验证complete/partial组合。
2. XBRL owner删除count，建立flat typed query params；exact-key validation统一拒绝未知字段。
3. 迁移所有actual SEC/BS/6-K/HTML/OCR producer；method absent/None/empty只在producer terminal归一为`statement_not_found`。
4. 删除`build_statement_locator`及引用，不保留wrapper/re-export。
5. 删除`_build_financials_payload` alternate owner及只固化其发明reason的测试；不扩展到其它fiscal dead code。
6. 修复被触及文件已有scoped Ruff项：`bs_report_form_common.py`未使用`Path`、`sec_processor.py`未使用`pandas`。
7. 运行registry/继承传播审计，证明所有concrete paths落入同一common/terminal validator。

### 5.3 Owner tests与失败语义

测试必须直接断言：

- Financial exact keys、optional reason presence、七值闭集；
- complete+reason、partial无reason、未知reason、缺少任一essential field、未知字段均fail closed；
- SEC generic、BS 10-K/10-Q/20-F、BS 6-K、HTML、OCR/6-K actual producers都满足contract；
- method缺失、返回None、空表、空rows四类观测都得到`statement_not_found`；
- XBRL exact keys、flat query params、zero-hit、partial两reason、all-concepts-failed typed error；
- `fiscal_period` 只接受共享 `FiscalPeriod` / `FISCAL_PERIODS` 的 `FY|H1|Q1|Q2|Q3|Q4`，缺席时不产生 `None` 键；
- `min_value` / `max_value` 分别显式拒绝 `True` 与 `False`，接受合法 `int` / `float`，并允许字段缺席；
- Producer不输出任何count，validator前后raw payload/list/facts深度相等；
- Fiscal extraction只消费新validator，不存在alternate financial reason owner。

最小focused命令：

```bash
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_processor_registry.py -k 'financial or statement or xbrl or quality or reason or fiscal'
pytest tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract
```

### 5.4 验证门

```bash
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract tests/fins/test_processor_registry.py
python -m coverage erase
python -m coverage run -m pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract
python -m coverage report --include='dayu/fins/domain/financial_result_contract.py,dayu/fins/domain/xbrl_result_contract.py,dayu/fins/processors/financial_base.py,dayu/fins/processors/html_financial_statement_common.py,dayu/fins/processors/report_form_financial_statement_common.py,dayu/fins/processors/sec_report_form_common.py,dayu/fins/processors/bs_report_form_common.py,dayu/fins/processors/six_k_form_common.py,dayu/fins/processors/sec_processor.py,dayu/fins/processors/bs_six_k_processor.py,dayu/fins/processors/sec_xbrl_query.py,dayu/fins/pipelines/sec_fiscal_fields.py' --fail-under=80
pyright <S1全部实际修改的production与test Python文件>
pyright
python -m ruff check <S1全部实际修改的Python文件>
git diff --check
```

S1 正式 pytest 与 coverage 命令对共享 `tests/fins/test_fins_read_runtime.py` 只能使用上述单一 fiscal node id；不得把整个共享文件、`-k xbrl_query_payload` 或六个 S2 normalize/dedup node 纳入 S1 收集。Coverage门必须逐个实际修改production文件`>=80.00%`，不能用aggregate掩盖低文件。只列入allowlist但零diff的文件不新增coverage义务。S1 modified-owner scoped pyright/类型验证必须零；同时必须执行full pyright。

S1 implementation 结束后、两路 review 开始前，Controller validation artifact 必须锁定同一受保护 tree，并产出不可变证据：

1. 记录 base HEAD、`git status --short`、S1 changed-path manifest、每个 changed path 工作树内容的 SHA-256，以及完整 S1 `git diff --binary` 的 SHA-256；path content-hash manifest + cumulative diff hash 共同构成两路 reviewer 的唯一受保护 review tree 标识，无需 stage 或 commit。
2. 在该 tree 上运行 full `pyright`，保留完整诊断，并产出精确 propagation ledger：每行必须记录诊断文件、symbol、pyright rule/message、已删除 producer field/type、对应 S2 owner/action。
3. ledger 中诊断只允许落在预声明四个 S2 production paths：`dayu/fins/tools/result_types.py`、`dayu/fins/tools/read_runtime_helpers.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/fins_tools.py`。每条必须是已删 producer field/type 的直接传播；测试文件、S1 owner、其它 production path、无法精确对应 S2 action 的任何诊断均使 S1 失败。
4. 两路 reviewer 必须分别重算并核对同一 diff hash，逐条核对同一 full-pyright ledger，不得用“S2 会修”接受未登记诊断。锁定后任何文件变化都使 Controller validation 与两路 review 失效，必须在新 hash 上完整重跑。

S1 不用 compatibility field、cast、ignore、shim 或临时 adapter 伪造 full pyright green，也不增加 S1 commit。该红色 full-pyright ledger 只是固定 two-slice/no-compat 约束下的 internal review checkpoint，不是可接受 product state；S2 完成后 full pyright 必须 `0 errors`。

### 5.5 S1 scans

Internal raw-total positive inventory只扫owner roots，不做全仓`total`零命中：

```bash
rg -n -i 'raw[_ -]?total|provider[_ -]?total|reported[_ -]?total|["'"']total["'"']' \
  dayu/fins/domain/xbrl_result_contract.py \
  dayu/fins/processors/sec_processor.py \
  dayu/fins/processors/bs_report_form_common.py \
  dayu/fins/processors/bs_six_k_processor.py \
  dayu/fins/processors/sec_xbrl_query.py \
  dayu/fins/pipelines/sec_fiscal_fields.py
```

预期零保留项。任何match都必须有“internal typed owner、provider input、validation/diagnostic action、owner test、无public传播”五联证据，否则失败。

Financial/internal negative scan：

```bash
rg -n 'statement_locator|StatementLocator|build_statement_locator|statement_method_missing|statement_empty|processor_error:|invalid_statement_result' \
  dayu/fins/domain/financial_result_contract.py \
  dayu/fins/processors \
  dayu/fins/pipelines/sec_fiscal_fields.py \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py
```

预期零命中。测试不得通过拆字符串规避scan；另用exact-key/AST/运行时assertions证明删除。

### 5.6 S1 review与commit边界

顺序固定为：AgentCodex implementation/self-check → Controller validation锁定§5.4 tree/diff hash与full-pyright exact ledger → AgentMiMo与AgentDS对同一immutable S1 diff并发完整review且独立核对同一ledger → Controller adjudication → 必要fix → 两路re-review → Controller逐条关闭。任何fix都必须生成新hash并重跑validation/review；全部关闭前不得进入S2。

S1不做中间commit。S1与S2是同一次破坏性contract cutover；中间commit会把旧public consumer与新producer组合声明为可接受历史状态。S1仍是严格review boundary，必须有focused tests、逐文件coverage、scoped Ruff、scans、diff check和限定propagation evidence，不能用临时shim制造绿色。

## 6. R08-S2 — read/tool/LLM single projection

### 6.1 依赖与 exact allowlist

进入条件：S1 implementation validation通过，两路review/fix/re-review和Controller adjudication全部关闭；S1 cumulative tree未commit且未混入其它scope。

S2 production diff闭集：

```text
dayu/fins/tools/result_types.py
dayu/fins/tools/read_runtime_helpers.py
dayu/fins/tools/read_runtime.py
dayu/fins/tools/fins_tools.py
```

当前证据表明`dayu/fins/tools/error_contract.py`没有R08字段/reason owner，因此不在allowlist。`dayu/config/prompts/**`没有目标字段，不改，只纳入negative scan。即使`read_runtime.py`在allowlist，R07 snapshot acquire/borrow/release、cache/revision、citation与source-changed symbols也不允许修改。

S2 tests diff闭集：

```text
tests/fins/test_fins_read_runtime.py
tests/fins/test_read_runtime_semantic_ownership_guards.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_storage_provider.py
```

必跑零diff回归：

```text
tests/fins/test_financial_read_contracts.py
tests/fins/test_processor_registry.py
tests/fins/test_fins_ingestion_tools.py
```

README diff闭集：

```text
dayu/fins/README.md
tests/README.md
```

修改README前重新阅读各自`Agent更新约束`。`dayu/fins/README.md`只写current最小contract与consumer动作；`tests/README.md`只写current owner-level覆盖，不写gate、review、命令或未来计划。根README、`dayu/README.md`、`dayu/config/README.md`不触发。

### 6.2 实施顺序

1. `result_types.py`删除public locator、`total`、`deduped_fact_count`，建立第4.3节精确命名的 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 与small builders；删除旧 tools `FinancialStatementResult` / `XbrlQueryResult` 名称，直接更新 imports、return annotations 与 tests，不做compatibility alias。
2. 同一owner邻接建立description metadata/helper，包含§4.4七值 reason 的业务含义与安全下一动作；不新建第二schema registry。
3. `read_runtime_helpers.py`执行`validate → copy query params/raw facts → normalize → stable deduplicate → public builder`。任何路径都不写producer payload、facts list或raw fact mapping。
4. `read_runtime.py` financial路径只validate并调用financial builder；XBRL路径只提供R07 context和helper输入。删除手工query params重组、旧count映射与reason默认。
5. `fins_tools.py`让两项tool descriptions消费owner helper；输入parameters仍只拥有调用参数。`fiscal_period.enum` 从 `FISCAL_PERIODS` 同源派生 `FY|H1|Q1|Q2|Q3|Q4`，`min_value` / `max_value` 保持 `type: number`；callable/schema tests 证明该 enum、字段缺席不补 `None` 与 bool 拒绝均成立。
6. 保留R07 borrowed snapshot/citation flow原样，通过guard tests证明同一snapshot context进入projection。
7. 按触发规则更新两份README。

### 6.3 Input/output mapping与失败语义

| 输入 | Public输出 | 禁止行为 |
|---|---|---|
| validated financial result | 逐字段复制 + R07 context | read按空rows猜reason；补currency/units/scale；保留locator |
| validated XBRL query params | 独立typed copy | 从调用参数重拼；缺失filter补`None`；兼容旧`filters_applied` |
| validated raw facts | 独立normalize/dedup list | 原地修改；把dedup结果写回producer payload；保留raw count |
| final returned facts | `facts` + 同helper `fact_count=len(facts)` | read/serializer第二处重算；输出total/dedupe diagnostic |
| optional producer reason | 存在才机械复制 | `get(..., default)`；解析错误消息；根据quality猜reason |
| R07 snapshot context | ticker/document/citation | 从ID、路径、meta前缀或新revision读取推断 |

Producer terminal validator失败继续走既有typed read failure mapping；S2不发明business reason/error code。合法zero-hit XBRL是completed result：`facts=[]`、`fact_count=0`、`data_quality=xbrl`、reason缺席。

### 6.4 截断组合风险与验证裁决

当前`query_xbrl_facts`声明Host `ToolTruncateSpec`，generic Host在超限时会把顶层`facts`替换为cursor envelope，而不会原子改写sibling `fact_count`。这是真实组合风险，不能靠普通under-limit smoke掩盖。

R08的直接owner边界是Fins typed public projection：进入Host前必须恒有`fact_count == len(facts)`。S2还必须新增两类组合验证：

1. Under-limit真实provider/ToolRuntime路径：LLM-facing completed value仍是typed result，等式成立。
2. Forced-truncation路径：明确断言Host envelope是独立治理层，不得被Fins serializer解释为第二份financial/XBRL contract；检查Fins raw/public projection在交给Host前仍满足等式，cursor/fetch_more仍由Host owner持有。

Forced-truncation 的 current-tree 可执行机制固定在 `tests/fins/test_fins_storage_provider.py`，不得新增 Host 测试或 mock：

1. 将现有 helper 窄扩为 `_tool_runtime(workspace_root: Path, *, extra_config: Mapping[str, JsonValue] | None = None, enable_truncation_manager: bool = False) -> tuple[ToolRuntimeHandle, _AcceptingPort]`，并把 `extra_config` 原样交给现有 `_spec(...)`；两个默认值保持现有 under-limit/cancellation tests 的行为。只有显式启用时，才使用公开 `FrameworkToolPolicyView` 启用 `FrameworkToolName.FETCH_MORE`，并将同一 bool 传给 `EffectiveToolBundleBuildRequest.enable_truncation_manager`。仍由现有 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())`、真实 provider definitions、process-backed capsule 与 `_AcceptingPort` 构造 runtime，不另建 fake executor。
2. 新增 exact node `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation`。它复用 `_build_fins_aapl_xbrl_workspace` 与真实 fixture，使用命名常量 `_FORCED_XBRL_MAX_ITEMS = 1`，通过 `_spec(..., extra_config={"limits": {"query_xbrl_facts_max_items": _FORCED_XBRL_MAX_ITEMS}})` 产生同一 provider 配置；测试不得硬编码当前 fixture 恰有三条 facts，只断言 pre-Host `len(facts) > _FORCED_XBRL_MAX_ITEMS`。
3. 先直接调用同一真实 provider 输出中的 `query_xbrl_facts` `ToolDefinition.callable`，捕获交给 Host 前的 completed Fins public value；先以 `"fact_count" in pre_value` 证明目标字段实际存在，再用直接索引断言 exact public contract、独立 `facts` list 与 `pre_value["fact_count"] == len(pre_value["facts"])`，并保存整个 value 与 facts 值副本。不得用 `pre_value.get("fact_count")`，避免把字段缺失与合法值混成同一个 `None`。该观测点是公开 business callable seam，不 patch callable、不绕过 processor/read/projection。
4. 再用相同 workspace、provider config 和调用参数经过启用 manager 的真实 `_tool_runtime(...)`。断言 provider business bundle 不定义 `fetch_more`，而 `runtime.effective_bundle.injected_framework_tool_names` 包含 `FrameworkToolName.FETCH_MORE`；Host completed value 必须满足 `set(post_value) == set(pre_value)`，除 `facts` 外每个顶层 public sibling 都与 pre-Host value 逐项相等，并用直接索引断言 `post_value["fact_count"] == pre_value["fact_count"]`。只有顶层 `facts` 按当前 LLM-facing ToolRuntime cursor contract 从 list 替换为含 visible value 与 `cursor` / `scope_token` 引用标签的 envelope。不得用 `.get("fact_count")`，不得把这个 post-Host envelope 再传给 Fins validator/builder，也不得要求 `fact_count == len(envelope)`。
5. 只从上述公开 envelope 读取 cursor 与 scope token，经同一个 `runtime.tool_executor` 调用 `FrameworkToolName.FETCH_MORE.value`，断言 visible prefix 与 fetch-more remainder 顺序拼接后逐项等于保存的 pre-Host facts。不得读取 `TruncationManager._cursors`、`FetchMoreToolCallable._manager`、私有 `_truncated_public_value`/字段常量、digest、raw accept payload 或其它 Host 内部状态。

当前只读可行性探测发生在 R08 实施前的旧 public contract：pre-Host 顶层 keys 与 post-Host 顶层 keys 完全相同，均为 `citation|data_quality|deduped_fact_count|document_id|facts|query_params|reason|ticker|total`；pre-Host `facts` 是三项 list，post-Host 只有该字段成为 `visible 1 + cursor/scope_token` envelope，`deduped_fact_count=3` 与 `total=15` 两个 sibling 均原样保留，公开 `fetch_more` 返回其余两项。`fact_count` 在 pre/post 两边都尚不存在，因此此前 `.get("fact_count") -> None` 只证明取值路径错误，不能解释成 Host 删除或包裹 sibling。该 shape 证明当前 Host public contract 只替换目标字段并保留全部顶层 siblings；正式测试必须在 S2 产生 `fact_count` 后通过字段存在性、直接索引、完整 key-set/非 facts sibling 等式来重新证明，不冻结 fixture 数量。若实施时 post-Host key set 改变、`fact_count` 缺失/变值，或任一公开 seam 无法同时观测 pre-Host typed value、Host completed envelope 与公开 fetch-more 结果，即与本 owner 裁决冲突，立即 stop 回 Controller；不得改用 monkeypatch/mock、私有属性、Host 修改、Issue 177 或 R09 truncation routing 补救。

本R08不修改Host、不私造cursor/fetch_more、不静默丢弃超限facts、不把configured limit搬到read做截断。如果Controller裁决“`fact_count=len(returned facts)`必须对Host截断后的每一页可见list成立”，当前generic Host API无法原子维护该sibling字段，S2必须stop并回Controller；不得越界改Host或用fallback伪装通过。该stop只处理已识别的owner冲突，不重开financial/XBRL产品contract。

### 6.5 S2 tests与真实 smoke

Owner/public tests必须覆盖：

- Financial public exact keys、optional reason presence、producer→public逐项相等、无locator/默认值；
- 两个 public type 只以 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 暴露，直接 imports 与 return annotations 均使用新名；旧 tools 类型名定义、alias、re-export、wrapper均不存在，domain producer 类型名保持不变；
- 两个 builder 接受 `Mapping[str, JsonValue]` citation 并输出不 alias 输入的独立 `dict[str, JsonValue]`；内容逐项等于同一 borrowed snapshot citation，不含 revision、private key、path，pyright 证明新 signatures 无 `Any`；
- Flat query params精确复制，缺失filter不出现`None`键；
- `fiscal_period` callable/schema 共享同一 `FiscalPeriod` / `FISCAL_PERIODS` 值集，schema enum 为 `FY|H1|Q1|Q2|Q3|Q4`；`min_value` / `max_value` schema 保持 `number`，callable/schema 路径拒绝 boolean 而接受 number；
- Normalize/dedup前后producer payload、facts list、每个raw fact深度相等；
- 两个raw facts归一到同一key时只返回一个fact且count为1；zero-hit count为0；
- Public只有`fact_count`，等于final facts长度；AST/source test证明只有builder一个production赋值owner；
- Tool description含字段、类型、必填性、全部枚举、optional reason规则和一个最小示例；financial tool description 额外包含七值 reason 的业务含义/安全下一动作。示例消费同源 metadata/helper，使用 `SEC_EDGAR`且不存在 `sec_filing`，不含 processor method/fallback branch 等内部术语；
- Tool serializer返回typed exact keys，不另写count；
- R07同snapshot citation/processor/result consistency仍成立；
- Process-backed completed/failed/cancelled paths不泄露revision、private key、路径或内部reason；
- 第6.4节under-limit与forced-truncation组合风险均被显式验证；forced node 必须完成 pre-Host 等式、Host public cursor envelope、Host-injected `fetch_more` remainder 三段公开链路，不断言私有 envelope/helper/manager 状态。

`tests/fins/test_fins_read_runtime.py` 的六个 normalize/dedup nodes 在 S2 必须全部迁移并由 S2 focused、coverage 与完整验证收集；不得 `skip` / `xfail`、删 node、改名逃避收集或用 compatibility fixture/production shim 保留旧 count contract。

必须复用`tests/fins/test_fins_storage_provider.py`现有真实仓储构造，不以简化fake替代：

1. 真实AAPL XBRL fixture：fixture→workspace→processor→read→tool business value；断言raw输入不变、facts已dedup、唯一count同源、citation来自同一snapshot。
2. 真实HTML财务表fixture：HTML source→processor抽取→financial read tool；断言最小字段、无locator、period/scale/quality不由read补造、citation可读。
3. No-statement路径：真实producer terminal形成partial + `statement_not_found`，read只复制reason。

Focused命令：

```bash
source .venv/bin/activate
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_tools.py
pytest tests/fins/test_fins_read_runtime.py -k 'xbrl_query_payload and not sec_fiscal_inference'
pytest tests/fins/test_fins_storage_provider.py::test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation
```

真实smoke evidence必须记录现有fixture路径、exact node id与结果。

### 6.6 S2验证门

```bash
source .venv/bin/activate
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_storage_provider.py
python -m coverage report --include='dayu/fins/tools/result_types.py,dayu/fins/tools/read_runtime_helpers.py,dayu/fins/tools/read_runtime.py,dayu/fins/tools/fins_tools.py' --fail-under=80
pyright
python -m ruff check <S1+S2全部实际修改的Python文件>
git diff --check
```

每个实际修改production文件line coverage必须单独`>=80.00%`，不能以四文件aggregate替代。Full pyright必须`0 errors`；全部实际修改Python文件scoped Ruff必须零。

### 6.7 双向 scans与唯一同源证明

#### A. Internal positive inventory

```bash
rg -n -i 'raw[_ -]?total|provider[_ -]?total|reported[_ -]?total|["'"']total["'"']' \
  dayu/fins/domain/xbrl_result_contract.py \
  dayu/fins/processors/sec_processor.py \
  dayu/fins/processors/bs_report_form_common.py \
  dayu/fins/processors/bs_six_k_processor.py \
  dayu/fins/processors/sec_xbrl_query.py \
  dayu/fins/pipelines/sec_fiscal_fields.py
```

预期零保留项。非零match必须逐条证明internal typed owner、provider input、validation/diagnostic use、owner test、no public propagation；缺一即失败。

#### B. Public/tool/schema/serializer/LLM negative scan

```bash
rg -n -i \
  'raw[_ -]?total|deduped_fact_count|deduped[_ -]?count|去重前.{0,12}total|原始.{0,12}fact.{0,12}数|statement_locator|StatementLocator|statement_method_missing|statement_empty|processor_error:|invalid_statement_result|sec_filing' \
  dayu/fins/tools \
  dayu/config/prompts \
  dayu/fins/README.md \
  tests/README.md \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_storage_provider.py
```

预期零命中。内部contract负向测试不要把禁止literal放进public扫描roots；用exact-key set/AST assertions表达。

#### C. `fact_count`唯一owner scan

```bash
rg -n 'fact_count' \
  dayu/fins/tools/result_types.py \
  dayu/fins/tools/read_runtime_helpers.py \
  dayu/fins/tools/read_runtime.py \
  dayu/fins/tools/fins_tools.py \
  dayu/config/prompts \
  dayu/fins/README.md \
  tests/README.md
```

每个match只能归类为：typed public field、唯一builder的`len(returned_facts_copy)`赋值、owner-generated description/example、current README或test assertion。Read runtime、serializer、tool callable不得出现第二个赋值/重算。运行时必须断言`result["fact_count"] == len(result["facts"])`；AST test证明单一production赋值owner。

#### D. R07 no-touch propagation scan

以`git diff -U0`核验`read_runtime.py`只改financial/XBRL projection symbols；snapshot acquire/borrow/release、cache revision、citation generation、source-changed paths零diff。运行既有processor/result/citation同snapshot tests。

### 6.8 README同步

- `dayu/fins/README.md`删除mandatory locator、producer total、dedup count说明，写入最小producer contract、optional actionable reason、独立public dedup projection和唯一fact_count。
- `tests/README.md`更新为producer exact contract、raw immutability、unique public count、真实AAPL/HTML smoke和R07 citation一致性。
- 不写R08/slice/review/未来计划，只陈述current事实。

### 6.9 S2 review与commit边界

顺序固定：AgentCodex implementation/self-check → Controller validation → AgentMiMo与AgentDS对同一immutable S1+S2 cumulative diff并发review → Controller adjudication → 必要fix → 两路re-review → Controller关闭全部finding。

S2不单独commit。只有S1/S2闭环、aggregate validation与aggregate双路deepreview都通过后，Controller才可授权一个exact-scope local implementation commit。该commit只完成R08，不完成umbrella。

## 7. Aggregate validation、review与后续

Aggregate矩阵：

```bash
source .venv/bin/activate
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
pyright
python -m ruff check <R08全部实际修改的Python文件>
git diff --check
```

同时执行三个真实smoke exact nodes、全部双向scans、R07 no-touch scan和逐文件coverage检查。

已审计baseline仅用于增量判定：focused contract/read/ownership/consistency matrix为`111 passed`；真实AAPL/HTML/description/failed-outcome/fiscal exact nodes为`5 passed`；full pyright为零；full Ruff有150个继承问题。R08不承担全仓Ruff，但所有实际修改文件scoped Ruff必须归零；S1必改producer中已有两个F401随本切片清除。不得新增warning类别或pyright错误。

Aggregate deepreview必须检查：owner唯一性、reason动作性、count单一同源、raw immutability、query params单一shape、tool/serializer drift、R07 no-touch、compat/shim、allowlist/README/tests越界。所有finding完成fix/re-review和Controller adjudication后才可进入accepted local implementation commit。

R08 completion后umbrella仍active；依次继续R09、R10、R11、R12，之后还需umbrella aggregate validation/deepreview/final closeout。

## 8. Stop conditions与禁止补救

| 观测 | 正确处置 | 禁止补救 |
|---|---|---|
| Producer不能提供required essential field | 停在producer owner澄清 | read默认/猜值/空字符串 |
| Method absent/empty分散 | actual producer terminal统一`statement_not_found` | read看rows推断；保留旧reason alias |
| Provider确有raw total | internal typed validation/diagnostic inventory+tests | 暴露public/LLM；改名逃scan |
| S1 type change触发S2旧consumer错误 | 精确登记S2 propagation，S2后full pyright归零 | compat field、cast、ignore、shim |
| Dedup需要修改fact | 深复制后修改public fact | 原地覆盖raw fact/list |
| Description需要字段清单 | 消费result_types owner helper | 手写第二份contract |
| Host截断产生cursor envelope | 按第6.4节验证或stop回Controller | Fins私造fetch_more、静默drop、越界改Host |
| 旧测试期待locator/count/internal reason | 迁移fixture/assertion | 生产兼容分支保旧测试 |
| 发现R09-R12/deferred issue | 记录out-of-scope并停止扩张 | 顺手实现 |

## 9. Code-generation handoff checklist

### S1

- [ ] Base/R07 lineage与worktree核验；
- [ ] S1 allowlist、contracts、all actual producers完成；
- [ ] `test_fins_read_runtime.py` 只修改并在正式 pytest/coverage 中运行 S1 fiscal node，六个 S2 read normalize/dedup nodes未提前迁移、运行、skip/xfail或shim；
- [ ] Locator helper与alternate reason owner删除；
- [ ] 共享 fiscal-period owner、bool 显式拒绝与 focused owner tests完成；
- [ ] Focused tests、逐文件coverage、scoped Ruff、scans、diff check完成；
- [ ] Controller 锁定 immutable tree/diff hash，full-pyright exact ledger 只含四个预声明 S2 production paths，两路 reviewer 独立核对通过；
- [ ] Internal positive inventory逐条闭合；
- [ ] 双路review/fix/re-review与Controller adjudication关闭；
- [ ] 未开始S2、未commit。

### S2 / aggregate

- [ ] S1 gate已关闭；
- [ ] Single typed public projection/helper完成；
- [ ] Public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`，旧 tools 名称无 alias/re-export/wrapper；
- [ ] Citation 使用 `Mapping[str, JsonValue]` 输入和独立 `dict[str, JsonValue]` 输出，同 borrowed snapshot 内容一致且 R07 no-touch；
- [ ] Raw facts不变、public facts独立dedup、唯一count同源；
- [ ] Tool description/serializer自同一owner派生且自足，七值 reason 均有 LLM-safe 下一动作，示例使用 `SEC_EDGAR`；
- [ ] `fiscal_period` schema 与 producer 共享 `FY|H1|Q1|Q2|Q3|Q4` owner，number schema/callable 的 bool 拒绝已验证；
- [ ] 真实 provider 的 pre-Host typed 等式、Host public cursor envelope 与 Host-injected `fetch_more` remainder 组合验证通过；若 public seam 不可观测则 stop 回 Controller；
- [ ] R07 snapshot/citation symbols零语义变更；
- [ ] AAPL、HTML、no-statement真实smoke通过；
- [ ] 两份README按自身约束更新；
- [ ] Full pyright零、修改文件Ruff零、逐文件coverage>=80%；
- [ ] Positive/negative/unique-count/no-touch scans通过；
- [ ] S2双路review与aggregate双路deepreview关闭；
- [ ] 未stage/commit，等待Controller另行授权。

## 10. 本 fixed-plan re-review fix gate 自检要求

本gate唯一允许新增/修改artifact：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md
```

交付前必须以`git status --short --untracked-files=all`核对本次只增加上述两个 allowed-path delta，不覆盖或误认用户既有 worktree 状态；由于两个 artifact 可处于 untracked 状态，分别使用 `git diff --no-index --check /dev/null <path>` 做 whitespace/diff check。以 Controller 锁定的 plan SHA-256 `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` 为 before hash，计算 final plan SHA-256，只在 re-review fix artifact/handoff 中报告，不自嵌入 plan；artifact 逐项记录 `R08-RR-PF-01..02` 的 before/after plan 位置、Controller 三项 rejected/no-fix 路径缺席证据、final hash/status/no-index diff check 与 scope。确认本计划没有 optional-reason 私有 helper 指令、reason frozenset 额外 checklist、R09 truncation routing、Host/Issue 177 实施或其它 accepted finding 扩张后，停止在 Controller validation；不得进入 implementation。
