# WU-OBS-SIGNALS-01 Plan Review

## Review Metadata

- **Work unit**: `WU-OBS-SIGNALS-01` (P01 + P02 + P03 + P04 combined)
- **Plan artifact**: `docs/host/wu-obs-signals-p01-p04-plan.md`
- **Review artifact**: `docs/reviews/wu-obs-signals-p01-p04-plan-review-ds.md`
- **Review date**: 2026-06-11T19:15:08
- **Design truth**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Review scope**: plan gate adversarial review — plan correctness, completeness, architecture boundary respect, slice specificity, code-generation readiness

## Reviewed Target and Scope

This review assesses whether `docs/host/wu-obs-signals-p01-p04-plan.md` is code-generation-ready for the four combined signal contracts P01 context pressure, P02 tool latency, P03 structured failure metadata, and P04 partial tool-call summary. The review does not assess the implementation itself (no implementation exists), nor does it judge WU-OBS-00 analyzer design.

## Assumptions Tested

1. **Assumption**: P01-P04 share the same data flow path and can be combined without overdesign.
   - **Verdict**: **Holds.** Verified by inspecting `_extract_tool_trace` (line 461), `_trace_summary` (line 1024), `_build_hot_row` (line 912), `_build_cold_line` (line 962), and `insert_tool_trace_hot_row_if_absent` (line 350). All four signals flow through the same extraction → summary → hot row / cold line path. No extra abstraction, new sink, or new schema is needed.

2. **Assumption**: Signal stable sources exist in current code and are not duplicated.
   - **Verdict**: **Holds.** Verified sources: P01 uses `BudgetEstimate` (`dayu/host/context_budget.py:168`), `_append_projection_signal` (`engine_ingest.py:2649`), and `context_events.py` canonical payloads. P02 uses `ToolResultMeta.started_at/finished_at` (`dayu/contracts/tool_result.py:26-37`). P03 uses `ToolResultFailure.error/hint` (`dayu/contracts/tool_result.py:78`), `ToolCancelledOutcome.reason/hint` (`dayu/contracts/tool_outcome.py:94`), `ToolPolicyDecision` (`tool_runtime.py:321`). P04 uses `PartialToolCallSummary` (`dayu/engine/contracts/partial_tool_call.py:11-28`). All sources are typed, validated, and single-owner.

3. **Assumption**: Architecture boundaries are enforced — Engine does not understand Host budget; Tool Trace is not durable truth; ToolRuntime accept/execution semantics do not change.
   - **Verdict**: **Holds.** Plan line 46-49 explicitly forbids these violations. Design docs confirm: Engine design §1 (line 17-24) says Engine doesn't own context budget policy; Host design §14.1 (line 1654) says Tool Trace is EventLog-derived projection, not durable truth; plan Non-goals (line 48) says no change to ToolRuntime accept semantics.

4. **Assumption**: `trace_summary` JSON shape is business-readable, self-explanatory, bounded/redacted.
   - **Verdict**: **Holds with concerns** (see Finding 1, Finding 2).

5. **Assumption**: No hidden schema migration, public contract change, state-machine change, extra payload, Any/object/untyped signatures, compatibility wrappers, or magic strings.
   - **Verdict**: **Holds with concerns** (see Finding 3, Finding 4).

6. **Assumption**: Slices are code-generation-ready.
   - **Verdict**: **Holds with concerns** (see Finding 5, Finding 6).

---

## Findings

### Finding 1 — 未修复 — 严重程度：高 — P03 failure_metadata 对 tool_cancelled 映射不清

