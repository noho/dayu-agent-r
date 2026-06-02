# WU-TOOL-02 Plan Review (AgentMiMo)

## 审查范围

- Plan artifact: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Design source: `docs/host/design.md`
- Control source: `docs/host/host-core-followup-implementation-control.md`
- Code inspection: `docs/reviews/wu-tool-02-discussion-code-inspection-20260602.md`
- Planning handoff: `docs/reviews/wu-tool-02-planning-handoff-20260602.md`
- Current branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Gate: plan review

## 审查结论

**Plan review pass，附 2 个非阻断观察。** Plan handoff-ready、code-generation-ready，implementation agent 可按 slices 直接执行，不需要重新设计结构边界、字段归属、file ownership 或测试矩阵。

## Findings

### 1-未修复-低-`ToolFactKind.LOST` 校验规则未显式声明

**当前写法**: Plan "Fact Kind 字段归属与校验规则" 章节只列了 `COMPLETED` / `FAILED` / `CANCELLED` / `GOVERNED_ERROR` / `REUSE` 五类 fact kind 的字段归属和校验规则，未提及 `ToolFactKind.LOST`。

**直接证据**:
- `dayu/host/tool_runtime.py:274` 定义了 `LOST = "lost"`。
- `ToolFactAcceptCandidate.__post_init__` (line 467) 的 else 分支会 raise `ValueError("unsupported tool_fact_kind")`，覆盖所有未列出的 kind。
- `_tool_fact_kind()` (line 4877) 当前不会返回 `LOST`；`LOST` 的构造路径在 resolve_wait / waiting 模块，不经过 `_tool_fact_accept_candidate()`。
- `ToolAwaitingAcceptCandidate` 定义在 `dayu/host/waiting.py:182`，是独立类型，不在本 work unit scope 内。

**反例/失败场景**: 如果 implementation agent 在重写 validation helper 时只按 plan 列出的五类 kind 实现分支，`LOST` 会落入 else 分支抛出 ValueError，行为与当前一致。但如果未来 resolve_wait 路径需要构造 `LOST` candidate，validation helper 需要补充对应规则。

**建议改法**: Plan 应在 "Fact Kind 字段归属与校验规则" 章节末尾补充一句："`ToolFactKind.LOST` 当前无生产构造路径（`_tool_fact_kind()` 不返回 LOST），validation helper 的 else 分支保持 raise ValueError；若未来 resolve_wait 路径需要构造 LOST candidate，需单独设计校验规则。" 验证：拆分后 validation helper 对 `LOST` 仍抛出 ValueError。

**严重程度**: 低。当前行为不变，但显式声明可避免 implementation agent 困惑。

### 2-未修复-低-`ToolAcceptResult` payload_ref/payload_digest 一致性约束措辞与当前代码不完全对齐

**当前写法**: Plan "Proposed Typed Structure" 中 `ToolAcceptResult` 约束写道："有 `payload_ref` 时 `payload_digest` 必须与 `payload_ref.payload_digest` 一致"。

**直接证据**:
- `_candidate_payload_descriptor_exists()` (line 2984) 只检查 payload descriptor 是否存在，不校验 `payload_digest` 与 `payload_ref.payload_digest` 的一致性。
- 当前 `ToolFactAcceptCandidate.__post_init__` 对 `COMPLETED` 校验 `payload_digest` 必须是 sha256 digest，但不校验它与 `payload_ref` 的一致性。

**反例/失败场景**: Implementation agent 如果按 plan 措辞在 `ToolAcceptResult` 的 `__post_init__` 中新增 `payload_ref.payload_digest == payload_digest` 校验，可能在现有测试中发现不一致的构造（如果存在），导致不必要的 validation 失败。

**建议改法**: 将措辞改为描述当前实际行为："`COMPLETED` 必须有 `payload_digest`；`payload_ref` 存在时由 `_candidate_payload_descriptor_exists()` 校验 descriptor 存在性"。一致性校验可作为未来增强，不纳入本 work unit。验证：拆分后 `COMPLETED` candidate 的 validation 行为与当前一致。

