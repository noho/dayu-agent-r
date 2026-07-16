# WU-SEMANTIC-OWNERSHIP-01 / R08 fixed plan complete re-review — AgentDS

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | 并发第二路 complete plan re-review |
| timestamp | `2026-07-17 04:05:07 +0800` |
| reviewed target | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| fixed plan SHA-256 | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-controller-adjudication.md` |
| Codex fix | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md` |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-controller-validation.md` |
| base HEAD | `8d9bf63b3ab56f9ba3d5355d75af4ee002548c9c` |
| review scope | 逐项 R08-PF-01..07 closure、adversarial、owner boundary、slice sequencing、测试/验证、LLM-facing、自相矛盾、scope review |
| result | **PASS with 1 medium + 1 low material finding / 0 blocker** |

本 review 是 Controller validation 通过后对同一固定 SHA 的并发第二路完整 re-review。不重开已被 Controller 拒绝且无新直接代码证据的问题。

## 2. SHA-256 核验

```text
07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5
  docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

与 Controller validation 记录的固定 SHA 一致。本 review 基于该不可变 plan artifact。

## 3. R08-PF-01..07 closure verification

### R08-PF-01 — S1 internal checkpoint exact propagation evidence

**Plan 位置**: §3.4 line 158、§5.1 lines 360-374、§5.3 lines 394-405、§5.4 lines 422-431、§5.6 line 464

**核验**:
- S1 test allowlist 已明确纳入共享 `tests/fins/test_fins_read_runtime.py`，并按 symbol 划定 S1 fiscal fixture/node (`_extract_fiscal_from_xbrl_query`、`_FiscalXbrlProcessor`、`test_sec_fiscal_inference_rejects_invalid_xbrl_total`→rename) 与 S2 normalize/dedup nodes 的边界。
- §5.4 锁定 Controller validation 产出：base HEAD、`git status --short`、changed-path manifest、逐 path 内容 SHA-256、完整 binary diff SHA-256、full-pyright exact propagation ledger（文件/symbol/rule/已删 field/type/S2 owner/action）。诊断只允许落在四个预声明 S2 production paths。
- 两路 reviewer 必须独立核对同一 immutable hash/ledger。

**代码证据**: 当前 `tests/fins/test_fins_read_runtime.py:269` 存在 `test_sec_fiscal_inference_rejects_invalid_xbrl_total`，`line 8` import `_extract_fiscal_from_xbrl_query`，`line 13` 定义 `_FiscalXbrlProcessor` fixture——均在 S1 symbol boundary 内。

**状态**: **closed** ✓

### R08-PF-02 — financial reason 的 LLM-safe next-action projection

**Plan 位置**: §4.4 lines 287-311、§6.2 line 514、§6.5 line 557

**核验**:
- 七值闭集保持不变，`unsupported_statement_type` 保留并明确语义：表达 actual processor 无法服务全局合法 statement type。
- §4.4 新增完整 reason→下一动作矩阵表，覆盖所有七个 reason 的业务含义与 LLM-safe 下一动作。
- `result_types.py` 同源 metadata/helper 拥有该矩阵；`fins_tools.py` 只机械消费。

**代码证据**: 当前 `fins_tools.py:977-983` 的 `query_xbrl_facts` description 暴露 `total`（去重前原始 fact 数）和 `deduped_fact_count`（去重后数量）为内部诊断事实，plan S2 将修正。当前 financial description 不含 reason 矩阵，plan 要求补齐。

**状态**: **closed** ✓

### R08-PF-03 — exact citation JSON typing strategy

**Plan 位置**: §4.3 lines 255-280、§6.5 line 551

**核验**:
- 两个 public builder 精确接受 `Mapping[str, JsonValue]`，立即复制为独立 `dict[str, JsonValue]`。
- 不修改 `Citation` dataclass、R07 snapshot/citation 生成或字段语义。
- 不新建第二 citation schema；R07 `_build_citation` 保持 no-touch。

**代码证据**: 当前 `dayu/fins/domain/tool_models.py` 中 `Citation` 为 frozen dataclass，`to_dict()` 返回 `dict[str, Any]`。`read_runtime.py:2079` 调用 `self._build_citation(borrow=borrow)` 返回 citation dict。Plan 策略是在 builder 边界做 `Mapping[str, JsonValue]`→`dict[str, JsonValue]` 复制，不改 upstream。

