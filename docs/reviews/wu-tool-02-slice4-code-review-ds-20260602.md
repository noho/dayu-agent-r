# WU-TOOL-02 Slice 4 Code Review — AgentDS

## 审查范围

Slice 4 `EventLog payload consumers regression 与 README/doc sync`。重点审查：
- Slice 4 未修改 production/test/README 是否合理，是否遗漏 `ToolFactAcceptCandidate` flat field consumer。
- `tool_trace` / `memory` / `compaction_evidence` / `compact_material` 是否只消费 committed EventLog payload。
- README/doc sync decision 是否符合 AGENTS.md。
- validation coverage 是否足以支撑 Slice 4 验收。

## 审查真源

- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/host-core-followup-implementation-control.md`
- Approved plan：`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Slice 4 implementation handoff：`docs/reviews/wu-tool-02-slice4-implementation-handoff-20260602.md`
- Slice 4 implementation report：`docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`
- 代码真源：当前分支 `refactor/wu-tool-02-accept-candidate-cleanup` 的实际文件内容

---

## Findings

### No blocking findings

---

### Finding DS-01 (Low): `rg` regex pattern 不能覆盖间接 flat field 消费路径

**证据**：

Slice 4 handoff 指定的 `rg` 命令（`docs/reviews/wu-tool-02-slice4-implementation-handoff-20260602.md:55`）使用的正则 `candidate\.(session_id|run_id|...)` 只能匹配形如 `candidate.session_id` 的直接属性访问。它无法捕获以下模式：
- 先将 candidate 字段赋值给局部变量再使用（如 `sid = candidate.session_id`）
- 通过 `getattr(candidate, "session_id")` 动态访问
- 在 f-string 或 format 中嵌入（如 `f"{candidate.session_id}"`，虽然该模式实际上会被 `candidate\.` 捕获）

**风险说明**：该 `rg` 是辅助检查，handoff 和 plan 均明确将其定位为不能替代 pyright 的辅助手段。pyright（0 errors）和 121 个 payload consumer regression tests（全部通过）才是 Slice 4 的主要证明。`rg` 覆盖盲区不构成 correctness 风险。

**裁决**：不要求修复。当前三层证据（pyright + regression tests + rg 人工判读）足以支撑 Slice 4 验收。

---

### Finding DS-02 (Low): Slice 4 验证范围按 plan 限定，未覆盖全仓

**证据**：

- Slice 4 implementation report（`docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md:61`）明确记录："本 slice 只覆盖 handoff 指定的 payload consumer tests 与 production consumer pyright 范围；未运行全仓 pytest 或全量 pyright，这属于后续 aggregate gate 范围"。
- Approved plan Slice 5（`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md:392-411`）明确将全量 pytest + 全量 pyright 作为 aggregate verification 步骤。

**风险说明**：Slice 4 范围外的测试（如 `test_toolruntime_accept_barrier.py`、`test_toolruntime_executor.py` 等）可能存在与 Slice 4 消费路径的交互问题，但按 plan 设计这属于 Slice 5 aggregate gate。Slice 4 的 121 passed + 0 pyright errors 覆盖了所有 handoff 指定的验证命令。

**裁决**：不要求修复。Slice 4 scope 符合 approved plan。

---

### Finding DS-03 (Info): `dayu/host/waiting.py` 中 `ToolAwaitingAcceptCandidate` flat field 访问不在 scope 内

**证据**：

`rg` 命中全部集中在 `dayu/host/waiting.py`（`docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md:40-43`）：
- `dayu/host/waiting.py:431-436`：读取 `candidate.session_id`、`candidate.run_id` 等 —— 这些是 `ToolAwaitingAcceptCandidate` 的 flat 字段。
- `dayu/host/waiting.py:1716-1721`、`1735-1740`、`1753-1758`：同上。
- `tests/host/test_wait_awaiting_accept.py` 和 `tests/host/test_toolruntime_executor.py` 的命中：awaiting accept 路径测试。

**风险说明**：Approved plan（`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md:156-158`）明确声明 awaiting candidate 不在本次结构拆分 scope 内，因为 `ToolAwaitingAcceptCandidate` 属于 wait/external job accept barrier，不是 `ToolFactAcceptCandidate` 的字段过宽问题。

**裁决**：不要求修复。这些 flat field 访问是 `ToolAwaitingAcceptCandidate` 的正确使用方式，不属于本 work unit 迁移遗漏。

---

## README / Doc Sync 裁决

**裁决：Slice 4 不更新任何 README 的决定正确，符合 AGENTS.md。**

**证据**：

