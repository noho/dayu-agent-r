# Host 设计 Post-Runtime/Lane 就绪评审

- 日期：2026-05-13
- 评审模型：MiMo
- 范围：`docs/host/design.md`、`docs/host/implementation-control.md`
- 术语真源：`dayu/README.md` 术语约定节
- 上下文：draft design v2 收口后、phase 编排前的就绪评审
- 上一轮裁决：`docs/reviews/host-design-final-readiness-controller-adjudication-20260513.md`

## 评审方法

对 `design.md` 全部 28 节逐节做 adversarial reading，重点挑战：
- 状态机完整性与一致性
- 模块边界与反向依赖
- 语义歧义与矛盾
- 过度设计与冗余概念
- implementation-control 的编排就绪度

对 `implementation-control.md` 检查：
- phase 编排是否就绪
- 追踪项是否完整、可操作
- 与 design.md 和裁决文档的一致性

## Findings

### P0：阻塞 phase 编排

#### F1. implementation-control.md 缺少 phase 清单

**位置**：`docs/host/implementation-control.md` 全文

**现象**：上一轮裁决（A1）明确要求"在任何可交付实施的 phase plan 开始前，`docs/host/implementation-control.md` 必须先补齐 phase 清单"，并给出了最小字段和推荐编排顺序。当前文档仍只有工作流描述、强制约束和追踪区，没有实际 phase 清单。

**影响**：无法启动任何 phase 的 handoff implementation-ready plan。Phase plan 的进入条件、退出条件、允许修改范围和验证要求没有编排载体。

**建议修正**：按裁决 A1 的推荐编排顺序，在 `implementation-control.md` 中新增 Phase 清单节，每个 phase 至少包含：名称、目标、对应 design 章节、进入条件、退出条件、允许修改范围、明确不做项、前置依赖、必须验证的类型、必须解决或继续追踪的事项。

### P1：语义歧义或状态机覆盖不足

#### F2. 状态迁移表缺少 context compaction recovery 路径

**位置**：`docs/host/design.md` §9.1 状态迁移契约表

**现象**：Context compaction 的 reactive path（§25.1）描述了一个完整路径：`CONTEXT_COMPACTION_REQUESTED` -> close current Attempt -> `RECOVERING` -> compact -> `CONTEXT_COMPACTED` -> new Attempt -> dispatch。但 §9.1 的状态迁移表中没有显式覆盖 context compaction 触发的 recovery 路径。

当前表中 `Engine failure` 行提到"context_compaction_required 在可恢复时进入 RUN_RECOVERING + new Attempt"（通过 §13.4 映射），但 §9.1 表中没有对应的独立行。读者需要从 §9.1 的 `recovery dispatch` 行、§13.4 的 `run_failed` 映射和 §25.1 的 compact event 响应路径三处交叉推导才能拼出完整路径。

**影响**：phase plan 实现者可能遗漏 context compaction 的状态迁移路径，或错误地将其与 crash recovery 混淆。两者虽然共享 `RECOVERING` 状态和 `RUN_STARTED(start_reason=recovery)` 语义，但触发条件、前置事件序列和 compact 动作完全不同。

**建议修正**：在 §9.1 状态迁移表中增加一行：

```
| context compaction (reactive) | Run `RUNNING` / Attempt `RUNNING` | Run `RECOVERING` / Attempt `FAILED` 或 `SUSPENDED` | `CONTEXT_COMPACTION_REQUESTED`、`ATTEMPT_FAILED`(可选)、`RUN_RECOVERING` | 关闭当前 Attempt；Host compact 后创建新 Attempt |
```

同时在 §25.1 中明确：context compaction recovery 复用 `RECOVERING` 状态和 `RUN_STARTED(start_reason=recovery)` 语义，不需要新增 `start_reason` 枚举值。

#### F3. `dispatching` 中间态的失败路径未覆盖

**位置**：`docs/host/design.md` §17 WorkerProxy / EngineWorker dispatch semantic contract

