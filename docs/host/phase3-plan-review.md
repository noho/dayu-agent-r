# Host P3 Phase Plan Review

## 结论

通过。

## Findings

无。

## Open Questions

- 无阻塞 plan review 的开放问题。
- `docs/host/phase3-plan.md` 的“待用户确认项”均属于进入实现前需要用户拍板的方案选择，例如是否新增最小 Session 级测试入口、是否新增 `USER_INPUT_ACCEPTED` canonical event、`pinned_state` 是否仅 seed / patch、是否新增最小 `list_session_timeline`。这些问题会影响实现形态，但 plan 已给出默认建议、替代路径与停止条件，不构成本轮 plan review 阻塞。

## Review Notes

- `docs/host/phase3-plan.md` 已覆盖 `docs/host/migration-plan.md` 第 6 节要求的必填栏目：目标、非目标、前置条件、架构边界、文件级改动清单、新增 / 修改契约、状态机变化、数据持久化 / schema 变化、多进程并发影响、ToolRuntime / EngineWorker / Engine 边界影响、EventLog / RunEventStore / projection 影响、临时实现边界、runtime dependency、测试清单、验证命令、README / docs 触发判断、review gate、停止条件、风险与回滚、待用户确认项、迁移 Agent 汇报格式。
- P3 范围控制清晰：非目标明确排除 P4 context overflow compact / retry、P6 持久 projection / observers、P7 lifecycle governance / admission / 幂等、P9 Reply Outbox、P10 RemoteProxy、P11 wait / suspend / resume，并在“不可接受临时实现”“停止条件”“风险与回滚”中重复约束，足够交接给迁移 Agent。
- Host / Engine / ToolRuntime / RunEventStore / `dayu.runtime` 边界清晰：RunInputBuilder 与 memory projection 保持 Host internal；Engine 只消费 `RunInput.messages`；ToolRuntime facts 只能经 canonical RunEvent 或 projection 进入 RunInputBuilder；`dayu.runtime` 不承载 Host memory / projection / RunInputBuilder 语义。
- preview / reasoning / delta 隔离要求明确：plan 多处规定它们只能进入 display read model，不能进入 `RunInput` replay、memory pool、RunInputBuilder 运行态输入或 RunResult 推导；测试清单也覆盖“展示可见但运行态不可见”的差异。
- P3 smoke、测试清单和验证命令足够：测试覆盖 memory projection、RunInputBuilder、最小多轮 smoke、public/import boundary、#48 不变量、OLD / NEW 差异、ToolRuntime facts 摘要与敏感字段过滤；验证命令包含受影响 pytest 与 pyright。
- README / docs 触发判断符合总控与 AGENTS 约束：plan 文档本身不机械更新 README，代码落地后按 `dayu/host/README.md`、`tests/README.md`、`dayu/README.md`、`docs/host/design.md` 的职责范围检查更新。
- “语义和实际实现逻辑是否错开”的专项要求已进入 review gate：plan 明确设置 semantic vs implementation gate，并列出 preview 过滤、final answer 来源、scope token 泄漏、#48 单总池 / recent turns floor、P7 admission 偷做等需要 code review 对照实现与测试验证的例子。
