# P1-P7 Design Conformance Review Controller Adjudication

日期：2026-05-16

## Scope

- Review target：已合并 `main` 上的 Host P1-P7 实现，HEAD=`c39de2e`
- Design truth：`docs/host/design.md`
- Control reference：`docs/host/implementation-control.md`
- Review artifacts：
  - `docs/reviews/p1-p7-design-conformance-review-mimo-20260516.md`
  - `docs/reviews/p1-p7-design-conformance-review-ds-20260516.md`
  - `docs/reviews/p1-p7-design-conformance-review-codex-20260516.md`

## Reviewer Results

- AgentMiMo：PASS。未发现 blocking design deviation；提出 `tool_runtime.py` 文件规模与 sha256 digest 正则重复定义两个低/信息项。
- AgentDS：PASS with Medium wiring gap。确认 1 个 Medium production wiring gap：`HostDispatchScheduler` 未向 `ToolRuntimeBuildRequest` 注入 `awaiting_accept_port` 与 `wait_adapter_registry`；另有 `RunStartReason` 缺少未来 `steer` / `recovery` 枚举值和 `ATTEMPT_RUNNING` 事实归属说明项。
- AgentCodex：FAIL。提出 1 个 blocking design-conformance finding：P7 awaiting accept path 已在 direct ToolRuntime/helper 路径实现，但真实本地 dispatch scheduler 的生产 ToolRuntime 构造路径未接入 awaiting accept port 与 wait adapter registry，导致 production local dispatch 无法触发 `WAITING`。

## Controller Findings

### C-P1P7-001 — Accepted Blocking — P7 awaiting production wiring 未接入 `HostDispatchScheduler`

- 来源：AgentCodex C01；AgentDS D01 独立确认。
- 严重性：blocking design conformance / production wiring。
- 状态：accepted。

#### What Can Go Wrong

真实本地执行路径经 `HostDispatchScheduler` 构造 ToolRuntime。业务工具如果返回 `ToolAwaitingOutcome`，当前生产 wiring 不会进入 Host awaiting accept path，不会创建 wait record，不会把 Run 推进到 `WAITING`，也不会把 Attempt 推进到 `SUSPENDED`。ToolRuntime 会把 awaiting outcome 降级为受治理工具失败。

这意味着 P7 的核心能力“长事务工具让 Run 进入 WAITING，并由 `resolve_wait` resume”只在 direct ToolRuntime 测试装配中可达，尚未在生产本地 dispatch 入口闭环。

#### Direct Evidence

- `dayu/host/dispatch.py` 的 `HostDispatchScheduler._run_input_builder_for_dispatch(...)` 构造 `ToolRuntimeBuildRequest` 时只传入：
  - `effective_bundle_request`
  - `execution_scope`
  - `accept_port=DefaultHostToolFactAcceptPort(...)`
  - `duplicate_governance_registry`
- 同一路径未传入：
  - `awaiting_accept_port`
  - `wait_adapter_registry`
- `dayu/host/tool_runtime.py` 的 `ToolRuntimeBuildRequest` docstring 明确说明：`awaiting_accept_port` 或 `wait_adapter_registry` 缺失时，awaiting outcome 返回受治理错误。
- `dayu/host/tool_runtime.py` 的 `_accept_awaiting(...)` 直接检查 `self._awaiting_accept_port is None or self._wait_adapter_registry is None`，命中后返回 `_awaiting_configuration_failure()`。
- `HostLocalExecutionOptions` 与 `HostToolingOptions` 当前也没有可供 production composition root 注入 wait adapter registry 的字段。
- `tests/host/test_phase7_waiting_integration.py` 的 P7 集成测试直接构造 `DefaultToolRuntimeFactory(...).create_tool_runtime(...)`，并手工传入 `DefaultHostToolAwaitingAcceptPort(...)` 与 `_wait_adapter_registry()`，绕过了 `HostDispatchScheduler` 的生产装配路径。

#### Design / Plan Alignment

