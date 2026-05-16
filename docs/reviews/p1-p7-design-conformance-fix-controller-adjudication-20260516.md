# P1-P7 Design Conformance Fix Controller Adjudication

日期：2026-05-16

分支：`fix/host-p1-p7-awaiting-production-wiring`

设计真源：`docs/host/design.md`

总控文档：`docs/host/implementation-control.md`

Fix target：`C-P1P7-001`，P7 awaiting production wiring 未接入 `HostDispatchScheduler`

## Verdict

**PASS。`C-P1P7-001` 可关闭。**

Codex 本轮修复将 awaiting production wiring 接到 `HostDispatchScheduler` 的 tool-enabled production request 构造路径，而不是只修 lower-level `ToolRuntime` 测试路径。MiMo 与 DS 独立复审均为 PASS，未发现 Blocking / High / Medium finding。Controller 接受该结论。

## Evidence

- Fix artifact：`docs/reviews/p1-p7-design-conformance-fix-awaiting-production-wiring-20260516.md`
- MiMo fix review：`docs/reviews/p1-p7-design-conformance-fix-review-mimo-20260516.md`，Verdict PASS
- DS fix review：`docs/reviews/p1-p7-design-conformance-fix-review-ds-20260516.md`，Verdict PASS
- Production code：
  - `dayu/host/tooling.py` 在 `HostToolingOptions` 增加 construction-scope `wait_adapter_registry`
  - `dayu/host/dispatch.py` 在 `HostDispatchScheduler._run_input_builder_for_dispatch` 构造 `ToolRuntimeBuildRequest` 时注入 `DefaultHostToolAwaitingAcceptPort` 与 `tooling_options.wait_adapter_registry`
- Test coverage：
  - `tests/host/test_phase7_waiting_integration.py` 增加 scheduler-level integration test，覆盖 public start、scheduler drain、production `ToolRuntimeExecutor` awaiting outcome、Run `WAITING`、Attempt `SUSPENDED`、active wait record 与 `resolve_wait` resume

## Accepted Reviewer Notes

### Low

1. MiMo L1：`HostToolingOptions.wait_adapter_registry` docstring 可进一步说明 adapter 调用发生在 Host transaction 外。
   - Controller disposition：接受为文档增强建议，非 blocking。本轮字段说明已明确不进入 durable row 或 per-run request；transaction 外调用约束由 `wait_adapter.py` 与调用方保持。

2. DS L-P1P7-001：新测试未经过完整 Engine agent loop，而是捕获 production `AgentRunRequest` 后直接调用 production `tool_executor.execute()`。
   - Controller disposition：接受为覆盖深度 residual risk，非 blocking。C-P1P7-001 的 root cause 是 scheduler production wiring 缺失；该测试已覆盖 scheduler 构造出的 production `ToolRuntimeExecutor`。

3. DS L-P1P7-002：scheduler close 时原始 `SUSPENDED` Attempt 的 clean EOF closeout 依赖已有容错。
   - Controller disposition：接受为测试边界 residual risk，非 blocking。当前 Host suite 通过，且该风险不影响 awaiting accept wiring 是否已接入 production path。

## Architecture Decision

本轮修复保持 `UI -> Service -> Host -> Engine` 分层边界：

- `wait_adapter_registry` 是 Host construction / composition-scope 输入，不进入 Engine、`dayu.runtime`、per-run request 或 durable row。
- `DefaultHostToolAwaitingAcceptPort` 仍在 Host 层执行三事实原子写入与 Host 状态推进。
- `ToolRuntime` 只通过 Host 内部 port 与 registry 接受 awaiting outcome，没有新增 callback endpoint、poller 后台循环、recovery scan、remote worker 或 external job physical cancel。
- 未新增 design doc 外的新 durable table、EventLog event type 或跨层反向依赖。

## Final Disposition

`C-P1P7-001` 从 blocking finding 降为 closed。P1-P7 corrected design conformance review 在该 blocking finding 修复后可进入 fix PR gate。

剩余事项按原 Phase 7 residual owners 跟踪，不阻塞本 fix：

- callback endpoint
- poller 后台循环与 retry fencing
- recovery scan
- remote worker / remote wait resume
- external job physical cancel / revoke
- `RunStartReason.STEER` / `RunStartReason.RECOVERY`
- Engine agent loop 到 awaiting 的更完整端到端测试
