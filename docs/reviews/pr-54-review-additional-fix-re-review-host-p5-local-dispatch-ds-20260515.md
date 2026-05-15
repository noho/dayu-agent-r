# PR 54 Additional Fix Re-Review — AgentDS

## Gate

- Gate: PR 54 additional review accepted-fix re-review gate
- Role: AgentDS (re-review agent), 只做 re-review，不改生产代码
- Source controller artifact: `docs/reviews/pr-54-review-additional-controller-adjudication-20260515.md`
- Source fix artifact: `docs/reviews/pr-54-review-additional-fix-host-p5-local-dispatch-codex-20260515.md`
- Source review artifacts:
  - `docs/reviews/pr-54-review-20260515-1221.md`
  - `docs/reviews/pr-54-review-20260515-1224.md`
- Output file: `docs/reviews/pr-54-review-additional-fix-re-review-host-p5-local-dispatch-ds-20260515.md`

## Verdict

**PASS** — Controller accepted fix items A1-A10 全部通过对口修复验证；未实现 rejected 或 deferred 项；可进入 controller final adjudication。

## Accepted Fix Coverage A1-A10

| ID | 生产代码位置 | 测试覆盖 | 证据 | 状态 |
| --- | --- | --- | --- | --- |
| A1 | `dispatch.py:846-925` | `test_dispatch_scheduler.py:754` | `try:` 包含 envelope 构造、`handle.local_worker_id` 读取、ingestor 构造、事件循环。`finally` 918-925 执行 discard/unregister/close handle/release lane。测试用 `_FlakyLocalWorkerIdHandle` 在 `local_worker_id` 抛出异常，验证 lane 仍可被后续 acquire 获取。 | PASS |
| A2 | `engine_ingest.py:1658-1695` | `test_engine_ingest_mapping.py:694,720` | `_is_preview_event` 对所有 10 种 preview event type 同时校验 `event.type` 与 `isinstance(event.data, DataClass)`。测试覆盖 `data=None` 和 `data=IterationStartedData`(错配 CONTENT_DELTA)，均返回 REJECTED。正向测试覆盖匹配 data 类型仍正常写入。 | PASS |
| A3 | `run_input.py:774-779` | `test_run_input_builder.py:311` | `_validate_snapshot_rows` 新增 run `RUNNING`、attempt `STARTING`、dispatch record `DISPATCHING` 三道状态校验。测试 parametrize 覆盖三种非法组合 (FAILED/STARTING/DISPATCHING, RUNNING/CANCELLED/DISPATCHING, RUNNING/STARTING/PENDING)，均抛 `HostDurableError`。 | PASS |
| A4 | `api.py:308-309` | `test_public_contracts.py:500` | `__post_init__` 中 `isinstance(self.cancellation_token, CancellationToken)` 拒绝非 CancellationToken（含 `None`）；非 Protocol 实现抛出 `TypeError`。测试传入 `cast(CancellationToken, None)` 验证。 | PASS |
| A5 | `durable/state.py:2949-2955` | `test_run_attempt_transitions.py:988` | `_run_mutation_result_for_active` 在 rowcount=0 且 `_is_terminal_run_status(latest.status)` 时返回 `CAS_LOST`，不再误归类为 `INVALID_STATE`。测试覆盖已 CANCELLED row 的底层 dispatch cancel replay 返回 `CAS_LOST`。 | PASS |
| A6 | `durable/run_transition.py:2511-2515` | `test_run_attempt_transitions.py:543` | `_validate_terminal_input` 将 `_attempt_terminal_event_type` / `_run_terminal_event_type` 的 `ValueError` 包在 `try/except ValueError` 中转为 `HostDurableError`。测试 parametrize 覆盖 `(CANCELLED, CANCELLED)` 等非法终态组合，预期 `HostDurableError`。 | PASS |
| A7 | `dispatch.py:440-449` | `test_dispatch_scheduler.py:734` | `close()` 只通过 `_safe_cancel_worker_handle` 发送 cancel 信号，不再直接 close handle。`_CloseCountingHandle` 测试验证 `cancel_count==1` 且 `close_count==1`（由 consume task finally 执行）。 | PASS |
| A8 | `local_proxy.py:117-129` | `test_local_proxy_engine_ingest.py:155` | `close()` 内 `self._events = None` + `self._closed = True`，二次 close 检查 `_closed` 提前返回为 no-op，close 后 `events()` 检查 `_closed` 抛出 `RuntimeError("local worker handle is closed")`。 | PASS |
| A9 | — | `test_local_proxy_engine_ingest.py:91,124,155` + `test_dispatch_scheduler.py:796` | 补充三组真实 DefaultLocalProxy 测试：Engine `run_agent_messages` raise RuntimeError 验证异常不吞掉；空 stream 验证 clean EOF；scheduler 经真实 `DefaultLocalEngineWorkerFactory` 的 stream error 映射为 `RunStatus.LOST` + `RUN_LOST` event reason=`worker_lost_before_terminal`。 | PASS |
| A10 | `test_import_boundary.py:24-29` | `test_import_boundary.py` 内 `HOST_FORBIDDEN_PREFIXES` 检查 | `HOST_FORBIDDEN_PREFIXES` 新增 `"dayu.config"`，`test_host_does_not_import_upper_or_business_layers` 扫描 `dayu/host/` 下所有 `.py` import 时拒绝任何 `dayu.config` 导入。 | PASS |

