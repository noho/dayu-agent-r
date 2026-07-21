# WU-CLI-SMOKE-01-R1 Goal Confirmation

## Gate

- Work unit：`WU-CLI-SMOKE-01-R1` Engine Delta Transient Live Stream Remediation。
- 类型：高风险 bug fix。
- Gate：`goal confirmation`。
- Decision：pass；用户于 2026-07-20 明确确认目标与范围。
- Design truth：`docs/host/design.md`、`docs/engine/design.md`。
- Control truth：`docs/host/issues-implementation-control.md`。
- Additional control：`docs/phaseflow-umbrella-optimization-control.md`，风险级别为 `production-high`。

## 第一性原理判断与直接证据

问题真实存在且高严重度判断成立：`EngineEvent` 的三类 per-chunk delta 都只服务运行态展示，Engine 不拥有 Host durable cursor、EventLog 或多客户端 fanout；Host ingest 却把 `REASONING_DELTA` 单独写成每 chunk 一条 `PREVIEW` EventLog row，而 `CONTENT_DELTA` 与 `TOOL_CALL_DELTA` 只返回 accepted/no-row。`watch_session_events` 当前完全通过 EventLog cursor 轮询，因此 reasoning 的实时展示被错误绑定到 durable storage，写放大会随 chunk 数线性增长。

语义 owner 判定：

- Engine 只拥有本次 `EngineEvent stream` 内的 delta 产生与顺序。
- Host ingest 负责 Attempt / execution identity 校验；Host runtime 负责 transient identity、ordering、fanout、slow consumer、detach 与 close。
- EventLog 只拥有 durable facts 与 durable `event_sequence`，不拥有 transient delta。
- Service / UI / CLI 只消费 Host public typed contract 并选择展示类型，不得绕过 Host 消费 raw `EngineEvent`。

当前 `docs/host/design.md` 仍保留 reasoning durable `PREVIEW` 特例，并把 `HostEvent` 定义为带 durable `event_sequence` 的 EventLog-derived view。plan gate 必须先收敛并更新该设计边界，再据此生成实现方案；不得让实现或测试先行发明另一套语义。

## 已确认目标与成功信号

- `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 统一进入 Host-owned typed transient live contract，三者均不写 EventLog。
- Host 在 durable identity governance 通过后发布 transient delta；非法、stale 或 late candidate 不得进入 live fanout。
- 同一 `open_host` runtime 内的多个已 attach watcher 能按统一 contract 接收三类 delta，消费者可以按 type 选择。
- transient identity 与 ordering 不伪装成 durable `HostEvent.event_sequence` 或离线 replay cursor。
- 慢 watcher、detach、Host close 与 worker terminal 不反压 EventLog append、不泄漏 task、不取消 Run、不制造 terminal fact。
- CLI `prompt` / `interactive` 的实时 `--thinking`、`--no-thinking`、final answer、activity/detail、stdout/stderr、取消与 renderer close 保持正确且不重复输出。
- 大量三类 delta 的 EventLog row 数均为零；terminal final answer 与其它 durable facts 继续正常提交和补读。

## 非目标与范围边界

- 第一版只承诺同一 `open_host` runtime 内的多 watcher fanout；不引入跨进程 broker、跨 Host 实例 fanout、断线补放或重启恢复。
- 不实现 delta durable replay、历史 token/thinking 查询、retention 补救或 EventLog 压缩。
- 不修改模型 reasoning 开关，不实施 `WU-CLI-SMOKE-01-R2` thinking panel。
- 不重写 canonical HostEvent、outbox、audit、Tool Trace、Conversation Memory 或 Engine delta contract。
- 不建设通用事件总线；只实现当前三类 delta 所需的最小 Host-owned typed runtime contract。

## Slice 与 review 约束

- 本 WU 命中生产行为、EventLog、public Host / Service contract、并发与用户可见 CLI 行为，采用 umbrella `production-high` 完整 gate。
- plan 默认控制在 2–3 个语义闭环 slices；超过 3 个必须证明无法按 contract/fanout、consumer migration、final validation 闭环合并。
- 每个生产 slice 必须由 AgentMiMo 与 AgentDS 双路 code review；accepted finding 由 AgentCodex 修复并双路 re-review。
- plan review 使用 `/planreview`；code、aggregate 与 PR review 使用 `/deepreview`。

## 风险与开放问题

- blocking open questions：无。
- plan 必须具体裁决 transient typed envelope、run/attempt identity、运行态 sequence、跨 durable/transient 观察顺序、bounded slow-consumer policy、watch attach race、terminal/detach/close 语义与 public API 形状。
- 任何要求跨进程实时 fanout 或 durable replay 的新证据都属于 scope expansion，必须返回用户裁决。

## Validation

- PR 179 GitHub 状态：merged，merge commit `bd1d3e94c571e0b98096e9cfa4d169cefd8003c9`。
- 本地 `main` 在建分支前位于 `bd1d3e94`。
- 工作分支：`phaseflow/wu-cli-smoke-01-r1`。
- `git diff --check`：pass。

## Completion

`goal confirmation` gate pass。下一个未完成 gate 是 `plan`，由 AgentCodex 产出 code-generation-ready plan。