1. `dayu/host/README.md`（`dayu/host/README.md`）已存在。其 ToolRuntime 章节（:219-239）描述的是 accept barrier、EventLog payload、wait、duplicate governance 的**稳定语义**，不描述内部 `ToolFactAcceptCandidate` 字段结构。本 work unit 未改变这些稳定语义，因此不触发 `dayu/host/README.md` 更新。

2. `tests/README.md`（`tests/README.md`）记录测试分层、运行方式和维护约定（如 `tests/README.md:186-187` 的 helper 约定）。本 Slice 未修改任何测试文件，未新增测试 helper 约定，未改变测试层级，因此不触发更新。

3. 根目录 `README.md`、`dayu/README.md` 不在 Slice 4 allowed scope 内（`docs/reviews/wu-tool-02-slice4-implementation-handoff-20260602.md:11-18`），且没有触发 AGENTS.md 定义的更新条件。

4. Approved plan 的 README/doc sync decision 章节（`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md:413-419`）明确：只有当 Host 开发手册描述了 ToolRuntime accept candidate 内部结构、或 tests helper 约定发生稳定变化时才更新。当前两项条件均不成立。

---

## Validation Coverage 裁决

**裁决：Slice 4 validation coverage 足以支撑验收。**

**证据矩阵**：

| 验证手段 | 范围 | 结果 | 证据 |
|---|---|---|---|
| pytest payload consumer regression | 5 个测试文件 | 121 passed | `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md:22`；独立复现确认 |
| pyright Host production consumers | 5 个 production 文件 | 0 errors | `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md:28`；独立复现确认 |
| rg flat field 辅助检查 | `dayu/` + `tests/` | 命中仅 awaiting 路径 | 独立复现确认 |
| 人工判读 | rg 全部命中 | 无误报为 ToolFactAcceptCandidate 遗漏 | 独立复现确认 |

**独立验证结果**：

```text
pytest: 121 passed in 0.48s
pyright: 0 errors, 0 warnings, 0 informations
rg dayu/host/: 命中仅 waiting.py（ToolAwaitingAcceptCandidate）
rg dayu/host/tool_runtime.py: 0 hits（迁移完成）
```

**覆盖分析**：

- Type safety：pyright 0 errors 证明 `tool_trace.py`、`memory.py`、`compaction_evidence.py`、`compact_material.py` 无类型错误。
- Payload schema：EventLog payload keys 经 `_tool_result_payload()`（`dayu/host/tool_runtime.py:3483-3531`）写入的 JSON key 名与迁移前一致，consumer 端通过相同的 key 名读取，不依赖 candidate 类型。
- Consumer isolation：四个 production consumer 文件均无 `ToolFactAcceptCandidate` 或子结构引用，只消费 committed EventLog payload 或 accepted evidence envelope。
- 全仓覆盖缺口：按 approved plan 属于 Slice 5 aggregate gate，不在 Slice 4 scope 内。

---

## Residual Risks / Uncovered Areas

| ID | 描述 | 严重性 | 处置 |
|---|---|---|---|
| RR-DS-S4-01 | Slice 4 只覆盖 handoff 指定的验证范围；未运行全仓 pytest 和全量 pyright | Low | Deferred to Slice 5 aggregate verification per approved plan |
| RR-DS-S4-02 | `rg` regex 不能证明不存在间接 flat field 消费，但 pyright + tests 已覆盖 | Info | Accepted as sufficient evidence; pyright is the primary proof |
| RR-DS-S4-03 | `dayu/host/waiting.py` 中 `ToolAwaitingAcceptCandidate` 仍使用 flat field 结构 | Info | Explicitly out of scope per approved plan; belongs to future awaiting hardening work unit |

---

## Final Verdict

**`pass`**

**理由**：

1. 四个 payload consumer production 文件（`tool_trace.py`、`memory.py`、`compaction_evidence.py`、`compact_material.py`）均无 `ToolFactAcceptCandidate` 或子结构引用，只消费 committed EventLog payload。直接代码证据确认。

2. `tool_runtime.py` 中无残留 old flat field `candidate.field_name` 访问。`rg` 在 `tool_runtime.py` 返回 0 hits。迁移完成。

3. EventLog payload keys（`_tool_result_payload()` 第 3483-3531 行）与迁移前一致。`accepted_evidence_envelope` 和 `raw_tool_outcome` payload 字段通过 `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE` 常量写入，consumer 端通过相同常量读取，语义稳定。

4. `ToolFactAcceptCandidate` 仅存在于 `dayu/host/tool_runtime.py`，不导出到 `__init__.py` 或任何其他模块。

5. 121 个 payload consumer regression tests 全部通过。pyright 0 errors。

6. README/doc sync decision 符合 AGENTS.md 触发规则。`dayu/host/README.md` 描述稳定语义（未变），`tests/README.md` 描述测试约定（未变）。

7. 三个 findings 均为 Low/Info 级别，无 blocking finding。
