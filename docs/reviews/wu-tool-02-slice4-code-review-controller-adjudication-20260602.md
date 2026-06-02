# WU-TOOL-02 Slice 4 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Slice: Slice 4 `EventLog payload consumers regression 与 README/doc sync`
- Review artifacts:
  - `docs/reviews/wu-tool-02-slice4-code-review-mimo-20260602.md`
  - `docs/reviews/wu-tool-02-slice4-code-review-ds-20260602.md`
- Implementation report: `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`
- Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

## Controller Summary

Slice 4 review 通过。AgentMiMo 与 AgentDS 均给出 `pass`，均未发现 blocking finding。两份 review 独立确认：

- `dayu/host/tool_trace.py`、`dayu/host/memory.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py` 不直接消费 `ToolFactAcceptCandidate`，仍只消费 committed EventLog payload / accepted evidence envelope。
- 旧 flat field `candidate.*` 辅助检查的剩余命中属于 `ToolAwaitingAcceptCandidate`，该 awaiting 路径已由 approved plan 明确排除在本次 `ToolFactAcceptCandidate` 结构拆分 scope 外。
- Slice 4 不修改 production、tests 或 README 的结论成立；README/doc sync decision 符合 AGENTS.md 中稳定文档职责与触发规则。
- 指定 payload consumer regression tests、指定 pyright 与人工判读足以支撑 Slice 4 验收；全仓 pytest 与全量 pyright 属于后续 aggregate verification gate。

## Finding Adjudication

### MiMo Finding 01: rg 辅助检查不覆盖 awaiting candidate 独立性确认

- Reviewer severity: informational
- Controller decision: accepted-as-note，不要求修复。
- 裁决依据：review 已用 `ToolAwaitingAcceptCandidate` 类型签名确认 `rg` 命中属于 wait / external job accept barrier，不是 `ToolFactAcceptCandidate` 遗漏。基于 design_doc 的 Host 强约束与 approved plan scope，当前最佳实践是保持 awaiting 路径不被本 work unit 顺手重构。

### MiMo Finding 02: 未运行全仓 pytest / 全量 pyright

- Reviewer severity: informational
- Controller decision: deferred-to-aggregate-gate，不要求 Slice 4 修复。
- 裁决依据：approved plan 明确 Slice 4 只验证 payload consumers，aggregate gate 再运行全仓验证。提前把全仓验证当作 Slice 4 blocking 会扩大 slice scope，削弱 phaseflow 的可独立验收边界。

### DS Finding 01: rg regex 不能覆盖间接 flat field 消费路径

- Reviewer severity: low
- Controller decision: accepted-as-note，不要求修复。
- 裁决依据：`rg` 在 handoff 中只是辅助检查；主要证明来自 pyright、payload consumer regression tests 和 reviewer 的直接代码核对。基于第一性原理，当前 risk 已由类型检查与行为回归覆盖到 Slice 4 的真实 consumer 边界，不需要为辅助 grep 扩展新的复杂扫描。

### DS Finding 02: Slice 4 验证范围按 plan 限定，未覆盖全仓

- Reviewer severity: low
- Controller decision: deferred-to-aggregate-gate，不要求 Slice 4 修复。
- 裁决依据：同 MiMo Finding 02；全仓 pytest / pyright 是 Slice 5 aggregate verification 的验收项。

### DS Finding 03: `ToolAwaitingAcceptCandidate` flat field 访问不在 scope 内

- Reviewer severity: informational
- Controller decision: accepted-as-note，不要求修复。
- 裁决依据：approved plan 明确 awaiting candidate 属于独立 wait accept barrier，不是当前 `ToolFactAcceptCandidate` 字段过宽问题。当前 phase 目标是最小化满足 accept fact candidate cleanup，不引入等待路径无关重构。

## Final Decision

Slice 4 code review pass。无 accepted blocking finding，无需 fix / re-review。下一步由 controller 运行 Slice 4 指定验证；验证通过后可接受 Slice 4 并进入 aggregate verification gate。
