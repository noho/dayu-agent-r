# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Review — AgentMiMo

## Review Metadata

- Reviewer: AgentMiMo
- Review gate: `plan review`
- Reviewed artifact: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Source finding truth: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` R3-D section
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-goal-confirmation.md`
- Review timestamp: 20260713-080259

## Motive And Owner Judgment

**动机成立。** 严重性评估正确：这不是 style/god-file cleanup，而是 production semantic ownership fix。

直接证据支持动机：

1. `financial_base.py:16-27`：`FinancialStatementResult` 的 `data_quality: NotRequired[str]` 和 `reason: NotRequired[str]` 是 optional，当 plan 正确指出它们应为 required。
2. `result_types.py:259-272`：`FinancialStatementResult` 使用 `total=False` + cast bridge，形成 shadow contract。
3. `result_types.py:307-316`：`XbrlQueryResult` 同样 `total=False` + cast bridge。
4. `read_runtime.py:236-249`：`_ProcessorFinancialStatementPayload` 是 `total=False` 的 shadow TypedDict。
5. `read_runtime.py:1639-1675`：read runtime 只投影 rows/currency/units/locator，丢弃 periods/scale/data_quality/reason。
6. `sec_xbrl_query.py:483-486`：catch-all `except Exception: continue` 把异常转为空成功。
7. `read_runtime_helpers.py:1017-1036`：`_infer_fiscal_year` 忽略 `fiscal_period` 参数，恒定返回 `None`。
8. `read_runtime.py:1023-1026`：`except Exception: pass` 吞掉 search/index 异常。
9. `fins_tools.py:853`、`fins_tools.py:923`：tool description 只有 "读取标准财务报表"/"查询结构化 XBRL 数值 facts"，不含输出字段说明。

Owner 判定正确：financial result/domain contracts → Fins processor/domain；read projection → read runtime/tool boundary；source freshness → storage/read cache。

## Findings

### 1-未修复-中-XBRL zero-row quality invariant 与 state matrix "legitimate empty success" 语义张力

- **位置**: Contract And Implementation Decisions §1 invariants "rows=[] 不可声明完整 xbrl/extracted"；§2 state matrix ">=1 concept execute success, 0 rows, 0 failures → data_quality=xbrl, reason=None"
- **问题类型**: 契约缺失 / 语义歧义
- **当前写法**: invariant 说 `rows=[]` 不能声明 `xbrl`；state matrix 说概念查询成功但无 facts 时 `data_quality=xbrl`。两处对 `xbrl` 质量的语义定义不同。
- **反例/失败场景**: 实现 agent 可能对 `get_financial_statement` 的 `rows=[]` 结果设 `data_quality=partial`（遵循 invariant），但对 `query_xbrl_facts` 的 `facts=[], total=0` 设 `data_quality=xbrl`（遵循 matrix）。LLM 看到两个不同 quality 对空数据的表达，可能混淆"XBRL extraction 成功但无数据"与"XBRL query 成功但无 facts"。
- **为什么有问题**: `FinancialDataQuality` 是跨两个工具共享的 domain type。如果 `xbrl` 在一个工具表示"有数据"，在另一个表示"查询成功但无数据"，LLM 无法仅靠 quality 字段做业务判断。
- **直接证据**: `filing_semantics.py:38-39` 定义 `FinancialDataQuality = Literal["xbrl", "partial", "extracted"]`，两个工具共享此 type；`sec_processor.py:646` 当前逻辑 `"data_quality": "xbrl" if rows else "partial"` 明确把空 rows 排除出 xbrl。
- **影响**: 实施 agent 可能在 `query_xbrl_facts` 对 `facts=[]` 使用 `data_quality=xbrl`，而 LLM 期望 `xbrl` 意味着有结构化数据。
- **建议改法和验证点**: 在 state matrix 中明确：`data_quality=xbrl` 只在 `total > 0` 时使用；`total=0` 的合法空集用 `data_quality=extracted`（表示"查询执行成功但无 facts"，区别于 `partial` 的"有降级"）。或者在 LLM-facing description 中显式说明 `xbrl` 在 `query_xbrl_facts` 中的语义是"查询成功"而非"有数据"。
- **修复风险**: 低
- **严重程度**: 中

### 2-未修复-中-XbrlQueryResult 新类型缺少 deduped_fact_count 的显式契约

- **位置**: Contract And Implementation Decisions §2 XbrlFactsResult type definition；§3 LLM-facing description "deduped_fact_count（若有）是展示去重数"
- **问题类型**: 契约缺失
- **当前写法**: `XbrlFactsResult` type 只有 `query_params/facts/total/data_quality/reason` 五个字段。LLM description 提到 `deduped_fact_count`（若有），但 type 定义中没有声明该字段。
- **反例/失败场景**: 实现 agent 可能把 `deduped_fact_count` 放进 extra payload 或 NotRequired 字段，但 plan 没有指定它是 Required 还是 NotRequired。如果实现 agent 认为它应该在 type 中，可能自行添加一个 NotRequired 字段，与 plan 的"所有字段 required"原则冲突。
- **为什么有问题**: `result_types.py:316` 当前有 `deduped_fact_count: int` 作为 NotRequired 字段。plan 要求消除 `total=False`，但没有说明 `deduped_fact_count` 在新 contract 中的定位。
- **直接证据**: `result_types.py:316`；plan §2 type definition 不含 `deduped_fact_count`；plan §3 LLM description 提到它。
- **影响**: 实施 agent 需要自行决定是否在 `XbrlFactsResult` 中包含该字段以及其 requiredness，可能导致不一致实现。
- **建议改法和验证点**: 在 `XbrlFactsResult` type definition 中显式声明 `deduped_fact_count: int | None`（required，None 表示未去重），或说明它不属于 domain contract 而属于 read projection 层。在 required assertions 中补充 round-trip 断言。
- **修复风险**: 低
- **严重程度**: 中

