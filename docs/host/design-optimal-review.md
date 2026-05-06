# Host Design 最优方案 Review

## 1. Review 范围

- 审查文件：`docs/host/design.md`
- 审查角度：如果从头设计最优 Agent Host，当前 design 是否足够接近最优方案。
- 参考对象：OpenClaw、Codex、Claude Code 的 session、command queue、streaming、
  retry、hook、compaction、transcript 等公开经验。
- 本 review 未修改代码。

## 2. 外部参考

- Codex CLI features：https://developers.openai.com/codex/cli/features
- Claude Code hooks：https://code.claude.com/docs/en/hooks
- Claude Code features overview：https://code.claude.com/docs/en/features-overview
- OpenClaw session management：https://docs.openclaw.ai/concepts/session
- OpenClaw command queue：https://docs.openclaw.ai/concepts/queue
- OpenClaw streaming：https://docs.openclaw.ai/concepts/streaming
- OpenClaw retry policy：https://docs.openclaw.ai/concepts/retry
- OpenClaw compaction：https://docs.openclaw.ai/concepts/compaction
- OpenClaw session pruning：https://docs.openclaw.ai/concepts/session-pruning

## 3. 结论

当前 design 的主方向已经接近优秀 Agent Host 骨架：`Session / Run / Attempt / EventLog /
Outbox / WorkerProxy` 的切分是对的，Host / Engine 不懂业务也守住了。

进入下一步计划阶段前，建议先修掉两个阻塞点：

- `start_run` 创建幂等键。
- 同一 Session active Run 仲裁。

否则实施 Agent 很容易在第一阶段把重复 Run 和聊天顺序问题写进 schema，后续迁移代价会很高。

## 4. 阻塞 Findings

### 4.1 `start_run` 缺少创建幂等键

`RunInput` 可幂等回放只解决同一个 Run 内 resume / replay，不解决 `start_run` 调用本身幂等。
Web / WeChat / Service 调用 `start_run` 超时后重试，可能创建两个 Run，进而写入两次 transcript、
两份 outbox。

建议：用 `StartRunRequest` 取代散参，包含 `session_id`、`client_request_id` 或
`input_message_id`、`RunInput`、`RunOptions`。Host 对 `(session_id, client_request_id)`
做唯一约束；重复提交返回同一个 `RunStream / RunHandle`，不得新建 Run。

### 4.2 同一 Session active Run 仲裁没有落成契约

文档说 SessionManager 管写入顺序，Run 有 `QUEUED`，Lane 是独立信号量，但没有明确同一
Session 下多个 `start_run` 的仲裁规则。

建议：增加 Session 级 run admission policy。第一版规定：同一 Session 同时只能有一个
`QUEUED / RUNNING / WAITING / RECOVERING / CANCELLING` Run；后续输入要么以 Host 内部队列
排为 next run，要么返回 busy / rejected。该规则必须是持久化原子仲裁，不靠内存锁。

## 5. 重要 Findings

### 5.1 `RunStream.events` 生命周期与背压语义需要明确

`RunStream.events` 应是 EventLog 的订阅视图，不是执行控制通道。调用方断开只关闭订阅，
不取消 Run；RunEvent 必须先落 EventLog 再推送；慢消费者由 cursor 补读，不反压 Engine 主执行，
除非明确进入资源保护策略。

### 5.2 EventLog 缺少“持久事实事件”和“展示型流式事件”的分层

建议定义 `RunEventKind` 或事件层级：

- `lifecycle / result / tool_summary / validation / recovery` 为持久事实。
- `assistant_delta / progress / preview` 可配置持久化或 coalesce 为稳定 block。

Outbox projection 只能依赖 canonical facts，不能依赖 volatile preview。

### 5.3 缺少客户端读取聊天记录的 public API

文档说明 Session 要提供 transcript / timeline read model，但 public interface 只有
`get_session`，没有可分页读取聊天记录的接口。

建议：增加 `list_session_timeline(session_id, after, limit) -> SessionTimelinePage`。
它读取展示 read model，不是 ContextBuilder 输入；reasoning 字段只出现在 read model，
不参与运行态回放。