`docs/host/design.md` §20 的目标语义是 ToolRuntime Host accept path 拥有 awaiting canonical transition：`ToolAwaitingOutcome` 应被 Host accept path 持久化为 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` 与 active wait record。P7-S5 plan 也要求 integration proof 覆盖 local awaiting tool -> `WAITING` -> manual/poll resolve -> resumed Run。

当前 lower-level implementation 满足该语义，但 production scheduler composition 未接线，不能把 P7 判断为 production-complete。

#### Required Fix Direction

- 在 Host local execution composition 中引入明确的 wait adapter registry wiring。应保持层边界：adapter object 不进入 durable row，不进入 per-run request。
- `HostDispatchScheduler._run_input_builder_for_dispatch(...)` 构造 `ToolRuntimeBuildRequest` 时必须注入：
  - `DefaultHostToolAwaitingAcceptPort(transaction_runner=..., event_log_store=...)` 或等价 port
  - Host composition root 提供的 `WaitAdapterRegistry`
- 补真实 scheduler-level integration test：通过 public start / scheduler / ToolRuntime production path 运行返回 `ToolAwaitingOutcome` 的 business tool，断言 Run -> `WAITING`、Attempt -> `SUSPENDED`、active wait record created，再通过 `resolve_wait` 恢复。
- 更新 README / 总控状态，区分当前 direct ToolRuntime path 与 production dispatch path 的修复结果。

### C-P1P7-002 — Accepted Low / Deferred — `RunStartReason` 缺少 `steer` / `recovery`

- 来源：AgentDS D02。
- 严重性：Low。
- 状态：accepted-as-deferred。

`docs/host/design.md` 对 `RUN_STARTED.start_reason` 的第一版枚举列出 `initial`、`queue_promotion`、`resume`、`steer`、`recovery`。当前 `RunStartReason` 只有 `INITIAL`、`QUEUE_PROMOTION`、`RESUME`。

这不影响 P1-P7 当前可执行路径，因为 steer 与 recovery 尚未实现；但后续 steer / recovery phase 应补齐枚举与 codec 测试，避免实现时再引入 schema / contract drift。

### C-P1P7-003 — Rejected As Current Deviation — `ATTEMPT_RUNNING` 由 dispatch path 追加

- 来源：AgentDS D03。
- 严重性：Info。
- 状态：rejected-as-current-deviation。

`docs/host/design.md` 顶部职责表确实说 Attempt Dispatch “不得生成治理事实”，但同一设计文档后续状态机明确规定 worker accepted 后 Host append `ATTEMPT_RUNNING`，Attempt 进入 `RUNNING`。当前 `HostDispatchScheduler` 在 worker accept 后追加 `ATTEMPT_RUNNING` 并推进 Attempt 状态，符合后续具体状态机设计；这不是当前 blocking design deviation。

若后续要清理职责表措辞，应走设计文档澄清，不应把当前实现视为偏离。

### C-P1P7-004 — Non-blocking Maintainability — `tool_runtime.py` 规模过大

- 来源：AgentMiMo。
- 严重性：Low。
- 状态：deferred cleanup。

`tool_runtime.py` 规模接近 5000 行，承载 effective bundle、accept barrier、truncation、fetch_more、duplicate governance、diagnostics、awaiting accept 等多个 concern。当前设计将 ToolRuntime 作为工具治理 owner，行为未发现错误；但后续 phase 继续扩展前应考虑按 concern 拆分，避免形成长期 God module。

### C-P1P7-005 — Non-blocking Cleanup — sha256 digest 正则重复定义

- 来源：AgentMiMo。
- 严重性：Info。
- 状态：deferred cleanup。

`dayu/host/api.py` 与 `dayu/host/durable/codec.py` 均定义等价 sha256 digest pattern。当前语义一致，PR 56 fix 已让 `waiting.py` 复用 durable digest 真源；后续可进一步统一 public API digest 校验实现。

## Accepted Architecture Evidence

三份 review 对以下事项基本一致：

- 未发现 `dayu.engine` 反向依赖 `dayu.host`。
- 未发现 `dayu.host` 依赖 `dayu.service` / `dayu.ui` / `dayu.fins`。
- `dayu.runtime` 保持层中立，只依赖标准库与 `dayu.contracts`。
- EventLog / Run / Attempt / WaitRecord 的核心状态枚举与 DDL CHECK 约束整体对齐设计。
- `resolve_wait` condition chain、late diagnostic、`WAITING` cancel、WaitPoller 交易外 adapter 调用、Engine awaiting confirmation diagnostic 均与 P7 设计方向一致。
- 未发现把 adapter object / callable 放入 durable wait record。
- callback endpoint、recovery scan、remote wait resume、tool trace projection 等 non-goals 仍未越界实现。

## Verdict

P1-P7 corrected design conformance review **不通过**，原因是 C-P1P7-001：P7 awaiting production wiring 未接入 `HostDispatchScheduler`。这是 production wiring 层面的 blocking gap，不是下层 waiting / resolve_wait state machine 本身的错误。

建议进入 accepted-fix gate：先修复 C-P1P7-001，并以真实 scheduler integration test 证明 production local dispatch 可触发 `WAITING`。修复后再派 AgentMiMo / AgentDS / AgentCodex 做 targeted re-review。
