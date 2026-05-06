# Host Design 最佳实践 Review

## 1. Review 范围

- 审查文件：`docs/host/design.md`
- 审查角度：production-grade Agent Host 最佳实践。
- 参考对象：OpenClaw、Codex、Claude Code 的 session、streaming、tool governance、
  hook / permission、transcript / resume 等公开经验。
- 本 review 未修改代码。

## 2. 外部参考

- OpenClaw Agent Runtime：https://docs.openclaw.ai/concepts/agent
- OpenClaw Gateway Architecture：https://docs.openclaw.ai/concepts/architecture
- Codex CLI docs：https://developers.openai.com/codex/cli
- Claude Code Hooks：https://code.claude.com/docs/en/hooks
- Claude Code permissions：https://code.claude.com/docs/en/agent-sdk/permissions

## 3. 结论

阻塞问题：无。

整体方向成立，没有发现 Host / Engine 懂业务、公开 Agent 内部零件、或把 pending / resume
直接外露这类方向性错误。

建议在进入下一步计划阶段前，先把重要 findings 写回 `docs/host/design.md` 或形成修订清单，
避免实施 Agent 在幂等、流式生命周期、Session 并发、状态机闭合和事件可见性上自行脑补。

## 4. 重要 Findings

### 4.1 `start_run` 缺少调用幂等键

`RunInput` 已要求可重放，但这是同一个 Run 内 resume / replay 的幂等，不等于客户端调用
`start_run` 的幂等。Web / WeChat / CLI 在网络超时后重试，可能创建两个 Run。

建议：引入 `StartRunRequest`，或在 `RunOptions` 中强类型包含
`client_request_id` / `idempotency_key`。Host 按 `session_id + key` 去重；重复调用返回
同一个 `RunHandle` 并从 cursor 继续。

### 4.2 事件流订阅生命周期不能驱动 Run 执行

如果实施 Agent 把 `AsyncIterator` 当成执行 coroutine，客户端断线、取消 iterator 或不消费事件
可能意外取消 Run。

建议：明确 Host / RunSupervisor owns execution；`RunStream.events` 只是订阅。
关闭事件流只释放订阅资源，不取消 Run；取消必须只通过 `cancel_run`。

### 4.3 同一 Session active Run 仲裁规则不够可实施

文档说 Session 保证顺序与上下文一致性，但没有明确同一 Session 是否只允许一个 active Run，
新 Run 是 queue、reject 还是并发。

建议：第一版明确同一 Session 单 active Run。后续输入进入 `QUEUED` 或被拒绝；必须有
session-local sequence / active-run compare-and-set。

### 4.4 取消与等待路径没有完全闭合

`cancel_run` 应能作用于 `QUEUED / RUNNING / WAITING / RECOVERING`，但合法路径主要只写了
`RUNNING -> CANCELLING`。

建议：补全合法迁移表，例如 `QUEUED -> CANCELLED`、`WAITING -> CANCELLING -> CANCELLED`、
`WAITING -> FAILED / TIMED_OUT 映射`、`CANCELLING -> LOST`。

### 4.5 terminal event、RunResult、Run 状态的原子边界不够明确

已处理 final answer 到 Outbox 的漏洞，但仍存在 terminal event 写入、RunResult 持久化、
Run 状态更新三者不一致的风险。

建议：定义 terminal 收敛事务：append terminal event、persist RunResult、update Run state
必须同事务或可 reconcile。cursor 明确 exclusive / inclusive、per-run / global、是否严格单调。

### 4.6 WorkerProxy 内部 cancel 只用 `run_id` 过粗

对外 `cancel_run(run_id)` 合理；但内部 worker 已经有 attempt / lease / fencing。
旧 attempt 的迟到控制消息不能误伤新 attempt。

建议：WorkerProxy 内部控制命令携带 active `attempt_id + fencing token`，或明确只由当前 lease owner 接受。

### 4.7 RunEvent 可见性分层不够清楚

`RunStream.events` 可能同时承载客户端事件、内部 attempt 事件、tool raw 事件、validator 事件。
实现时容易把内部事件直接推给客户端。

建议：定义 `RunEvent` audience / visibility，或拆 projection：client stream event、
internal audit event、trace event。reasoning 只能进入 client transcript projection，不能进入
ContextBuilder，也不能作为 replay 输入。

### 4.8 Conversation Memory 仍有业务中立性回退

Host / Engine 不懂业务是硬约束，但 memory bullet 使用了“财报数字 / 章节定位 / XBRL facts”等表述。

建议：改成业务中立表达：结构化 tool facts、evidence anchors、source references 不应被 LLM
二次摘要丢失精度；具体财报事实由工具 / 业务层定义。

## 5. 建议 Findings

- Replay 章节建议补充 validator decision 必须持久化到 EventLog，并记录 validator version、
  replay_count、repair_instruction 引用，避免进程恢复后 replay 决策丢失或无限循环。
- Outbox 章节建议提前规定 `delivery_key` 组成必须包含 channel / recipient / result_id 或等价维度。
- EventLog 建议预留 retention / compaction / backpressure 口径，避免无界增长和慢订阅拖垮运行。

## 6. 修复状态

修复日期：2026-05-06。

- 4.1 已修复：`docs/host/design.md` 已引入 `StartRunRequest` 与
  `(session_id, client_request_id)` 创建幂等约束。
- 4.2 已修复：已明确 `RunStream.events` 是 EventLog 订阅视图，关闭或慢消费不驱动 / 不取消 Run。
- 4.3 已修复：已补充同一 Session 第一版单 active Run 仲裁规则，新的 `client_request_id`
  在 active Run 存在时返回 typed busy / conflict。
- 4.4 已修复：已补充 `QUEUED`、`WAITING`、`RECOVERING` 和 `CANCELLING` 的取消收敛路径。
- 4.5 已修复：已补充 terminal event、`RunResult`、Run state 与 Outbox projection fact 的收敛边界，
  并说明 cursor exclusive / per-run 单调语义。
- 4.6 已修复：已将 WorkerProxy 内部取消改为携带 `attempt_id` 与 `fencing_token` 的
  `WorkerCancelRequest`。
- 4.7 已修复：已为 `RunEvent` 增加 visibility / audience，并补充 canonical event 与 preview
  event 分层。
- 4.8 已修复：Conversation Memory 已改为业务中立表述，不再把财报事实写成 Host 语义。
- 建议项已修复：Replay validator decision 持久化、Outbox `delivery_key` 组成、EventLog
  retention / compaction / backpressure 口径均已写回设计草稿。