**状态**: **closed** ✓

### R08-PF-04 — citation example uses current SourceType truth

**Plan 位置**: §4.4 lines 313-333、§6.5 line 557、§6.7.B lines 625-640

**核验**:
- 唯一最小 JSON 示例使用 `"source_type": "SEC_EDGAR"`，保留 `document_id`、`ticker`、`source_provider`。
- §6.7.B negative scan 规则包含 `sec_filing` 作为禁止字面量。

**代码证据**: `read_runtime.py:148-155` 确认 `SourceType.SEC_EDGAR` 是 SEC EDGAR provider 的 citation source_type 唯一真源值。`sec_filing` 在代码中不存在。

**状态**: **closed** ✓

### R08-PF-05 — fiscal_period input schema and typed query params share one enum

**Plan 位置**: §4.2 lines 217, 230-232、§4.4 line 311、§5.3 line 395、§6.2 line 517、§6.5 line 553

**核验**:
- `fiscal_period.enum` 从 `dayu.fins.domain.filing_semantics.FISCAL_PERIODS` 派生，值集为 `FY|H1|Q1|Q2|Q3|Q4`。
- S1 validator 与 S2 schema/tests 共享同一 owner；字段缺席时不补 `None`。

**代码证据**: `filing_semantics.py:35` 定义 `FiscalPeriod: TypeAlias = Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`，`line 79-80` 定义 `FISCAL_PERIODS: Final[frozenset[FiscalPeriod]]`。当前 `fins_tools.py:1748` 的 `query_xbrl_facts.fiscal_period` 参数 schema 只有 `"type": "string"` 和 description 举例，**没有 `enum` 字段**——这正是 plan 要求修复的 gap。`fins_tools.py:1499` 的 `list_documents.fiscal_periods` 已有 `"enum": ["FY", "H1", "Q1", "Q2", "Q3", "Q4"]` 但为手写 literal，不是从 `FISCAL_PERIODS` 派生。

**状态**: **closed** ✓

### R08-PF-06 — bool is rejected at the XBRL producer query-param validator

**Plan 位置**: §4.2 line 232、§4.4 line 311、§5.3 line 396、§6.2 line 517、§6.5 line 553

**核验**:
- S1 `xbrl_result_contract.py` validator 在 accepting `int | float` 前显式拒绝 `bool`。
- Owner tests 覆盖 `True`、`False`、`int`、`float`、missing。
- S2 JSON Schema 保持 `type: number`，callable/schema tests 证明 boolean 拒绝。

**代码证据**: 当前 `xbrl_result_contract.py:215` `_required_non_negative_int` 已有 `isinstance(value, bool)` 检查（拒绝 bool for int）。但对于 `min_value`/`max_value` 的 float 路径，当前没有独立的 bool 拒绝逻辑——plan 要求新增。`fins_tools.py:1749` 的 `min_value`/`max_value` schema 使用 `"type": "number"` 保持不变。

**状态**: **closed** ✓

### R08-PF-07 — public result names are explicit and have no compatibility aliases

**Plan 位置**: §3.4 line 146、§4.3 lines 244-280、§6.2 line 513、§6.5 line 550

