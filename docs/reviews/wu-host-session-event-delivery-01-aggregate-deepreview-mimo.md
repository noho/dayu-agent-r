# WU-HOST-SESSION-EVENT-DELIVERY-01 Aggregate Deep Review

## Scope

- Mode: current changes (full WU aggregate)
- Branch: `phaseflow/wu-host-session-event-delivery-01`
- Base: `main` (commit `2c02079a`)
- HEAD: `035d0035`
- Reviewer: AgentMiMo (mimo-v2.5-pro)
- Review date: 2026-07-22T03:40:10+08:00
- Output file: `docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-mimo.md`

## Included Scope

WU 全部 4 个 slice 的 production/config/test/README 变更，共 150 个文件，+19213/-2429 行。

## Excluded Scope

- `docs/host/issues-implementation-control.md` 未提交变化（Controller-owned control bookkeeping）
- AgentDS 的全部 review artifact（保持独立）
- `dayu/engine/**` 和 `docs/engine/design.md`（WU non-goal）

## Parallel Review Coverage

| 审查维度 | 覆盖方式 | 结论 |
|---|---|---|
| Core delivery ownership (transient_delta, open_host, api contracts) | Subagent 深审 | PASS |
| Terminal post-commit coordination (terminal_post_commit, run_transition, all producers) | 主 reviewer 亲自走读 | PASS |
| Service/CLI observation (entrypoint_runtime, runtime_display, session_execution) | Subagent 深审 | PASS |
| Config/assembly/contracts (config_loader, host_runtime.json, host_assembly, __init__) | Subagent 深审 | PASS |
| Cross-slice coupling, semantic ownership drift, promotion bypass, Engine boundary | 主 reviewer 亲自 scan + 走读 | PASS |

## Findings

未发现实质性问题。

以下为各维度审查结论与直接证据摘要。

---

### 1. Core Delivery Ownership

**状态机完整性**: UNRESERVED -> RESERVED -> ATTACHED -> OVERFLOWED -> DETACHED 全路径正确，`close()` / `_close_from_hub()` / `hub.close()` 三个关闭路径均幂等不泄漏 (`transient_delta.py:628,670,989`)。

**retained_items 不变量**: `len(mailbox) + (1 if in_flight is not None else 0)` 在 `_offer()` (L643)、`pop_next_nowait()` (L499)、`release_in_flight()` (L519)、`_clear_retained_state()` (L712) 四条路径始终一致。overflow 前瞻检查 (L654) 在 append 之前执行，语义正确。

**Overflow 语义**: 溢出时 `_overflowed=True` + `_detach_from_fanout` (L656-659)，已接受 prefix 保留，prefix 耗尽后抛 `HostApiError(DELIVERY_INTERRUPTED, TRANSIENT_MAILBOX_OVERFLOW)` (`open_host.py:1293-1298`)。

**Async attach 线性化**: cursor transaction 完成后、return 前的临界区无 await (`open_host.py:1209-1231`)。`_raise_if_closed()` (health_gate) 和 `hub.attach()` (hub._closed) 双层 gate 顺序正确：`_close_owned_resources` 先 `begin_closing()` 再 `hub.close()`，前者拦截所有后续 attach。

**Level readiness**: `_is_ready()` (L684-696) 覆盖 mailbox 非空、overflow、closed、terminal watermark 领先四种条件。`wait_ready()` (L529-558) 使用双检锁模式避免丢失唤醒。

**Host close ordering**: `_close_owned_resources()` (L1419-1545) 严格按 health_gate -> wait_poller -> durable_actor drain -> scheduler -> terminal coordinator -> delivery hub -> projection flush -> actor close -> store close -> mark_closed 顺序。Terminal coordinator close (L450-466) 使用 drain 模式排空已排队 notice 后才设 closing。

**资源泄漏**: reservation token 双层 try/except 保护 (`open_host.py:1209-1234`)；iterator `__anext__` 捕获所有 BaseException 后调用 `aclose()` (`open_host.py:1632-1647`)；hub close 释放所有残余 reservation (`transient_delta.py:989-1014`)。

---

### 2. Terminal Post-Commit Coordination

**TerminalPostCommitPort 定义**: `terminal_post_commit.py` 严格只定义 `TerminalPostCommitNotice` (frozen/slots, 三字段: session_id/terminal_event_sequence/wake_queue_promotion) 和 `TerminalPostCommitPort` Protocol (同步 `notify_terminal_post_commit`)。不 package export，不依赖 Service/UI。

**RunTransitionResult.run_event**: 所有 transition 函数正确填充 `run_event` 字段。`project_terminal_notice_from_exact_run_event` (`run_transition.py:926-959`) 严格校验 `run.terminal_event_id/event_sequence/session_id/run_id` 与 `exact_run_event` 四项一致性，不读取 durable store，不允许 commit 后 latest/max 回读。

