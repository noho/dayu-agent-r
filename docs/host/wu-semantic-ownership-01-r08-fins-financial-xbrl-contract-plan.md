# WU-SEMANTIC-OWNERSHIP-01 / R08 Financial/XBRL 最小契约实施计划

## 0. Gate 与结论

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| sub-WU | 既有 remediation `R08`；不是新 WU、feature 或 issue |
| gate | 同一 R08 candidate-exhaustion plan-only correction；完成后停回 Controller，由 Controller 派发两路完整 corrected-plan review |
| accepted plan lineage / 当前 correction 前 plan SHA-256 | `0dc85654bb29612a547e7976f3eeb4801171f786` / `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| R07 completion commit | `28b6fc1956bd3832489a471fa29bfe354b319860` |
| 固定 slices | S1 producer domain contracts + all actual processors；S2 read/tool/LLM single projection |
| 受保护 stopped implementation/test/README tree | 23-path `dayu/fins + tests` tracked binary diff SHA-256 固定为 `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`；guards SHA-256 固定为 `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`；shared test SHA-256 固定为 `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`；staged 为空 |
| accepted finding | `R08-CR-PCF02`：删除零 caller 的重复 private document-type collector，保留 actual typed/sorted owner 与全部五个已授权测试 |
| 本 gate 授权 | 只修改本计划并新增 `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-correction-codex.md`；不修改当前 production/tests/README、S1/S2/fix artifact、control/design/prior review artifacts，不运行 implementation，不 stage、不 commit、不 push、不建 PR |

R08 只落实 umbrella remediation plan §15 已裁决的 Topic 6.4：收窄 financial/XBRL 的 LLM-facing contract，并建立单一 public typed projection。R06 transaction/publication owner 与 R07 identity/revision/snapshot/citation/provenance owner 已完成，本计划只消费它们，不回改。

## 1. 第一性原理判断

问题真实存在，且不是命名或文案问题：

1. Financial producer 将财务事实与 `statement_locator`、`statement_method_missing`、`statement_empty` 等处理器诊断混在同一 contract，read 又原样公开，使内部调用路径变成 LLM 业务事实。
2. XBRL producer 用 `len(facts)`生成 `total`，read 再公开 `deduped_fact_count`。模型实际消费的是已去重 facts，双计数没有独立业务动作，却形成两个 owner。
3. Producer 当前将可选 XBRL filters 放在 `query_params.filters_applied`，read 却从 `query_params` 顶层读取同名键并补 `None`，已经形成直接可证的 shape drift。
4. Tool description 手写第三份字段定义，公开 raw total / dedupe diagnostic，且没有自足说明必填性、完整枚举和最小示例。
5. `dayu/fins/pipelines/sec_fiscal_fields.py::_build_financials_payload` 没有 production caller，却作为替代 owner 发明 `processor_error:<message>` 与 `invalid_statement_result` reason；它不能以“兼容”名义保留。
6. `R08-CR-CF01` 删除四个越界 omnibus/compatibility 节点及九个专用 imports 后，累计 coverage 实测为 `386 passed`，15 个 changed production 文件中 14 个过线，`read_runtime_helpers.py` 只有 `320/494 = 64.78%`；R08 normalize/dedup changed-owner 完整调用闭包即使全部覆盖也至多 `351/494 = 71.05%`。因此当前 whole-file 80% gate 与稳定 owner 测试授权数学上冲突，必须修计划的测试授权，而不是恢复越界节点、弱化阈值或改 production 迎合 coverage。
7. 五个已授权 stable-owner tests 全部实现后的 stopped-tree 实测为 `388/494 = 78.54%`。直接 source/AST evidence 证明 `read_runtime_helpers.py::_collect_available_document_types` 独占 12 个全未覆盖 executable statements，只有一个 definition、零 caller、零 import；actual public suggestion path 则由 `read_runtime.py::_collect_available_document_types_for_source_documents` typed owner 调用 `resolve_document_type_for_source` 并 `return sorted(doc_types)`。保留前者会留下第二个不可达 producer 并虚增 coverage 分母；`R08-CR-PCF02` 因而必须在 owner boundary 删除该 dead duplicate，而不是直测 private helper或增加第六个 coverage node。

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
- `test_fins_read_runtime.py` 保持 §5.1 固定 symbol boundary；四个已删除越界节点与九个专用 imports 永久不恢复。`test_read_runtime_semantic_ownership_guards.py` 中 §6.1 的五个 stable-owner tests 全部保留且不可修改；删除 dead duplicate 后，以 fresh candidate-4 exclusion proof 与 fresh all-five proof 证明第五项仍是 whole-file exact-key `>=80.00%` 的 first/shortest threshold-crossing prefix，不增加第六项测试。
- S1→S2 保持 producer→consumer 的实现依赖顺序，但两步属于同一累计 destructive cutover；S1 不再是独立 validation/review gate，只有累计 S1+S2 tree 全绿后才进入一次 immutable dual code review、fix/re-review 与 aggregate deepreview。R08 后仍需 R09-R12 与 umbrella aggregate deepreview。

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
| list-documents 可用文档类型 suggestion | `dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents` | 保留 typed `_SourceDocumentSummary` 输入、`resolve_document_type_for_source` 调用与 sorted 输出；删除 `read_runtime_helpers.py` 中零 caller 的重复 private collector |

### 2.3 明确 out-of-scope

- R09 direct-stream validator；R10 HKEX；R11 upload/placeholders；R12 init/reset；
- Issues 142、151、175、177、178；统一 authorization；
- Host generic truncation/cursor/fetch_more、Engine、Service、UI；
- R07 identity/snapshot/revision/citation/provenance owner；
- financial/XBRL 之外的 error codes、ingestion、download/upload、storage contract；
- compatibility re-export/wrapper、fallback、shim、双写字段、loose parsing、`getattr/hasattr` 补偿、默认 reason、历史 payload 分支；
- 除 `R08-CR-PCF02` 唯一授权的 `_collect_available_document_types` 删除外的任何 dead-code 清理、全仓 Ruff 清理或 README 扩写；不得触碰 S1/S2 artifacts。

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
| `dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types` | 与实际 list-documents owner 重复，当前只有定义、零 caller、零 import，12 个 executable statements 全未覆盖 | `R08-CR-PCF02` 唯一生产改动：删除完整 definition；禁止直测、wrapper、re-export或迁移该 helper |
| `dayu/fins/tools/read_runtime.py` | 手工拼结果与query params；同时拥有实际 typed/sorted `_collect_available_document_types_for_source_documents` | S2机械消费projection；不补默认/猜reason；candidate-exhaustion fix 不改该文件及实际 owner |
| `dayu/fins/tools/fins_tools.py` | 手写LLM字段contract | S2消费owner metadata/helper |
| `dayu/fins/pipelines/sec_fiscal_fields.py::_build_financials_payload` | 无production caller，发明alternate reasons | S1删除该owner及只固化它的测试 |
| `dayu/fins/pipelines/sec_fiscal_fields.py::_extract_fiscal_from_xbrl_query` | 消费旧total validator | S1只传播新validator，不新建owner |
| `dayu/config/prompts/**` | 当前没有目标字段 | 不改；纳入public/LLM negative scan |

测试迁移 inventory：

- `tests/fins/test_financial_read_contracts.py`：S1 owner contract、SEC/BS/6-K/HTML/OCR actual producers。
- `tests/fins/test_sec_pipeline_download.py`：S1删除alternate reasons与invalid-total旧断言，保留真实fiscal语义。
- `tests/fins/test_fins_read_runtime.py`：S1 只迁移 `_extract_fiscal_from_xbrl_query` 直接消费的 XBRL producer-contract fixture/node；S2 再迁移同文件的 read normalize/dedup/query params/唯一 count nodes，具体 symbol 边界见§5.1。
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`：S2 exact projection与R07 citation/snapshot guards；`R08-CR-PCF01` 已在此形成 §6.1 五项完整 stable-owner 前缀，candidate-exhaustion continuation 保持内容锁且不再产生 test delta。
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
- 两个 implementation step 都不得修改该文件的 generic LRU、form matching nodes；共享 import 行只能作与上述各自 symbols 直接相关的机械调整。六个 normalize/dedup nodes 仍由 S2 完整迁移，并与 S1 fiscal node 一起在累计 S1+S2 tree 上运行和验收；不得对任一 node 加 `skip` / `xfail`、兼容 fixture 或 production shim 伪造绿色。

`R08-CR-CF01` 已从该共享文件删除下列四个越界节点，后续不得恢复、改名、参数化或搬运其结构：

```text
test_read_helper_document_discovery_rules_preserve_public_semantics
test_search_next_section_owner_ranks_exact_hits_per_query
test_table_data_projection_owner_emits_self_describing_shapes
test_navigation_and_xbrl_default_rule_owners_fail_closed
```

下列九个只服务这些节点的 imports 同样不得恢复到该文件，也不得以 alias 或局部 import 规避边界：

```text
_build_table_data_payload
_normalize_document_types
_normalize_periods
_normalize_section_children
_normalize_taxonomy_name
_resolve_default_xbrl_concepts
build_search_next_section_fields
resolve_document_type_for_source
resolve_has_financial_data
```

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

S1 owner tests 仍须随 producer owner 实现，但不在 producer/旧 public consumer 共存的中间 tree 上形成正式 collection、coverage 或 acceptance 命令。`test_sec_fiscal_inference_consumes_countless_xbrl_contract` 与全部 S1 owner tests 在 S2 恢复 public import graph 后，按 §6.6 的累计命令统一收集。

### 5.4 S1 中间 tree 定位：实现证据，不是 validation/review gate

S1 implementation artifact `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` 保留为 blocked intermediate evidence。它记录 producer/processor 实现、focused owner matrix、modified-owner pyright、scoped Ruff、source scans、diff check，以及下列 plan-drift root-cause；它不代表可接受 product state：

- 任何 `dayu.fins.tools` 子模块 collection 都会经旧 S2 consumer import graph 读取已删除的 `StatementLocator`，因此 S1 exact fiscal node 不能在测试执行前被收集；
- 两份当前可收集 owner tests 与已发现相关测试并集仍使七个实际修改 processor 文件只有 `41%–67%` whole-file coverage；
- full pyright 的五条诊断全部是新 producer contract 向尚未迁移 S2 consumer 的直接传播，但红色 ledger 只保留为 drift/root-cause 证据，不再构成 formal pass。

因此 S1 完成实现后直接在同一未提交 tree 上进入 S2，且必须满足：

1. S1/S2 实现顺序不变；S2 只按 §6.1 既有 production/test/README allowlist 迁移 public consumer，不提前或反向修改 producer owner；
2. 不为 S1 中间 tree 运行或要求独立 exact-node collection、whole-file coverage session、full-pyright propagation-ledger pass、Controller immutable-tree lock、双路 code review、fix/re-review；
3. 不新增 compatibility field/type、lazy import、cast、ignore、test shim、skip/xfail、默认值或临时 adapter；
4. S1/S2 之间不 stage、不 commit；当前 S1 artifact 保持 blocked intermediate evidence；
5. focused tests、real smokes、全部 scans、full pyright、scoped Ruff、逐文件 coverage、immutable tree lock 与双路 review 全部移动到 §6.6/§6.9 的累计 S1+S2 tree。

### 5.5 Producer-owner scans（在累计 tree 上执行）

以下 scans 保持原样，但不构成 S1 独立 gate；S2 完成后与 §6.7 的 public/LLM/AST/no-touch scans 在同一累计 tree 上统一执行。

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

### 5.6 S1→S2 累计 cutover 与 commit 边界

顺序固定为：AgentCodex S1 implementation/self-check（blocked intermediate evidence）→ AgentCodex 直接在同一 tree 上实施 S2 → §6.6 累计完整验证。S1 不是独立 acceptance、validation 或 review boundary；不得在 S1/S2 之间插入 Controller lock、MiMo/DS review、fix/re-review、stage 或 commit。

S1与S2是同一次破坏性contract cutover；中间commit会把旧public consumer与新producer组合声明为可接受历史状态。只有累计 S1+S2 tree 按 §6.6 全绿、按 §6.9 完成 immutable dual code review/fix/re-review、再完成 aggregate deepreview 后，Controller才可授权一个exact-scope accepted local implementation commit。

## 6. R08-S2 — read/tool/LLM single projection

### 6.1 依赖与 exact allowlist

进入条件：S1 producer/processor implementation 与 blocked intermediate artifact 已完成；当前 11 个 production、3 个 tests 的受保护 binary diff SHA-256 仍为 `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`；tree 未 stage/commit 且未混入其它scope。S1 独立 validation/review 不再是 S2 前置条件。

Candidate-exhaustion implementation 的 re-entry lock 取代上述历史 S2 entry hash：23-path
`dayu/fins + tests` stopped tracked binary diff 必须为
`65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`，
`test_fins_read_runtime.py` 内容 SHA-256 必须为
`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，
`test_read_runtime_semantic_ownership_guards.py` 内容 SHA-256 必须为
`553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`，且 staged 为空。
任一不匹配先停回 Controller；不得在未知 drift 上删除 production 或修改测试。

S2 production diff闭集：

```text
dayu/fins/tools/result_types.py
dayu/fins/tools/read_runtime_helpers.py
dayu/fins/tools/read_runtime.py
dayu/fins/tools/fins_tools.py
```

上述是累计 S2 历史闭集，不扩张本次 delta。`R08-CR-PCF02` implementation 的**唯一生产改动授权**精确为：

```text
删除 dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types 的完整 definition
```

不得修改 `resolve_document_type_for_source`，不得修改
`dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents`，也不得修改
任何其它 production symbol。禁止把旧 helper 改名、搬运、包裹、re-export、保留兼容 alias，或在
caller/adapter/test 侧补偿。删除后 actual typed/sorted owner 必须仍以
`list[_SourceDocumentSummary] -> list[str]` 直接参数接口调用 `resolve_document_type_for_source` 并
`return sorted(doc_types)`。

当前证据表明`dayu/fins/tools/error_contract.py`没有R08字段/reason owner，因此不在allowlist。`dayu/config/prompts/**`没有目标字段，不改，只纳入negative scan。即使`read_runtime.py`在allowlist，R07 snapshot acquire/borrow/release、cache/revision、citation与source-changed symbols也不允许修改。

S2 tests diff闭集：

```text
tests/fins/test_fins_read_runtime.py
tests/fins/test_read_runtime_semantic_ownership_guards.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_storage_provider.py
```

上述同样是累计历史闭集。本次 implementation 不允许任何 test delta：五个 §6.1 exact nodes
已经形成完整授权前缀，必须全部保留；shared test 与 guards 分别保持上述 `01db...6692`、
`5531...928d` 内容锁。禁止 compatibility test、private-helper direct test、fake-only test、
omnibus 搬运、skip/xfail、coverage pragma/omit 或其它 coverage bypass。

`R08-CR-PCF01` 没有增加 test path；它曾只对上述闭集内既有
`tests/fins/test_read_runtime_semantic_ownership_guards.py` 授权下表候选 owner-family。
Stopped tree 已按表中顺序实现全部五个 exact nodes，旧逐步 ledger 证明前四项当时未过线、第五项
完成后仍因 dead duplicate 分母而停止。本次不再实现、删除或修改任何 node；下表作为五项既有
contract 与 seam 的 immutable inventory，最终 first/shortest 结论只由 §6.6 的两个 fresh proof 建立。

| 顺序 / stable owner family | 建议 exact test node | 必须使用的 production seam | 业务输入、输出与 failure signal |
|---|---|---|---|
| 1. document-type/filter public projection | `test_list_documents_projects_stable_document_type_and_filter_contract` | `FinsReadRuntime.list_documents` public seam | 用真实 filesystem repositories 创建 filing/material source facts，传入去空、去重且含一个未知值的 `document_types` 与合法 `fiscal_periods`；按 `document_id` 键控断言 canonical `document_type`、normalized `filters`、filtered documents 与无匹配时的 `broaden_filter` suggestion。不得依赖 repository 返回顺序，不得输入或断言任何 compatibility availability/capability 字段；参数类型/空 ticker 等既有 public failure 必须继续抛 typed `FinsReadArgumentError`/business error，不得被新 fixture 吞掉。 |
| 2. section public payload projection | `test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref` | `FinsReadRuntime.read_section` public seam | 通过真实 repository + typed `DocumentProcessor` protocol fixture 提供含合法/非法 children、page range、content/title 的 section；断言 public `children` 只含有效 `ref/title`、page range 与 citation/identity 来自 runtime。对于未知 `ref` 输入，typed fixture 的 `read_section` 必须抛 `KeyError`，再由 `FinsReadRuntime.read_section` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。不得断言 processor 私有状态、父标题调用次数或其它偶然顺序。 |
| 3. table public payload projection | `test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref` | `FinsReadRuntime.get_table` public seam | 通过同类 repository-backed typed processor inputs 分别给出 records、合法 Markdown 与普通文本；断言 public `data.kind` 及各 shape exact keys/values、table identity/citation。对于未知 `table_ref` 输入，typed fixture 的 `read_table` 必须抛 `KeyError`，再由 `FinsReadRuntime.get_table` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。typed fixture 只提供协议输入，不得成为被断言对象；不得读 processor private method/state。 |
| 4. XBRL taxonomy/default-concept selection | `test_query_xbrl_facts_selects_default_concepts_from_typed_taxonomy` | `FinsReadRuntime.query_xbrl_facts` public seam | concepts 缺席时，用 typed taxonomy-capable processor 与明确 form/taxonomy business facts，断言 processor 收到 owner-selected、非空且与该 form/taxonomy 对应的 concepts，public result 的 `query_params.concepts` 与之同源；unknown taxonomy 必须走 global defaults，processor typed failure 继续投影既有 typed business failure。不得直接调用 `_normalize_taxonomy_name` 或 `_resolve_default_xbrl_concepts`，不得断言 mapping 的内部遍历顺序。 |
| 5. search next-step public projection | `test_search_next_section_projection_ranks_business_evidence_per_query` | **唯一 module-helper 例外**：`build_search_next_section_fields` | 只有前四个 public-seam node 依次完成后仍低于 80% 才可新增。输入含单/多 query、明确非平手的 evidence count/exact facts、malformed/no-section matches；断言 exact `next_section_to_read` / `next_section_by_query`、只保留业务字段、无候选 query 映射 `None`，malformed input 不能伪造 ref。不得构造平手后断言 first-index 偶然顺序。 |

Public seam 是前四个 family 的硬边界；不得因测试装配不便改为直接调用
`_normalize_document_types`、`_normalize_periods`、`_normalize_section_children`、
`_build_table_data_payload`、`_normalize_taxonomy_name`、`_resolve_default_xbrl_concepts` 或其它
私有 helper。唯一直接 module-helper 例外是表中第 5 项
`build_search_next_section_fields`：next-step projection 没有独立 public callable，强行走完整
search 会把检索/ranking owners 混入同一证据；该例外不扩展到 private cache、snapshot
internals、processor private method 或 Host private truncation state。

每个已授权 node 必须保持完整中文 docstring，明确 owner、业务 contract、输入、返回与
failure signal；测试必须穿过 production seam 并断言业务可观察 exact output/typed failure。
只调用不验证、只断言非空、fake 自证、空执行、覆盖私有分支、偶然顺序与为了 coverage
改 production 都失败。可用 typed processor fixture 驱动协议输入，但必须组合真实 repository
与 public runtime，且断言对象只能是 production public output/failure；不得形成 fake-only test。

本授权不允许新增或恢复 `resolve_has_financial_data` 的 compatibility evidence。新增 diff 中
禁止输入、断言、fixture key 或直接 helper 调用：`availability`、
`has_structured_financial_statements`、`has_financial_statement_sections`、
`has_financial_statement`、`has_xbrl`。也不得复制原四节点的 omnibus 结构、只改 test 名搬运，
或在一个 node 中拼接两个无依赖 owner family。

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
7. 按 §6.8 执行 README trigger check；保留累计 tree 已有 README，candidate-exhaustion delta 不改 README。
8. Candidate-exhaustion continuation 先匹配 stopped-tree/shared/guards/staged 锁并确认五个 exact nodes 全部存在；随后只删除 `_collect_available_document_types`，立即执行 §6.7.G source/AST proof。再按 §6.6 从零运行 exclude-candidate-5 与 all-five 两个 fresh coverage proof；前者必须仍低于 80%，后者必须首次达到 whole-file `>=80.00%`。达标后再次 `coverage erase`，从零完整重跑原 §6.6/§6.7 全部 acceptance validation。不得修改 tests、README、其它 production 或 artifacts；旧 incremental ledger 只作 stopped-tree evidence。

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

### 6.5 累计 owner/public tests与真实 smoke

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

`tests/fins/test_fins_read_runtime.py` 的六个 normalize/dedup nodes 在 S2 必须全部迁移，并在 §6.6 累计 focused、coverage 与完整验证中和 S1 fiscal node 一起收集；不得 `skip` / `xfail`、删 node、改名逃避收集或用 compatibility fixture/production shim 保留旧 count contract。

Candidate-exhaustion continuation 必须保留
`test_read_runtime_semantic_ownership_guards.py` 中 §6.1 候选表的全部五个 exact nodes，且不再产生
任何 test delta。每个 node 既有的单 owner、指定 seam 与 exact business assertions 都不可弱化；
禁止 compatibility/private-helper direct test、fake-only test、omnibus 搬运、skip/xfail、
coverage pragma/omit 或其它 bypass。stopped artifact 中逐 node 的
`covered/statement/percent` ledger 只证明旧 `494`-statement tree 的 candidate exhaustion，不是
删除 dead duplicate 后的 acceptance evidence。最终 artifact 必须另行记录 §6.6 两次 fresh proof，
以 candidate 4 未过线、candidate 5 过线机械证明完整五项仍是 first/shortest threshold-crossing prefix。

必须复用`tests/fins/test_fins_storage_provider.py`现有真实仓储构造，不以简化fake替代：

1. 真实AAPL XBRL fixture：fixture→workspace→processor→read→tool business value；断言raw输入不变、facts已dedup、唯一count同源、citation来自同一snapshot。
2. 真实HTML财务表fixture：HTML source→processor抽取→financial read tool；断言最小字段、无locator、period/scale/quality不由read补造、citation可读。
3. No-statement路径：真实producer terminal形成partial + `statement_not_found`，read只复制reason。

以下 focused 命令是 §6.6 唯一累计 validation 的组成部分，不是 S2 独立 gate：

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

### 6.6 累计 S1+S2 validation gate

S2 初始实现后的累计 validation 仍是唯一 acceptance validation。`R08-CR-PCF01` 的旧增量
ledger 已在 stopped tree 完成五项 exhaustion，只作 historical evidence；不得把其中任一 session、
JSON 或百分比复用为新 tree acceptance。`R08-CR-PCF02` 先删除 12-statement dead duplicate，随后
必须从 repository root 运行两个彼此独立、各自先 `coverage erase` 的 fresh mechanical proof。

第一个 proof 排除 candidate 5，只保留 candidate 1-4 与累计测试集，证明 deletion 后的最短前缀
尚未过线：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py \
  --deselect tests/fins/test_read_runtime_semantic_ownership_guards.py::test_search_next_section_projection_ranks_business_evidence_per_query
python -m coverage json -o workspace/tmp/r08-candidate-4-proof-coverage.json
python - workspace/tmp/r08-candidate-4-proof-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
print(f"CANDIDATE_4_PROOF {target}: {covered}/{statements} = {percent:.2f}%")
if covered != 382 or statements != 482 or percent >= 80.0:
    raise SystemExit(1)
PY
```

预期必须精确为 `382/482 = 79.25% < 80.00%`。任何 numerator、denominator 或阈值关系不匹配都
停止回 Controller；不得改测试、coverage 配置或 production 继续试探。

第二个 proof 再次从零开始，包含全部五个 candidate，证明第五项首次越过阈值：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
python -m coverage json -o workspace/tmp/r08-candidate-5-proof-coverage.json
python - workspace/tmp/r08-candidate-5-proof-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
print(f"CANDIDATE_5_PROOF {target}: {covered}/{statements} = {percent:.2f}%")
if covered < 388 or statements != 482 or percent < 80.0:
    raise SystemExit(1)
PY
```

预期至少为 `388/482 = 80.50% >= 80.00%`。candidate 4 fresh failure 与 candidate 5 fresh pass
共同证明五项完整连续前缀仍是 first/shortest threshold-crossing prefix；不增加第六项、不追求
100%、不补其它 missing line。两个 proof JSON 都不是最终 15-file acceptance checker。

上述 fresh proof 达标后，再次 `coverage erase`，从头完整执行以下累计 validation；它同时验收 S1
producer/processor、S2 public consumer/projection 与 code-review fix，不存在 S1-only、S2-only
或增量 ledger acceptance session。所有命令都在同一未提交 tree 上运行：

```bash
source .venv/bin/activate
# S1 focused owner matrix（此时 public import graph 已由 S2 恢复）
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_processor_registry.py -k 'financial or statement or xbrl or quality or reason or fiscal'
pytest tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract

# S2 focused/public matrix
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py

# 三段 forced-truncation public chain + AAPL/HTML/no-statement real smokes
pytest tests/fins/test_fins_storage_provider.py::test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation
pytest \
  tests/fins/test_fins_storage_provider.py::test_fins_read_aapl_xbrl_query_runs_in_spawned_child \
  tests/fins/test_fins_storage_provider.py::test_fins_read_financial_statement_runs_in_spawned_child \
  tests/fins/test_fins_storage_provider.py::test_fins_read_financial_statement_projects_statement_not_found

# R08 aggregate matrix；随后运行完整 Fins regression
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
pytest tests/fins -q

# 累计测试集包含既有 focused/aggregate/零diff回归 targets；只有新增/修改测试才限于 S1/S2 test diff allowlist并直连owner
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
python -m coverage json -o workspace/tmp/r08-cumulative-coverage.json

# 必须从 repository root 运行；Git pathspec 直接产生 repo-relative、仅 dayu/fins 的实际 changed production Python manifest
git diff --name-only -z --diff-filter=ACMR -- \
  ':(top,glob)dayu/fins/**/*.py' \
  > workspace/tmp/r08-changed-production-python.nul

