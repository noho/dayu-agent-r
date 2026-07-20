# WU-SEMANTIC-OWNERSHIP-01 P2-D Plan Review - AgentDS

## Review Scope

- **Work unit:** `WU-SEMANTIC-OWNERSHIP-01 P2-D`
- **Gate:** plan review (adversarial)
- **Reviewed artifacts:**
  - Plan: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-controller-validation.md`
- **Design sources:** `docs/host/design.md`, `docs/engine/design.md`
- **Control document:** `docs/host/issues-implementation-control.md`
- **Agent:** AgentDS

## Conclusion

**pass-with-findings**

Plan 动机成立、owner boundary 正确、实现路径最小、无过度设计或兼容性代码。3 个 finding（均为 LOW/MEDIUM），无 blocking finding。

---

## 1. 动机验证

### 1.1 故障是否真实存在

**通过。** 直接证据链充分：

- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 的 `second_terminal.kind is HostEventKind.FAILED`（plan  §"直接失败信号"）
- 回溯路径：`compact_material.py::_accepted_tool_evidence_delta_blocks`（line 2294）→ `run_input_material_block(... readable_source_text=projection.source.text)` → `RunInputMaterialBlock.__post_init__`（lines 327-330）对 `EVIDENCE_MATERIAL` section 要求 `readable_source_text` 非空
- `projection.source.text` 当前为 `None` 因为 `_source_projection(...)` 在 envelope 缺失或 visible business source refs 为空时返回 `text=None`（`accepted_result_projection.py` lines 612-629）

### 1.2 严重性判断是否正确

**通过。** Plan 正确判断这不是测试夹具问题。直接证据：

- `AcceptedToolResultSourceProjection.text` 类型为 `str | None`（line 115），docstring 写明"无业务 source 时为 `None`"——这是 projection contract 的语义决定，不是测试 fixture 构造的偶然
- `_source_projection(...)` 在两种场景返回 `text=None`：
  - envelope 缺失（line 612-615）
  - visible business source refs 为空（lines 623-629）
- Production 路径中，ToolRuntime 写入的 accepted evidence envelope 的 `source_refs` 和 `locator_refs` 可能为空（取决于工具实现），因此生产 compact material 可能命中同一路径

### 1.3 是否有更直接的 root cause

**通过。** Plan 识别的 root cause 准确：projection 对 query 已有 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 降级文案，但 source 只有 `state=UNAVAILABLE` 和 `diagnostic_reason` 而没有等价的 LLM-facing 文本。这是同一个 projection owner 内的半收紧 contract。

---

## 2. Owner Boundary 验证

### 2.1 语义所有者判定

**通过。**

| 阶段 | Owner | 判定 |
|---|---|---|
| 产生 | ToolRuntime / Host accept path → `TOOL_RESULT_ACCEPTED` durable truth | 正确 |
| 校验 | accepted evidence envelope 校验 producer ref / tool identity / result ref / digest | 正确 |
| 持久化 | `TOOL_RESULT_ACCEPTED` canonical EventLog row + payload descriptor / raw outcome | 正确 |
| 共享投影 | `project_accepted_tool_result(...)` | **正确——fix 必须落在此处** |
| 消费者 | compact material / Memory / RunInputBuilder / Tool Trace / Read API | 正确——只消费投影 |

### 2.2 为何不在 compact material 或 fixture 止血

Plan 的拒绝理由成立：

- test fixture 改 source refs → 只能让 smoke 通过，生产仍会复现（plan §"为什么不能在 test fixture 或 compact material 下游止血"）
- compact material 用 `projection.source.text or "..."` → 把 source-unavailable 所有权放到单个消费者，Memory / Tool Trace / Read API 会看到不同语义（违反 AGENTS.md "若多个消费者需要同一语义，必须抽取或复用同一个 source-of-truth"）
- compact material 用 event id / payload ref 伪造 source → 违反 LLM-facing 文本约束

### 2.3 为何收紧 projection 而不是新增 helper

Plan §"备选方案及拒绝理由" 充分：
- 新增 `source_text_for_llm(projection.source)` → 引入第二个 projection helper，所有消费者必须迁移，仍有漏点
- `AcceptedToolResultSourceProjection` 本身就是 source 投影值对象，直接收紧字段更小、更一致

---

## 3. Contract 收紧验证：`text: str | None` → `text: str`

### 3.1 是否合理

**通过。** 理由充分：

1. **与 query projection 对齐。** `AcceptedToolResultQueryProjection.text` 已是 `str`（line 101），source 应该一致。
2. **Consumer contract 已要求非空。** `CompactEvidenceBlock.readable_source_text` 是 `str`（`compaction.py` line 460）。`RunInputMaterialBlock.__post_init__` 对 evidence section 要求 `readable_source_text` 非空（lines 327-330）。projection 的 `str | None` 是 contract 不一致的根源。
3. **`state` + `diagnostic_reason` 已足够表达 unavailable。** 不需要用 `text=None` 作为额外信号。
4. **不涉及 durable schema。** `TOOL_RESULT_ACCEPTED` payload 结构不变，只改 projection 层。

### 3.2 是否造成不必要的 contract churn

**通过——但需注意以下 consumers 的 None-guard。**

已验证所有 `projection.source.text` 的直接消费者：

| 文件 | 行号 | 消费方式 | 影响 |
|---|---|---|---|
| `compact_material.py` | 2294 | `readable_source_text=projection.source.text` | **正受益——不再 crash** |
| `durable/memory.py` | 432 | `evidence_source_text=projection.source.text` | 值从 `str\|None` 变为 `str`；`_MemoryProjectionPayloadView.evidence_source_text` 类型为 `str\|None`，接受 `str` 无类型错误 |
| `durable/memory.py` | 453 | 同上 | 同上 |

间接消费者（通过 `RunInputMaterialBlock.readable_source_text`，类型仍为 `str | None`）：

| 文件 | 行号 | None-guard | 影响 |
|---|---|---|---|
| `run_input.py` | 3018-3019 | `if block.readable_source_text is not None:` | guard 仍有效（非 evidence block 可为 None），evidence block 始终通过 |
| `compact_pipeline.py` | 1121-1122 | 同上 | 同上 |
| `compact_material.py` | 2749-2750 | `if block.readable_source_text is None: raise` | evidence pack 断言始终通过 |
| `compact_material.py` | 3223 | `source_note=block.readable_source_text` | 值从 potential `None` 变为 always `str` for evidence blocks |

**无 contract churn 风险。** 下游的 `str | None` 类型域接受 `str` 是安全的协变。

---

## 4. LLM-facing 文案验证

### 4.1 提议文案审查

提议文案：
```
ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"
```

**通过。** 逐项验证：

| 检查项 | 结果 |
|---|---|
| 业务中性（不暗示工具结果无效） | ✓ "不可用"是状态说明，"未提供可安全展示的来源"解释原因，不评价结果质量 |
| 不暴露 event id | ✓ |
| 不暴露 payload ref / digest / cursor | ✓ |
| 不暴露 policy / ToolRuntime / Host governance | ✓ |
| 不自称"内部"、"系统"、"Host" | ✓ |
| 与 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 模式一致 | ✓ "查询语义不可用；参数未安全展开。" vs "业务来源不可用；工具结果未提供可安全展示的来源。" |

### 4.2 不暴露 internal refs 的验证

Plan 的 optional source scan（§"Optional source scan"）扫 `event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest` 在 projection 文件中的出现。**建议实施时也扫 `tests/host/test_accepted_result_projection.py`**，确认 unavailable source 测试断言不偶然引入这些 token。

---

## 5. Validation 覆盖验证

### 5.1 测试覆盖矩阵

| 被测消费者 | Plan 列出的测试 | 覆盖状态 |
|---|---|---|
| Compact material (pre-dispatch evidence block) | `test_compact_material.py` + 新增 focused test | ✓ |
| Compact material (evidence pack) | `test_public_compact_smoke.py` targeted smoke | ✓ |
| RunInputBuilder | `test_run_input_builder.py` | ✓ |
| Conversation Memory | `test_memory_projection.py` | ✓ |
| Tool Trace / Read API | `test_tool_trace_projection.py` / `test_tool_trace_queries.py` | ✓ |
| Direct projection | `test_accepted_result_projection.py` | ✓ |
| Pyright | 全量 | ✓ |

### 5.2 Missing consumer inventory

**DS-F01 (MEDIUM):** Plan 的 "Affected Files / Modules" 未列出 `dayu/host/durable/memory.py`。该文件在 lines 432 和 453 直接消费 `projection.source.text` 并赋值给 `_MemoryProjectionPayloadView.evidence_source_text`。虽然不需要修改该文件（`str | None` 接受 `str` 值无类型错误），但 plan 的 consumer inventory 应将其列为"需验证无行为变更的受影响消费者"。Plan 已覆盖 `tests/host/test_memory_projection.py` 测试，但 production file 盘点不完整可能让 implementer 漏掉 memory projection 路径的 propagation audit。

**最小修复：** Plan §"Affected Files / Modules" 的 Production 列表增加 `dayu/host/durable/memory.py`，标注"无需行为修改；验证 evidence_source_text 从 `None` 变为 unavailable 文案后 memory 投影仍一致"。

### 5.3 Tool Trace 覆盖

Plan 对 tool trace 的处理正确：如现有 trace summary 暴露 source 文本，更新或补充断言；若只暴露 state / refs，确认不需要修改。这是合理的分场景处理。

---

## 6. README 触发判断

**通过。** Plan 的 README 判断符合 AGENTS.md 触发规则：

- `dayu/host/` production 修改 → 触发 `dayu/host/README.md` 检查。Plan 正确判断现有 README 已记录 accepted tool result 统一投影，预计无需更新
- `tests/` 修改 → 触发 `tests/README.md` 检查。Plan 正确判断不新增测试层级，预计无需更新
- 不触及根 README、`dayu/README.md`、设计真源更新

**DS-F02 (LOW):** 如果新增的 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 成为一个稳定的 public constant（被测试和文档引用），建议在 `dayu/host/README.md` 的 accepted result projection 相关章节补一行说明。Plan 自身已在 §"README / Docs Decision" 表达了"可做最小补充"的意图，与 finding 方向一致。此 finding 仅是提醒 implementer 在 closeout 时做最终判断。

---

## 7. 过度设计 / 兼容性代码 / 下游补丁风险

### 7.1 过度设计

**无。** 方案是最小改动：一个常量 + 类型从 `str | None` 改为 `str` + `_source_projection(...)` 两个 unavailable 分支改为返回常量文本。不新增抽象层、不新增模块、不新增 schema。

### 7.2 兼容性代码

**无。** Plan 明确声明：
- "不修改 durable `TOOL_RESULT_ACCEPTED` schema，不迁移旧库，不兼容旧 source 语义"（§"Non-goals" #1）
- 唯一向后不兼容的变更是测试断言从 `is None` 改为 `== ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`——这是一次性 contract 迁移，不是兼容性分支

### 7.3 下游补丁 / 测试夹具掩盖

**无。** Plan 明确拒绝：
- 不在 test fixture 中补 source refs 来绕过 unavailable
- 不在 compact material 中用 `or "..."` 局部止血
- 不用 event id / payload ref 伪造 source

---

## 8. Propagation Audit 预判

Plan §"Propagation Audit" 的 6 段验证路径覆盖了从 durable truth → projection → compact material pack → compactor proposal → accepted compact fact → follow-up RunInput / memory / trace 的完整链路。每段都明确了"应看到什么、不应看到什么"。审核通过。

**建议实施后额外验证：** 在 `test_accepted_result_projection.py` 的 direct consumer equivalence test 中（plan §"Tests" 第 2 条），对 unavailable source 场景同时断言 `compact material evidence block`、`run input text`、`memory text`、`tool trace summary` 中的 source 文本都等于同一个常量引用（`is` 或 `== ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT`），而不仅仅是 `!= None`。这样能机械防止各消费者各自 hardcode 不同文案。

---

## 9. Implementation Slice 评估

Plan 建议单 slice（P2-D-S1），理由充分：
- 单字段 semantic contract 收紧
- Production 改动集中在 projection owner
- Tests 必须与 contract 同步（中间状态会在 pyright 或 consumer tests 中失败）
- 不涉及 durable schema / public API / Engine contract / 跨层装配

**通过。** 单 slice 合理，不会产生孤立半成品。

---

## Findings Summary

| ID | Severity | 位置 | 描述 | 最小修复 |
|---|---|---|---|---|
| DS-F01 | MEDIUM | Plan §"Affected Files / Modules" | Consumer inventory 缺 `dayu/host/durable/memory.py`（lines 432, 453 直接消费 `projection.source.text`） | Production 列表增加该文件，标注"无需行为修改；验证 evidence_source_text 从 `None` 变为 unavailable 文案后 memory 投影仍一致" |
| DS-F02 | LOW | Plan §"README / Docs Decision" | 新增 public constant `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 后，建议 README 做最小补充 | Implementation closeout 时判断是否需要补一行 constant 说明 |
| DS-F03 | LOW | Plan §"Validation Plan" | Optional source scan 建议同时覆盖 test 文件 | 在 source scan 命令中增加 `tests/host/test_accepted_result_projection.py`，或改为 rg 在 `dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py` 两个文件中扫描 |

**无 blocking finding。所有 finding 均为 LOW/MEDIUM，可在 implementation 或 closeout 阶段直接处理，无需重新进入 plan gate。**

---

## Reviewer Signature

- Agent: AgentDS
- Review type: adversarial plan review
- Conclusion: pass-with-findings
- Date: 2026-07-09
