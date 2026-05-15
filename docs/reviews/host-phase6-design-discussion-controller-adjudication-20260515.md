# Host Phase 6 Design Discussion Controller Adjudication - 2026-05-15

## 结论

Controller 裁决：Phase 6 仍需先完成 design write-back，再进入 handoff implementation-ready plan；但
`docs/reviews/host-phase6-design-discussion-codex-20260515.md` 中原列 6 个 blocking questions 有部分严重性被高估。

本轮已按用户讨论结论写回：

- `docs/host/design.md`
- `docs/host/implementation-control.md`

写回目标不是引入重型机制，而是防止后续 planning / implementation agent 把实现 invariant、run-local algorithm 或 Phase 7
等待能力误读成 Phase 6 durable / recovery 设计。

## 裁决记录

### BQ1 accepted - accepted ack timeout / rejected 默认治理动作

裁决：接受为 Phase 6 design blocker。

理由：ack timeout / rejected 决定 LLM 是否能消费工具结果、是否进入 `WAITING`、是否触发 recovery，属于 Host 状态治理与
ToolRuntime accept barrier 语义，不应由 implementation agent 自行选择。

写回：`docs/host/design.md` 已明确 Phase 6 第一版采用有限 accept retry；仍未确认时返回 governed tool error，不让 LLM
消费原始结果，不创建 wait record，不把 Run 推入 `WAITING`，不触发 recovery。

### BQ2 accepted - tool fact accept 幂等映射

裁决：接受为 Phase 6 design blocker。

理由：这是 ToolRuntime 重试提交同一个工具事实时 Host 如何识别既有 accepted fact 的问题，不是语义级重复工具调用治理。
若未固定 scope / digest，accept retry 测试与 idempotency conflict 测试无法直接生成。

写回：`docs/host/design.md` 已明确 Phase 6 默认 `scope_kind=tool_fact_accept`，`scope_id` 至少绑定 `attempt_id` 与
`tool_call_id`，`semantic_input_digest` 覆盖 tool identity、normalized arguments digest、tool fact kind、result /
payload digest、policy decision digest 与 truncation metadata digest。

### BQ3 downgraded - effective ToolBundle 同源

裁决：降级为 implementation invariant 与测试要求，不作为 design blocker。

理由：业务工具声明现场的 `@tool -> ToolDefinition(schema + ToolCallable) -> ToolBundle` 已经保证 schema / callable 同源。
装配错配属于普通代码 bug，应通过单一 effective `ToolBundle` 派生 schema projection 与 callable dispatch，并用测试覆盖
`fetch_more` 注入，不需要重型 durable snapshot 机制。

写回：`docs/host/design.md` 已把 attempt-local effective tool view 定义为 RunInputBuilder 暴露 schemas 与 ToolRuntime
dispatch 的单一真源，并明确 Phase 6 不为该普通 invariant 引入额外 durable snapshot 机制。

### BQ4 downgraded - truncation / fetch_more durable descriptor

裁决：降级为 design boundary write-back 与 implementation algorithm/test requirement，不作为 durable 架构 blocker。

理由：参考旧实现，`fetch_more` 是同 Run 内的 short-lived cursor 续读能力；cursor / `scope_token` 的生成、single-use、
TTL 与 scope hash 校验是 TruncationManager 算法问题。原设计中跨 restart / recovery / replay 续读的 wording 会诱导过度设计。

写回：`docs/host/design.md` 已明确 Phase 6 第一版 `cursor` / `scope_token` 是 Run-scoped、short-lived、
ToolRuntime-local capability；不承诺跨 Run、跨 Session、Host restart、Attempt `LOST` / recovery、replay 或长期 memory
retrieval 后继续可用。`docs/host/implementation-control.md` 已同步移除 durable cursor descriptor wording。

### BQ5 accepted-with-scope - Phase 6 / Phase 7 awaiting 边界

裁决：接受边界问题，但裁决为 Phase 6 只保留 placeholder / unsupported 行为。

理由：ToolRuntime 可以遇到 awaiting outcome 类型，但 wait record、`WAITING`、`resolve_wait` 与长耗时 external job 资源收口均为
Phase 7 owner。Phase 6 不得留下半状态机。

写回：`docs/host/design.md` 已明确 awaiting / wait outcome port 是 placeholder；Phase 6 不创建 wait record，不把 Run 推入
`WAITING`，不实现 `resolve_wait`。

### BQ6 downgraded/split - side-effect / paid / long-running tools

裁决：拆分处理。

- side-effect / paid tool policy 属于 Phase 6 ToolRuntime policy 与测试输入。
- long-running / external job awaiting 属于 Phase 7。

理由：`docs/host/design.md` 已有 tool governance policy 与工具级 idempotency key 方向；不需要作为新的大裁决阻塞
Phase 6。长耗时工具完整路径则明确归属 §20 Tool Awaiting / Wait Record 与 Phase 7。

写回：`docs/host/implementation-control.md` 已把 Phase 6 追踪项收窄为 side-effect / paid idempotency policy，把 external
job id、cancel handle、等待资源清理转交 Phase 7。

## 当前 Gate

当前 gate：Phase 6 design refinement write-back completed，待 controller 复核 diff 后进入 handoff implementation-ready plan。

进入 plan 前仍需 planning agent 显式覆盖：

- ToolRuntime ports 的 typed request / response / error shape。
- accept candidate / accepted ack / rejected ack / timeout governed error。
- run-scoped TruncationManager / `fetch_more` cursor 算法与测试矩阵。
- duplicate governance action matrix。
- replay no-tool 双层防线测试。
- Phase 7 / 11 / 13 / 14 非目标 guard。