**现象**：dispatch 流程定义了 `dispatching` 作为 dispatch record 的中间状态（lane acquired -> recheck -> dispatch record = dispatching -> WorkerProxy dispatch）。设计也说"dispatch 失败...必须关闭 Attempt"。但没有明确 `dispatching` 状态下 dispatch 失败时，Run 应进入什么状态。

Attempt 的终态集合是 `SUCCEEDED / FAILED / CANCELLED / SUSPENDED / STEERED / LOST`。dispatch 失败时 Attempt 应进入 `FAILED` 或 `LOST`。但 Run 应进入 `FAILED`、`RECOVERING` 还是 `LOST`？这取决于 Host policy 和失败原因（WorkerProxy 连接失败 vs worker reject vs startup timeout）。

**影响**：recovery phase 实现时，需要明确 `dispatching` 状态下进程崩溃的恢复语义。dispatch record 显示 `dispatching` 但 Attempt 仍为 `STARTING`，lane token 可能已持有但未释放。

**建议修正**：在 §17 dispatch semantic contract 中补充 dispatch 失败的 Run 状态决策：

```
dispatch failed (after lane acquired, dispatch record = dispatching):
  -> release lane token
  -> Attempt -> FAILED or LOST (by failure type)
  -> Run -> FAILED / RECOVERING / LOST (by Host policy + recovery eligibility)
  -> recovery scan 遇到 dispatch record = dispatching 且 Attempt = STARTING:
     -> 按 positive orphan proof 判定后，Attempt -> LOST
     -> Run 按 recovery policy 进入 RECOVERING 或 LOST
```

#### F4. `CANCELLING -> RECOVERING` 转换的退出语义不完整

**位置**：`docs/host/design.md` §9.1 状态迁移契约表 `cancel_run` on active 行、§27 Recovery

**现象**：`cancel_run` on active 行的前置状态包含 `RECOVERING`，目标状态包含 `RECOVERING`（即 `CANCELLING` 中间态可到达 `RECOVERING`）。同时 §27 recovery scan 分类规则说"`RUNNING` / `CANCELLING` 且具备 positive orphan proof：Run 按 policy 进入 `RECOVERING` 或 `LOST`"。

这意味着可能产生 `RUNNING -> CANCELLING -> RECOVERING -> RUNNING -> ...` 的路径：用户取消 -> Attempt 丢失 -> 恢复启动 -> 新 Attempt dispatch。此时用户的取消意图是否仍然有效？

设计没有明确 `CANCELLING -> RECOVERING` 转换后，是否应保留 cancel intent 并在 recovery 完成后继续取消，还是将 cancel 视为已由 Attempt 丢失收口。

**影响**：可能导致用户以为已取消的 Run 在恢复后继续执行，产生意外的 LLM 调用和费用。

**建议修正**：在 §9.1 或 §22 Cancel 中补充规则：

```
CANCELLING -> RECOVERING 场景：
- 如果 cancel_run 已 durable accepted (CANCEL_REQUESTED 已提交)，recovery 创建的新 Attempt 必须在 dispatch 前检查 pending cancel intent。
- 若 cancel intent 仍有效，新 Attempt 不得 dispatch；Run 直接进入 CANCELLED。
- 若 cancel intent 已过期或被显式撤销（未来能力），recovery 继续正常路径。
```

#### F5. `purge_session` 对 audit JSONL 的影响未定义

**位置**：`docs/host/design.md` §5 Session 生命周期 `purge_session` 删除范围、§15 Audit `LogAuditSink`

**现象**：`purge_session` 删除范围包括"该 Session 的 EventLog rows、projection rows"。`LogAuditSink` 写本地 append-only JSONL audit log file。设计没有明确 `purge_session` 是否应处理 audit JSONL 中对应 Session 的记录。

