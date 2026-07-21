# WU-HOST-SESSION-EVENT-DELIVERY-01 Goal Confirmation

## Decision

- decision: `pass`
- work unit: `WU-HOST-SESSION-EVENT-DELIVERY-01 Host Session Event Delivery Ownership and Bounded Mailbox`
- type: architecture-sensitive public contract / ownership correction
- current gate: `goal-confirmation-pass`
- next entry point: `plan`
- confirmed by: user, 2026-07-21
- blocking open questions: None

## Preflight 与前置条件

- GitHub PR #180 已核实为 `MERGED`，merge commit 为 `2c02079a82c049b49914be412178006ccd354049`。
- 本地 `main` 已与 `github/main` fast-forward 对齐到该 commit。
- 已从最新 `main` 创建独立分支 `phaseflow/wu-host-session-event-delivery-01`。
- 创建分支前工作树干净；未覆盖既有改动，也未发现分支范围冲突。

## 动机与直接代码证据

动机基于最新 `main` 的直接代码证据成立：

- `dayu/host/transient_delta.py` 仍以 Host 私有固定 item 常量和 batch `drain_nowait()` 管理 transient queue，无法表达统一 construction-time policy，也会把已出队 batch 保留到 iterator generator。
- `dayu/service/entrypoint_runtime.py` 仍创建第二条 Service event-copy relay queue 与 drain task，导致 Session Event Delivery ownership 分裂。
- `dayu/host/api.py` 的 public watch factory 仍为同步返回 `AsyncIterator`，尚未定义 async attach 的 successful-return 生效边界。
- terminal producer 当前仍存在只携带 `session_id` 的 promotion / wake 路径，尚未统一传递 transaction-local exact terminal sequence。
- packaged runtime config 尚无 `session_event_delivery_policy` 的两个 required 字段与默认值。

因此问题不是容量数字微调，而是 Host / Service ownership、attach 线性化、bounded retention、durable/transient merge 和 terminal post-commit 协调尚未形成单一闭环。

## 语义 owner

- Host Session Event Delivery：live fanout、每订阅唯一 mailbox、唯一 in-flight retained-item accounting、per-Session subscription admission、overflow / detach、durable/transient merge 与 closable iterator lifecycle 的唯一 owner。
- Host EngineEvent ingest：durable identity、late-state validation，以及从同一 validation transaction 取得 `Attempt.started_event_sequence` causal fence。
- EventLog / durable transition：terminal durable fact 与 exact committed `event_sequence` 的唯一 owner。
- local-only `TerminalPostCommitPort`：本 opener 的 terminal-ready wake 与 optional queue-promotion hint；不承担跨进程广播或 correctness 真源。
- Service：统一 iterator 的 sole consumer、exact-five observation/cleanup contract、快速非阻塞 callback 适配与本地 degraded recovery。
- runtime composer / operator：opener-wide `HostSessionEventDeliveryPolicy` 的配置与装配 owner。
- Engine：只拥有单个 Engine event generator 内的顺序；不拥有 Host cursor、fanout、mailbox、replay或跨域排序。

## 目标与成功信号

- 保留统一、可关闭的 Host session event iterator 外观，并把 public factory 改为 async attach；successful return 是订阅生效边界。
- 删除 Service event-copy relay；Host 成为 Session Event Delivery 的唯一 owner。
- 每订阅只有一个按 retained item 数量有界的 mailbox，加至多一个 counted in-flight item；packaged `transient_mailbox_max_items=512`。
- 同一 Session、同一 opener runtime 最多同时 attach `max_subscriptions_per_session=4` 个 watcher；cap 在任何 mailbox / cursor transaction / task / iterator allocation 前线性化 reserve。
- 使用 typed admission / overflow errors；当前只有 item overflow，不引入恒定容量分类字段或 byte-dimension enum。
- causal fence、bounded durable catch-up、mailbox-empty periodic reconciliation、跨 opener deterministic barriers 与 terminal producer static/runtime barriers全部闭环。
- Service sole consumer、exact-five observation/cleanup、callback 非阻塞与必要执行域隔离全部闭环。
- runtime config、assembly、CLI 调用点、低基数 metrics、受影响测试、单文件覆盖率目标 `>=80%`、完整 pyright、`git diff --check` 与 README trigger audit 通过。

容量 contract 明确只按 retained item 数量有界，不承诺 transient payload logical bytes、Python resident heap、Host-global Session 数量或跨 Session 总内存上界。普通 UI 每个 turn 独立 attach / close watcher；单个 Agent Run 仍可能包含多次 LLM iteration。用户已明确接受 provider / model 输出边界下不另设 byte cap 的 residual risk。

## Scope boundary

实施范围覆盖 Host public contract / exports、Session Event Delivery、terminal post-commit 协调、所有 terminal producer、durable merge、runtime config / assembly、Service sole-consumer 状态机、CLI 调用点、测试、metrics 与 README audit。`docs/host/design.md` 是主要设计真源；`docs/engine/design.md` 只用于裁决 Engine 边界；`docs/host/issues-implementation-control.md` 是唯一主总控。

`docs/phaseflow-umbrella-optimization-control.md` 不是本 WU 的任务流水账，本 WU 不修改它。

## 非目标

- 不持久化、重放或断线补放 delta。
- 不建立第三 sequence domain 或 durable/transient 全局总序。
- 不实现跨进程 terminal 广播。
- 不让慢 UI / Service 暂停 Agent 或 Engine。
- 不增加 Host-global 跨 Session quota。
- 不实施 `WU-CLI-SMOKE-01-R2`。
- 不创建 GitHub Issue；当前 owner / destination 是用户明确裁决。

## Dispatch

下一步派发 AgentCodex 形成 code-generation-ready implementation plan。plan 完成后，AgentMiMo 与 AgentDS 将并行、独立使用 `$planreview` 审查；任何 material finding 逐项基于代码证据裁决。
