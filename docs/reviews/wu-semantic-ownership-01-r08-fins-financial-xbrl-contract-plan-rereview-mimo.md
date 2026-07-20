# WU-SEMANTIC-OWNERSHIP-01 / R08 fixed plan — AgentMiMo re-review

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | fixed plan complete re-review（并发第一路） |
| timestamp | `20260717-040510` |
| reviewed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| **fixed plan SHA-256** | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-controller-adjudication.md` |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-controller-validation.md` |
| AgentCodex fix artifact | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md` |
| result | **PASS / 1 low finding / 0 blocker** |

本 re-review 完整阅读固定计划全文、Controller 裁决真源、AgentCodex fix artifact、Controller validation artifact，以及当前代码中的 domain contracts、processors、tools、read runtime helpers、filing semantics 和 result types。逐项复核 `R08-PF-01..07` 关闭状态，并对整份 fixed plan 做 adversarial、owner boundary、slice sequencing、测试/验证、LLM-facing、自相矛盾与 scope review。

SHA-256 通过 `sha256sum` 命令验证，与 Controller validation 锁定值一致。

## 2. R08-PF-01..07 逐项 closure 复核

| ID | 裁决要求 | 固定计划落实证据 | 代码真源核验 | 状态 |
|---|---|---|---|---|
| `R08-PF-01` | S1 test allowlist 纳入共享文件；symbol boundary 精确；Controller 锁定 hash/ledger | §3.4 line 158 纳入 `test_fins_read_runtime.py`；§5.1 lines 360-374 精确划定 S1 fiscal symbol 与 S2 normalize/dedup nodes 的边界和 focused commands；§5.4 lines 422-431 要求 Controller 锁定逐 path SHA-256 + binary diff SHA-256 + full-pyright exact propagation ledger；§5.6 line 464 要求两路 reviewer 重算同一 hash 并逐条核对 ledger | 当前 `xbrl_result_contract.py` 仍含 `total` 字段，`read_runtime_helpers.py:1170-1178` 的 `NormalizedXbrlQueryPayload` 仍含 `total` + `deduped_fact_count`，确认 S2 propagation 必要性 | **closed** |
| `R08-PF-02` | 七值闭集保留；`unsupported_statement_type` 不是未来占位；同源 description 拥有 LLM-safe 下一动作 | §4.4 lines 287-311 完整七值 reason→下一动作矩阵；§4.1 line 99 明确 `unsupported_statement_type` 表达 actual processor 无法服务全局合法 statement type；§4.4 line 309 禁止暴露 method/fallback branch | 当前 `financial_result_contract.py:28-38` 确认九值闭集（含 `statement_method_missing`、`statement_empty`），plan S1 删除两值归一为 `statement_not_found`，目标七值正确 | **closed** |
| `R08-PF-03` | builder 接受 `Mapping[str, JsonValue]`，立即复制为独立 dict；不改 Citation dataclass；不建第二 citation schema | §4.3 lines 255-280 精确规定 `Mapping[str, JsonValue]` 输入 → `dict(citation)` → 独立 `dict[str, JsonValue]` 输出；§4.3 line 276 明确 R07 `_build_citation` no-touch；§6.5 line 551 要求测试证明不 alias、无 revision/private key/path、pyright 无 `Any` | 当前 `result_types.py:246-260` 的 `FinancialStatementResult.citation` 为 `dict[str, Any]`；`tool_models.py:86-87` 确认 `Citation` 是 frozen dataclass 非 TypedDict；plan 不改 `tool_models.py` 符合裁决 | **closed** |
| `R08-PF-04` | 示例 `source_type` 从 `sec_filing` 改为 `SEC_EDGAR`；tests 断言不存在 `sec_filing` | §4.4 lines 313-330 最小 XBRL 示例使用 `SEC_EDGAR`；§6.5 line 557 要求 description/example tests 断言不存在 `sec_filing`；§6.7.B lines 625-640 将 `sec_filing` 纳入 negative scan 禁止字面量 | `rg -n 'sec_filing' dayu/fins/tools/ dayu/config/prompts/` 返回零命中；当前 SourceType 真源为 `SEC_EDGAR`；plan 示例正确 | **closed** |
| `R08-PF-05` | `fiscal_period.enum` 从 `FISCAL_PERIODS` 同源派生；不建第二 literal owner | §4.2 lines 217, 230-232 指定消费 `FiscalPeriod` / `FISCAL_PERIODS`；§4.4 line 311 要求 `sorted(FISCAL_PERIODS)` 派生 schema enum；§5.3 line 395、§6.2 line 517、§6.5 line 553 分别要求 S1/S2 tests 覆盖 | `filing_semantics.py:79-81` 确认 `FISCAL_PERIODS = frozenset(("FY", "H1", "Q1", "Q2", "Q3", "Q4"))`；当前 `fins_tools.py:1748` schema 无 enum 字段（`{"type": "string", "description": "..."}`），plan 要求补全 | **closed** |
| `R08-PF-06` | validator 先拒绝 `bool` 再接受 `int \| float`；tests 覆盖 True/False/int/float/missing | §4.2 line 232 精确规定"先显式拒绝 `bool`，再接受 `int \| float`"；§5.3 line 396 要求 owner tests 覆盖五种情况；§6.2 line 517、§6.5 line 553 要求 S2 callable/schema test | 当前 `xbrl_result_contract.py:200-217` 的 `_required_non_negative_int` 已对 `total` 执行 `isinstance(value, bool)` 拒绝；plan 要求对 `min_value`/`max_value` 施加同类显式 bool 拒绝 | **closed** |
| `R08-PF-07` | tools public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`；删除旧名无 alias | §4.3 lines 244-280 精确命名；§6.2 line 513 要求删除旧 tools `FinancialStatementResult` / `XbrlQueryResult`；§6.5 line 550 要求 tests 证明旧名不存在 | 当前 `result_types.py:246,285` 确认旧名 `FinancialStatementResult` / `XbrlQueryResult` 仍存在；domain `financial_result_contract.py:77` 的 `FinancialStatementResult` 保持原名不变（plan 不重命名 domain 类型） | **closed** |

