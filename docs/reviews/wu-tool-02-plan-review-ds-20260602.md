# WU-TOOL-02 Plan Review — AgentDS

## 审查范围

- Plan artifact: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- 对照真源: `docs/host/design.md`、`docs/host/host-core-followup-implementation-control.md`
- 对照前置 artifact: `docs/reviews/wu-tool-02-discussion-code-inspection-20260602.md`、`docs/reviews/wu-tool-02-planning-handoff-20260602.md`
- 当前代码核对: `dayu/host/tool_runtime.py` (ToolFactAcceptCandidate, validation helpers, producer, consumer)、`tests/host/test_toolruntime_accept_barrier.py` (test helpers)

## 总体评估

Plan 整体 handoff-ready 且 code-generation-ready。动机判断成立，scope boundary 清晰，Hard Boundaries 与 design.md 的 ToolRuntime / accept barrier / EventLog / memory / compaction / tool trace 边界对齐正确。不引入兼容 facade、public API 泄漏、magic payload 或跨层依赖。Stop conditions 覆盖充分。

以下 findings 均为非阻断级别。无 blocking finding。

---

## Findings

### 01-未修复-MEDIUM-Slice 1 与 Slice 2 的 tool_runtime.py 同文件修改存在顺序冲突

**证据**：

- Slice 1 allowed files 包含 `dayu/host/tool_runtime.py`，步骤 2 为"将 `ToolFactAcceptCandidate` 顶层改为组合结构"。
- Slice 2 allowed files 同样包含 `dayu/host/tool_runtime.py`，步骤 1-2 迁移 `_tool_fact_accept_candidate()` 和 `_tool_fact_reuse_accept_candidate()` producer。
- Slice 1 non-goals 声明"不迁移 ToolRuntime executor producer"。
- Slice 1 验证命令包含 `pyright dayu/host/tool_runtime.py`。

**风险**：

`ToolFactAcceptCandidate` 从 flat fields（`candidate.session_id`、`candidate.tool_call_id` 等）变为 composite（`candidate.identity.session_id`、`candidate.call.tool_call_id`）后，同一文件内的 producer 函数 `_tool_fact_accept_candidate()` 和 `_tool_fact_reuse_accept_candidate()` 当前直接以关键字参数构造 flat candidate（参见 `tool_runtime.py:4675-4879` 区域的 producer 代码），Slice 1 完成后这些 producer 会立即类型失败。Slice 1 的 pyright 验证命令无法通过，除非：
- 将 Slice 1 和 Slice 2 的 `tool_runtime.py` 改动合并为一个 slice，或
- Slice 1 暂时保留旧 flat 字段作为 property facade（但 plan Hard Boundaries 明确禁止此做法）。

**建议**：

在 plan 中明确两种处理方式之一：
1. 合并 Slice 1 和 Slice 2 对 `tool_runtime.py` 的修改，Slice 1 即同时完成结构定义、validation、accept barrier reader 和 producer 迁移；Slice 2 仅处理 executor tests。或
2. Slice 1 只定义子结构 dataclass（不改变 `ToolFactAcceptCandidate` 顶层），Slice 2 再改 `ToolFactAcceptCandidate` 顶层 + producer 迁移。

当前 plan 表述下，implementation agent 会面临"Slice 1 验证不过，但 non-goals 说不该改 producer"的困境。

**Why**: `tool_runtime.py` 中 dataclass 定义、producer、consumer 共存于同一模块，结构变更的 blast radius 无法按 producer/consumer 边界拆分到不同 slice 而不产生中间 broken state。

**How to apply**: controller 裁决选择合并或重排后，更新 plan 对应 slice 的 allowed files、non-goals、步骤和验证命令。

---

### 02-未修复-LOW-ToolAcceptDiagnostics 单一字段子结构可能过度分解

**证据**：

- Plan 定义 `ToolAcceptDiagnostics` 仅含 `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]` 一个字段。
- 当前代码中 `diagnostic_refs` 是 `ToolFactAcceptCandidate` 的普通顶层字段，在 accept barrier、ack 构造、governed event payload 和 diagnostic logging 中直接读取。

**风险**：

单一字段的 frozen slots dataclass 不增加语义分组价值，但增加了一层属性访问间接（`candidate.diagnostics.diagnostic_refs` vs `candidate.diagnostic_refs`）。在 consumer 读取路径（ack 构造、governed payload、logging）中增加无谓嵌套。

**建议**：

Plan 已声明"命名可按实现局部微调，但职责边界必须保持"。建议 implementation agent 评估：若 `diagnostic_refs` 未来不会扩展为多字段子结构，将其保留为 `ToolFactAcceptCandidate` 的直接字段（与其他子结构并列），不作为独立 dataclass。

---

### 03-未修复-LOW-Slice 4 旧字段残留检测 rg 命令存在覆盖盲区

**证据**：

Plan Slice 4 步骤 4 的 grep 命令：
```bash
rg -n "candidate\.(session_id|run_id|...)" dayu tests
```
仅匹配字面量 `candidate.xxx` 模式。

**风险**：

以下模式不会被捕获：
- 变量重命名：`c.session_id`、`fact.session_id`
- 解构或 getattr：`getattr(obj, "session_id")`
- 测试中通过 `**kwargs` 展开构造

**建议**：