- **位置**: plan OBS-SIG-03 (line 388-412), P03 JSON shape (line 257-271)
- **问题类型**: 契约缺失
- **当前写法**: Plan line 268 shows `failure_kind` 示例值为 `"tool_failed"`，但 line 398 说 "Add `failure_metadata` to `TOOL_RESULT_ACCEPTED` payload for failed, cancelled, and governed-policy outcomes"。对于 `tool_cancelled`，plan 未给出对应的 `failure_kind` 枚举值和 shape 变体。
- **反例/失败场景**: `ToolCancelledOutcome` 有 `reason`（`ToolCancelledReason` 枚举）、`message`、`hint`、`meta`，与 `ToolResultFailure.error` 字段完全不同。若 implementation agent 强行用 `error_code` 字段承载 `cancel_reason`，analyzer 将无法区分工具级取消和工具失败；若 implementation agent 自行发明 `failure_kind="tool_cancelled"` 和相应 shape，则 plan 未对此 shape 做设计决策。
- **为什么有问题**: 工具取消语义不等同于工具失败（`tool_outcome.py:96-102` 明确说 "取消终态不计入连续失败工具批次计数"）。将 cancel reason 塞进 `error_code` 或把 cancelled 当作 `tool_failed` variant 处理，会使 analyzer 无法正确区分取消与失败，影响后续的可恢复性判断。
- **直接证据**: `dayu/contracts/tool_outcome.py:94-115` 定义了 `ToolCancelledOutcome` 的字段，`dayu/host/tool_runtime.py:286-291` 定义了 `ToolFactKind.CANCELLED = "cancelled"`，证明取消是独立事实类别。Plan line 257-271 的示例 shape 使用 `"tool_failed"` 且包含 `error_code` 字段，无法直接映射 `ToolCancelledOutcome`。
- **影响**: implementation agent 需自行设计 cancelled 映射，可能做出错误假设，导致 P03 信号与事实语义不一致。
- **建议改法和验证点**: 在 P03 shape 中显式增加 `failure_kind="tool_cancelled"` 变体，字段包含 `cancel_reason`（从 `ToolCancelledOutcome.reason` 取值）、`cancel_message`（bounded）、`cancel_hint`（bounded/truncated）。测试需断言 cancelled outcome 产出正确的 `failure_kind` 和 `cancel_reason`，且 analyzer fixture 可区分取消与失败。
- **修复风险（低）**: 只需补充 shape 文档和一条规则，不影响其它设计决策。
- **严重程度（高）**: 语义错误会传播到 analyzer，导致不可恢复的分类错误。

---

### Finding 2 — 未修复 — 严重程度：中 — P01 compaction context_pressure shape 未覆盖 CONTEXT_COMPACTION_ATTEMPT_REJECTED

- **位置**: plan OBS-SIG-01 P01 compaction shape (line 187-204), context compaction rule (line 279-280)
- **问题类型**: 契约缺失
- **当前写法**: Plan line 187-204 给出 `signal_source="CONTEXT_COMPACTION_FAILED"` 的 `context_pressure` shape，P03 line 279-280 提到 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的 `failure_metadata` 规则。但 P01 的 `context_pressure` 只给了 COMPACTION_FAILED 一种 shape；ATTEMPT_REJECTED 是否也需要 `context_pressure` 未说明。
- **反例/失败场景**: Attempt rejected 是 compaction operation 内的中间生命周期事件，它携带 `failure_category`、`repairable`、`next_policy_decision`、`budget_after_attempted_compact` 等字段 (`context_events.py:145-154`)。如果 P01 不为其提供 `context_pressure`，analyzer 在扫描 trace 时会看到 FAILED 行有 `context_pressure` 而 ATTEMPT_REJECTED 行没有，造成信号不一致。若 implementation agent 自行决定是否为 ATTEMPT_REJECTED 生成 `context_pressure`，结果不确定。
- **为什么有问题**: ATTEMPT_REJECTED 包含 `budget_after_attempted_compact` 和 `next_policy_decision`——这些恰是 analyzer 需要追踪的预算决策链路。缺信号会迫使 analyzer 回退到 context_events payload 解析。
- **直接证据**: `dayu/host/context_events.py:145-154` 定义 `ATTEMPT_REJECTED_REQUIRED_FIELDS` 包含 `budget_after_attempted_compact`、`next_policy_decision`、`failure_category`、`repairable`。Plan line 279 提到 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的 failure_metadata 规则，但 P01 节未提及。
- **影响**: implementation agent 可能遗漏 ATTEMPT_REJECTED 的 P01 信号，导致 analyzer 的预算追踪不完整。
- **建议改法和验证点**: 显式决定 ATTEMPT_REJECTED 是否需要独立 `context_pressure` shape。若需要，补充其 shape（字段可比 COMPACTION_FAILED 精简，重点暴露 `budget_after_attempted_compact`、`next_policy_decision`、`failure_category`）。若不需要，在 non-goals 中显式声明并由 analyzer 从其它行推导。
- **修复风险（低）**: 需补充设计决策，不改变代码结构。
- **严重程度（中）**: 信号覆盖缺口不会导致错误数据，但会使 analyzer 被迫做额外 payload 解析。

---

### Finding 3 — 未修复 — 严重程度：中 — `_trace_summary` 签名扩展方式未指定，可能导致 God function

