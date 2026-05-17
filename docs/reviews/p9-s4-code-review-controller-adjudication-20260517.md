# P9-S4 Code Review Controller Adjudication

日期：2026-05-17

范围：P9-S4 `Projection Repair and After-commit Catch-up Wiring`

## Verdict

PASS。

AgentMiMo 与 AgentDS 双路 re-review 均确认 remaining blocking findings 为 0。P9-S4 可以进入 accepted slice commit。

## 设计真源对齐

- 符合 `docs/host/design.md` §24 Conversation Memory：memory projection 仍是 EventLog 可重建 read model，不写 EventLog，不成为 Run / Attempt / wait / dispatch 治理真源。
- 符合 `docs/host/design.md` §23 RunInputBuilder：repair-required 与 catch-up 不改变 RunInputBuilder 的 current prompt / memory 注入顺序，也不让旧 raw turns 绕过 memory budget。
- 符合 `docs/host/implementation-control.md` Phase 9 裁决：projection lag 显式可观测，小范围补齐与 rebuild / catch-up 属于 projection-local 行为，不触发 Run recovery。

## Accepted Findings

- 接受并修复 MiMo / DS 关于 `resolve_wait` 路径缺少 projection catch-up hook 的 finding。`resolve_wait(...)` 现在通过 command handle 的 admission service 注入 `ProjectionCatchupPort`，在 wait resolution transaction commit 后 best-effort 追平 projection。
- 接受并修复 DS 关于 ToolRuntime worker event consume path 缺少 hook 的 finding。`DefaultHostToolFactAcceptPort` 在成功接受 `TOOL_RESULT_ACCEPTED` 后触发 best-effort catch-up。
- 接受并修复 MiMo / DS 关于 catch-up failure 静默吞掉的 finding。通用 helper 迁移到 `dayu.host.projection`，失败时使用 `dayu.host.projection` logger 记录 exception，同时不掩盖 durable command / accept 结果。
- 接受并修复 MiMo / DS 关于 `ProjectionCatchupPort` 放在 admission 模块导致 cross-concern coupling 的 finding。端口与 no-op 实现已迁移到 projection core 模块。
- 接受 S4 对 memory reset 的约束：`reset_conversation_memory_projection(...)` 按 `consumer_id` 清理 memory snapshots / items / diagnostics、checkpoint 与 failure，保留其它 consumer；同 consumer 下其它 policy snapshot 被清理是正确行为，因为 projection checkpoint 是 consumer-scoped。

## Rejected / Deferred Findings

- `resolve_wait` late rejection path 也可能触发一次 catch-up。该行为是低风险冗余，不改变 EventLog、Run 状态或 projection truth；暂不作为 blocking fix。
- `wake_queue_promotion` 与 future `promote_next_queued_run` hook 可能出现重复 catch-up。当前没有重复写 truth 或状态破坏，留给后续 Host hardening / cleanup。
- 当前 after-commit catch-up 是 synchronous best-effort。P9 目标是 session memory projection 可追平、repair 可重建，不引入 heavy sink runner 或后台 batch worker；heavy sink / batch runner owner 仍为 Phase 13 / Phase 15。
- 默认 public command handle 仍使用 no-op projection catch-up port；生产 memory catch-up 需要 composition root 显式注入 concrete port。该残余风险写入总控文档，由后续 Host composition / Service wiring owner 处理。

## Verification

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py`
- `pyright dayu/host tests/host`
- `git diff --check`

## Residual Risk

无 blocking residual risk。保留的风险均有明确 owner：projection catch-up 性能与 batch 化归 Phase 13 / Phase 15；production composition root concrete memory catch-up 注入归后续 Host / Service wiring；late rejection 冗余 catch-up 与未来重复 hook 归 Host hardening cleanup。