两种可能：
1. audit JSONL 不受影响（它是 append-only 文件，不是 projection table）。但已 purge Session 的 audit 记录将引用不存在的 EventLog rows，`event_id` / `event_sequence` 对齐失效。
2. audit JSONL 需要某种标记或清理。但 append-only 文件不支持原地删除。

**影响**：purge 后 audit trail 的完整性。审计人员可能需要查询已 purge Session 的审计记录，但发现 EventLog 已不存在。

**建议修正**：在 §5 `purge_session` 删除范围或 §15 Audit 中明确：

```
purge_session 对 audit JSONL 的处理：
- audit JSONL 是 append-only 文件，purge 不删除已写入的 audit 记录。
- purge tombstone 本身应写入 audit JSONL，标记该 Session 已被 purge。
- 已 purge Session 的 audit 记录保留，但其 EventLog refs 不再可查询。
- 后续 audit 查询工具应能识别 purge tombstone 并提示用户。
```

#### F6. `RunInputBuilder` memory snapshot 校验失败的行为未明确

**位置**：`docs/host/design.md` §24 Conversation Memory

**现象**：设计要求"RunInputBuilder 消费 memory snapshot 前必须校验 snapshot cursor 覆盖本次构造 messages 所需的 EventLog cursor。若 snapshot 缺失或滞后，Host 必须从 EventLog canonical facts 重建所需 stable layer，或进入结构化 context governance / recovery"。

这里的"或"字产生了两种截然不同的行为：
1. 自动从 EventLog 重建（silent rebuild）。
2. 进入 context governance / recovery（可能涉及状态迁移和新 Attempt）。

设计没有明确选择标准。是所有情况都 silent rebuild？还是只有严重滞后时才进入 recovery？如果 silent rebuild，是否需要 diagnostic 事件？

**影响**：Memory phase 实现时可能做出与 Context Governance phase 不一致的假设。如果 silent rebuild 频繁发生，可能掩盖 projection lag 问题；如果进入 recovery，可能过度触发状态迁移。

**建议修正**：在 §24 中明确决策规则：

```
memory snapshot 校验失败的处理：
- snapshot cursor 滞后但 EventLog delta 在 policy 阈值内：silent rebuild from EventLog + 记录 diagnostic。
- snapshot cursor 严重滞后或缺失：Host 进入 structured context governance（不是 recovery）。
- rebuild 后的新 snapshot 应更新 memory projection checkpoint。
- 不得因为 memory projection lag 而触发 Run 状态迁移（recovery 是 crash recovery，不是 projection lag recovery）。
```

### P2：设计优化与清晰度

#### F7. `RUN_STARTED` 的 `start_reason` 未明确覆盖 context compaction

**位置**：`docs/host/design.md` §9.1 `RUN_STARTED` 定义

**现象**：`RUN_STARTED` 的 `start_reason` 枚举为 `initial | queue_promotion | resume | steer | recovery`。Context compaction reactive path 最终创建新 Attempt 时使用 `RUN_STARTED(start_reason=recovery)`。但设计没有显式说明 context compaction 使用 `recovery` 作为 `start_reason`。

读者需要推导：context compaction -> `RECOVERING` -> new Attempt -> `RUN_STARTED(start_reason=recovery)`。

**影响**：轻微。audit 和 tool trace 可能无法区分 crash recovery 和 context compaction recovery，但这在 v1 可接受。

**建议修正**：在 §9.1 `RUN_STARTED` 定义中增加一句：

```
`start_reason=recovery` 覆盖 crash recovery 和 context compaction recovery；如需区分，可通过关联的 `CONTEXT_COMPACTION_REQUESTED` / `ATTEMPT_LOST` event ref 判断。
```

#### F8. `purge_session` tombstone 存储位置未指定

**位置**：`docs/host/design.md` §5 Session 生命周期

**现象**：设计定义了 purge tombstone 的最小字段，说"它可以位于 purged Session EventLog 之外"，但没有指定具体存储位置。是独立 tombstone table？独立文件？还是 durable store 中的专用区域？