**Terminal producer 接线**: 所有 terminal producer 通过 `terminal_post_commit_port.notify_terminal_post_commit(notice)` 调用 port:
- `admission.py`: L793, L835, L859 (cancel, closeout)
- `waiting.py`: L767, L817 (fail, lost/expiry)
- `engine_ingest.py`: L873, L2808 (close_terminal, close_active_cancel)
- `recovery.py`: L356 (batch terminal notices)
- `dispatch.py`: L1378, L1679, L1907, L3986 (watchdog, fail_unstarted, startup_timeout, active_cancel)

**Promotion bypass 审计**: 全仓 `wake_queue_promotion` 调用仅 5 处:
- `admission.py:4692`: `_wake_start_governance_if_needed`，ACCEPTED Run（非 terminal），ordinary promotion wake。正确。
- `recovery.py:361`: `result.queue_promotion_sessions`（ordinary promotion sessions），terminal notices 在 L356 单独处理。正确。
- `open_host.py:447`: coordinator `_handle_notice` 内部调用 promotion port，是 coordinator 的职责。正确。
- `open_host.py:585,587`: ordinary non-terminal promotion 调用。正确。
- **结论**: terminal producer 内无直接 `wake_queue_promotion` 调用。所有 terminal 旁路已删除。

**Standalone command handle**: `command.py:174-177` 定义 `_NoLocalDeliveryTerminalPostCommitPort`，`notify_terminal_post_commit` 为空实现。`create_host_command_handle` (L404) 显式注入该 port。正确。

**Scheduler factory/bind failure barrier**: `dispatch.py` 的 `HostDispatchScheduler.open` 使用 `_TerminalPostCommitPortFactory` (L532-539) 获取 port。bind 失败时按逆序关闭已创建资源，不暴露未绑定 scheduler。

---

### 3. Service/CLI Observation

**Sole consumer**: `_consume_host_events` (`entrypoint_runtime.py:1309-1408`) 是唯一调用 `anext(watcher)` 的协程，由 `asyncio.create_task` 包装为 `_WatchAndWaitRuntime.consumer_task`。无第二 observation channel。

**Capacity-one slot**: `_ServiceObservationState.try_commit` (L636-662) 四重守卫: stop_requested/phase 检查、late commit 拒绝、generation 匹配、run_id 匹配。`ack_target_terminal` (L678-696) 清除 slot 支持多轮复用。

**Exact-five disposition**: `_ServiceObservationResult` (L558-560) 精确五成员 union。`_finish_observation_result` (L1664-1723) 和 `_raise_observation_failure` (L1735-1754) 完全覆盖，含 `assert_never` 穷举检查。

**Cleanup 顺序**: `_close_watch_and_wait_runtime` (L1834-1861): request_stop -> consumer_task.cancel -> await consumer_task -> watcher.aclose -> mark_closed (finally)。异常链: aclose 失败为 cleanup_error，caller primary identity 保持。

**Callback execution port**: `EntrypointCallbackExecutionPort` Protocol (L266-301) 定义 `invoke_activity`/`invoke_thinking`。`RuntimeDisplayController` (runtime_display.py:116-465) 实现: private `ThreadPoolExecutor(max_workers=1)` (L150-153)、`asyncio.Lock()` serial gate (L154)、不保存 HostSessionEvent。

**Caller finally ordering**: `_close_prompt_lifecycle` (session_execution.py:633-686): begin_closing -> cancel_and_await_task(submit_task) -> _close_runtime_display (含 executor shutdown) -> monitor.close -> sigint_monitor.close -> cancel_and_await_task(sigint/key tasks)。异常链: primary_error 保持 top-level，cleanup_error 作为 cause。

**Delivery interruption recovery**: 三条路径均恰好一次 durable recovery，不 reattach。`degraded` flag 确保后续降级为 durable polling。

---

### 4. Config/Assembly/Contracts

**Policy validation**: `HostSessionEventDeliveryPolicy` (api.py:1077-1113) frozen/slots, 两 required 字段, `_require_positive_int_field` 校验。

**Config strict parser**: `_parse_session_event_delivery_policy` (config_loader.py:1996-2030) 完整 fail-closed: missing/extra/bool/zero/negative/float/string 全部 ConfigFieldError。

**Packaged JSON**: `host_runtime.json:21-24` 精确 `{transient_mailbox_max_items: 512, max_subscriptions_per_session: 4}`。

**Assembly**: `_compose_options` (host_assembly.py:885-893) 一对一投影，无 override 逻辑。

**Package exports**: `__init__.py` 正确导出 6 个新公共类型到 `__all__`。

**OpenHostOptions**: `session_event_delivery_policy` (api.py:1183) 位于有默认值字段之前，`__post_init__` isinstance 校验。

**HostApiErrorDetail**: closed union (api.py:1503-1508) 包含 `HostSessionEventDeliveryDetail` 和 `HostSessionEventAdmissionDetail`。

**HostSessionEventIterator Protocol**: (api.py:3622-3651) 完整声明 `__aiter__`/`__anext__`/`aclose`。

---

