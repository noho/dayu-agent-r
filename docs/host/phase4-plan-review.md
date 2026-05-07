# Host P4 Handoff Plan Review

## 结论

通过，无 findings。

`docs/host/phase4-plan.md` 足以交给迁移 Agent 实施。计划符合 `docs/host/migration-plan.md` 第 6 节 phase plan
模板要求，也符合 AGENTS.md 中 Host / Engine / runtime / EventLog 相关架构硬约束。

## Review 范围

本次 review 只检查 handoff plan，不修改生产代码。参考材料：

- `docs/host/phase4-plan.md`
- `docs/host/migration-plan.md`
- `docs/host/design.md`
- `docs/host/phase3-plan.md`
- `dayu/host/README.md`
- 当前 `dayu/host/` 与 `dayu/engine/` 相关代码

已按 plan 要求复核 NEW 代码中的 `compact`、`overflow`、`context_length`、`ConversationMemory`、
`conversation_memory`、`summar` 相关位置。当前代码事实显示：

- `dayu.engine` 已定义 `EngineEventType.CONTEXT_COMPACTION_REQUESTED` 与
  `ContextCompactionRequestedData` 契约。
- 当前 OpenAI runner 错误分类仍以 HTTP / network / protocol 中性错误为主，未发现 provider context overflow
  生产路径已经落地。
- `dayu.host` 已落地 P3 的 `USER_INPUT_ACCEPTED`、`InMemoryConversationMemoryStore`、
  `DefaultRunInputBuilder` 与 internal-only `RunInputBuildTrace`。
- 当前 `RunEventStore` terminal guard 会拒绝 terminal 后继续 append，P4 plan 已专门把 recoverable overflow
  terminal 与 retry 追加事件的冲突列为必须处理的 EventLog 契约点与停止条件。

## Gate 检查

- P4 目标限定清楚：只迁移 context overflow compact 归属与 retry / 失败收口，不提前实现 P6 observer /
  persistent projection、P7 lifecycle governance、P8 lease / fencing、P9 Reply Outbox。
- Engine / Host 边界清楚：Engine / Runner 只报告强类型 overflow / compaction-required 事实；Host 负责
  compact policy、attempt retry 与 Host-owned failure 收口；未把 Host ToolRuntime、memory、trace 或 compact
  governance 塞回 Engine。
- EventLog 真源清楚：compact 输入限定为 `USER_INPUT_ACCEPTED`、canonical facts、memory snapshot 与
  `RunInputBuildTrace` 诊断中可追溯的事实；明确禁止 display timeline、preview、reasoning、request transcript
  旁路，也没有另造 transcript 真源。
- P3 已解决事实表述清楚：Engine stream 无 terminal 的 Host-owned `RUN_FAILED` 与 CRITICAL log 被列为 P3
  事实，P4 明确不重复治理，也明确无 terminal 不触发 compact retry。
- 文件级改动、契约、状态机、测试、README/docs、utils smoke 与验证命令足够具体。尤其是 recoverable overflow
  trigger 不能污染 final `get_run_result` / memory projection、terminal-after-append 不能被破坏、fake overflow
  smoke 与真实 provider overflow 覆盖差异均已写清。
- `dayu.runtime` 边界正确：plan 明确不把 compact、memory、attempt retry policy 放入 runtime；P4 不涉及 lane。
- 待用户确认项写“无”合理。当前不确定性主要是实施前代码事实确认与停止条件，不是需要用户预先裁决的产品或架构选择。

## 残余风险

P4 的主要实施风险仍是当前 Engine 可能只有契约、没有真实 provider overflow 生产路径。plan 已把该风险纳入
前置复核、文件级小范围 Engine 协作补充、测试条件、停止条件与风险回滚，足以指导迁移 Agent 在不越界的情况下处理。