**影响**：Storage phase 实现时需要自行决定，可能导致实现不一致。

**建议修正**：在 §5 中增加一句约束：

```
tombstone 存储位置由 Host Storage phase 决定，但必须满足：(1) 不在被 purge 的 Session 的 EventLog 中；(2) 支持按 session_id 查询；(3) 与 durable store 同事务提交或具备等价持久性保证。
```

#### F9. `cancel_session_runs` 与 queue promotion 的交互未显式说明

**位置**：`docs/host/design.md` §11 公共接口 `cancel_session_runs` 语义

**现象**：`cancel_session_runs` 取消该 Session 下所有未终态 Run，包括 `QUEUED` Run（直接 `CANCELLED`）。设计说"active Run 取消后 queued Run promotion"在 §9 中有规则。但 `cancel_session_runs` 取消所有 queued Run 后，是否还需要触发 promotion check？

逻辑上：所有 queued Run 已被取消，promotion check 会发现没有可 promotion 的 Run，所以是 no-op。但设计没有显式说明这个 no-op 行为。

**影响**：轻微。实现者可能不确定是否需要在 `cancel_session_runs` 完成后触发 promotion check。

**建议修正**：在 §11 `cancel_session_runs` 语义中增加一句：

```
所有 queued Run 被取消后，promotion check 为 no-op（无可 promotion 的 Run）；实现可以选择触发或跳过 promotion check，结果一致。
```

#### F10. `EngineEvent stream` 非正常终止与 `RECOVERING` 状态的关系

**位置**：`docs/host/design.md` §17 EngineEvent stream 非正常终止规则

**现象**：设计说"Host must not leave Run indefinitely RUNNING solely waiting for restart scan"。这暗示 stream 异常终止后，Host 应主动评估 Attempt 状态，而不是被动等待 recovery scan。

但设计没有明确这个"主动评估"的时机和机制。是在 stream EOF 时立即评估？还是通过后台定时任务？如果 Host 进程本身崩溃，这个主动评估不会发生，只能依赖下次启动的 recovery scan。

**影响**：WorkerProxy phase 实现时需要决定 stream close 的处理策略。

**建议修正**：在 §17 中补充：

```
stream 异常终止时的 Host 收口：
- Host 进程存活时：stream EOF / error 后，Host 立即评估 Attempt 状态（不等待 recovery scan）。
- Host 进程崩溃时：依赖下次启动的 recovery scan。
- 主动评估路径：记录 diagnostic -> 按 policy 判定 Attempt 为 failed / lost / recoverable -> 更新 Run 状态。
```

#### F11. `ToolRuntime` 部署在远端时的 policy snapshot 一致性

**位置**：`docs/host/design.md` §18.2 ToolRuntime Boundary

**现象**：设计说"治理配置和真源来自 Host attempt snapshot"。attempt snapshot 包含 policy snapshot ids / refs。但如果 Host 在 Attempt 执行期间更新了 policy（例如 admin 修改了 tool governance policy），远端 ToolRuntime 使用的仍是旧 policy snapshot。

设计没有明确这是 expected behavior（snapshot 语义）还是需要某种 policy refresh 机制。

**影响**：轻微，但需要明确语义以避免实现时的困惑。

**建议修正**：在 §18.2 中增加一句：

```
attempt-local policy snapshot 是 immutable snapshot，Attempt 创建后不受 Host policy 变更影响。policy 变更只影响后续新创建的 Attempt。
```

## 与上一轮裁决的一致性检查

