# WU-PROJ-01 S3/S4 Residual Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Date: 2026-06-11
- Controller: Phaseflow
- Scope: `WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1`

## 总控裁决

两个 residual 都仍成立，并且都必须在 PR #136 当前分支内实施。它们不是 CAP-R1 修复的重复项，也不需要扩大到生产语义重设计。

## WU-PROJ-01-S3-R1

裁决：`accepted`

内容：补 dispatch before-worker catch-up happy path 独立集成测试，覆盖 required cursor 已被 projection checkpoint 覆盖时继续构造 ordinary RunInput 并接受 worker。

直接证据：

- CAP-R1 新增的 `test_open_host_dispatch_memory_catchup_reaches_required_cursor` 覆盖的是 required catch-up 追到 target 后允许 worker accept。
- S3-R1 要覆盖的是 checkpoint 已覆盖 required cursor 的 dispatch-level happy path，也就是在 worker accept 前不会因为 memory projection lag repair 阻断 ordinary RunInput 构造。
- 现有 `test_dispatch_lag_repair_rebuild_not_reached_fails_closed`、`test_memory_lag_pre_dispatch_failure_does_not_enter_recovering` 等覆盖失败收口，不是该 happy path。

实施边界：

- 优先只补 `tests/host/test_dispatch_scheduler.py` 独立集成测试。
- 若发现 production code 与设计不一致，必须停下报告；不要为了测试通过改生产语义。
- 测试应断言 worker accepted、ordinary RunInput 被构造、Run 可进入预期状态，并对 catch-up 行为做可观察断言，证明该路径不是失败收口或旧 recovery。

## WU-PROJ-01-S4-R1

裁决：`accepted`

内容：稳定 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 的 lane timeout flaky。

直接证据：

- 历史 review 记录该测试曾因 lane timeout 0.01s 偶发失败。
- 当前 `_open_scheduler(...)` helper 默认 `lane_default_timeout_seconds=0.01`；该测试没有验证 lane timeout 语义，使用该默认值会把 reactive fallback 语义测试暴露给无关的 timing 风险。
- S4-R1 应修测试结构或 fixture，使测试断言 reactive compact failure fallback 使用 failed view，而不是依赖宿主机调度在 10ms 内完成 lane acquire。

实施边界：

- 优先在该测试或相关测试 helper 中使用更确定的 synchronization / 更宽的测试专用 lane timeout。
- 不修改生产 lane acquire 语义。
- 不降低该测试对 fallback artifact、第二次 dispatch request、Attempt 数量和 no compact artifact 的断言强度。

## 后续 gate

进入 implementation gate，由 AgentCodex 实施 S3-R1 与 S4-R1。完成后必须走 code review / fix / re-review，再创建 accepted slice commit。