# exact-key 逐文件 coverage checker；manifest 为空、key 缺失或任一文件低于 80.00% 都非零退出
python - \
  workspace/tmp/r08-changed-production-python.nul \
  workspace/tmp/r08-cumulative-coverage.json <<'PY'
import json
import os
from pathlib import Path
import sys

threshold = 80.0
manifest_path = Path(sys.argv[1])
coverage_path = Path(sys.argv[2])
manifest = [
    os.fsdecode(raw_path)
    for raw_path in manifest_path.read_bytes().split(b"\0")
    if raw_path
]
if not manifest:
    print("FAIL manifest: no changed dayu/fins Python files")
    raise SystemExit(1)

coverage_files = json.loads(coverage_path.read_text(encoding="utf-8"))["files"]
failed = False
for path in manifest:
    if not path.startswith("dayu/fins/") or not path.endswith(".py"):
        print(f"FAIL {path}: manifest path is not repo-relative dayu/fins Python")
        failed = True
        continue
    if path not in coverage_files:
        print(f"FAIL {path}: exact coverage JSON key is missing")
        failed = True
        continue
    percent = coverage_files[path]["summary"]["percent_covered"]
    status = "PASS" if percent >= threshold else "FAIL"
    print(f"{status} {path}: {percent:.2f}%")
    if percent < threshold:
        failed = True

