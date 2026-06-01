# WU-LIFE-01 + WU-LIFE-02 Discussion Controller Adjudication

日期：2026-06-01
总控：AgentController
当前 gate：discussion / code inspection
输入 artifact：docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md

## 裁决结论

WU-LIFE-01 + WU-LIFE-02 的动机成立，但当前证据不支持把它扩大为 recovery 或 scheduler close 的生产逻辑重写。基于 `docs/host/design.md` 的设计目标和第一性原理，当前最佳实践是进入 plan gate，形成以 proof matrix、focused regression tests 和最小必要生产修复为边界的 code-generation-ready plan。

## Finding 裁决

| ID | 裁决 | 原因 |
|---|---|---|
| DCI-01 | accepted | WU-LIFE-01 风险真实存在，缺口集中在 recovery lifecycle matrix、scanner still-live / inconclusive 集成证明、WAITING startup diagnostic-only 用户可见语义和现有失败 reason 的矩阵归档；这直接服务 Host durable recovery truth，不需要先改设计真源。 |
| DCI-02 | accepted | WU-LIFE-02 风险真实存在，缺口集中在 close 中途取消、非空 dispatch / promotion queue 不无限 drain、cancel_all 快照语义和 close window 不写 terminal fact；这直接服务 Host handle lifecycle 与用户 cancel fact 分离目标。 |
| DCI-03 | accepted | 不修改 `docs/host/design.md`；现有设计真源已定义 recovery positive orphan proof、WAITING 不恢复、Host opener close 不写 terminal fact、scheduler close 不无限 drain 等边界。 |
| DCI-04 | accepted | RR-DUR-01 在本 gate 关闭：recovery scanner 不依赖 projection checkpoint，已有 recovery projection-lag 与 deterministic checkpoint CAS 测试足以证明该风险不是 WU-LIFE recovery lifecycle 的前置条件。 |
| DCI-05 | accepted | RR-DUR-04 纳入 WU-LIFE-01 plan 的 proof matrix 范围，但不预设生产代码修改；只有直接证据显示 governance decision 使用长 read transaction 或 projection lag 作为 truth 时才允许 implementation fix。 |

## Plan Gate 要求

planning agent 必须产出 handoff-ready、code-generation-ready plan，并至少满足以下边界：

- 计划默认以测试与证明补强为主，不预设生产逻辑重写。
- Slice A 覆盖 recovery lifecycle proof matrix 与 focused recovery tests。
- Slice B 覆盖 scheduler close / cancel_all lifecycle matrix 与 focused close-window tests。
- 明确列出每个场景是已有覆盖、新增覆盖还是非目标。
- 明确任何生产代码修改的触发条件：新增测试证明 reason 不可区分、diagnostic payload 不足、状态转换不稳定、资源泄漏或 terminal fact 误写。
- 不改变 durable schema、EventLog event type、Host public API、Run / Attempt 状态机、WAITING durable 语义、close 不写 terminal fact 的设计边界。

## Blocking Open Questions

none

## 总控状态更新

进入 plan gate。discussion/code inspection artifact 与本裁决 artifact 写回总控文档；RR-DUR-01 标记 closed，RR-DUR-04 保持当前 work unit owner 并进入 plan proof matrix。
