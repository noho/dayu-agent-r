# P9.5 S14 Code Review Controller Adjudication

## 范围

- Slice: P9.5 S14 P9 Memory Cleanup And Production Catch-Up Wiring。
- Design source: `docs/host/design.md`。
- Control doc: `docs/host/implementation-control.md`。
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S14。
- Implementation artifact: `docs/reviews/p9-5-s14-memory-cleanup-catchup-implementation-20260517.md`。
- Reviews:
  - `docs/reviews/p9-5-s14-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s14-code-review-ds-20260517.md`

## 裁决原则

S14 必须只收口 P9 memory cleanup 与 concrete catch-up 可验证路径；不得引入 snapshot history retention、P10 Context Governance、RECOVERING/recovery、长期 retrieval 或 public memory edit/reset/forget。任何 generic catch-up 默认接入若需要 at-or-before snapshot history，必须停在 S14 外。

## Review 结论

- AgentMiMo: PASS，0 blocking。
- AgentDS: PASS，0 blocking。
- Controller: 接受两个 review 结论。当前 S14 diff 可接受，无需 fix / re-review。

## 裁决要点

- `current_goal` first-write-wins 已由现有 `_pinned_state_with_user_input(...)` 直接实现，本 slice 不重写 production projection，只补多输入与 inline-delta targeted tests是正确取舍。
- `read_run_input_continuity_events(...)` 与 `EventLogStore.read_run_input_continuity_events(...)` 已确认无生产代码调用，删除后没有兼容 wrapper / re-export，符合“历史 raw turns 不得绕过 memory budget”的目标。
- `DurableSessionContinuityProvider` 仍只保留 resume-specific continuity，不发射历史 raw user / assistant turns。
- Explicit concrete catch-up path 已覆盖 `start_run` user input、ToolRuntime accepted tool fact、`resolve_wait` committed tool fact 三条 committed EventLog 投影入口。
- Controller 复核期间曾发现将 generic concrete catch-up 默认接入 `create_host_command_handle(...)` / `HostDispatchScheduler.open(...)` 会在 queued future input 场景把 latest-only snapshot 推过当前 dispatch cursor。该行为依赖 snapshot history，违反 S14 stop condition。当前最终 diff 已撤回该默认接入，保留显式注入与 dispatch worker 前 cursor-bound catch-up，裁决为正确保守边界。
- `_payload_digest_for_verified_fact(...)` 修复了无 `payload_ref` 工具事实写入 `payload_digest` 列导致 schema CHECK 失败的 root cause，并保留 payload ref / payload digest 成对不变量。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py -k "current_goal or history_pool or final_answer or preview or import or catch_up"`
  - 7 passed。
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py -k "session_continuity or memory or current_goal or resume"`
  - 12 passed。
- `source .venv/bin/activate && pytest tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py`
  - 59 passed。
- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py::test_worker_terminal_promotes_and_dispatches_queued_run tests/host/test_phase5_local_execution_integration.py::test_queue_promotion_after_terminal_and_cancel_wakes_dispatch tests/host/test_resolve_wait_command.py::test_resolve_wait_committed_tool_fact_catches_up_memory`
  - 3 passed。
- `source .venv/bin/activate && pytest tests/host`
  - 554 passed。
- `source .venv/bin/activate && python -m pyright dayu tests`
  - 0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - clean。

## 最终裁决

S14 accepted。剩余 snapshot history retention 与 generic production catch-up defaulting 均不属于 S14，必须留给单独 owner；当前 slice 不阻塞后续 P9.5 S15。
