# P1-P5 Design Conformance Review - AgentCodex

## Verdict

PASS。

本轮以 `docs/host/design.md` 为设计真源，对当前分支 `feat/host-phase5-local-dispatch` 的 P1-P5 全仓实现做 corrected review gate；`docs/host/implementation-control.md` 仅作为 phase 范围线索。未发现 blocking 级设计偏差。

- PR：54
- 审查时间：2026-05-15
- blocking findings：0
- non-blocking hardening findings：2
- 本轮性质：只做静态设计一致性 review；未修改生产代码、未提交、未 push、未创建 PR。

## Scope

覆盖路径：

- P1：公共契约、`ToolBundle` 构造输入边界、`dayu.runtime` 中立性、Host/Engine/Service/UI/Fins 反向依赖、弱类型逃逸。
- P2：durable store、fresh schema、EventLog、event id/sequence、append/read/idempotency、payload artifact/liveness、事件真源边界。
- P3：session/run/attempt/admission、active run invariant、lane slots、queue promotion、cancel/terminal closeout、幂等语义。
- P4：`create_host_command_handle`、public facade、request/response contract、unsupported operation、异步调度生命周期边界。
- P5：RunInputBuilder、local dispatch、local proxy、EngineEvent ingest、active cancel；确认 Host 仍持有 Agent/AsyncAgent/AsyncOpenAIRunner 生命周期和取消治理。
- 跨 phase 分层与生产接线：`UI -> Service -> Host -> Engine`，runtime 中立，Host 到 Engine 的允许路径，durable bootstrap、transaction runner、EventLogStore、idempotency、command facade、admission service、dispatch scheduler、lane DB、LocalProxy、EngineEventIngestor、queue promotion。
- P6+ 预留：确认未提前实现 RemoteProxy、ToolRuntime、Recovery、ScenePrepare、ToolsDiscovery 等超 scope 能力为业务真源。

未覆盖项：

- 未重新运行测试或 pyright；本轮是 corrected review gate 的静态设计一致性检查，不是验证执行轮次。
- 未审查 PR diff 之外的第三方依赖源码。

## Findings

### F1 - ATTEMPT_RUNNING durable helper payload 弱于生产 scheduler 路径

- severity：non-blocking hardening
- owner 建议：Host durable transition owner
- 证据：
  - 生产 scheduler 在 worker accept 后直接 append `ATTEMPT_RUNNING`，payload 包含 `local_worker_id`、`lane_name`、`lane_claim_id` 等 dispatch/lane 诊断事实：`dayu/host/dispatch.py:747`、`dayu/host/dispatch.py:756`、`dayu/host/dispatch.py:1025`。
  - 低层 helper `AcceptWorkerRunningInput` 只接收 `run_id`、`attempt_id`、`attempt_running_event_id`、`occurred_at`、`actor`、`source`、`worker_accept_reason`：`dayu/host/durable/run_transition.py:269`。
  - helper `accept_worker_running_in_transaction` 会用该较弱输入追加 `ATTEMPT_RUNNING` 并推进 Attempt：`dayu/host/durable/run_transition.py:833`、`dayu/host/durable/run_transition.py:864`。
- 设计判断：
  - 这不是当前生产路径的 blocking 偏差。P5 scheduler 生产接线没有使用该 helper 作为 local dispatch accept 真源，而是在同一 write transaction 中 append 完整事件并调用 `mark_attempt_running_row` / `mark_dispatch_worker_accepted_row`：`dayu/host/dispatch.py:747`、`dayu/host/dispatch.py:761`、`dayu/host/dispatch.py:766`。
  - 风险是后续维护者可能误用低层 helper，产生比生产路径弱的 `ATTEMPT_RUNNING` canonical fact。
- 建议落点：
  - 收紧 `AcceptWorkerRunningInput`，补齐 worker/lane/dispatch 诊断字段；或明确将 helper 降级为测试/非生产辅助并限制调用面。
  - 验证点：新增 durable transition 单测，断言 helper 生成的 `ATTEMPT_RUNNING` payload 与 scheduler 生产 payload 的关键字段一致。

### F2 - 低层 dispatch CAS 允许 PENDING 直跳 DISPATCHING，接口能力宽于当前生产路径

- severity：non-blocking hardening
- owner 建议：Host durable state owner
- 证据：
  - 生产 scheduler 先将 pending dispatch 标记为 `WAITING_FOR_LANE`，再 acquire runtime lane token，随后 durable recheck 后标记 `DISPATCHING`：`dayu/host/dispatch.py:472`、`dayu/host/dispatch.py:510`、`dayu/host/dispatch.py:540`、`dayu/host/dispatch.py:563`。
  - 低层 `mark_dispatching_after_lane_row` docstring 和 SQL 均允许来源状态为 `PENDING` 或 `WAITING_FOR_LANE`：`dayu/host/durable/state.py:2077`、`dayu/host/durable/state.py:2090`、`dayu/host/durable/state.py:2133`。
- 设计判断：
  - 这不是 blocking 偏差。设计要求 lane 是 capacity primitive，不是 owner/lease/fencing；当前生产 scheduler 已在 Host 内完成 pending -> waiting -> lane acquire -> dispatching 的受控路径，dispatch record 没有被建模成 owner/lease。
  - 风险是 durable helper 的能力比生产路径宽，后续其他调用方若绕过 `_mark_waiting_for_lane`，会削弱 `WAITING_FOR_LANE` 作为调度诊断阶段的可观测性。
