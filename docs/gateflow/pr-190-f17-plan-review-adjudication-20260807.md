# PR 190 F17 Plan Review Adjudication

## Review inputs

- AgentMiMo：`docs/reviews/plan-review-20260807-143241.md`，结论 `pass`，无 findings。
- AgentDS：`docs/reviews/plan-review-20260807-143636.md`，结论 `pass`，3 个低严重度 findings。

两路均独立复现 production FIRST strict singleton mismatch，确认 inventory 为 5/43/16、
owner chain 与 two-hunk scope 正确，并独立推演保存后的 manifest digest 为
`064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`。该值仍只作
交叉检查，implementation 必须从保存后的 raw bytes 重新计算。

## Finding adjudication

### F17-P1：pre-state dirty check 缺少显式 stop condition

- 裁决：`accepted`
- 理由：plan 已要求保护 existing dirty work，但实施步骤应把它操作化。修订时必须允许本 work unit
  已知的 Goal/Plan/Review/Adjudication artifacts，同时规定任何其它 dirty path 都立即停止；不得要求
  删除或覆盖既有 evidence。
- Owner：AgentCodex plan fix。

### F17-P2：旧 digest 绑定校验方法不够明确

- 裁决：`accepted`
- 理由：manifest 是结构化 JSON，应按精确 `path` 定位唯一 entry，再校验该 entry 的完整
  `content_sha256`，并确认其余 42 entries 不使用旧值。raw substring/grep 不能作为 owner 绑定证明。
- Owner：AgentCodex plan fix。

### F17-P3：rollback 验证未独立于正向验证

- 裁决：`rejected-with-reason`
- 理由：原 plan rollback 已明确“重算 raw digests”，且 `git diff` 会显示任何相对 HEAD 的额外 bytes
  变化；finding 所称额外未提交 bytes 可能不出现在 diff 的前提不成立。现有精确反向 patch、raw digest
  重算和 changed-file guard 已充分，不新增重复真源。

## Gate decision

Plan 方向与 owner boundary 接受；在 F17-P1/P2 修订并完成双路 re-review 前，不进入 implementation。
没有 public contract、schema、Oracle/scenario 或 readiness scope 扩张。
