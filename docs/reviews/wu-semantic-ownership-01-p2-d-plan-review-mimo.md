# WU-SEMANTIC-OWNERSHIP-01 P2-D Plan Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: plan
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-controller-validation.md`

## Review Dimensions

### 1. Motivation and Severity

**Verdict: 成立，严重性正确。**

直接代码证据确认 root cause 不是测试夹具过严：

- `dayu/host/accepted_result_projection.py:600-634` — `_source_projection()` 在 envelope 缺失或 visible business source refs 为空时返回 `text=None`，`state=UNAVAILABLE`。
- `dayu/host/compact_material.py:306-330` — `RunInputMaterialBlock.__post_init__()` 对 `EVIDENCE_MATERIAL` section 要求 `readable_source_text` 非空（`_require_non_empty_text`）。
- `dayu/host/compact_material.py:2271-2294` — `_accepted_tool_evidence_delta_blocks()` 直接传 `projection.source.text` 作为 `readable_source_text`。
- `tests/host/test_public_compact_smoke.py:371` — `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 在 second terminal 为 `FAILED`，因为 `RunInputMaterialBlock.__post_init__` 校验 `readable_source_text` 非空时抛出 `ValueError`。

这不是 fixture 过严。ToolRuntime 写入 `TOOL_RESULT_ACCEPTED` 时，普通 accepted tool result 的 `source_refs` 和 `locator_refs` 可以为空（无业务来源），这在 production compact material 路径同样会触发。

Controller notes 正确指出这一点。

### 2. Owner Boundary

**Verdict: 正确。**

- 语义：accepted tool evidence 的 LLM-facing source。
- 第一次产生事实：ToolRuntime / Host accept path 写入 `TOOL_RESULT_ACCEPTED` payload、accepted evidence envelope 和 raw outcome。
- 共享投影 owner：`dayu/host/accepted_result_projection.py::project_accepted_tool_result` 负责把 durable truth 投影成 LLM-safe query/status/source/result 语义。
- 下游消费者：compact material、RunInputBuilder、Conversation Memory、Tool Trace / Read API 只消费 projection。

query 投影已有先例：`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`（`accepted_result_projection.py:35`）在 request atom / semantic query 不可用时返回非空、业务中性、LLM-facing 文本。source 投影应遵循同一模式。

plan 正确拒绝了在 test fixture 或 compact material 下游止血的方案：

- test fixture 改 source refs 只能让 smoke 通过，production 路径仍会复现。
- compact material 用 `projection.source.text or "..."` 会把 source-unavailable 文案的所有权放到单个消费者，Memory / Tool Trace / Read API 仍会看到另一套语义。

### 3. `str | None` → `str` Tightening

**Verdict: 合理，但需确认一处下游 ripple。**

收紧理由成立：

- `CompactEvidenceBlock.readable_source_text` 已经是 `str`（`compaction.py:460`），不是 `str | None`。
- `RunInputMaterialBlock` 对 `EVIDENCE_MATERIAL` section 已要求 `readable_source_text` 非空（`compact_material.py:327-330`）。
- query projection 已使用同样模式：`text: str` + `state` + `diagnostic_reason`（`accepted_result_projection.py:92-103`）。
- 保留 `str | None` 会让每个消费者都必须判断 `None`，并倾向于局部 fallback。

需要确认的下游 ripple：

- `dayu/host/memory.py:988` — `evidence_source_text: str | None`。当 projection 返回 unavailable 文案时，`_evidence_memory_projection` 的 `if source_text is not None:` guard（`memory.py:1753`）仍为 True，会写入 `来源：业务来源不可用；...`。行为正确，但 memory field 的 docstring 可能需要同步更新，说明该字段在 projection owner 收紧后不再为 `None`。
- `dayu/host/compaction.py:460` — `CompactEvidenceBlock.readable_source_text: str` 已经是 required，无 ripple。

这不是 contract churn；它是把已有半收紧修正为完整收紧。受影响的类型签名只有 `AcceptedToolResultSourceProjection.text` 一处，且该类型是 internal projection view，不是 Host public API。

### 4. LLM-facing 文案

**Verdict: 业务中性、自解释。**

plan 提议的常量：
```python
ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"
```

逐项检查：