## Rejected/Deferred Items 未实现确认

逐一审查后确认，本轮 workspace changes 中**不存在**以下项目实现痕迹：

| 原始项目 | 来源 | 裁决 | 确认方法 |
| --- | --- | --- | --- |
| active cancel dispatch record → cancelled | `1224` F2 | rejected | `grep` `run_transition.py`: `active_cancel_closeout_in_transaction` 对 dispatch record 仍只有 read（行 768），无 write; `cancel_starting_dispatch_record_row` 未被 active cancel 路径调用。 |
| 非 terminal duplicate precheck | `1224` F8 | rejected | `grep` `engine_ingest.py`: `_duplicate_terminal_event_ids` 仍对非 terminal event 返回 `()`; ingest 层未新增非 terminal 重复检测分支。 |
| token-cancel build short-circuit | `1221` F7 | rejected | `grep` `run_input.py`: `build()` 内无 `cancellation_token.is_cancelled()` 调用；builder 不基于 token 本地状态短路。 |
| cancel port refactor (command.py → dispatch.py 解耦) | `1224` F4 | deferred | `command.py:80` 仍 `from dayu.host.dispatch import ActiveCancelMessage, cancel_active_worker` 直接依赖模块级单例 `DEFAULT_ACTIVE_WORKER_REGISTRY`。 |
| watchdog / hang timeout | `1224` F2 (residual) | deferred | `dispatch.py` 中无 watchdog、无 hang timeout 机制。 |
| dead code `run_input.py:346-347` | `1224` F12 | deferred(not in A list) | 冗余 None 检查仍保留。 |

## Findings

### B1-低-A1 finally 内 safe close 与 safe release 串行执行无独立隔离