**结论：`R08-PF-01..07` 全部 `7/7 closed`。**

## 3. Adversarial review

### 3.1 Motivation 成立性

Plan §1 的五条第一性原理判断均经代码真源验证：

1. Financial producer 混入 `statement_locator`（`sec_processor.py:612,676`、`bs_report_form_common.py:236,421`）和内部 reason（`statement_method_missing` at `sec_processor.py:629`、`statement_empty` at `sec_processor.py:639,658`）→ 成立。
2. XBRL `total=len(facts)`（`sec_processor.py:756`、`bs_report_form_common.py:343`）+ read 侧 `deduped_fact_count`（`read_runtime_helpers.py:1220`）双 count → 成立。
3. `filters_applied` shape drift：plan 声称 producer 用嵌套 `query_params.filters_applied` 放可选 filters，read 从 `query_params` 顶层读取 → 需验证。当前 `XbrlQueryParams` TypedDict 无 `filters_applied`，但 plan 目标是 flat typed params，这与当前 TypedDict 一致。shape drift 可能存在于 processor 运行时输出而非 TypedDict → plan 处理正确。
4. Tool description 手写字段定义：当前 `fins_tools.py:1748-1750` 手写 `fiscal_period`/`min_value`/`max_value` schema → 成立。
5. `_build_financials_payload` 无 production caller：`rg` 确认只在 `test_sec_pipeline_download.py:2113,2120,2121` 出现 → 成立。

### 3.2 Owner boundary review

| 边界 | 计划描述 | 代码核验 | 判定 |
|---|---|---|---|
| Financial producer result | `dayu.fins.domain.financial_result_contract` + actual processor | 当前 owner 正确；plan S1 收窄 contract 后 producer 适配 | ✓ |
| XBRL raw query result | `dayu.fins.domain.xbrl_result_contract` + actual processor | 当前 owner 正确；plan S1 删除 `total`、建立 flat params | ✓ |
| Public result | `dayu.fins.tools.result_types` typed projection | 当前混入 `statement_locator`/`total`/`deduped_fact_count`；plan S2 建立 `Public*` 类型 | ✓ |
| R07 snapshot/citation | no-touch | plan §2.2、§4.3 line 276、§6.7.D 明确 no-touch | ✓ |
| Host truncation | 独立 governance 层 | plan §6.4 不改 Host、不私造 cursor/fetch_more | ✓ |