### 3-未修复-中-S2 cache revision race 的 rebuild retry 边界未指定

- **位置**: Contract And Implementation Decisions §4 "R1 != R2 时不缓存、不返回可能混合状态的 processor，抛 source_changed_during_read typed failure。调用方可重试，不做无界 rebuild loop"
- **问题类型**: 状态机漏洞 / 并发恢复风险
- **当前写法**: plan 说"调用方可重试，不做无界 rebuild loop"，但没有指定最大重试次数或 backoff 策略。
- **反例/失败场景**: 如果 source 在短时间内被频繁更新（例如多个 download pipeline 并发），每次 rebuild 都可能在 R1/R2 之间检测到变化，导致反复重试直到达到某个未指定的上限。
- **为什么有问题**: "不做无界 rebuild loop" 是正确的约束，但没有具体数字或策略，实施 agent 需要自行决定。
- **直接证据**: plan §4 cache contract "R1 != R2" 段落。
- **影响**: 实施 agent 可能实现 0 次重试（立即 fail）或 N 次重试（自行选择 N），导致行为不一致。
- **建议改法和验证点**: 指定最大重试次数（例如 2 次）或"立即 fail，不重试"。在 required assertions 中补充：连续 R1 != R2 时，第 N 次 fail 不再尝试 rebuild。
- **修复风险**: 低
- **严重程度**: 中

### 4-未修复-低-S1 tool description 更新范围未明确哪些字段需要在 description 中出现

- **位置**: Contract And Implementation Decisions §3 "fins_tools.py 两个 tool description 必须在当前 schema 文字内自足说明" followed by field list
- **问题类型**: 不可直接实施
- **当前写法**: plan 列出了 description 需要包含的字段说明，但没有提供示例文本或明确的 description 模板。实施 agent 需要自行编写 LLM-facing 文本。
- **反例/失败场景**: 实施 agent 可能写出过于简短的 description（只列字段名不解释语义），或过于冗长的 description（包含内部实现细节），或遗漏某些字段的 allowed values。
- **为什么有问题**: plan 的 AgentMiMo Focus checklist 要求"LLM-facing description 是否自足说明字段、类型、allowed values、scale-vs-units 和 partial reason"，但 plan 本身没有提供 description 示例文本。
- **直接证据**: plan §3 tool description requirements；current `fins_tools.py:853` description "读取标准财务报表" 只有 7 个字。
- **影响**: 实施 agent 编写的 description 可能不满足 LLM-facing 文本约束（CLAUDE.md），需要 review 返工。
- **建议改法和验证点**: 在 plan 中提供 `get_financial_statement` 和 `query_xbrl_facts` 的 description 示例文本，至少覆盖 periods/scale/data_quality/reason 四个字段的语义说明和 scale-vs-units 区分。
- **修复风险**: 低
- **严重程度**: 低

## Accepted Plan Strengths

1. **Owner boundary 清晰**: 每个 accepted finding 有唯一 owner，没有 read/tool/fixture fallback 修补 processor/storage 错误语义。
2. **Data-flow 方向正确**: processor → domain validator → read normalizer → result type → ToolResultSuccess/Failure → LLM description，每层只做校验/投影，不重算。
3. **Type safety 设计合理**: 新 domain contract 全部 required 字段，消除 `total=False`/cast/extra bag，使用 Literal type 而非 loose string。
4. **Quality/reason matrix 覆盖完整**: complete、partial、unavailable、valid empty、all failure 五类可唯一分辨。
5. **Slice 切分合理**: 3 slices 按 owner/validation/blast radius 切分，没有 one-finding-per-slice，依赖链清晰（S1 → S2 → S3）。
6. **Stop conditions 充分**: 每个 slice 有明确的停止条件，防止 scope creep。
7. **Tool-security/R3-E 明确 out of scope**: Hard Non-Goals 列表完整，没有把 upload/download security 放进 R3-D。
8. **Propagation scans 覆盖关键 patterns**: 扫描旧 shadow payload、NotRequired quality/reason、query catch-and-continue、duplicate scale map。
9. **Design truth 对齐**: 正确引用 `engine/design.md` 的 ToolResultSuccess/Failure 边界和 `host/design.md` 的 LLM-facing evidence self-explaining 要求。

## Blocking Questions

无。

所有 findings 为 non-blocking，实施 agent 可在实现过程中自行解决或在 review 阶段修复。

## Final Decision

**approved**

4 个 findings 均为中/低严重程度，不构成 blocking issue。plan 动机成立、owner 判定正确、data-flow 设计合理、slice 切分充分、stop conditions 完整。实施 agent 可以安全进入 implementation。
