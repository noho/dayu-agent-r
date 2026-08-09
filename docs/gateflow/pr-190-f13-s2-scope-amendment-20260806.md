# PR 190 F13 S2 Scope Amendment

## Gate metadata

- work unit: F13 S2 — public Tool Trace 同源投影
- state: accepted
- base: `d4b3ee7cb4b959d88323483ffc430a595938b122`
- reason: review 发现 fresh summary contract 的 provenance 字段存在静默默认值

## 直接证据与 owner 裁决

`ToolTraceCompactorResponseSummary.accepted_evidence_facts` 是 resolver accepted
provenance tuple 的 exact pass-through 字段。它当前声明默认值 `()`；因此任何遗漏该参数的
accepted summary 构造都会静默把“未提供 provenance”改写为“合法的空 facts”。虽然当前生产
builder 显式传参，但 public typed contract 本身没有强制 owner 输入，违背 fresh contract 与
fail-closed 语义。

正确修复是删除默认值，强制所有构造方显式选择 accepted tuple 或 rejected empty tuple。唯一
受影响的非 S2 allowed file 是既有 runtime scenario assembly 中的 attempt-rejected expected
summary；它只需显式传 `accepted_evidence_facts=()`，不改变 scenario 行为或 production owner。

## Narrow scope addition

新增允许修改：

- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - 仅允许为现有 `ToolTraceCompactorResponseSummary` attempt-rejected 构造补充显式
    `accepted_evidence_facts=()`。

不允许借此修改 runtime smoke 语义、fixture、provider/tool、scenario acceptance 或其它文件。

## Review evidence

- AgentMiMo：`docs/reviews/pr-190-f13-s2-review-mimo-20260806.md` 的
  `Scope Amendment Re-review`，结论 `ACCEPTED`。
- AgentDS：`docs/reviews/pr-190-f13-s2-review-ds-20260806.md` 的
  `Scope Amendment Re-review`，结论 `ACCEPTED`。

## Validation addition

- 原 S2 focused tests；
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`；
- target/full pyright、changed-file Ruff、compileall、`git diff --check`。