**严重程度**: 低。措辞不影响 implementation agent 正确实现，但精确描述可避免引入不必要的新校验。

## 对照 Checklist

### Design Doc 边界检查

| 检查项 | 结果 |
|---|---|
| ToolRuntime 行为不变 | 通过。Plan 明确不改变 dispatch、timeout、cancellation、truncation、fetch_more、accept retry 行为。 |
| Host accept barrier 语义不变 | 通过。EventLog event type、payload key、idempotency scope、accepted evidence envelope shape 均不变。 |
| EventLog durable payload 不变 | 通过。Hard boundary 明确约束。 |
| Memory / compaction 消费路径不变 | 通过。`memory.py`、`compaction_evidence.py`、`compact_material.py` 只消费 committed EventLog payload，不消费 candidate。 |
| Tool trace 边界不变 | 通过。`tool_trace.py` 消费 EventLog payload，不直接依赖 candidate 结构。 |
| Duplicate governance 语义不变 | 通过。字段只是从顶层移到 `ToolAcceptDuplicateGovernance` 子结构，校验规则不变。 |
| Evidence-backed fact 门槛不变 | 通过。Plan 明确声明。 |
| 不引入 public API | 通过。`ToolFactAcceptCandidate` 保持 Host 内部类型。 |
| 不引入兼容 wrapper / facade | 通过。Plan 明确禁止旧顶层字段 property。 |

### Control Doc 验收信号检查

| 验收信号 | 结果 |
|---|---|
| ToolRuntime、compaction、memory、tests 使用同一 candidate 类型 | 通过。Plan 保持 `ToolFactAcceptCandidate` 为唯一组合根。 |
| 类型检查不依赖 `object` / `Any` / magic payload | 通过。所有子结构使用严格类型。 |
| 测试 helper 不再手写超宽构造参数 | 通过。Plan 要求测试改为构造组合子结构。 |
| 无 god dataclass 回流 | 通过。7 个子结构职责清晰。 |

### Handoff Readiness 检查

| 检查项 | 结果 |
|---|---|
| 结构边界足够具体 | 通过。7 个子结构有明确字段列表和用途说明。 |
| 字段归属足够具体 | 通过。每类 fact kind 有独立字段归属和校验规则。 |
| File ownership 足够具体 | 通过。Production / Tests / Read-only / Documentation 四类 ownership 分离。 |
| 测试矩阵足够具体 | 通过。5 个 slice 各有 allowed files、预期断言和验证命令。 |
| 验证命令足够具体 | 通过。每个 slice 有 pytest + pyright 命令。 |
| Stop conditions 足够具体 | 通过。覆盖 public contract、durable schema、EventLog 语义、ToolRuntime 行为等关键场景。 |
| AgentMiMo / AgentDS 并行全仓 review 已纳入 | 通过。Plan Review Gates 和 Slice 5 均明确要求。 |

### 过度设计 / 过度耦合检查

| 检查项 | 结果 |
|---|---|
| 无过度设计 | 通过。7 个 frozen dataclass 直接映射现有字段分组，无抽象层。 |
| 无过度耦合 | 通过。子结构间无循环依赖，组合根保持扁平。 |
| 无旧字段兼容 facade | 通过。Plan 明确禁止。 |
| 无 public API 泄漏 | 通过。 |
| 无 payload/event 语义风险 | 通过。Hard boundary 约束 payload key 和 event type 不变。 |

### Slice 质量检查

| 检查项 | 结果 |
|---|---|
| Slice 沿代码依赖边界切分 | 通过。Slice 1 结构+validation → Slice 2 producer → Slice 3 duplicate/diagnostics → Slice 4 payload consumer → Slice 5 aggregate。 |
| 每个 slice 可独立验证 | 通过。每个 slice 有 pytest + pyright 命令。 |
| 不留下孤立半成品 | 通过。Slice 1 完成后 accept barrier 可独立运行；Slice 2 完成后 producer 可独立运行。 |
| 验证命令不会诱导 implementation 改变行为 | 通过。验证命令只运行测试和类型检查，不修改代码。 |
