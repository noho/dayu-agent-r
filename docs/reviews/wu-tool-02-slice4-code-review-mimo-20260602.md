# WU-TOOL-02 Slice 4 Code Review — AgentMiMo

## Review Inputs

- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/host-core-followup-implementation-control.md`
- Approved plan：`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Slice 4 implementation handoff：`docs/reviews/wu-tool-02-slice4-implementation-handoff-20260602.md`
- Slice 4 implementation report：`docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`
- 当前分支：`refactor/wu-tool-02-accept-candidate-cleanup`

## Findings

No blocking findings。

### Finding 01 — Non-blocking: rg 辅助检查不覆盖 awaiting candidate 独立性确认

- **Severity**: informational
- **证据**: implementation report 声明 `waiting.py`、`test_wait_awaiting_accept.py`、`test_toolruntime_executor.py` 中的 `rg` 命中属于 `ToolAwaitingAcceptCandidate`（awaiting 路径），不是 `ToolFactAcceptCandidate`。reviewer 独立验证：
  - `dayu/host/waiting.py:375` — `accept_tool_awaiting(self, candidate: ToolAwaitingAcceptCandidate)`；全部 `candidate.*` 命中均在 `ToolAwaitingAcceptCandidate` 类型上下文中。
  - `tests/host/test_toolruntime_executor.py:422` — `candidate: ToolAwaitingAcceptCandidate`；行 428-429 的 `candidate.run_id` / `candidate.attempt_id` 读取属于 awaiting fake port。
  - `tests/host/test_wait_awaiting_accept.py` — 同样全部命中在 awaiting candidate 构造。
- **风险**: 无。人工判读正确。
- **建议**: 无需修复。可选改进：在 implementation report 中增加一行显式说明"rg 命中文件均经类型签名确认属于 `ToolAwaitingAcceptCandidate`，不是 `ToolFactAcceptCandidate`"，使 review 证据链更完整。

### Finding 02 — Non-blocking: 未运行全仓 pytest / 全量 pyright

- **Severity**: informational
- **证据**: implementation report 明确声明"未运行全仓 pytest 或全量 pyright，这属于后续 aggregate gate 范围"。Slice 4 handoff 只要求运行指定的 5 个 payload consumer tests 和 5 个 production consumer 文件的 pyright。
- **风险**: 无。这符合 plan Slice 4 的 scope 定义。全量验证由 Slice 5 aggregate verification 负责。
- **建议**: 无需修复。

## 重点审查裁决

### 1. Slice 4 未修改 production / test / README 是否合理

**裁决：合理。**

直接证据：

1. **Production consumers 不直接依赖 `ToolFactAcceptCandidate`**：reviewer 对 `dayu/host/tool_trace.py`、`dayu/host/memory.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py` 执行 grep 搜索 `ToolFactAcceptCandidate` 及所有 flat candidate 字段模式，结果为零命中。这四个文件只消费 committed EventLog payload（`TOOL_RESULT_ACCEPTED` 的 cursor / payload），不消费 accept candidate 本身。

2. **rg 命中全部属于 awaiting 路径**：`dayu/host/waiting.py` 中的 `candidate.*` 读取全部是 `ToolAwaitingAcceptCandidate`（类签名在 `waiting.py:182`），属于 wait / external job accept barrier，不在本 work unit scope 内（plan 明确声明 "awaiting 路径不在本次结构拆分 scope 内"）。

3. **Tests 未修改合理**：payload consumer tests（`test_tool_trace_projection.py`、`test_tool_trace_queries.py`、`test_memory_projection.py`、`test_compaction_operation.py`、`test_llm_compaction.py`）测试的是 committed EventLog payload 的 projection / query / compaction 行为，不构造 `ToolFactAcceptCandidate`。121 passed 证明 payload 语义未变。

### 2. ToolFactAcceptCandidate flat field consumer 遗漏检查

**裁决：无遗漏。**