- **位置**: plan OBS-SIG-00 (line 322-340), 当前 `_trace_summary` 签名 (line 1024-1041)
- **问题类型**: 最佳实践偏离 / 过度耦合
- **当前写法**: Plan line 328 说 "Extend `_trace_summary` signature to accept these optional mappings." 当前 `_trace_summary` 已有 15 个 keyword-only 参数和 1 个 positional 参数（`tool_trace.py:1024-1041`）。Plan 要加 4 个 (`context_pressure`, `tool_timing`, `failure_metadata`, `partial_tool_call_signal`)。
- **反例/失败场景**: 19 参数函数在实现和维护中易出错——新增参数位置错误、调用方漏传、类型标注遗漏。CLAUDE.md "编码硬约束" 明确禁止 "God function"。
- **为什么有问题**: 方案执行上可行但违反了项目编码纪律。Plan 应该预见到此问题并给出结构化的解决方案（例如将 4 个新对象包装为一个 `_TraceSummarySignalFields` dataclass 或直接并入 `_ToolTraceExtract`），而不是把设计决策推给 implementation agent。
- **直接证据**: `dayu/host/tool_trace.py:1024-1041` 当前 15 参数签名；CLAUDE.md "禁止 God function" 约束。Plan line 328 仅说 "Extend signature" 未说明如何避免 God function。
- **影响**: implementation agent 可能因 plan 未指定而选择直接加参数，导致工具 trace 模块出现 God function。后续维护者再重构成本更高。
- **建议改法和验证点**: 二选一：(a) 将 4 个新信号对象放入 `_ToolTraceExtract` dataclass，`_trace_summary` 从 extract 中读取；(b) 定义一个 `TraceSummarySignalFields` dataclass 作为 `_trace_summary` 的单一参数。方案 (a) 更自然，因为 extract 已经是 trace_summary 构造的输入聚合点。测试只需验证 extract 中的信号字段正确投影到 summary JSON。
- **修复风险（低）**: 不影响 logic，只调整数据流封装方式。
- **严重程度（中）**: 导致 God function，违反编码纪律，增加维护成本。

---

### Finding 4 — 未修复 — 严重程度：中 — P03 `failure_metadata` 的统一 shape 有过度耦合风险

- **位置**: plan P03 JSON shape (line 256-271), OBS-SIG-03 (line 388-412)
- **问题类型**: 过度耦合
- **当前写法**: Plan 用一个 `failure_metadata` object 统一承载 tool failure、policy block、provider protocol error、context compaction failure 四类不同语义的失败。不同来源共享 `error_code`、`provider_error_code`、`repair_hint`、`policy_decision_kind`、`policy_block_reason` 等字段，但各来源只填充子集。
- **反例/失败场景**: Analyzer 消费 `failure_metadata` 时必须先读 `signal_source` 才知道哪些字段有效。例如 tool_failed 有 `error_code` 没 `policy_block_reason`，而 policy_blocked 恰恰相反。如果 analyzer 不加区分地阅读字段，会把 `error_code=null` 误读为 "无错误" 而非 "不适用"。更糟的是，future slice 若为其中一种来源新增字段，该字段会污染所有来源的 shape namespace。
- **为什么有问题**: 不同失败来源的语义不同，用同一 namespace 混合它们违反了 "不同概念不同 shape" 的最佳实践。Plan 的 `signal_source` 字段可做区分，但 JSON schema 层面的字段混合使 analyzer 的消费代码需要 if-else 分支或 discriminated union 解析。
- **直接证据**: Plan line 256-271 示例 shape 同时包含 `error_code`（tool failure 用）和 `policy_block_reason`（policy block 用）；line 279 增加 `failure_category`、`repairable` 等 compaction 专用字段。这些字段在 tool failure 场景无意义，但存在于同一个 JSON object namespace。
- **影响**: analyzer 消费复杂化和潜在的 misreading（把 null 当作信号）。长期维护风险：新增 failure source 时需要扩展同一个 object，无法独立演进。
- **建议改法和验证点**: 考虑将 `failure_metadata` 改为 discriminated union，每个 variant 只暴露其有意义的字段。若 unified shape 是刻意选择（为简化 analyzer 的初步分类），应在 plan 中显式记录此 tradeoff 和消费规则："analyzer 必须先读 `failure_kind`，再按 kind 分支读取有意义字段；`null` 字段表示该来源不适用该维度"。同时标注 failure_kind 为封闭枚举并在 plan 中列出全部允许值。
- **修复风险（中）**: 涉及 schema 设计决策，需要确认 analyzer 消费模型。
- **严重程度（中）**: 当前可工作但有演进风险，需要显式文档而非隐式约定。

---

### Finding 5 — 未修复 — 严重程度：低 — OBS-SIG-00 与后续 slice 的 `_trace_summary` caller 更新存在顺序依赖