- 建议落点：
  - 如果 P5 后不再需要 PENDING 直跳能力，收紧 helper 仅允许 `WAITING_FOR_LANE`；或者拆成两个命名明确的 helper，并为直跳路径给出明确设计用途。
  - 验证点：补充 state 层 CAS 单测，覆盖 `PENDING` 直跳是否被允许的设计选择。

## No-Issue Coverage

### P1 - 公共契约与 runtime 边界

- no issue：`dayu.contracts.tool_declaration.ToolBundle` 是声明/投影对象，未成为 Host command 或 per-run payload；Host 侧 `HostToolingOptions` 只把 business `ToolBundle` 作为构造输入并校验保留工具名。
- no issue：`dayu.runtime` 的 lane/filelock 是层中立 runtime primitive，未 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- no issue：边界测试覆盖 Host 禁止 import fins/service/ui、runtime 禁止 import host/engine/service/ui/fins、Engine 禁止 import Host，且限制 Host import Engine 的允许模块。
- no issue：抽样扫描未发现 P1-P5 生产签名通过 `Any`、裸 `object`、无类型参数/返回值逃逸；schema 字面量中的 `"object"` 不属于签名逃逸。

### P2 - durable store 与 EventLog

- no issue：schema 使用 fresh bootstrap；版本不匹配 fail-fast，不保留旧 schema 兼容路径。
- no issue：`event_log` 以 `event_sequence INTEGER PRIMARY KEY AUTOINCREMENT` 和 `event_id UNIQUE` 建模；append 同一 event_id 同 body 幂等返回，异 body 冲突。
- no issue：EventLog append/read 是真源 primitive，continuity 和 latest 读取按 canonical fact 与 sequence 读取，没有用 projection/read model 替代事件真源。
- no issue：idempotency record 以 `(scope_kind, scope_id, idempotency_key)` 为主键，same request digest 重放，different digest 冲突。
- no issue：payload descriptor/digest/ref 的校验集中在 EventLog append 层，artifact/liveness 没有泄漏为业务层投影真源。

### P3 - session/run/attempt/admission

- no issue：Admission service 集中处理 session lifecycle、active run invariant、queued/running promotion、cancel 和 terminal closeout 触发。
- no issue：active run invariant 同时由 admission 读写逻辑与 partial unique index 保护。
- no issue：queued run promotion 在 active release 后按 durable FIFO 选择最早 queued run，并创建 local pending dispatch。
- no issue：cancel 语义区分 queued、predispatch running、active attempt、terminal replay 与 unsupported states；session-scope cancel 先读全集，避免部分取消。

### P4 - public API command path

- no issue：`create_host_command_handle` 只装配 durable store、transaction runner、EventLogStore、idempotency、admission 与 public facade，不隐式启动 local scheduler。
- no issue：public facade 的 request/response contract 保持稳定，unsupported operation 以稳定 unsupported response 返回，不写 EventLog 或 idempotency。
- no issue：local async dispatch 生命周期仍需调用方显式创建/open scheduler，Host 治理边界没有下放给 Engine。

### P5 - local dispatch / proxy / ingest / cancel

- no issue：dispatch scheduler 拥有 lane acquire、worker accept、worker event consume、active registry、lane release、worker close；dispatch record 是诊断与重复抑制记录，不是 owner/lease/fencing。
- no issue：RunInputBuilder 只读取 durable canonical facts、Run/Attempt/Dispatch row 与显式 policy/provider snapshot，不读取 UI/service 临时状态。
- no issue：LocalProxy 只把 Host 构造的 `AgentRunRequest` 交给 Engine public entry，Engine event 通过 Host envelope 进入 `EngineEventIngestor`。
- no issue：Engine ingest 验证 Host durable context 后才映射 Engine events；terminal closeout、active cancel closeout 与 unsupported waiting/suspended 均由 Host 写 canonical/diagnostic events 并触发 queue promotion。
- no issue：active cancel 的 durable 真源仍是 Host；in-process active worker registry 只做 best-effort cancel signal，不替代 durable closeout。

### Cross-Phase Layering 与生产接线

- no issue：Engine 未反向 import Host；Host 到 Engine 的依赖集中在设计允许的 local proxy/run-input/ingest 边界。
- no issue：Host 未 import `dayu.fins`，财报文档路径未在 P1-P5 Host 代码中绕过 `dayu.fins.storage`。
- no issue：production wiring 已接到 durable store bootstrap、transaction runner、EventLogStore、idempotency、admission service、command facade、dispatch scheduler、runtime lane DB、LocalProxy、EngineEventIngestor 与 queue promotion。
- no issue：P6+ 能力未被提前实现为业务真源；RemoteProxy、ToolRuntime、Recovery、ScenePrepare、ToolsDiscovery 等仍是明确预留点或 unsupported 路径。

## Residual Risk

- Host durable transition：F1 的 helper 与生产 scheduler payload 不完全同构，建议在 P5 hardening 或 P6 前收紧。
- Host durable state：F2 的 low-level CAS 能力宽于生产路径，建议在后续 phase 明确是否保留 PENDING 直跳能力。
- Host lifecycle composition：当前 command handle 与 scheduler 是显式双对象装配，设计上可接受；如果产品层需要“一键启动 Host”，应新增更高层 composition，不要让 command facade 隐式拥有 scheduler 生命周期。
- Active cancel watchdog / orphan recovery：P5 已完成 active cancel 信号与 ingest closeout；跨进程 worker orphan、stuck cancelling 的恢复属于后续 recovery phase，应继续保持 Host durable store 为真源。

## Final Gate

PASS：P1-P5 当前实现未发现偏离 `docs/host/design.md` 的 blocking 设计问题。