**核验**:
- Tools public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`。
- 旧 tools `FinancialStatementResult` / `XbrlQueryResult` 删除，不保留 re-export/alias/wrapper。
- Domain producer `FinancialStatementResult` / `XbrlFactsResult` 保持不变。

**代码证据**: 当前 `result_types.py:246` 定义 tools `FinancialStatementResult`（含 `statement_locator`），`line 285` 定义 `XbrlQueryResult`（含 `total`、`deduped_fact_count`）。`read_runtime.py:84-94` import 这些旧名用于 return annotations。Plan 要求在 S2 删除旧名并全面替换。

**状态**: **closed** ✓

### Closure summary

| ID | 状态 |
|---|---|
| `R08-PF-01` | closed |
| `R08-PF-02` | closed |
| `R08-PF-03` | closed |
| `R08-PF-04` | closed |
| `R08-PF-05` | closed |
| `R08-PF-06` | closed |
| `R08-PF-07` | closed |

**7/7 closed，0 deferred，0 product blocker。**

## 4. Adversarial review — new material findings

### DS-RR-01 — S1 verification gate runs full test file conflicting with preserved S2 nodes [Medium]

- **位置**: Plan §5.4 lines 411-413 vs §5.1 lines 370-374
- **问题类型**: 切片过粗 / 自相矛盾
- **当前写法**: §5.1 明确规定 S2 normalize/dedup test nodes 在 S1 不得迁移、保持原样；§5.4 S1 验证门命令直接运行 `pytest ... tests/fins/test_fins_read_runtime.py`（无 `-k` 过滤），期望全绿。
- **反例/失败场景**: S1 删除 XBRL producer contract 中的 `total` 字段后，当前 `read_runtime_helpers.py:1199-1223` 的 `_normalize_xbrl_query_payload`（S2 未改）内部调用 `validate_xbrl_facts_result_payload` 再访问 `validated.total`（line 1219）。若 S1 validator 将 `total` 从已知字段删除并拒绝 unknown keys，则：
  1. 含 `total` 键的 S2 测试 fixture（lines 133/158/186/227/256）被 validator 以 unknown key 拒绝 → `ValueError`，与测试期望的错误消息不匹配；
  2. 不含 `total` 键的 fixture（line 109）通过 validator 但在 `_normalize_xbrl_query_payload` 访问 `validated.total` 时抛 `AttributeError`。

  所有 6 个 S2 test nodes（lines 96-266）均无法通过。
- **为什么有问题**: §5.3 的 S1 focused command 正确地只运行单个 test node `test_sec_fiscal_inference_consumes_countless_xbrl_contract`，但 §5.4 的正式验证门未做同等过滤。两处命令不一致，实施 Agent 按 §5.4 执行验证时会遭遇 6 个预期外失败，无法判定 S1 是否通过。
- **直接证据**:
  - `tests/fins/test_fins_read_runtime.py:96-266` — 6 个 S2 test nodes 存在且均调用 `_normalize_xbrl_query_payload`
  - `dayu/fins/tools/read_runtime_helpers.py:1199` — `_normalize_xbrl_query_payload` 调用 `validate_xbrl_facts_result_payload`
  - `dayu/fins/tools/read_runtime_helpers.py:1219` — `total=validated.total` 访问已删除字段
  - `dayu/fins/domain/xbrl_result_contract.py:102-104` — 当前 validator 检查 `total`
  - Plan §4.2 — S1 删除 `total` 并拒绝 unknown keys
  - Plan §5.4 lines 411-413 — 验证命令运行整文件
- **影响**: 实施 Agent 在 S1 验证阶段跑偏（误判 S1 失败或被迫提前迁移 S2 nodes）；Controller validation 无法按计划进行。
- **建议改法和验证点**: 将 §5.4 的 `test_fins_read_runtime.py` 整文件运行替换为与 §5.3 focused command 一致的单 node 运行，或加 `-k 'not (xbrl_query_payload and not sec_fiscal_inference)'` 显式排除 S2 nodes。同时 §5.4 coverage 命令只收集 production file coverage，test file 内容不影响 coverage 结果，安全。
- **修复风险**: 低 — 只改 plan 中的一条 shell 命令，不动架构/contract/test。
- **严重程度**: Medium — 不修复会导致 S1 验证门无法通过，但修复只需一行命令调整。

### DS-RR-02 — Truncation forced-path test mechanics underspecified [Low]

- **位置**: Plan §6.4 lines 534-543、§6.5 line 561
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: §6.4 正确识别 Host truncation 替换 `facts` 为 cursor envelope 但不原子更新 `fact_count` 的组合风险。§6.5 line 561 要求"under-limit与forced-truncation组合风险均被显式验证"。但 plan 未给出 forced-truncation 测试的具体构造方式。
- **反例/失败场景**: 实施 Agent 不知道如何构造 forced-truncation 场景：是用真实超限 fixture 触发 Host ToolRuntime 截断？还是用 mock 模拟 Host cursor envelope？没有明确预期，测试可能写成只验证 under-limit 路径的 happy case，漏掉真正的 truncation 风险。
- **为什么有问题**: 这是已识别的真实跨层风险（Fins projection × Host truncation），测试设计不能全靠实施 Agent 自行判断。
- **直接证据**: Plan §6.4 识别了风险，§6.5 只写了"均被显式验证"但未给出测试构造策略。
- **影响**: 实施 Agent 可能写一个形式化的 happy-path test 满足 checklist，实际未覆盖 truncation 场景。
- **建议改法和验证点**: 在 §6.4 或 §6.5 补充最小测试构造策略：(a) 使用真实 AAPL fixture + `FinsToolLimits.query_xbrl_facts_max_items` 设为极小值（如 1）强制截断；(b) 断言截断前 Fins public projection `fact_count == len(facts)`；(c) 不要求测试 Host cursor envelope 内部结构（那是 Host owner），但必须证明 Fins 交给 Host 前等式成立。
- **修复风险**: 低。
- **严重程度**: Low — plan 已正确识别风险且 stop condition 已明确，测试构造细节可在 implementation 阶段由 Controller 澄清。

## 5. Architecture boundary review

### 5.1 Owner boundary 核验

Plan §2.2 的 owner 分配表与当前代码一致：

| 语义 | Plan owner | 当前代码 owner | 一致性 |
|---|---|---|---|
| opaque ticker/document identity | R07 storage | `read_runtime.py:2350-2411` `_resolve_canonical_ticker` + `_resolve_canonical_document_id` | ✓ R08 no-touch |
| revision/snapshot/borrow lifecycle | R07 storage/read snapshot boundary | `read_runtime.py:192-373` `_CachedProcessor` + `_ProcessorBorrow` | ✓ R08 no-touch |
| provenance/citation | R07 snapshot/citation projection | `read_runtime.py:2079` `self._build_citation(borrow=borrow)` | ✓ R08 只消费 |
| financial producer result | `financial_result_contract.py` + actual processors | `financial_result_contract.py:77-88` `FinancialStatementResult` | ✓ S1 唯一 owner |
| XBRL raw query result | `xbrl_result_contract.py` + actual processors | `xbrl_result_contract.py:25-32` `XbrlFactsResult` | ✓ S1 唯一 owner |
| public financial/XBRL result | `result_types.py` typed projection | `result_types.py:246-260` `FinancialStatementResult`、`line 285-296` `XbrlQueryResult` | ✓ S2 替换为 Public* 命名 |

无 owner 冲突或边界模糊。

### 5.2 Dependency direction

```
Producer domain contracts (S1)
    ↓ (no reverse dep)