### 5. Cross-Slice Coupling & Semantic Ownership

**Stale delivery semantics scan**: `rg` 搜索 `_TRANSIENT_WATCH_BUFFER_CAPACITY|_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY|session_live_stream|reason_code="slow_consumer"|transient_mailbox_max_bytes|delivery_size_bytes|cumulative_byte|byte_full|oversized.*mailbox` 结果为空。旧 256 常量和 availability-mapped overflow 已完全删除。

**Engine boundary**: `rg` 搜索 `TerminalPostCommit|session_event_delivery` in `dayu/engine` 结果为空。Engine public contract 未被修改。

**Runtime reverse dependency**: `rg` 搜索 `from dayu.(engine|host|service|ui|fins)` in `dayu/runtime` 结果为空。

**All watch_session_events callers**: 所有 production/test/utils 调用点均使用 `await`，返回值为 public `HostSessionEventIterator`。

---

## Verification Results

### Tests

| Suite | Result |
|---|---|
| Focused host (transient_delta, watch_session_events, terminal_post_commit, open_host_runtime, public_contracts, public_open_host_options) | 124 passed |
| Terminal producer focused (engine_ingest_mapping, run_attempt_transitions, admission_queue, terminal_post_commit, dispatch_scheduler, command_handle) | 287 passed |
| Service/CLI focused (entrypoint_runtime, transient_delivery_interruption_path, runtime_display, prompt_command, interactive_command) | 164 passed |
| Public contract/config/assembly (public_contracts, package_exports, public_open_host_options, config_loader, host_assembly, host_admin) | 265 passed |
| **Full affected suites (tests/host, tests/runtime, tests/service, tests/cli)** | **3443 passed, 9 skipped, 6 deselected** |
| Stress tests (host_production_stress, transient_delta_stress) | 6 passed |

### Type Check

- **pyright**: 0 errors, 0 warnings, 0 informations

### Coverage (single-file, all ≥ 80%)

| File | Coverage |
|---|---|
| `dayu/host/transient_delta.py` | 92% |
| `dayu/host/open_host.py` | 84% |
| `dayu/host/terminal_post_commit.py` | 95% |
| `dayu/service/entrypoint_runtime.py` | 86% |

### Source Scans

| Scan | Result |
|---|---|
| Stale delivery semantics (`_TRANSIENT_WATCH_BUFFER_CAPACITY` etc.) | **EMPTY** |
| Engine boundary leakage (`TerminalPostCommit\|session_event_delivery` in engine) | **EMPTY** |
| Runtime reverse dependency (`from dayu.(engine\|host\|service\|ui\|fins)` in runtime) | **EMPTY** |
| `git diff --check` | Clean |
| `watch_session_events` callers all `await` | Verified |
| Terminal producer `wake_queue_promotion` bypass | **Zero** — all 5 call sites are ordinary non-terminal or coordinator |
| README trigger audit | 5/5 triggered files updated (host, service, config, dayu, tests) |

## Open Questions

无。

## Residual Risk

无实质性 residual risk。

以下为已评估但确认为 non-issue 的观察:

1. **双层 lifecycle gate**: `watch_session_events` 中 `_raise_if_closed()` (health_gate) 和 `hub.attach()` (hub._closed) 使用不同标志。当前代码中 `_close_owned_resources` 先 `begin_closing()` 再 `hub.close()`，前者始终先于后者拦截，hub._closed 检查是冗余安全网而非 bug。不影响正确性。

2. **entrypoint_runtime.py 覆盖 86%**: 未覆盖行主要是错误路径的边界分支（如 executor scheduling failure、特定 iterator error 包装路径），已有 `assert_never` 穷举检查兜底。不影响 acceptance。

## Verdict

**PASS**

WU-HOST-SESSION-EVENT-DELIVERY-01 全部 4 个 slice 实现完整，与 plan 和 design 对齐。所有 acceptance criteria 均已验证通过:

- ✅ async attach 与 successful-return 边界
- ✅ Host 唯一 delivery owner
- ✅ 每订阅唯一 items-only mailbox + counted in-flight, default 512
- ✅ per-Session admission default 4
- ✅ typed admission/overflow 错误与低基数 metrics
- ✅ 确定性 overflow 顺序
- ✅ delayed cursor/factory cancellation/Host close/partial allocation
- ✅ durable causal fence、bounded catch-up、mailbox-empty reconciliation、双 opener ordering
- ✅ local-only TerminalPostCommitPort 和全部 terminal producer static/runtime barriers
- ✅ Service relay 删除、sole consumer、exact-five observation/cleanup、callback 非阻塞与 CLI 私有 executor
- ✅ runtime config/assembly/CLI 调用点
- ✅ 无 byte contract
- ✅ Engine 边界与全部非目标
- ✅ affected tests 全通过 (3443 passed)
- ✅ 每个改动 production 单文件 coverage ≥ 80%
- ✅ 完整 pyright (0 errors)
- ✅ README trigger audit

**READY_FOR_CONTROLLER**