在 plan Slice 4 步骤中补充说明：该 grep 是最佳努力检测，不替代 pyright 类型检查。同时建议在 aggregate verification 阶段额外运行 `rg -n "\b(session_id|run_id|attempt_id|execution_id|iteration_id|tool_call_id|tool_name|tool_schema_digest|tool_identity_digest|normalized_arguments_digest|outcome_digest|payload_digest|raw_tool_outcome|duplicate_key|duplicate_decision|reuse_prior_event_refs|policy_decision|tool_idempotency_key|diagnostic_refs|accept_idempotency_key|semantic_input_digest|duplicate_scope|duplicate_decision_message)\b" dayu/host/tool_runtime.py --no-filename` 确认旧顶层字段名不存在于新 `ToolFactAcceptCandidate` 类体中（但允许存在于子结构类体、EventLog payload key 字符串和 docstring 中）。

---

### 04-未修复-LOW-Validation 分解粒度未明确

**证据**：

- 当前 `_validate_common_candidate_fields()` (line 3759) 混合校验 identity 字段（session_id, run_id, attempt_id, execution_id）、call 字段（iteration_id, tool_call_id, tool_name, tool_schema_digest, tool_identity_digest, normalized_arguments_digest）、idempotency 字段（accept_idempotency_key, semantic_input_digest）和 result 字段（payload_digest, payload_ref）。
- Plan 要求"公共 identity / call / idempotency / governance / duplicate / result 校验拆开，fact kind validator 只检查对应子结构"。

**风险**：

Implementation agent 需要自行决定每个子结构 `__post_init__` 的校验范围、跨子结构的约束（如 `payload_ref` 一致性）放在哪个 validator 中、以及 fact kind validator 如何复用子结构校验。这些决策影响测试覆盖边界，但 plan 未给出分解原则。

**建议**：

Plan 中补充一条校验分解原则："每个子结构的 `__post_init__` 只校验本结构内部字段 invariant；跨子结构约束（如 `result.payload_digest == result.payload_ref.payload_digest`）在 `ToolFactAcceptCandidate.__post_init__` 中校验；fact kind validator 只检查对应 fact kind 的子结构必填/禁止规则。" 不需要枚举每个 validator 的具体实现。

---

### 05-未修复-LOW-Fact Kind 校验规则章节过细节

**证据**：

"Fact Kind 字段归属与校验规则" 章节（Ordinary Result / Reuse / Plain Governed Error / Duplicate Governed Error）写了精确到字段级别的必填/禁止/等值约束，包括 `policy_decision.reason_code` 必须等于 `duplicate_decision_message` 等细粒度规则。这些内容更接近实现级 validator spec。

**风险**：

如果 implementation agent 在实现中发现某个校验规则需要微调（例如 policy_decision 和 duplicate 字段的对齐方式有边界情况），当前 plan 的细节程度可能导致 agent 犹豫是否可以调整，或误以为必须逐字实现。这不影响 code-generation-readiness，但可能增加不必要的往返沟通。

**建议**：

在 plan 中显式声明：Fact Kind 校验规则章节描述的是语义约束，不是逐行实现模板；implementation agent 可以在保持语义不变的前提下调整 validator 组织方式、错误消息和检查顺序。

---

## 设计文档对照检查

| 检查项 | 状态 |
|--------|------|
| ToolRuntime 边界（design.md §18.2）：工具事实必须走 Host accept barrier | ✓ Plan 明确不改变 accept barrier 语义 |
| ToolRuntime port 边界：Host tool fact accept port 独立于 dispatcher/policy/truncation/awaiting | ✓ Plan 只改 accept candidate 内部结构 |
| EventLog payload（design.md §13）：`TOOL_CALL_REQUESTED` / `TOOL_CALL_GOVERNED` / `TOOL_RESULT_ACCEPTED` payload key 不变 | ✓ Plan Hard Boundaries 和 Consumer 迁移路径均明确 |
| EventLog 幂等（design.md §13）：accept idempotency key scope 不变 | ✓ `ToolAcceptIdempotency` 保持 accept_idempotency_key + semantic_input_digest |
| Memory projection（design.md §26）：只消费 committed EventLog，不消费 candidate | ✓ memory.py 列为 read-only |
| Compaction evidence（design.md §26）：从 accepted evidence envelope + raw outcome 读取 | ✓ compaction_evidence.py / compact_material.py 列为 read-only |
| Tool trace：EventLog payload 诊断字段不变 | ✓ tool_trace.py 列为 read-only |
| Duplicate governance attempt-scope（design.md §18.3） | ✓ Plan 明确保持 attempt-local 语义不变 |
| Awaiting accept candidate（design.md §20） | ✓ Plan 明确 awaiting 不在 scope，`ToolAwaitingAcceptCandidate` 在独立 `waiting.py` |
| 禁止 public API 泄漏 | ✓ `ToolFactAcceptCandidate` 保持 Host 内部类型 |
| 禁止兼容 facade/re-export | ✓ Hard Boundaries 明确禁止 |
| 禁止 Any/object/无类型签名 | ✓ 所有子结构均要求严格类型 |

## AgentMiMo/AgentDS 并行全仓 review gate

Plan 已在 Slice 5 步骤 4 和 Review Gates 章节纳入 AgentMiMo 与 AgentDS 并行全仓 review 作为 ready-to-open-draft-PR 前置条件。该 gate 定位正确：不替代常规 slice review、aggregate deepreview、测试和 pyright。

## 结论

**Plan review pass** — 无 blocking finding。

Finding 01（slice 顺序冲突）是唯一需要 controller 裁决的中等严重项，建议在 plan 中明确 tool_runtime.py 的修改归属策略。其余 findings 均为 LOW，可在实现阶段自然消解，不需要 plan fix loop。

Implementation agent 可以直接按当前 plan 进入 implementation gate，但需在 Slice 1 开始前确认 Finding 01 的裁决结果。