- 不暴露 `event_id`、`payload_ref`、`payload_digest`、`cursor`、`policy`、`ToolRuntime`、`Host governance` — 通过。
- 不暗示工具结果无效或工具执行失败 — "业务来源不可用" 是状态说明，不是错误结论 — 通过。
- 不伪装成财报事实、文档事实或工具结果事实 — 通过。
- 与现有 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT = "查询语义不可用；参数未安全展开。"` 风格一致 — 通过。
- 模型可以从该文案推断"这个 evidence block 的来源不可用，但工具结果本身仍然可用" — 语义正确。

### 5. Validation Coverage

**Verdict: 基本覆盖，有一处可补充。**

plan 列出的 validation 命令和 expected assertions 覆盖：

| 消费者 | 测试文件 | plan 覆盖 |
|---|---|---|
| accepted-result projection | `test_accepted_result_projection.py` | 是 |
| compact material | `test_compact_material.py` | 是 |
| RunInputBuilder | `test_run_input_builder.py` | 是 |
| Conversation Memory | `test_memory_projection.py` | 是 |
| Tool Trace | `test_tool_trace_projection.py` / `test_tool_trace_queries.py` | 是（conditional） |
| public compact smoke | `test_public_compact_smoke.py` | 是 |
| pyright | `pyright` | 是 |

可补充项：

- plan 的 Affected Files / Tests 列出了 `test_memory_projection.py`，但 validation plan 的 pytest 命令中没有包含它（第三条命令是 `test_compact_material.py test_run_input_builder.py test_memory_projection.py`，实际已包含 — 复查确认 OK）。
- Tool Trace 覆盖是 conditional："如现有 trace summary 暴露 source 文本，更新或补充 unavailable source 断言；若只暴露 state / refs，则确认不需要修改。" 这是合理的，因为 Tool Trace 的 source 展示取决于 trace summary 的当前 shape。

### 6. README Trigger Judgment

**Verdict: 足够。**

- `dayu/host/README.md` — plan 检查后预计无需更新，因为 README 已记录 accepted tool result 的 query/status/result/source 由 Host 统一投影。若 implementation 新增 public constant 并在开发者契约中稳定使用，可做最小补充。判断正确。
- `tests/README.md` — plan 检查后预计无需更新，因为只补充现有 Host 测试，不新增层级、运行方式或维护规则。判断正确。
- 不更新根 README、`dayu/README.md`、`docs/host/design.md` 或 `docs/engine/design.md` — 判断正确。

### 7. Over-engineering / Compatibility / Downstream Patch Risk

**Verdict: 无过度设计，无兼容性代码，无下游补丁风险。**

- 不引入新的抽象层、新的 schema、新的 projection helper 或新的 public API。
- 不修改 durable `TOOL_RESULT_ACCEPTED` schema。
- 不修改 compactor prompt、compact proposal schema 或 public API。
- 不在 compact material、RunInputBuilder、Memory、Tool Trace 或测试 fixture 内用特例分支补默认 source。
- `__all__` 更新（plan 提及）是 expected export maintenance。

## Findings

### F-01: Memory `evidence_source_text` docstring 同步 — Severity: LOW

**Finding:** `dayu/host/memory.py:988` 的 `evidence_source_text: str | None` docstring 写明"可选业务可读工具 source 文本"。当 projection owner 收紧后，该字段在正常路径下不再为 `None`（projection 始终返回 `str`）。虽然 memory consumer 的 `if source_text is not None:` guard 行为正确，但 docstring 可能误导开发者认为该字段仍可能为 `None`。

**Direct evidence:** `dayu/host/memory.py:988` — `evidence_source_text: str | None = None`，docstring 为"可选业务可读工具 source 文本"。

**Owner boundary:** 这不是 projection owner 的问题，而是 memory consumer 的 docstring 同步。memory field 类型保持 `str | None` 是合理的（初始构造或 fallback 路径仍可能为 `None`），但 docstring 应说明正常路径下该字段来自 projection 的 non-None source text。

**最小修复要求:** implementation 时检查 `memory.py` 的 `evidence_source_text` docstring 是否需要同步更新。若 memory field 类型保持 `str | None`，docstring 应补充说明正常 accepted-result 路径下该字段由 projection owner 保证非空。

**Severity classification:** LOW — 不影响行为正确性，不影响 LLM-facing 输出，不影响测试通过。纯 docstring 同步。

### F-02: Proposed source-unavailable 常量文本需确认中文语义 — Severity: INFO

**Finding:** plan 提议的 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"` 是业务中性的。但 "工具结果未提供可安全展示的来源" 中 "工具结果" 作为主语可能被模型误解为"工具结果本身有问题"。更中性的表述可以是 "工具执行未关联可展示的业务来源" 或 "该工具调用未提供可引用的业务来源"。

**Direct evidence:** plan `Recommended Implementation` 节。

**Owner boundary:** 文案常量在 projection owner 处定义。

**最小修复要求:** INFO 级别，不阻塞 plan。implementation agent 可选择保持 plan 提案或微调措辞，只要满足"业务中性、不暗示工具结果无效、不暴露内部治理字段"的约束即可。

**Severity classification:** INFO — 不影响 plan pass/fail 判断。

## Conclusion

**Pass。**

plan 动机成立、root cause 定位准确、owner boundary 正确、LLM-facing 文案业务中性、validation 覆盖完整、无过度设计或下游补丁风险。两个 findings 均为 LOW/INFO 级别，不阻塞 implementation gate。

| ID | Severity | Owner Boundary | 状态 |
|---|---|---|---|
| F-01 | LOW | memory consumer docstring 同步 | accepted，implementation 时检查 |
| F-02 | INFO | projection owner 文案措辞 | accepted，implementation agent 自行裁决 |