Read runtime helpers (S2)
    ↓ (no reverse dep)
Public typed projection (S2)
    ↓ (no reverse dep)
Tool definitions / LLM-facing text (S2)
```

Plan 的 S1→S2 顺序合理：先收窄 producer contract，再统一 public projection。无反向依赖。

### 5.3 过度耦合检查

- Plan 不引入 generic builder、god bag、reflection 或新 schema framework。✓
- S1 与 S2 通过 typed contract 边界解耦，不是通过共享可变状态。✓
- Citation 投影策略（`Mapping[str, JsonValue]`→`dict[str, JsonValue]`）在 builder 边界做独立复制，不与 R07 耦合。✓

## 6. Slice sequencing review

### 6.1 S1→S2 顺序

Plan §5（S1 producer contracts）→ §6（S2 read/tool/LLM projection）顺序合理：
1. S1 先消除 producer 的内部诊断字段（locator、method/empty reasons、total）
2. S2 再建立单一 public projection

两 slice 之间的 full-pyright exact propagation ledger 机制（§5.4）设计正确：S1 不需要绿色 pyright，但必须精确登记每个诊断到对应的 S2 owner/action。这避免了"S2 会修"的无追踪承诺。

### 6.2 中间 commit 策略

Plan §5.6 和 §6.9 明确不做中间 commit——S1 与 S2 是同一次破坏性 contract cutover，中间 commit 会把旧 public consumer + 新 producer 组合声明为可接受历史状态。策略正确。

### 6.3 DS-RR-01 的 sequencing 影响

见 §4 DS-RR-01。这是本 review 发现的唯一 sequencing 规格缺陷：S1 验证门命令未与 S1/S2 symbol boundary 保持一致。

## 7. Test/validation review

### 7.1 S1 tests

Plan §5.3 的 owner test 清单覆盖了：
- Financial exact keys、optional reason、七值闭集
- complete+reason / partial 无 reason / 未知 reason / 缺 essential field / 未知字段 → fail closed
- SEC/BS/6-K/HTML/OCR actual producers
- method absent→None→empty table→empty rows → `statement_not_found`
- XBRL exact keys、flat query params、zero-hit、partial reasons、all-concepts-failed error
- `fiscal_period` 共享 `FISCAL_PERIODS` 值集
- `min_value`/`max_value` bool 拒绝
- Producer 不输出 count
- Fiscal extraction 只消费新 validator

覆盖完整。✓

### 7.2 S2 tests

Plan §6.5 覆盖了：
- Public exact keys、producer→public 逐项相等
- 新类型名 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`
- Citation `Mapping[str, JsonValue]`→`dict[str, JsonValue]` 独立性
- Flat query params 精确复制
- `fiscal_period` enum 共享 owner
- Raw immutability (normalize/dedup 不修改 producer payload)
- 唯一 `fact_count` 只有一个 builder 赋值 owner
- Tool description 自足性
- 真实 AAPL XBRL + HTML + no-statement smoke