raise SystemExit(1 if failed else 0)
PY

pyright

# NUL-safe 地生成并消费 dayu/fins + tests/fins 全部实际 changed Python manifest；空 manifest 必须失败
git diff --name-only -z --diff-filter=ACMR -- \
  ':(top,glob)dayu/fins/**/*.py' \
  ':(top,glob)tests/fins/**/*.py' \
  > workspace/tmp/r08-changed-fins-python.nul
python -c '
import os
from pathlib import Path
import sys

paths = [
    os.fsdecode(raw_path)
    for raw_path in Path(sys.argv[1]).read_bytes().split(b"\0")
    if raw_path
]
if not paths:
    print("FAIL Ruff manifest: no changed dayu/fins or tests/fins Python files")
    raise SystemExit(1)
os.execv(sys.executable, [sys.executable, "-m", "ruff", "check", *paths])
' workspace/tmp/r08-changed-fins-python.nul
git diff --check
```

Coverage manifest 与 coverage run/json 必须都从 repository root 运行。Git 的 top-level glob pathspec 直接限制到 `dayu/fins/**/*.py`，不得先收集 README 或其它非 Python path 再人工过滤；checker 只以 manifest 中 repo-relative path 对 coverage JSON `files` 做 exact key lookup，不做 basename、suffix、absolute-path、路径规范化或其它 loose fallback。若 JSON key 不是同一 repo-relative exact path，必须修正 coverage invocation/working directory后重跑；不得放宽匹配。每个实际 changed production Python 文件都必须打印 ledger，且 `summary.percent_covered >= 80.00`；manifest 空、exact key缺失与任一低于阈值均使 gate 失败。不得使用 aggregate `--fail-under`、changed-line coverage、pragma/omit、fake-only padding、skip/xfail 或阈值豁免代替逐文件结果；只在allowlist中但零diff的production文件不计入实际 changed manifest。

Ruff manifest 同样由 Git top-level glob pathspec 直接限定到 `dayu/fins/**/*.py` 与 `tests/fins/**/*.py`，以 NUL 分隔路径，并由同一命令块机械传给 Ruff；不得手抄 allowlist、遗漏 tests、把零diff文件伪装为实际 changed path，或让空 manifest 静默成功。

累计 coverage 测试集必须直接触达每个 changed owner 的 contract/behavior。若现有测试不足，只能在 §5.1/§6.1 已有 test allowlist 中修改与该 owner 直接对应的文件；不得扩大 production allowlist、修改无关功能、通过 fixture 固化偶然实现，或添加 coverage-only 空执行。

Full pyright 必须为 `0 errors`，不再接受红色 propagation ledger；全部实际修改 Python 文件 scoped Ruff 必须零。§5.5、§6.7 的 source/LLM/unique-owner/no-touch scans，AST owner assertions，README current-contract scan，retained-security/no-deferred-scope scan，以及 `git diff --check` 必须在同一累计 tree 全部通过。

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

#### E. AST、README、security与scope scan

- AST/runtime owner assertions 必须证明 `fact_count` 只有 `result_types.py` public builder 一个 production 赋值点，旧 tools 类型名无 alias/re-export/wrapper，producer/public exact keys 与 optional reason presence 一致；
- README/LLM scan 必须证明 `dayu/fins/README.md`、`tests/README.md` 和 tool descriptions 只陈述 current contract，不含 locator、raw/dedup count、processor/Host 治理术语、历史 gate 或未来计划；
- retained-security/no-touch scan 必须证明 R06/R07 storage、identity、revision、snapshot、citation、containment、symlink、atomic publication/recovery、Host truncation owner均无语义 diff；
- exact allowlist scan 必须拒绝 S1/S2 production/test/README allowlist外路径，以及 R09-R12、Issues 142/151/175/177/178、Host/Engine/Service/UI、`dayu/config/prompts/**` 或统一 authorization 实现。

#### F. `R08-CR-PCF01` correction-specific source/AST scans

共享文件删除边界必须零命中：

```bash
rg -n \
  'test_read_helper_document_discovery_rules_preserve_public_semantics|test_search_next_section_owner_ranks_exact_hits_per_query|test_table_data_projection_owner_emits_self_describing_shapes|test_navigation_and_xbrl_default_rule_owners_fail_closed|_build_table_data_payload|_normalize_document_types|_normalize_periods|_normalize_section_children|_normalize_taxonomy_name|_resolve_default_xbrl_concepts|build_search_next_section_fields|resolve_document_type_for_source|resolve_has_financial_data' \
  tests/fins/test_fins_read_runtime.py
```

`test_fins_read_runtime.py` final SHA-256 必须仍为
`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`；复用 blocked-fix
artifact 的 top-level AST 比较，证明 common function AST 零变化、generic LRU/form-matching
nodes unchanged，且文件只保留两个未改 generic nodes、六个 S2 normalize/dedup nodes和一个
S1 fiscal node。任何漂移都失败，不能用“新 coverage”解释。

新 stable-owner 测试文件必须通过以下 compatibility/private-helper negative scan：

```bash
rg -n \
  'availability|has_structured_financial_statements|has_financial_statement_sections|has_financial_statement|has_xbrl|resolve_has_financial_data|_build_table_data_payload|_normalize_document_types|_normalize_periods|_normalize_section_children|_normalize_taxonomy_name|_resolve_default_xbrl_concepts|\b_collect_available_document_types\b' \
  tests/fins/test_read_runtime_semantic_ownership_guards.py
```

预期零命中。AST import assertion 必须证明相对 correction-entry tree 新增的
`read_runtime_helpers.py` production symbol import 为空；只有确实执行到 §6.1 第 5 个候选时，
才允许它精确等于 `{build_search_next_section_fields}`。`FinsReadArgumentError` 作为 public typed
failure assertion 可机械加入既有 import；不得加入其它 helper、private cache/processor/Host
state import。AST node assertion还必须证明五个已授权 tests 精确等于候选表的完整连续前缀，
每个 node 只有一个 owner family，没有 `skip` / `xfail` marker，也没有 coverage pragma/omit；
guards 内容 SHA-256 必须仍为 `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`。

对 23-path stopped-tree manifest 做 exact diff scan：candidate-exhaustion implementation 相对
`65a92406...6dff` 只允许 `dayu/fins/tools/read_runtime_helpers.py` 产生一个 symbol deletion delta；
tests、README、其它 production path 与 S1/S2 artifacts 全部 immutable。最终仍须在新 aggregate
binary diff 上执行 §6.6 全部 15-file exact-key ledger 与完整 §6.7，不能复用
`65a92406...6dff` 上的 incremental coverage、validation、review lock 或 reviewer verdict。

#### G. `R08-CR-PCF02` dead-helper deletion 与 actual-owner source/AST proof

删除后先做 source scan，旧 helper 的 definition、caller、import 必须全为零：

```bash
if rg -n '\b_collect_available_document_types\b' dayu tests; then
  echo 'FAIL old helper definition/caller/import remains'
  exit 1
fi
echo 'PASS old helper source matches=0'
```

预期零命中。由于 actual owner 名称带后缀，word-boundary pattern 不会把
`_collect_available_document_types_for_source_documents` 误报为旧 symbol。随后运行 AST proof：

```bash
source .venv/bin/activate
python - <<'PY'
import ast
from pathlib import Path

old_name = "_collect_available_document_types"
actual_name = "_collect_available_document_types_for_source_documents"
definitions = 0
callers = 0
imports = 0
for root in (Path("dayu"), Path("tests")):
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == old_name
            for node in ast.walk(tree)
        )
        callers += sum(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name) and node.func.id == old_name
                or isinstance(node.func, ast.Attribute) and node.func.attr == old_name
            )
            for node in ast.walk(tree)
        )
        imports += sum(
            isinstance(node, ast.ImportFrom) and any(alias.name == old_name for alias in node.names)
            or isinstance(node, ast.Import)
            and any(alias.name == old_name or alias.name.endswith(f".{old_name}") for alias in node.names)
            for node in ast.walk(tree)
        )
if (definitions, callers, imports) != (0, 0, 0):
    raise SystemExit(
        f"FAIL old helper remains: definitions={definitions}, callers={callers}, imports={imports}"
    )

runtime_path = Path("dayu/fins/tools/read_runtime.py")
runtime_tree = ast.parse(runtime_path.read_text(encoding="utf-8"), filename=str(runtime_path))
owners = [
    node
    for node in runtime_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == actual_name
]
actual_calls = [
    node
    for node in ast.walk(runtime_tree)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == actual_name
]
if len(owners) != 1 or len(actual_calls) != 1:
    raise SystemExit(f"FAIL actual owner cardinality: definitions={len(owners)}, callers={len(actual_calls)}")
owner = owners[0]
input_annotation = ast.unparse(owner.args.args[0].annotation)
return_annotation = ast.unparse(owner.returns)
owner_call_names = {
    node.func.id
    for node in ast.walk(owner)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
}
sorted_returns = [
    node
    for node in ast.walk(owner)
    if isinstance(node, ast.Return)
    and isinstance(node.value, ast.Call)
    and isinstance(node.value.func, ast.Name)
    and node.value.func.id == "sorted"
]
if input_annotation != "list[_SourceDocumentSummary]" or return_annotation != "list[str]":
    raise SystemExit(f"FAIL actual owner typing: {input_annotation} -> {return_annotation}")
if "resolve_document_type_for_source" not in owner_call_names or len(sorted_returns) != 1:
    raise SystemExit("FAIL actual owner lost typed resolution or sorted output")
print("PASS old helper definition/caller/import=0; actual typed/sorted owner definition/caller=1")
PY
```

该 scan 只验证删除与 owner 不变量，不授权修改 `resolve_document_type_for_source`、actual owner、
`read_runtime.py` 或 tests。实施 artifact 还必须记录 `read_runtime.py` content SHA 在 stopped tree
前后相同；任何差异立即停止回 Controller。

### 6.8 README trigger check

- 累计 S1/S2 tree 已有 README 内容保持受保护；candidate-exhaustion implementation 不得修改它们。
- 删除零 caller 的 private dead helper 不改变用户可见 contract、tool schema、安装/CLI 工作流、测试职责或分层关系，因此虽命中 `dayu/fins/` 路径检查触发，也不机械修改 `dayu/fins/README.md`、`tests/README.md`、根 README 或 `dayu/README.md`。
- 若实施证据反而显示用户可见语义变化，立即停止回 Controller；不得以 README 补写掩盖 owner drift。

### 6.9 S2 review与commit边界

原始顺序固定：AgentCodex S2 implementation/self-check → §6.6/§6.7 累计 validation 全绿 → Controller 记录完整 changed-path manifest、每个 changed path content SHA-256 与完整累计 `git diff --binary` SHA-256 → AgentMiMo与AgentDS对同一 immutable S1+S2 cumulative tree 并发完整 code review并各自重算 hash → Controller adjudication → AgentCodex 修复全部 accepted findings → 在新 hash 上重跑完整累计 validation → 两路完整 re-review → Controller逐条关闭。

`R08-CR-CF01` 已使原 review lock `4d346f2b...d4b`、原 Controller validation 与两路 code
review失效；五项 candidate 完整前缀形成后的 `65a92406...6dff` stopped tree 仍因
`388/494 = 78.54%` 没有完成 §6.6/§6.7，不能复用旧 incremental ledger 或旧绿色。
Candidate-exhaustion corrected continuation 的顺序精确为：

```text
AgentCodex plan-only correction
-> Controller plan-diff/protected-tree validation
-> AgentMiMo + AgentDS complete corrected-plan review
-> accepted plan findings fix（若有）
-> complete corrected-plan re-review / Controller adjudication
-> corrected-plan accepted local commit
-> AgentCodex 从 65a92406...6dff stopped tree 只删除 dead duplicate helper
-> §6.7.G source/AST proof：旧 helper definition/caller/import 全零，actual typed/sorted owner 保留
-> §6.6 fresh exclude-candidate-5 proof 382/482=79.25%<80
-> §6.6 fresh all-five proof 至少 388/482=80.50%>=80
-> 再次 coverage erase，从零完整重跑原 §6.6/§6.7
-> Controller 锁定新的 changed-path content manifest / binary diff hash
-> AgentMiMo + AgentDS 对完整 S1+S2+fix tree code re-review
-> Controller 逐条关闭
-> aggregate deepreview
```

Corrected plan 未经双路 review/re-review 与 accepted-plan commit 前，不得删除 helper 或运行
implementation validation。删除使 stopped diff `65a92406...6dff` 失效，Controller 必须只在最终
全绿 tree 上建立新 lock。code re-review 必须审完整累计 diff，包括原 S1/S2、四节点/九 imports
删除、五个 stable-owner tests 与 dead duplicate helper 删除；不得只审单一 deletion delta。

Controller 只能在累计 validation 全绿后锁 tree；任一 production、test、README、artifact 或其它 reviewed path 变化都会使先前 lock/review 失效，必须在新 content manifest 与 binary diff hash 上重跑。两路 reviewer 必须审查完整累计 diff，不得把 S1 当作已单独接受的历史或只审 S2 增量。

S1/S2 都不单独commit，也不建立中间 checkpoint commit。只有累计 code review/fix/re-review闭环、aggregate deepreview及其必要fix/re-review全部通过后，Controller才可授权一个exact-scope local implementation commit。该commit只完成R08，不完成umbrella。

## 7. Aggregate deepreview与后续

§6.6 是唯一累计/aggregate validation 真源；不得在本节复制或缩减另一份命令矩阵。它必须同时覆盖三段 forced-truncation smoke、AAPL/HTML/no-statement real smokes、全部双向/source/AST/LLM/README/security/no-touch scans、full pyright、scoped Ruff、`git diff --check` 和每个实际 changed production 文件逐文件 coverage 检查。

已审计baseline仅用于增量判定：focused contract/read/ownership/consistency matrix为`111 passed`；真实AAPL/HTML/description/failed-outcome/fiscal exact nodes为`5 passed`；full pyright为零；full Ruff有150个继承问题。R08不承担全仓Ruff，但所有实际修改文件scoped Ruff必须归零；S1必改producer中已有两个F401随本切片清除。不得新增warning类别或pyright错误。

累计 immutable dual code re-review 闭环后，aggregate deepreview必须再次检查：owner唯一性、reason动作性、count单一同源、raw immutability、query params单一shape、tool/serializer drift、R07 no-touch、compat/shim、allowlist/README/tests越界、四节点/九 imports 删除、五个 stable-owner tests 完整不可变、dead duplicate helper definition/caller/import 全零、actual typed/sorted owner 保留，以及 candidate-4/candidate-5 fresh threshold proof 与 S1/S2/fix 累计变更之间的 semantic ownership drift。

任一 aggregate deepreview accepted finding 的修复只要改变 reviewed tree，旧累计 validation、changed-path content manifest、binary diff hash 与两路 aggregate deepreview 即全部失效。必须在新 hash 上重跑完整 §6.6 与 §6.7，包括全部 focused/aggregate/full Fins tests、real smokes、逐文件 coverage checker、full pyright、实际 changed Python scoped Ruff、全部 scans 与 `git diff --check`；全绿并锁定新 hash 后，再由两路 reviewer 对完整 aggregate tree 进行 re-review。只有两路 aggregate re-review 与 Controller 逐条 adjudication 全部关闭后，才可授权 accepted local implementation commit。

R08 completion后umbrella仍active；依次继续R09、R10、R11、R12，之后还需umbrella aggregate validation/deepreview/final closeout。

## 8. Stop conditions与禁止补救

| 观测 | 正确处置 | 禁止补救 |
|---|---|---|
| Producer不能提供required essential field | 停在producer owner澄清 | read默认/猜值/空字符串 |
| Method absent/empty分散 | actual producer terminal统一`statement_not_found` | read看rows推断；保留旧reason alias |
| Provider确有raw total | internal typed validation/diagnostic inventory+tests | 暴露public/LLM；改名逃scan |
| S1 type change触发S2旧consumer错误 | 保留为blocked intermediate/root-cause evidence并直接继续S2；累计tree full pyright归零 | 把红色ledger当formal pass；compat field、cast、ignore、shim |
| Dedup需要修改fact | 深复制后修改public fact | 原地覆盖raw fact/list |
| Description需要字段清单 | 消费result_types owner helper | 手写第二份contract |
| Host截断产生cursor envelope | 按第6.4节验证或stop回Controller | Fins私造fetch_more、静默drop、越界改Host |
| 旧测试期待locator/count/internal reason | 迁移fixture/assertion | 生产兼容分支保旧测试 |
| Stopped cumulative diff、guards、shared test 或 staged 状态不匹配 | 不删除 helper，立即回 Controller 澄清 drift | 在未知 tree 上继续；重建/恢复已删节点 |
| 一个 public-seam candidate 需要 private cache/processor method/Host state、fake-only 或 compatibility input 才能驱动 | 立即 stop 回 Controller；只有 search family 可用表中唯一 module-helper 例外 | 新增第二个 helper 例外、monkeypatch 私有状态、loose fixture |
| 删除后旧 helper definition/caller/import 任一非零，或 actual typed/sorted owner/`resolve_document_type_for_source` 漂移 | 停回 Controller，澄清 owner 与 tree | 直测 private helper；wrapper/re-export；修改 actual owner 或下游补偿 |
| Fresh candidate-4 proof 不是 `382/482=79.25%<80`，或 all-five proof 低于 `388/482=80.50%` / 未过线 | 保留现场证据并 stop 回 Controller | 修改测试、增加第六项、降低阈值、pragma/omit、fake/empty/compatibility padding |
| Fresh candidate-4 未过线且 all-five 过线 | 保留全部五项，清空 coverage 后完整重跑 §6.6/§6.7 | 删除任一已授权 test；追求 100%；补其它 missing branch |
| Dead-helper deletion 后任一 §6.6/§6.7 gate 失败 | 在原 owner/failure boundary修复并从零完整重跑；若需越界则 stop | 复用旧 incremental ledger/hash/validation/review；skip/xfail；只重跑失败子集即宣称通过 |
| 发现R09-R12/deferred issue | 记录out-of-scope并停止扩张 | 顺手实现 |

## 9. Code-generation handoff checklist

### S1

- [ ] Base/R07 lineage与worktree核验；
- [ ] S1 allowlist、contracts、all actual producers完成；
- [ ] `test_fins_read_runtime.py` 只修改 S1 fiscal node；六个 S2 read normalize/dedup nodes未提前迁移、skip/xfail或shim；
- [ ] Locator helper与alternate reason owner删除；
- [ ] 共享 fiscal-period owner、bool 显式拒绝与 focused owner tests完成；
- [ ] S1 implementation artifact明确保持blocked intermediate evidence，不声明acceptable product state；
- [ ] 未运行/要求S1独立exact-node collection、whole-file coverage、红色full-pyright ledger formal pass或immutable dual review；
- [ ] 未stage/commit，直接在同一tree进入S2。

### S2 / aggregate

- [ ] S1 blocked intermediate tree受保护且无compat/shim；S2按既有allowlist直接继续；
- [ ] Candidate-exhaustion re-entry 精确匹配 stopped 23-path `65a92406...6dff`、shared test `01db...6692`、guards `55318914...928d`，staged 为空；
- [ ] `test_fins_read_runtime.py` 固定 symbol boundary不变，四个删除节点与九 imports未恢复、改名、参数化或搬运；generic LRU/form-matching AST unchanged；
- [ ] Guards 中五个 stable-owner tests 全部存在且内容锁不变；前四项走 public runtime，第5项保持唯一 module-helper exception；无新增/删除/修改 test；
- [ ] 五个 nodes 的单 owner、完整中文 docstring、repository-backed public exact input/output/typed failure assertions保持；无 compatibility/private-helper direct test、private cache/processor/Host state、偶然顺序、fake-only、空执行、omnibus 搬运、skip/xfail或coverage bypass；
- [ ] 唯一 production delta 是删除 `read_runtime_helpers.py::_collect_available_document_types` 完整 definition；`resolve_document_type_for_source` 与 `read_runtime.py::_collect_available_document_types_for_source_documents` 零 diff；
- [ ] Source/AST proof 证明旧 helper definition/caller/import 全零，actual owner definition/caller 各一、typed input/output、调用 shared resolver 且 sorted output；
- [ ] 旧 `320/494→388/494` incremental ledger 只作 stopped-tree evidence；fresh exclude-candidate-5 proof 精确为 `382/482=79.25%<80`，fresh all-five proof 至少为 `388/482=80.50%>=80`，共同证明五项仍是 first/shortest threshold-crossing prefix；
- [ ] Single typed public projection/helper完成；
- [ ] Public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`，旧 tools 名称无 alias/re-export/wrapper；
- [ ] Citation 使用 `Mapping[str, JsonValue]` 输入和独立 `dict[str, JsonValue]` 输出，同 borrowed snapshot 内容一致且 R07 no-touch；
- [ ] Raw facts不变、public facts独立dedup、唯一count同源；
- [ ] Tool description/serializer自同一owner派生且自足，七值 reason 均有 LLM-safe 下一动作，示例使用 `SEC_EDGAR`；
- [ ] `fiscal_period` schema 与 producer 共享 `FY|H1|Q1|Q2|Q3|Q4` owner，number schema/callable 的 bool 拒绝已验证；
- [ ] 真实 provider 的 pre-Host typed 等式、Host public cursor envelope 与 Host-injected `fetch_more` remainder 组合验证通过；若 public seam 不可观测则 stop 回 Controller；
- [ ] R07 snapshot/citation symbols零语义变更；
- [ ] 三段forced-truncation、AAPL、HTML、no-statement真实smoke通过；
- [ ] README trigger 已检查；private dead helper 删除无用户 contract 变化，candidate-exhaustion continuation 不修改任何 README；
- [ ] S1+S2全部focused/aggregate tests与完整Fins regression通过；
- [ ] Full pyright零、全部实际修改Python文件Ruff零、每个实际changed production文件逐文件coverage>=80%，无changed-line/aggregate/豁免；
- [ ] 完整 §6.6/§6.7 从零重跑；15-file whole-file exact-key coverage全部 `>=80.00%`，positive/negative/source/AST/LLM/README/security/unique-count/no-touch/correction scans通过；
- [ ] 旧 plan SHA/reviews、`4d346f...d4b` review lock、`7a7ebf...1d6d` validation/reviews与 `65a92406...6dff` stopped incremental ledger均标记失效，不作最终通过证据；
- [ ] Controller在全绿后锁定累计changed-path content hashes与binary diff hash；MiMo/DS对同一immutable累计tree完成完整code review；
- [ ] 全部accepted findings由AgentCodex修复并经完整累计validation与双路re-review关闭；aggregate双路deepreview关闭；
- [ ] 任一 aggregate deepreview accepted fix 后在新 hash 上完整重跑 §6.6/§6.7，并经双路 aggregate re-review 与 Controller adjudication 关闭；
- [ ] 未stage/commit，等待Controller另行授权。

## 10. 本 candidate-exhaustion plan-only correction gate 自检要求

本gate唯一允许新增/修改artifact：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-correction-codex.md
```

交付前必须完整核对 `git status --short --untracked-files=all`，证明本次只增加上述两个
allowed-path delta，未修改当前 23-path production/test/README protected tree、S1/S2/fix
implementation artifacts、control/design/controller/reviewer/prior artifacts。以当前 accepted
plan SHA-256 `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02`
为 before hash，计算 final plan SHA-256，只在新 Codex artifact/handoff 中报告，不自嵌入 plan。

必须在修改前后都用 `git diff --binary -- dayu/fins tests | sha256sum`（平台等价
`shasum -a 256` 可接受）重算当前 23-path protected diff，并精确等于
`65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`；guards、shared test
必须分别仍为 `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`、
`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，staged 为空；任何 drift
使本 gate 失败。新 artifact 必须记录：修正动机、`R08-CR-PCF02` 修改段落、before/final plan
SHA、protected diff before/after、exact changed-path count、`git diff --check`、仅两条 authored
doc paths 的 whitespace check、完整 status、staged-empty、无 product/test/README/control/design/
prior-artifact 改动与本 turn 未运行测试/pyright/implementation 的事实。

确认 `R08-CR-PCF02` 已 code-generation-ready 写入 allowlist、implementation step、fresh coverage proof、
source/AST scans、README decision、checklist、stop conditions 与 aggregate handoff，同时 §4 product contracts、
S1/S2 path allowlists、R07 no-touch、Host truncation owner、Topic 8-9 no-code、
Issues 142/151/175/177/178 与 R09-R12 deferred boundaries均未改变后，停止回 Controller。
下一 gate 只能是两路完整 corrected-plan review；不得进入 test implementation、code re-review、
aggregate deepreview、commit 或任何后续 gate。