- **位置**: plan OBS-SIG-00, OBS-SIG-01 至 OBS-SIG-04
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: OBS-SIG-00 line 329 说 "Update all `_trace_summary` callers to pass `None` until their slice populates values." 但 OBS-SIG-00 只是 foundation slice——它应该只加 signature 参数并设默认值 `None`，而不是修改具体 caller 的 payload 提取逻辑（那是 P01-P04 的工作）。
- **反例/失败场景**: 当前 `_trace_summary` 的 caller 是 `_extract_canonical_trace`（line 516）、`_extract_diagnostic_trace`（line 842）、`_extract_usage_trace`（line 892）。这些 caller 需要从其对应 payload 中提取新信号字段。OBS-SIG-00 说 "Update all `_trace_summary` callers to pass `None`" 是正确的 staging，但如果 implementation agent 误解为在 OBS-SIG-00 就需修改提取函数内部的 payload 读取逻辑，会导致边界混乱。
- **为什么有问题**: Plan 表述可能被误解。OBS-SIG-00 应只做 signature 扩展 + 默认值；payload 提取在 P01-P04 各自 slice 中完成。当前的文字 "Update all callers to pass None" 是准确的，但描述不够精确——应该说 "pass `None` for each new parameter" 以明确只传默认值，不做提取。
- **直接证据**: Plan line 328-329; `tool_trace.py:516`、`842`、`892` 三个 caller 位置。
- **影响**: implementation agent 可能做多余工作或做错边界。
- **建议改法和验证点**: 在 OBS-SIG-00 "Exact changes" 中澄清：只修改 `_trace_summary` 签名添加 4 个 `JsonValue | None = None` 参数，caller 调用处显式传递 `context_pressure=None, tool_timing=None, failure_metadata=None, partial_tool_call_signal=None`。不做任何 payload 提取逻辑。这样 P01-P04 各自 slice 只需修改对应 caller 的相应参数为非 None。
- **修复风险（低）**: 措辞澄清即可。
- **严重程度（低）**: 不影响可行性，但可减少实施摩擦。

---

### Finding 6 — 未修复 — 严重程度：低 — `repair_hint` bounding 规则缺少具体截断阈值

- **位置**: plan line 149, P03 line 396
- **问题类型**: 契约缺失
- **当前写法**: Plan line 149 说 "bounded text only for `repair_hint`; long text must be truncated with a digest or `truncated=true`." 但没有给出具体的最大字符数或字节数阈值。
- **反例/失败场景**: Implementation agent 需要决定 hint 截断阈值，可能选 200 chars、500 chars 或 1024 chars。不同选择导致不同 trace 行中 hint 的可用性不同。如果后续 analyzer 依赖 hint 做分类，threshold 不统一可能导致行为漂移。
- **为什么有问题**: "bounded" 是方向性约束，不是可实施的 code-generation spec。Implementation agent 需自行决定具体数字，这属于 plan 应完成的设计决策。
- **直接证据**: Plan line 149 说 "bounded text only for `repair_hint`"; 整个 plan 中没有 hint 截断阈值的具体数字。对比：`PartialToolCallSummary` 明确有 `PARTIAL_TOOL_CALL_ID_MAX_CHARS: int = 128`。
- **影响**: implementation agent 自行猜测阈值；跨 implementation agent 不一致（如后续有人修改）。
- **建议改法和验证点**: 指定 `repair_hint` 最大长度（例如 500 字符或 1024 字节），或引用现有 bounded text 常量。Plan 中已有 `truncated=true` 标记的设计，只需补充具体数字。
- **修复风险（低）**: 选一个合理值并文档化。
- **严重程度（低）**: 不影响核心逻辑，但会导致实现不一致。

---

### Finding 7 — 未修复 — 严重程度：低 — P01 `context_pressure` 的 `policy_ref` 是内部治理标识，plan 未注明其 LLM-facing 约束

