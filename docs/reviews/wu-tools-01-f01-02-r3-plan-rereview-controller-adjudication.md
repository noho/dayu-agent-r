# WU-TOOLS-01-F01-02-R3 Plan Re-Review Controller Adjudication

## 基本信息

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: plan re-review adjudication
- Plan artifact: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-plan-rereview-ds.md`
- Controller decision: plan accepted; proceed to accepted plan commit and implementation gate

## Re-review 结论

AgentMiMo 与 AgentDS 均裁决 `pass`。PF-01 到 PF-09 全部为 `已修复`。Plan 当前达到 code-generation-ready，implementation agent 可按 Slice 0 -> Slice 1 -> Slice 2 -> Slice 3 -> Slice 4 推进，无需额外架构决策。

## PF 最终状态

| PF | 最终状态 | Controller 裁决 |
|---|---|---|
| PF-01 错误类型迁移表和目标模块 | 已修复 | accepted-fixed |
| PF-02 取消策略收敛为直接 `ToolCancelledOutcome(host_cancelled)` | 已修复 | accepted-fixed |
| PF-03 per-provider `asyncio.Lock` 创建、共享和获取时机 | 已修复 | accepted-fixed |
| PF-04 代表性 native callable 模板 | 已修复 | accepted-fixed |
| PF-05 Slice 0 helper API、typed result、`invalid_argument` 和有限校验范围 | 已修复 | accepted-fixed |
| PF-06 legacy adapter 测试行为迁移覆盖 | 已修复 | accepted-fixed |
| PF-07 Fins fixture 迁移路径 | 已修复 | accepted-fixed |
| PF-08 Web live smoke 残余追踪 | 已修复 | accepted-fixed |
| PF-09 `ToolCancelledOutcome.meta` 构造与测试 | 已修复 | accepted-fixed |

## 新增低严重度观察

| ID | 来源 | 内容 | Controller 裁决 | Owner / Destination |
|---|---|---|---|---|
| PRR-NR-01 | AgentDS | `WebToolFailure` 的 `url` / `next_action` / `http_status` 额外字段最终落点仍是实现细节 | deferred-with-owner | Slice 2 implementation；保持 `error` / `message` / `hint` 的 LLM-readable 语义，若需暴露额外字段只能进入安全文本或领域本地诊断，不扩展公共 outcome 契约。 |
| PRR-NR-02 | AgentMiMo / AgentDS | `host_cancelled_outcome(...)` 草案允许 `message=None`，而 `ToolCancelledOutcome.message` 实际要求非空字符串 | deferred-with-owner | Slice 0 implementation；helper 必须把 `None` 映射为非空默认 message，并用测试覆盖。 |

两项均不阻塞 accepted plan gate，因为 plan 已明确 cancelled outcome meta、reason 和测试要求；具体默认 message 与 Web 额外字段文本落点属于 implementation slice 内可验证细节。

## 下一步

- 创建 accepted plan 本地 commit。
- 进入 implementation gate，第一片为 Slice 0: Current ToolCallable Support。
- Implementation agent 必须遵循 plan 中的 stop conditions；若发现需要改变 `ToolCallRequest`、`ToolParametersSchema`、`ToolExecutionOutcome` 或 Host / Engine 状态机，必须停止并回到 design discussion。

## Residual Risk

当前没有未分类 residual risk。低严重度观察已分配到 implementation slice owner。
