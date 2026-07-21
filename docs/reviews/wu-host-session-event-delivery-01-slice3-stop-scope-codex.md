# WU Host Session Event Delivery 01 — S3 scope stop（Codex）

## 结论

S3 实施基于 `5ac328f0`。当前 required terminal port contract 已使两个既有测试 composition root 必须显式传播 terminal port，但这两个文件不在 accepted S3 Allowed tests 中。继续修改会违反 slice scope；为 production constructor 增加默认、可选或临时 no-op port 又会违反 accepted plan item 9/10。因此本轮停止并返回 Controller，未修改 control doc、accepted plan、其它代码或测试，也未 commit、push 或创建 PR。

## 当前 partial S3 changed-file list

以下是写入本 stop artifact 之前，相对 base `5ac328f0` 的 partial S3 代码/测试改动。

Production：

- `dayu/host/terminal_post_commit.py`（新增）
- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/waiting.py`
- `dayu/host/recovery.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/dispatch.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`

Tests：

- `tests/host/test_terminal_post_commit.py`（新增）
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_wait_cancel_late_result.py`
- `tests/host/test_wait_expiry_closeout.py`

工作树中另有 `docs/host/issues-implementation-control.md` 的既存修改；它是 Controller-owned control doc，不属于本次 S3 改动，本轮未触碰。

## 完整 pyright 证据

执行：

```text
source .venv/bin/activate && pyright
```

结果为 `9 errors, 0 warnings, 0 informations`。完整错误如下：

```text
/Users/leo/workspace/dayu-agent-r/tests/host/test_admission_multiprocess.py
  /Users/leo/workspace/dayu-agent-r/tests/host/test_admission_multiprocess.py:483:28 - error: Cannot access attribute "promotion" for class "TerminalCloseoutResult"
    Attribute "promotion" is unknown (reportAttributeAccessIssue)
  /Users/leo/workspace/dayu-agent-r/tests/host/test_admission_multiprocess.py:763:29 - error: Cannot access attribute "released_active_slot" for class "CancelRunResult"
    Attribute "released_active_slot" is unknown (reportAttributeAccessIssue)
  /Users/leo/workspace/dayu-agent-r/tests/host/test_admission_multiprocess.py:773:30 - error: Cannot access attribute "released_active_slot" for class "CancelRunResult"
    Attribute "released_active_slot" is unknown (reportAttributeAccessIssue)
  /Users/leo/workspace/dayu-agent-r/tests/host/test_admission_multiprocess.py:789:31 - error: Cannot access attribute "released_active_slot" for class "CancelRunResult"
    Attribute "released_active_slot" is unknown (reportAttributeAccessIssue)
/Users/leo/workspace/dayu-agent-r/tests/host/test_phase7_waiting_integration.py
  /Users/leo/workspace/dayu-agent-r/tests/host/test_phase7_waiting_integration.py:471:23 - error: Argument missing for parameter "terminal_post_commit_port_factory" (reportCallIssue)
/Users/leo/workspace/dayu-agent-r/tests/host/test_projection_read_model.py
  /Users/leo/workspace/dayu-agent-r/tests/host/test_projection_read_model.py:142:16 - error: Argument missing for parameter "terminal_post_commit_port" (reportCallIssue)
  /Users/leo/workspace/dayu-agent-r/tests/host/test_projection_read_model.py:145:31 - error: Argument missing for parameter "terminal_post_commit_port" (reportCallIssue)
/Users/leo/workspace/dayu-agent-r/tests/host/test_public_host_admin.py
  /Users/leo/workspace/dayu-agent-r/tests/host/test_public_host_admin.py:211:14 - error: Argument missing for parameter "terminal_post_commit_port" (reportCallIssue)
  /Users/leo/workspace/dayu-agent-r/tests/host/test_public_host_admin.py:214:27 - error: Argument missing for parameter "terminal_post_commit_port" (reportCallIssue)
```

其中 `tests/host/test_admission_multiprocess.py` 与 `tests/host/test_phase7_waiting_integration.py` 已在 accepted S3 Allowed tests 中；其 5 个错误可在既有 scope 内继续处理，不构成 scope amendment 理由。

## 缺失 caller 与 scope 冲突

全测试 constructor callsite 扫描确认两个未授权文件包含以下直接 composition：