- **位置**: plan P01 JSON shape line 167
- **问题类型**: 契约缺失
- **当前写法**: Plan line 167 的 P01 shape 包含 `"policy_ref": "policy-ref"`，未说明这是 Host 内部治理标识而非业务事实，也未说明 LLM-facing text 不得直接消费此字段。
- **反例/失败场景**: 如果 WU-OBS-00 analyzer 的 LLM prompt 中直接暴露 `policy_ref` 作为分类依据，LLM 会将其误解为有业务含义的标识。CLAUDE.md Agent 语义约束明确规定："内部治理标识如 label、id、ref、digest、cursor 只有任务必须引用时才可暴露；暴露时必须说明它只是引用标签，不是业务事实或推理依据。"
- **为什么有问题**: `policy_ref` 是 Host Context Governance 的 policy 引用，对 analyzer 而言只是溯源标签，不是预算决策的业务含义。不标注会违反 Agent 语义约束。
- **直接证据**: CLAUDE.md Agent 语义约束关于内部治理标识的规则；plan line 146-150 的 shared projection shape rules 说 "internal refs/digests may be present inside Tool Trace diagnostic material"，但没有逐个字段标注 LLM-facing 约束。
- **影响**: analyzer 可能错误地将 `policy_ref` 作为分类输入。
- **建议改法和验证点**: 在 P01 shape 文档中为 `policy_ref`、`estimator_digest`、`operation_id` 添加注释："诊断溯源标签，不作为 analyzer 业务分类输入"。
- **修复风险（低）**: 注释级修改。
- **严重程度（低）**: 文档完备性问题，不影响代码正确性。

---

## Open Questions

1. **OQ-1**: P01 compaction 的 `context_pressure` 是否需要为 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 提供独立 shape？建议在 implementation gate 前裁决。 → see Finding 2

2. **OQ-2**: P03 `failure_metadata` 的 unified vs discriminated-union shape 选择——plan 选择 unified 是否经过权衡？还是默认选择？若 unified 是刻意选择，建议在 plan 中记录 tradeoff。 → see Finding 4

3. **OQ-3**: `repair_hint` 的具体截断阈值是多少？应与现有 bounded text 策略一致。 → see Finding 6

## Residual Risks

| Risk | Owner/Destination | Notes |
| --- | --- | --- |
| `ToolResultMeta` optional → historical/third-party tools lack duration | P02 signal contract (handled: `status="missing_tool_result_meta"`) | Plan already classified this risk. Safe. |
| Context compaction events may not have every threshold field | P01 signal contract (stop-if-missing) | Plan has stop condition. Safe but stop should be tested early. |
| Provider partial arguments cannot prove JSON malformed | WU-OBS-00 analyzer | Plan correctly delegates. |
| `repair_hint` may contain long/sensitive text | P03 signal contract (truncate + flag) | Threshold unspecified (see Finding 6). |
| JSON fields in `trace_summary_json` not indexed → slow aggregation | WU-OBS-00 analyzer or future retention work | Plan correctly defers. |
| `_trace_summary` 参数膨胀 | OBS-SIG-00 implementation | See Finding 3. Mitigation: use `_ToolTraceExtract` as carrier. |
| Multiple extraction functions need modification for each signal | individual P01-P04 slices | Each slice modifies one or two extraction functions. Merge risk is low because signals are independent. |
| OBS-SIG-05 integration validation failure reveals design truth gap | Stop condition in OBS-SIG-05 | If tests fail, implementation must stop. This is correctly gated. |
| Cold JSONL schema drift from hot trace_summary | OBS-SIG-00 invariant check | `_build_cold_line` uses same extraction data. Test must assert identity. |

## Final Plan Review Conclusion

**Verdict: pass-with-risks**

The plan is structurally sound, well-aligned with design truth documents, and respects all architecture boundaries. All four signals share the same proven data flow path; combining them avoids duplicated infrastructure. The code evidence fully supports the plan's claims about existing stable sources.

Seven findings were identified, none blocking:
- **Finding 1 (high severity)**: P03 failure_metadata missing explicit `tool_cancelled` variant — needs shape completion before implementation.
- **Finding 2 (medium)**: P01 compaction context_pressure not covering ATTEMPT_REJECTED — design decision needed.
- **Finding 3 (medium)**: `_trace_summary` signature risks God function — structural mitigation available.
- **Finding 4 (medium)**: P03 unified failure_metadata shape has coupling risk — needs explicit tradeoff documentation.
- **Findings 5-7 (low)**: Clarifications and missing constants; do not block implementation.

All risks have owners or destinations. No unclassified risks. No hidden schema migrations, state-machine changes, Engine public contract changes, or ToolRuntime execution semantic changes.

### Validation Status

Validation (pytest + pyright) was **not run** — this is a plan review gate, not an implementation gate. Tests exist at the expected paths (`tests/host/test_tool_trace_projection.py`, `tests/host/test_tool_trace_queries.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_context_compact_events.py`), totaling 6,272 lines across four files.

### Blocking Open Questions

- Finding 1 should be resolved before implementation starts (P03 `tool_cancelled` shape).
- Finding 2 should be decided (ATTEMPT_REJECTED P01 treatment).
- Remaining findings can be resolved during implementation without plan amendment.

---

*Review completed 2026-06-11T19:15:08. No plan files, control documents, or code were modified.*
