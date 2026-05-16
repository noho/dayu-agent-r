# Host Phase 7 P7-S5 / Aggregate Exit Controller Adjudication

日期：2026-05-16

## Scope

- Slice：P7-S5 Integration, Docs, Gate Validation
- Phase：Phase 7 Tool Awaiting / resolve_wait / Wait Adapter aggregate exit
- Implementation artifact：`docs/reviews/host-phase7-implementation-s5-integration-docs-gate-validation-20260516.md`
- MiMo aggregate review：`docs/reviews/host-phase7-aggregate-review-s5-mimo-20260516.md`
- DS aggregate review：`docs/reviews/host-phase7-aggregate-review-s5-ds-20260516.md`

## Findings

未接受 blocking finding。

MiMo review 结论为 P7-S5 PASS、Phase 7 Aggregate Exit PASS。DS review 结论为 PASS，无 open questions。两份 review 均确认：

- P7-S5 新增集成测试覆盖本地 awaiting tool 经真实 ToolRuntime accept path 进入 `WAITING` / `SUSPENDED`，再由 public `resolve_wait(source=manual)` 恢复同一 Run 并创建新 Attempt。
- Poll path 已由 P7-S4 `test_wait_adapter_polling.py` 覆盖 ready -> `resolve_wait` 与 cancelled abandon，本 slice 不需要重复新增 poll 集成。
- `dayu/host/README.md` 已清理 `WAITING` cancel deferred 的旧表述，并同步 `ResolveWaitRequest` request shape、late diagnostic、最小 poller 与 Engine awaiting / suspended diagnostic boundary。
- Phase 7 S1-S5 整体满足设计真源与计划：typed wait outcome envelope、durable wait record、ToolRuntime awaiting accept、`resolve_wait` resume / terminal closeout、`WAITING` cancel、late diagnostic、poller 与 EngineEvent confirmation 边界一致。

DS review artifact 中有一处 evidence 文本把 `tests/host/test_phase7_waiting_integration.py` 的测试代码行号误写为 `dayu/host/README.md` 行号。controller 以实际 diff 和测试文件为准裁决；该 artifact 文字错误不影响 review 结论，不构成 blocking finding。

## Accepted Evidence

- `tests/host/test_phase7_waiting_integration.py` 新增 `test_local_awaiting_tool_manual_resolve_resumes_run`，使用 `DefaultToolRuntimeFactory`、`EffectiveToolBundleBuilder`、`DefaultHostToolFactAcceptPort`、`DefaultHostToolAwaitingAcceptPort` 与 `WaitAdapterRegistry` 组成真实 Host ToolRuntime path。
- 新测试断言 ToolRuntime 执行后返回 `ToolAwaitingOutcome`，Run 进入 `WAITING`，Attempt 进入 `SUSPENDED`，active wait record 处于 `WAITING`。
- 新测试通过 public `resolve_wait(...)` 提交 completed outcome 后断言 Run 回到 `RUNNING`，`current_attempt_id` 变更，并通过 RunInputBuilder 验证 resume request messages 包含 accepted wait result fact 与 wait id。
- `dayu/host/README.md` 现已说明 `cancel_run` / `cancel_session_runs` 支持 `WAITING` cancel，并明确 `RECOVERING` cancel 仍归 Phase 11。
- `dayu/host/README.md` 现已说明 `ResolveWaitRequest` 必须携带 UTC-aware `observed_at`、`source`、`idempotency_key` 与强类型 `outcome` envelope。
- `dayu/host/README.md` 现已说明 Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 只作为 diagnostic confirmation，不创建 wait record，不把 Run 推入 `WAITING`，也不把已 `WAITING` Run 失败收口。
- 未修改 `docs/host/design.md`。P7-S5 implementation 未修改 `docs/host/implementation-control.md`；该文档由 controller 在 checkpoint 阶段更新。

## Verification

- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`389 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## Residual Risk

- callback HTTP endpoint、callback auth / replay、远端 worker wait resume、外部 job physical cancel / revoke 仍未实现，归后续 callback adapter / remote / adapter hardening owner。
- Poller 当前只提供 `poll_once()` 单轮入口，无后台调度循环、退避、并发 in-flight fencing 或 adapter 错误重试治理，归后续 poller runtime hardening owner。
- Host recovery scan 对 `WAITING` Run 的启动后观察恢复仍未实现，归 Phase 11 Recovery owner。
- Engine 公共事件当前不携带 Host accepted wait refs，Phase 7 只能做 diagnostic / idempotent confirmation，不能做强 matching-ref 校验；该项归后续 Engine contract 演进。
- Durable duplicate ledger 与 durable tool trace projection 未实现，分别归后续 duplicate hardening / projection or tool trace owner。

## Verdict

P7-S5 accepted。Phase 7 aggregate exit accepted。可进入 accepted slice commit、总控文档 Phase 7 completion checkpoint，并准备 ready-to-open-draft-PR gate。