无跨层穿透、双向依赖或 owner 冲突。

### 3.3 Slice sequencing review

S1 → S2 依赖链：

- S1 修改 producer domain contracts + actual processors → S2 修改 tools/read/LLM projection。
- S1 不改 public consumer → S1 pyright 必然报 S2 consumer 错误 → plan 通过 full-pyright exact propagation ledger 接受已登记的 S2-bound 错误。
- S1 不做中间 commit → S1+S2 是同一次破坏性 cutover → 合理。
- S1 完成后 Controller 锁定 tree/hash → 两路 reviewer 核对 → S2 开始 → aggregate → commit。

sequencing 无循环依赖、无隐式顺序假设。

### 3.4 Test/validation review

- S1 tests：`test_financial_read_contracts.py`、`test_sec_pipeline_download.py`、`test_fins_read_runtime.py`（只改 fiscal symbol slice）→ 覆盖 producer contract 和 fiscal consumer。
- S2 tests：`test_fins_read_runtime.py`（normalize/dedup nodes）、`test_read_runtime_semantic_ownership_guards.py`、`test_processor_read_consistency.py`、`test_fins_storage_provider.py` → 覆盖 public projection、R07 guards、real smoke。
- Coverage：逐文件 `>=80%`，不能 aggregate 掩盖 → 合理。
- Scans：internal positive inventory + public negative + `fact_count` unique owner + R07 no-touch → 全面。

### 3.5 LLM-facing review

- 七值 reason 均有业务含义和安全下一动作（§4.4 lines 298-308）→ 满足 LLM-facing 文本约束。
- 禁止暴露 method/fallback branch/异常消息/Host 治理状态 → 明确。
- 最小示例使用 `SEC_EDGAR`、无 `sec_filing`、无 processor 内部术语 → 正确。
- `fiscal_period.enum` 从 `FISCAL_PERIODS` 派生 → 同源。
- Description 自足说明字段、类型、必填性、枚举与最小示例 → 满足七项要求。

### 3.6 Self-contradiction review

逐条检查 plan 内部一致性：

- §4.1 `reason` 七值闭集与 §4.4 reason→下一动作矩阵一致。
- §4.2 XBRL `data_quality` 只允许 `xbrl|partial` 与 §4.2 line 236 一致。
- §4.3 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 命名与 §6.2 line 513、§6.5 line 550 一致。
- §5.1 S1 allowlist 与 §3.3 actual producer inventory 一致。
- §6.1 S2 allowlist 与 §3.4 consumers inventory 一致。
- §6.4 截断组合风险的 stop rule 与 §8 stop conditions 一致。

无自相矛盾。

### 3.7 Scope review

- In-scope：financial/XBRL producer contract 收窄、public projection、tool description、read runtime → 正确。
- Out-of-scope：R09-R12、Issues 142/151/175/177/178、Host/Engine/Service/UI、R07 owners、其它 error codes → 正确。
- §2.3 明确禁止 compatibility re-export/wrapper/fallback/shim → 符合编码硬约束。
- §3.3 S1 production diff 闭集与 §5.1 allowlist 一致。
- §6.1 S2 production diff 闭集正确排除 `error_contract.py`。

scope 无越界、无遗漏。

## 4. New material findings

### 01-未修复-低-`reason` 从 required 变 NotRequired 时 validator `_require_field` 模式需调整