- `dayu/host/tool_runtime.py` 中的 `ToolFactAcceptCandidate` 已在 Slice 1-3 重构为组合结构（`identity`、`call`、`result`、`governance`、`idempotency`、`diagnostics`）。
- 所有 producer（`_tool_fact_accept_candidate()`、`_tool_fact_reuse_accept_candidate()`）和 accept barrier consumer 已在 Slice 2 迁移到组合结构读取。
- Slice 4 的 payload consumer files 从不读取 candidate 字段，只读取 EventLog payload。
- rg 辅助检查覆盖了所有旧 flat 字段名在 `dayu/` 和 `tests/` 目录下的残留，命中均经人工判读确认为 awaiting 路径或非 `ToolFactAcceptCandidate` 对象。

### 3. tool_trace / memory / compaction 是否只消费 committed EventLog payload

**裁决：是。**

- `dayu/host/tool_trace.py`：零 `ToolFactAcceptCandidate` 引用。tool trace hot / cold projection schema 由 committed `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` payload 驱动。
- `dayu/host/memory.py`：零 `ToolFactAcceptCandidate` 引用。memory projection 对 `TOOL_RESULT_ACCEPTED` 的事实生成门槛未改变；assistant final answer / raw accepted tool evidence 仍不自动成为 evidence-backed fact。
- `dayu/host/compaction_evidence.py`：零 `ToolFactAcceptCandidate` 引用。accepted evidence envelope 从 committed EventLog payload 读取。
- `dayu/host/compact_material.py`：零 `ToolFactAcceptCandidate` 引用。compaction material 按 accepted envelope + raw outcome 读取，fail-closed 行为未变。

### 4. README / Doc Sync Decision 裁决

**裁决：符合 AGENTS.md 触发规则，不更新合理。**

- `dayu/host/README.md`：reviewer 确认该文件不包含 `ToolFactAcceptCandidate`、`ToolAcceptIdentity`、`ToolAcceptCall` 等内部结构名称。README 描述的是 ToolRuntime accept barrier、EventLog payload、Memory 与 Context Compaction 的稳定语义，本 slice 未改变这些稳定语义。按 AGENTS.md 触发规则，"Host 内部 ToolRuntime accept candidate 结构"不属于 README 职责范围内的稳定事实。
- `tests/README.md`：reviewer 确认该文件只记录测试分层、运行方式与维护约定。其中 "candidate" 出现在通用测试覆盖描述中（如 "fact candidate"），不描述内部 helper 结构名。本 slice 未新增测试层级、运行命令或稳定 helper 约定。
- 根目录 `README.md`、`dayu/README.md`、`docs/host/design.md`、总控文档：不在 Slice 4 allowed scope，无触发更新条件。

### 5. Validation Coverage 裁决

**裁决：足以支撑 Slice 4 验收。**

Slice 4 的验证目标是证明 committed EventLog payload consumers 在 candidate 组合结构迁移后保持不变。验证手段三重覆盖：

1. **Payload consumer regression tests**（121 passed）：覆盖 tool trace projection / queries、memory projection、compaction operation、LLM compaction 五个 consumer 测试文件，证明 payload key、projection schema、memory fact 门槛、compaction fail-closed 行为未变。
2. **Production consumer pyright**（0 errors）：覆盖 `tool_runtime.py`、`tool_trace.py`、`compaction_evidence.py`、`compact_material.py`、`memory.py`，证明类型签名一致。
3. **rg 辅助检查 + 人工判读**：覆盖所有旧 flat field 名称在 dayu / tests 目录下的残留，确认无 `ToolFactAcceptCandidate` flat field 遗漏读取。

Slice 4 不需要验证 accept barrier 语义、duplicate governance、reuse 路径或 validation 逻辑——这些由 Slice 1-3 的 focused tests 覆盖。

## Residual Risks / Uncovered Areas

- 全仓 pytest 和全量 pyright 未在本 slice 运行，属于 Slice 5 aggregate verification scope。
- rg 是字符串辅助检查，不能替代类型检查证明。本 review 以指定 pyright、payload consumer regression tests 和 rg 人工判读共同作为 Slice 4 证据，与 implementation report 一致。

## Final Verdict

**pass**

Slice 4 implementation 符合 approved plan 和项目约束。Production consumers 确认只消费 committed EventLog payload，不直接依赖 `ToolFactAcceptCandidate`。未修改 production / test / README 合理，无遗漏 flat field consumer。Validation coverage 足以支撑本 slice 验收。