| 裁决项 | 状态 | 说明 |
| --- | --- | --- |
| A1 Phase 清单 | **未完成** | implementation-control.md 仍缺少 phase 清单（F1） |
| A2 Tool fact canonical owner | 一致 | design.md §18.2 和 §13.4 已覆盖 |
| A3 Cancel/suspend 竞态 | 一致 | design.md §9.1 和 §22 已覆盖 |
| A4 Steer lost 竞态 | 一致 | design.md §12 已覆盖 |
| A5 Resolve wait/resume | 一致 | design.md §9.1 和 §20 已覆盖 |
| A6 Recovery 成功路径 | 一致 | design.md §27 已覆盖 |
| A7 submit_followup 执行目标 | 一致 | design.md §11 和 §12 已覆盖 |
| A8 Retry/replay 前置条件 | 一致 | design.md §21 已覆盖 |
| A9 Memory snapshot 原子性 | 一致 | design.md §24 已覆盖 |
| A10 ToolRuntime accept barrier | 一致 | design.md §18.2 已覆盖 |
| A11 purge append-only 例外 | 一致 | design.md §5 已覆盖 |
| A12 close_session 与 promotion | 一致 | design.md §5 已覆盖 |
| A13 Event type 必要性审核 | **待 phase** | 需在 EventLog phase 进入前完成 |
| A14 EngineEvent stream 终止 | 一致 | design.md §17 已覆盖（F10 补充细节） |
| A15 Provider tokenizer gap | 一致 | 已追踪 |
| A16 Payload 存储阈值 | 一致 | 已追踪 |
| A17 RunInputBuilder provider 粒度 | 一致 | 已追踪 |
| A18 ToolRuntime port 粒度 | 一致 | 已追踪 |
| A19 Policy provider 边界 | 一致 | design.md §10.1 已覆盖 |
| A20 Outbox 身份与去重 | 一致 | design.md §16 已覆盖 |
| A21 取消后编辑再发送 | 一致 | design.md §12 已覆盖 |
| A22 追踪项继续保留 | 一致 | implementation-control.md 追踪区完整 |
| A23 写回分类 | **部分完成** | design.md 已写回大部分语义；phase 编排约束待写入 |

## 残余风险

1. **Engine Context Compaction Event 语义前置**：Engine 的 `0/0/0` budget 占位仍未修复。Host Context Governance phase 必须先完成 Engine contract cleanup，或在 plan 中写明临时兼容假设。当前 design.md §25.1 已明确 Engine overflow 只是 reactive fallback，但实现时仍可能误消费 `0/0/0`。

2. **SQLite 多进程写入正确性**：design.md 已定义 WAL、busy timeout、CAS 等约束，但实际正确性依赖 Storage phase 的实现和测试。多进程竞争 promotion、cancel/terminal race、EventLog sequence 单调性需要专门的并发测试。

3. **Remote exactly-once 非目标**：design.md 已明确不保证 exactly-once 远程物理执行。具有外部副作用的工具依赖工具级 idempotency key 和 best-effort cancel。这是已接受的残余风险。

4. **Provider tokenizer adapter gap**：v1 使用 conservative estimator。可能导致过度 compaction（浪费 context 容量）或不足 compaction（触发 provider overflow fallback）。已接受为 v1 限制。

5. **`CANCELLING -> RECOVERING` 路径的 cancel intent 保留**（F4）：如果不在 phase plan 中处理，可能导致用户取消的 Run 在恢复后继续执行。

## 最终裁决

**ready with fixes**

Host 设计架构方向正确，状态机基本一致，模块边界清晰，EventLog / projection 边界严格，tool fact accept barrier 设计完整。设计可以进入 phase 编排。

阻塞项：
- F1（P0）：implementation-control.md 必须先补齐 phase 清单，才能启动任何 phase plan。

建议在进入第一个 phase plan 前修正：
- F2-F6（P1）：状态机覆盖、dispatch 失败路径、cancel/recovery 竞态、purge 对 audit 的影响、memory snapshot 校验行为。

可与对应 phase 一起修正：
- F7-F11（P2）：start_reason 覆盖说明、tombstone 存储位置、promotion no-op 说明、stream 终止处理策略、policy snapshot 不变性。

当前设计不需要重写架构或推翻任何核心设计方向。