```text
tests/host/test_projection_read_model.py:142:        return HostCommandHandle(
tests/host/test_projection_read_model.py:145:            admission_service=create_host_admission_service(
tests/host/test_public_host_admin.py:211:    handle = HostCommandHandle(
tests/host/test_public_host_admin.py:214:        admission_service=create_host_admission_service(
```

这两个测试都绕过 standalone `create_host_command_handle` composition root，直接创建 durable store、`HostAdmissionService` 与 `HostCommandHandle`。S3 item 9 要求 production constructors 显式接收同一个 opener terminal port，所以这些 direct callers 也必须显式提供最终端口；否则它们既无法通过完整 pyright，也无法在运行时完成构造。

Accepted S3 Allowed tests 列表包含 `tests/host/test_phase7_waiting_integration.py` 等文件，但不包含：

- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_host_admin.py`

因此修改这两个 required propagation callers 会直接越过 accepted slice allowlist。

不能以 production fallback 消除该冲突。将 `terminal_post_commit_port` 改为 optional、提供 constructor/default factory 内部 no-op、先绑定临时 port 再替换，都会违反 item 9 的“production constructors 显式接收最终端口”和 item 10 的“禁止临时 no-op/default port/runtime rebind”。这还会模糊 terminal handoff 的 composition owner，并使遗漏装配在类型检查阶段无法 fail fast。

基于当前完整 pyright 与以下全测试 callsite 扫描，未发现第三个必须新增到 allowlist 的 caller 文件：

```text
rg -n "HostCommandHandle\\(|create_host_admission_service\\(|HostDispatchScheduler\\.open\\(" tests --glob '*.py'
```

除上述两个未授权文件外，剩余相关 callsite 均位于 accepted S3 Allowed tests，或使用已经负责 standalone 显式私有终点装配的 `create_host_command_handle`。这一结论限定于当前 base/工作树；修复现有 9 个类型错误后仍应再次运行完整 pyright 和相同静态扫描，以确认没有被前置错误遮蔽的新问题。

## 已通过的 focused tests

停止前已得到以下通过结果：

- `pytest -q tests/host/test_terminal_post_commit.py`：`6 passed`
- `pytest -q tests/host/test_engine_ingest_mapping.py`：`95 passed`
- `pytest -q tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py`：`26 passed`
- `pytest -q tests/host/test_dispatch_scheduler.py -k scheduler_terminal_port_failure`：`2 passed, 87 deselected`
- `tests/host/test_run_attempt_transitions.py` focused run：`54 passed`
- `tests/host/test_admission_queue.py` focused run：`27 passed`
- resolve/expiry/late-result/callback waiting focused set：`44 passed`
- dispatch scheduler、active-cancel 与 phase5 local execution affected set（新增 construction-failure cases 之前）：`118 passed`
- `tests/host/test_open_host_runtime.py` 当时完整 focused run：`24 passed`；之后新增的 same-durable-page 双 terminal/transient deterministic regression 已单独通过

这些结果只证明已执行的 focused 范围；由于 scope stop，尚未完成最终 affected/stress、逐 production 文件 coverage、完整 pyright、`git diff --check` 与最终 source/scope/README trigger audit，不能据此宣告 S3 ready。

## 最小 plan amendment 提案

建议 Controller 仅对 S3 Allowed tests 增补以下两个文件：

- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_host_admin.py`

授权内容严格限定为：在各自现有 direct test composition root 中创建 test-private、显式的 no-local-delivery terminal endpoint，并把同一个实例同时传给 `create_host_admission_service` 和 `HostCommandHandle`；不得修改 production constructor、terminal flag/dataflow、测试业务场景或断言语义，不得引入 optional/default/fallback port。

增补后的最小验证限定为：

1. 运行这两个测试文件，证明原有 projection/admin 行为未改变且 direct composition 可构造。
2. 运行 `tests/host/test_command_handle.py` 中 standalone exact-notice runtime fake，继续证明 production standalone 私有终点实际消费 transaction-local exact notice。
3. 重跑完整 pyright 与 constructor callsite 扫描；必须为零错误且不出现新的未授权 caller。
4. 然后只在原 accepted S3 allowlist 内处理 `test_admission_multiprocess.py` 和 `test_phase7_waiting_integration.py` 的现有错误，并恢复 S3 剩余验证流程。

STOP_CONDITION