### 5.4 `RunResult` 仍然太抽象

Replay validation、Outbox projection、断线补查都依赖同一个结果事实。

建议：规定 `RunResult` 是不可变快照，至少包含 `result_id`、`run_id`、terminal event cursor、
answer view、warnings/errors、artifact refs、created_at、validation status。业务 facts 不进入
Host 语义，但可通过通用 artifact / fact refs 引用。

### 5.5 Replay 的 Validator 来源需要持久化契约引用

Host 禁止进程内对象进入 `RunInput`，validator 如果只是 Service 注入的回调，进程恢复后会丢失。

建议：在 `RunOptions` 或 policy 中加入 `OutputContractRef`，它是可持久化、可解析的契约引用。
Host 只消费通用 `ValidationDecision`，并把 decision 写入 EventLog。

### 5.6 ToolRuntime 缺少最小生命周期事件口径

建议预留 `ToolRuntimeEvent` / `ToolGovernanceDecision` 的通用事实口径，例如：

- tool call proposed
- approved / denied / deferred
- started
- completed
- failed
- truncated / fetch_more

这些事件可映射为 RunEvent 或独立 audit event。

## 6. 建议 Findings

- Lane 需要写明 owner token / lease / fairness / stale cleanup 是 runtime 语义。
  lane acquire 返回 holder token；release 必须带 token；支持 timeout、TTL / heartbeat、
  stale holder cleanup、FIFO 或明确非 FIFO 策略。
- RemoteProxy 的流式协议不要被 Python `AsyncIterator` 形状绑死。保留本地 worker protocol，
  但远程 wire protocol 后续应以 cursor / ack / reconnect 为核心。

## 7. 可选的更优设计

### 7.1 `StartRunRequest` 取代散参

不是为了“多包一层”，而是为了把 `client_request_id`、admission policy、
output contract ref、delivery preference、trace correlation id 放在一个可持久化创建事实里。

### 7.2 `SessionTimeline` 独立于 `RunEventLog`

RunEvent 是执行事实；Timeline 是客户端阅读模型。二者分开，可以同时满足 debug / recovery
与产品展示，不让 reasoning、preview、tool progress 污染运行态上下文。

### 7.3 Canonical Event + Preview Event 双层 EventLog

第一版可以同表不同 kind，但概念上建议分层。Outbox、replay、recovery 只依赖 canonical event；
UI 可以消费 preview event。

## 8. 修复状态

修复日期：2026-05-06。

- 4.1 已修复：`docs/host/design.md` 已用 `StartRunRequest` 收束 `start_run` 创建事实，
  并要求 `(session_id, client_request_id)` 唯一。
- 4.2 已修复：已补充 Session admission policy。第一版同一 Session 同时最多一个非终态 Run，
  新 key 在 active Run 存在时返回 typed busy / conflict，不隐式创建 next-run queue。
- 5.1 已修复：已明确 `RunStream.events` 是订阅视图、EventLog 先落库再推送、慢消费者用 cursor
  补读。
- 5.2 已修复：已补充 canonical event 与 preview event 分层，Outbox、replay、recovery
  只依赖 canonical event。
- 5.3 已修复：public interface 已增加 `list_session_timeline`，并说明它是客户端 read model，
  不是 ContextBuilder 输入。
- 5.4 已修复：`RunResult` 已细化为不可变快照，并拆分 `artifact_refs` 与 `evidence_refs`。
- 5.5 已修复：已补充 `OutputContractRef` 与 validator decision 持久化要求。
- 5.6 已修复：已预留 ToolRuntime 最小生命周期事件口径。
- 6 已修复：lane owner token / lease / fairness / stale cleanup 已写入 runtime 语义；
  RemoteProxy wire protocol 已预留 cursor / ack / reconnect。
- 7.1 已采纳：`StartRunRequest` 已替代散参作为候选 public interface。
- 7.2 已采纳：`SessionTimeline` 已独立于 `RunEventLog`。
- 7.3 已采纳：已补充 canonical event 与 preview event 双层语义。