真实 smoke 复用现有仓储构造（`test_fins_storage_provider.py`），不引入简化 fake。✓

### 7.3 Coverage 门

Plan §5.4 和 §6.6 要求逐文件 line coverage ≥ 80%，不用 aggregate 掩盖低文件。Coverage 命令使用 `--include` 限定 production paths，正确。

## 8. LLM-facing review

### 8.1 Tool description 当前状态

当前 `fins_tools.py:977-983` 的 `query_xbrl_facts` description：
- 暴露 `total`（去重前原始 fact 数）和 `deduped_fact_count`（去重后数量）→ 内部诊断事实泄漏到 LLM
- 不符合 CLAUDE.md "不得把系统状态、调度状态、Host / Engine 内部治理信息伪装成财报事实"

当前 `fins_tools.py:900-907` 的 `get_financial_statement` description：
- 已自足说明字段、类型、允许值
- 缺少 reason 矩阵（七个 reason 的业务含义和下一动作）

Plan §4.4 的修复策略正确：从 `result_types.py` 单一 owner 派生 description metadata/helper，包含完整的七值 reason 矩阵。✓

### 8.2 Tool schema

当前 `fins_tools.py:1748` 的 `query_xbrl_facts.fiscal_period` 缺少 `enum` → plan 要求从 `FISCAL_PERIODS` 同源派生。✓

当前 `fins_tools.py:1749` 的 `min_value`/`max_value` 使用 `type: number` → plan 保持并配合 callable bool 拒绝。✓

### 8.3 最小示例

Plan §4.4 的 XBRL 示例使用 `SEC_EDGAR`（已通过 R08-PF-04 修正），满足 `fact_count == len(facts)` 等式。不暴露 processor 类名、method 状态、raw count、dedupe diagnostic。✓

## 9. 自相矛盾与 scope review

### 9.1 内部一致性

| 检查项 | Plan 位置 A | Plan 位置 B | 一致性 |
|---|---|---|---|
| 七值 reason 闭集 vs failure table | §3.1 lines 89-97 | §4.1 lines 195-203 | ✓ 完全匹配 |
| `fact_count` 唯一赋值 owner | §4.3 line 279 | §6.5 line 556 | ✓ 只一处 `len(returned_facts_copy)` |
| XBRL zero-hit 语义 | §4.2 line 235 | §6.3 line 532 | ✓ `facts=[]`、`fact_count=0`、`data_quality=xbrl` |
| `fiscal_period` 缺席不补 `None` | §4.2 line 231 | §4.4 line 311 | ✓ 多处一致 |
| `_build_financials_payload` 删除 | §3.4 line 150 | §5.2 line 382 | ✓ 只删除，不重构 |
| Host truncation stop rule | §6.4 line 543 | §8 line 711 | ✓ 一致 |
| S1 不做中间 commit | §5.6 line 466 | §6.9 line 671 | ✓ 一致 |

### 9.2 Scope 合规