- **入口/函数**: `_consume_worker_events` finally 块
- **文件(行号)**: `dayu/host/dispatch.py` 919-925
- **输入场景**: `_safe_close_worker_handle` 抛出非 `Exception` 的异常（当前 `_safe_close_worker_handle` 内部已 catch `Exception`，但若未来修改破坏此保证）。
- **实际分支**: `_safe_close_worker_handle` 异常导致后续 `_safe_release_lane_token` 不执行。
- **预期行为**: finally 块的四步清理（discard / unregister / close handle / release lane）应各自独立，前一步失败不阻止后续步骤。
- **实际行为**: 四步清理串行无隔离。当前 `_safe_close_worker_handle` 和 `_safe_release_lane_token` 内部各有 `except Exception` 保护，但 `_safe_release_lane_token` 内部若因 `except Exception` 外的异常退出，lane token 仍可能泄露。
- **直接证据**: `dispatch.py:924-925` 两个 await 串行执行，无独立 try/except 包裹。
- **影响**: 极低。当前 `_safe_close_worker_handle` 和 `_safe_release_lane_token` 内部已有 try/except protect。此 finding 是对未来修改的防御性提醒。
- **建议改法和验证点**: 无需当前修改。若未来 `_safe_*` 函数变更，确保保持独立异常隔离。
- **修复风险（低）**:
- **严重程度（低）**:

### B2-低-A3 状态校验在 read transaction 内，存在 TOCTOU 窗口

- **入口/函数**: `_load_current_run_facts_tx`
- **文件(行号)**: `dayu/host/run_input.py` 340-379
- **输入场景**: 状态校验通过后、`build()` 返回 `AgentRunRequest` 前，另一个并发事务推进了 attempt 到终态。
- **实际分支**: `_validate_snapshot_rows` 在 read transaction 内读取状态并通过校验；后续 `build()` 构造请求在事务外，状态可能已变更。
- **预期行为**: 这是 optimistic concurrency 可接受窗口；Engine 执行时应校验 attempt/run 当前状态。
- **实际行为**: 状态校验为防御性检查；当前测试中无并发场景。若 Engine 入口也做 defense-in-depth 检查，此窗口无实际影响。
- **直接证据**: `build()` 在 `self._transaction_runner.run_read(self._load_current_run_facts_tx, snapshot)` 之后构造 `AgentRunRequest`，不在同一事务保护内。
- **影响**: 极低。此为 defense-in-depth 校验，真源状态在 durable 层有 CAS 保护。
- **建议改法和验证点**: 无需当前修改。Engine 入口应做自己的状态 precondition 检查。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

- 无

## Residual Risk

| 风险 | 严重程度 | Owner | 说明 |
| --- | --- | --- | --- |
| active cancel watchdog 未实现 | 中 | Phase 11 | worker 收到 cancel 后永不产出 terminal 时，依赖 lane TTL + scheduler restart 恢复。P5 设计已记录此 gap。 |
| scheduler 并发 lane 竞争测试 | 中 | 后续 scheduler hardening | 当前所有测试为单 dispatch 串行推进；lane_capacity=1 的并发竞争未专项覆盖。 |
| multi-scheduler cancel port | 低 | Phase 11 | `command.py` 仍直接依赖 `dispatch.py` 模块级单例；单进程单 scheduler 部署不受影响。 |
| RemoteProxy 未实现 | 高 | Phase 7+ | 当前只实现了 LocalProxy；RemoteProxy 的 stream error / cancel / timeout 语义未进入测试矩阵。 |
| `_consume_worker_events` 的 except Exception 过于宽泛 | 低 | 后续 observability cleanup | 编程错误（TypeError/KeyError）可能与 worker_lost 混淆；当前不影响 functional correctness。 |

## Review Boundaries

- 审查范围：相对 `feat/host-phase5-local-dispatch` 分支上所有未提交 workspace changes（16 files changed）。
- 未审查：`docs/host/design.md` 与 `docs/host/implementation-control.md` 完整一致性检查。
- 未逐行走读全部 826 行测试变更；关键测试路径（A1-A10 对应测试）已逐行走读验证。
- 未重跑测试与 pyright（依赖 fix artifact 中记录的验证结果：`107 passed`, `375 passed`, `0 errors`）。

## Controller Handoff

A1-A10 全部通过独立证据验证；无 rejected/deferred 项被实现；prod code 中发现两个低严重度 non-blocking observation（B1/B2）均不需要阻塞 gate。建议进入 controller final adjudication。