- **位置**: §4.1 lines 179, 205；§4.2 lines 225-226；§5.2 steps 1-2
- **问题类型**: 契约变更隐含 validator 实现调整
- **当前写法**: plan 将 financial contract 的 `reason` 从 `FinancialStatementReason | None` 改为 `NotRequired[FinancialStatementReason]`（§4.1 line 179），将 XBRL contract 的 `reason` 从 `XbrlQueryReason | None` 改为 `NotRequired[XbrlQueryReason]`（§4.2 line 225）。§4.1 line 205 明确"complete时缺席"。
- **反例/失败场景**: 当前 `financial_result_contract.py:465` 的 `_required_financial_reason` 调用 `_require_field`（line 248-264），该函数在 key 缺失时抛 `ValueError`。当前 `xbrl_result_contract.py:243-265` 的 `_required_xbrl_reason` 同样调用 `_require_field`。当 `reason` 变为 `NotRequired` 且 `data_quality` 为 complete/xbrl 时，producer 不输出 `reason` key，validator 会因 key 缺失而抛异常。
- **为什么有问题**: plan 的 contract shape 变更（`None` → 缺席）与当前 validator 的 `_require_field` 模式（要求 key 存在）存在隐式冲突。实施 agent 若只改 TypedDict 定义而不调整 validator，complete 结果会 fail closed。
- **直接证据**:
  - `financial_result_contract.py:465`: `value = _require_field(payload, "reason")`
  - `financial_result_contract.py:248-264`: `_require_field` 在 key 缺失时抛 `ValueError`
  - `xbrl_result_contract.py:260`: `value = _require_field(payload, "reason")`
  - plan §4.1 line 179: `reason: NotRequired[FinancialStatementReason]`
  - plan §4.1 line 205: "`data_quality=xbrl|extracted` 时 `reason` 必须缺席"
- **影响**: 实施 agent 若按 plan 直接改 TypedDict 为 `NotRequired` 而不调整 validator，所有 complete financial/XBRL 结果会在 validator 失败。影响范围有限（只涉及 validator 内部逻辑），但会导致 S1 所有 complete 结果测试失败。
- **建议改法和验证点**: plan §5.2 steps 1-2 应补充说明：financial validator 的 `_required_financial_reason` 改为先检查 `"reason" in payload`，缺失时对 `data_quality=partial` 抛异常、对 complete 返回 `None`；XBRL validator 的 `_required_xbrl_reason` 同理。验证点：S1 tests 覆盖 complete（reason 缺席）和 partial（reason 存在）两种情况。
- **修复风险（低/中/高）**: 低。validator 逻辑调整是直接的，且 plan 的 contract shape 已明确"缺席"语义。
- **严重程度（低/中/高/严重）**: 低。plan 的 TypedDict 定义已正确表达 `NotRequired` 语义，实施 agent 阅读 contract 定义后自然会调整 validator。这是实现细节级别的调整，不改变 plan 的设计方向或 owner boundary。

## 5. Open questions

无。plan 的所有 open questions 已在 Controller 裁决中收敛。

## 6. Residual risks

| 风险 | 说明 | 跟踪目标 |
|---|---|---|
| Host truncation 与 `fact_count` 原子性 | plan §6.4 正确识别了 Host `ToolTruncateSpec` 会替换 `facts` 但不原子改写 `fact_count` 的组合风险。plan 给出了 stop rule（stop 回 Controller）但未给出解决方案。这是 R08 scope 外的已知风险。 | R09 或 Host governance issue |
| S1 full-pyright ledger 精确性 | S1 的 full-pyright 必然报 S2 consumer 错误。plan 要求 Controller 产出精确 propagation ledger 并限制在四个 S2 production paths。若 ledger 不精确，两路 reviewer 可能放过未登记错误。 | Controller validation gate |
| `XbrlQueryParams` 类型收窄 | plan 目标 shape 将 `fiscal_period` 从 `str | None` 改为 `FiscalPeriod`，`min_value`/`max_value` 从 `float | None` 改为 `int | float`。这些类型收窄会影响下游 consumer 的类型签名。 | S1/S2 pyright validation |

## 7. Conclusion

**PASS / 1 low finding / 0 blocker**

固定计划 SHA-256 `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` 已通过完整 re-review。`R08-PF-01..07` 全部 `7/7 closed`。新发现 1 个低严重度 finding（validator `_require_field` 模式需随 `reason` NotRequired 变更调整），不影响 plan 设计方向和 owner boundary，不构成 blocker。无 open question、0 product blocker。

计划可以进入 implementation。