Plan §2.3 out-of-scope 列表与当前 plan 内容一致：
- R09-R12、Issues 142/151/175/177/178、统一 authorization 均未触及 ✓
- R07 identity/snapshot/revision/citation/provenance owner 均列为 no-touch ✓
- `dayu/config/prompts/**` 不在修改 allowlist，只在 negative scan 中检查 ✓

### 9.3 Rejected paths absence

Controller 拒绝的路径在 fixed plan 中均缺席：
- `_build_financials_payload` 未被重构为 production path ✓
- 未增加第二 complete/partial 示例 ✓
- 未修改 `Citation` dataclass 或建 `PublicCitation` ✓
- 未引入 compatibility alias/re-export/wrapper/shim ✓
- 未修改 Host、R07 snapshot/citation owner ✓
- 未偷带 R09-R12、deferred Issues、统一 authorization ✓

## 10. 当前代码事实核验汇总

以下 plan 声称的关键事实已经过直接代码阅读核验：

| Plan 声称 | 当前代码证据 | 核验 |
|---|---|---|
| `_build_financials_payload` 无 production caller | `sec_fiscal_fields.py:95` 仅定义，全仓 production grep 零 caller | ✓ |
| `processor_error:` / `invalid_statement_result` 只在此 dead owner | `sec_fiscal_fields.py:115,128` 仅在 `_build_financials_payload` 内部 | ✓ |
| `filters_applied` 嵌套 shape | `sec_processor.py:716-726` 构建嵌套 dict；`bs_report_form_common.py:303-313` 同样 | ✓ |
| `total=len(facts)` 本地派生 | `sec_processor.py:756`；`bs_report_form_common.py` 类似 | ✓ |
| `build_statement_locator` 多 processor 引用 | `sec_xbrl_query.py:269` 定义，5 个 processor 文件 import+call | ✓ |
| `FiscalPeriod` TypeAlias = `Literal["FY","H1","Q1","Q2","Q3","Q4"]` | `filing_semantics.py:35` | ✓ |
| `FISCAL_PERIODS` frozenset | `filing_semantics.py:79-80` | ✓ |
| `SourceType.SEC_EDGAR` 是 SEC citation source_type 真源 | `read_runtime.py:148-155` mapping 到 `SourceType.SEC_EDGAR` | ✓ |
| `query_xbrl_facts.fiscal_period` schema 当前无 enum | `fins_tools.py:1748` 只有 `"type": "string"` + description 举例 | ✓ |
| 6 个 S2 test nodes 存在于 test 文件 | `tests/fins/test_fins_read_runtime.py:96-266` | ✓ |
| S1 test node 存在于 test 文件 | `tests/fins/test_fins_read_runtime.py:269-290` | ✓ |

全部核验通过。

## 11. Open questions

无。所有 plan 声称已通过与当前代码的交叉核验。

## 12. Residual risks

| 风险 | 跟踪 |
|---|---|
| Host generic truncation 不原子更新 `fact_count` sibling 字段 | Plan §6.4 已识别，stop rule 已明确。后续需在 S2 implementation 中按 §6.4 执行验证或 stop。R08 不修 Host。 |
| S1 full-pyright ledger 可能包含非预声明 propagation（需 Controller 逐条核验） | Plan §5.4 已规定 ledger 格式和两路 reviewer 核对义务 |
| `_FINANCIAL_STATEMENT_REASONS` frozenset 需随 TypeAlias 同步缩减到 7 值 | 隐含于 §3.1 + §4.1，实施 Agent 易遗漏，建议 S1 implementation checklist 显式列出 |

## 13. Final plan review conclusion

**PASS with 1 medium + 1 low material finding / 0 blocker**

- R08-PF-01..07：7/7 closed
- 新 material findings：2（DS-RR-01 Medium、DS-RR-02 Low）
- Deferred accepted finding：0
- Product blocker：0
- Controller rejected items 均未被重开

DS-RR-01 的修复只需调整 §5.4 一条 shell 命令（加 `-k` 过滤），不涉及架构/contract/类型变更，建议 Controller 在进入 S1 implementation 前裁决修复。DS-RR-02 为低严重度测试规格补充，可在 S2 implementation 阶段由 Controller 澄清。

本 review 未修改 plan/control/design/code/tests/README，未 stage/commit/push/PR。
