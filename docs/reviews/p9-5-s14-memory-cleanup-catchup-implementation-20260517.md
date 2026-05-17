# P9.5 S14 Memory Cleanup And Production Catch-Up Wiring Implementation

## 范围

S14 只处理不涉及 snapshot history 的 memory cleanup / test hardening 与 production concrete catch-up wiring。本次实现未引入长期检索、public memory edit / reset / forget、P10 Context Governance、recovery / RECOVERING，也未让 Host import `dayu.fins`。

## 第一性原理判断

动机成立。P9 memory 的真源是 committed EventLog，memory snapshot 是可重建 read model；因此 S14 应收口的是“当前 committed facts 是否能稳定投影，并被 production composition 追平”，不是补聊天历史保留。`current_goal` 已在 `dayu.host.memory` 中按 first-write-wins 实现，重写会增加无收益风险，所以本 slice 只补 targeted tests。`SessionContinuityProvider` 当前只保留 resume-specific continuity，historical raw turns 应通过 memory budget 进入 RunInputBuilder，不能在 continuity provider 中绕过 history pool。

## 实现变更

- 移除未使用的 legacy `read_run_input_continuity_events` reader 与 `EventLogStore` 方法；没有保留兼容 wrapper 或 re-export。
- 保持 `current_goal` 实现不变，补充多输入 first-write-wins 与后续 inline-delta 投影保留 prior `current_goal` 的测试。
- 通过 durable memory projection catch-up 补充 preview / reasoning / display-only exclusion 覆盖。
- 为 `dayu.host.memory`、`dayu.host.memory_repair`、`dayu.host.durable.memory` 增加 memory import-boundary 自动化测试。
- 保持 generic post-commit catch-up port 的显式注入边界：`create_host_admission_service(...)` 默认仍保持 no-op，测试 / dev 可显式注入 concrete port；本地 dispatch worker 启动路径继续使用 cursor-bound conversation memory catch-up。
- 修复无 payload ref 的工具事实 durable memory item 写入：非 payload digest ref 保留在 item JSON / provenance 中，只有存在 `payload_ref` 时才写入成对 `payload_digest` 列。
- 补充 user input、accepted tool fact、`resolve_wait` committed tool fact 的 catch-up end-to-end tests。
- 更新 `dayu/host/README.md`，同步 production concrete port 与 test / dev no-op 边界。

## 验证

- `pytest tests/host/test_memory_projection.py -k "current_goal or history_pool or final_answer or preview or import or catch_up"`：通过。
- `pytest tests/host/test_run_input_builder.py -k "session_continuity or memory or current_goal or resume"`：通过。
- `pytest tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py`：通过。
- `python -m pyright dayu/host tests/host`：0 errors / 0 warnings / 0 informations。
- `pytest tests/host`：554 passed。
- `python -m pyright dayu tests`：0 errors / 0 warnings / 0 informations。
- `git diff --check`：clean。

## 剩余风险

Snapshot history retention 按 S14 边界保持未触及，仍应归属单独 owner。Concrete catch-up 仍是同步 best-effort，并依赖既有 projection-local failure recording；batching / performance governance 不属于 S14。

控制器复核 full Host tests 时发现，若 `create_host_command_handle(...)` 或 `HostDispatchScheduler.open(...)` 默认接入无 cursor 上限的 generic concrete catch-up port，在 queued future input 场景会把 latest-only memory snapshot 推到当前 dispatch 所需 cursor 之后，触发 `snapshot_missing`。这正是 S14 stop condition 中的 snapshot-history 依赖，因此本 slice 不把 generic post-commit catch-up 默认接入 production composition；只保留显式注入与 dispatch worker 前 cursor-bound catch-up。
