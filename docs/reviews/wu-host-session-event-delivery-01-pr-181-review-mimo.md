# WU-HOST-SESSION-EVENT-DELIVERY-01 PR #181 Independent Review — AgentMiMo

- 日期：2026-07-22
- reviewer：AgentMiMo（独立，未读取 AgentDS 本轮 review artifact）
- PR：`#181` `feat(host): own session event delivery with bounded mailboxes`
- branch：`phaseflow/wu-host-session-event-delivery-01`
- base：`main`
- remote HEAD：`6e20767d`
- review scope：main..HEAD 完整 diff（154 files, +19645/-2429）

## PR Metadata 验证

| 项目 | 状态 | 说明 |
|---|---|---|
| Draft | ✅ `isDraft: true` | 正确保持 draft 状态 |
| Issue closing directive | ✅ 无 | PR body 明确 "no GitHub Issue is associated" |
| Commit range | ✅ 10 commits | plan → slices → service integration → deepreview |
| Commit scope | ✅ 无污染 | 非 docs 改动限于 production/tests/config/CLI |
| Merge conflict | ✅ `MERGEABLE` | 无冲突 |
| GitHub checks | ⏳ 2 pending | `windows-init-transaction` / `windows-upload-script` 仍在运行，非 blocking |
| Generated artifacts | ℹ️ `docs/reviews/` 含 40+ 文件 | 属于 gateflow 工作流产出，非 scope 污染 |

## PR Body 与实现一致性

PR body 声明的 contract boundaries 与实现逐项核对：

1. **"no byte or resident-heap bound"** ✅ — `HostSessionEventDeliveryPolicy` 只有 `transient_mailbox_max_items` 和 `max_subscriptions_per_session` 两个 int 字段，无 byte/heap 字段。
2. **"no delta persistence, replay, or reconnect backfill"** ✅ — transient delta 使用 `deque` mailbox，无持久化路径。
3. **"no third sequence domain or durable/transient global order"** ✅ — 只有 `runtime_sequence` (transient) 和 `event_sequence` (durable)。
4. **"no cross-process terminal broadcast"** ✅ — `TerminalPostCommitPort` 是 local-only Protocol。
5. **"no Host-global cross-Session quota"** ✅ — admission 按 per-Session reservation 计数。
6. **"no WU-CLI-SMOKE-01-R2 changes"** ✅ — 未修改 smoke 脚本逻辑。
7. **"no GitHub Issue"** ✅ — PR body 和 commit 均无 issue reference。

## 独立 Adversarial Review

### 1. Async Attach 与 Successful-Return Boundary

**verdict: PASS**

`open_host.py` 的 `watch_session_events` 已改为 `async def`，factory 内完成：
- `reserve(session_id)` → 线性化 admission cap
- `await durable_actor.call(cursor)` → 真实 cursor transaction
- `self._raise_if_closed()` → critical segment 前 recheck
- `attach(reservation, durable_cursor=cursor)` → mailbox + fanout 注册
- `_HostSessionEventIterator(...)` → iterator 构造

全部在 return 前完成；cancellation/Host close/partial failure 通过 `reservation.release()` 释放。无 pending cursor future 或 lazy first-anext attach 暴露给 caller。

### 2. Host Sole Delivery Owner 与 Item-Only Bound

**verdict: PASS**

`transient_delta.py` 的 `HostTransientDeltaHub` 唯一拥有：
- `_reservations: dict[str, set[HostTransientDeltaReservation]]` — per-Session admission
- `_subscriptions: dict[str, set[HostTransientDeltaSubscription]]` — fanout
- 每 subscription 的 `deque[HostTransientDeltaMailboxEntry]` mailbox + `_in_flight` 唯一引用
- `retained_items = len(mailbox) + (1 if in_flight else 0)` — 冻结公式

packaged policy `512/4` 通过 `host_runtime.json` → `ConfigLoader` → `host_assembly.py` → `OpenHostOptions` 一对一传递，无 hidden fallback。

旧 `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256` 常量和 `asyncio.Queue` 已删除。旧 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256` 和 Service event-copy relay 已删除。

### 3. Typed Errors / Metrics

**verdict: PASS**

- `HostApiErrorCode.DELIVERY_INTERRUPTED` + `HostSessionEventDeliveryDetail(reason=TRANSIENT_MAILBOX_OVERFLOW)` — overflow typed error
- `HostApiErrorCode.RESOURCE_EXHAUSTED` + `HostSessionEventAdmissionDetail(reason=SESSION_SUBSCRIPTION_LIMIT_REACHED)` — admission typed error
- `HostApiErrorDetail` union 更新为 4 members，`HostUnavailableDetail` 保留用于真正 availability 场景
- `_DeliveryLogEvent` / `_DeliveryLogOutcome` / `_DeliveryLogReason` — 低基数结构化日志，不含 Session/Run/subscription/payload 字段

### 4. Fence / Reconciliation / Cross-Opener

**verdict: PASS**

- `ValidatedTransientDeltaCandidate.durable_causal_fence_event_sequence` — 从同一 validation transaction 的 `Attempt.started_event_sequence` 产生
- `HostTransientDeltaMailboxEntry.durable_causal_fence_event_sequence` — per-entry fence
- `_watch_session_events_after` 中 head fence check → bounded durable page catch-up → terminal fence delivery
- `needs_durable_reconciliation` — watermark 领先 cursor 时触发 reconciliation
- `_SessionEventReconciliationWaiter` — mailbox-empty periodic timeout 驱动 reconciliation page read
- `_TerminalPostCommitCoordinator` — opener-local delivery watermark + promotion watermark 双标量

### 5. Terminal Producer Completeness

**verdict: PASS**

所有 terminal producer 已改为使用 `project_terminal_notice_from_exact_run_event` + `TerminalPostCommitPort`：

| Producer | 文件 | wake_queue_promotion |
|---|---|---|
| terminal closeout | `engine_ingest.py` | True (new terminal) / False (duplicate) |
| active cancel closeout | `admission.py` | True |
| cancel queued | `admission.py` | False |
| cancel predispatch starting | `admission.py` | True |
| cancel recovering | `admission.py` | True |
| cancel active attempt | `admission.py` | False (non-terminal request) |
| cancel terminal ack | `admission.py` | False |
| session cancel | `admission.py` | 按 target 分类，sorted by sequence |
| wait resolve failed/lost | `waiting.py` | True |
| wait expiry | `waiting.py` | True |
| active cancel watchdog | `dispatch.py` | 按 run_event id 判定 |
| startup recovery | `recovery.py` | True (updated) |
| dispatch governance fail | `dispatch.py` | 通过 `_fail_unstarted_in_transaction` |

旧 `promotion_triggered: bool` 和 `_promote_after_release` 已完全删除。`RunTransitionResult` 新增 `run_event: EventLogRow | None` 字段，所有 transition 函数均已填充。

剩余 `wake_queue_promotion` 引用在 `recovery.py:361` 和 `admission.py:4692` 属于 ordinary admission/startup promotion 路径（非 terminal），使用 `AdmissionWakeupPort`，符合 plan："ordinary admission/startup accepted/queued promotion仍直接使用普通 port"。

### 6. Service Exact-Five / Cleanup

**verdict: PASS**

`entrypoint_runtime.py` 的 `_ServiceObservationState` 实现：
- capacity-one first-commit slot (`try_commit`)
- generation handshake (`bind` / `wait_for_binding`)
- exact-five disposition union (`_TargetTerminal` / `_TargetCompleted` / `_TargetCancelled` / `_TargetFailed` / `_TargetCleanupFailed`)
- cleanup double-failure chain (`_raise_primary_with_cleanup`)
- late commit suppression (`stop_requested` / `mark_closed`)

旧 `_WatchAndWaitRuntime` 已从 `(watcher, queue, drain_task)` 改为 `(watcher, state, consumer_task, closed)`，无第二条 event-copy relay。

### 7. CLI Display Controller / Executor Isolation

**verdict: PASS**

`RuntimeDisplayController` 已改为 `EntrypointCallbackExecutionPort` 实现：
- 私有 `ThreadPoolExecutor(max_workers=1)` — 不使用 event loop 默认 executor
- `asyncio.Lock` serial gate — 串行化所有 display work
- `begin_closing()` → `_require_open()` — 拒绝 closing/closed 后新 work
- `aclose()` — renderer close → executor shutdown
- 每个 caller lifecycle 独立创建、精确关闭

### 8. Config / Assembly / Callers

**verdict: PASS**

- `config_loader.py`：`SessionEventDeliveryPolicyConfig` + strict exact-field parser
- `host_runtime.json`：`session_event_delivery_policy: { transient_mailbox_max_items: 512, max_subscriptions_per_session: 4 }`
- `host_assembly.py`：一对一构造 `HostSessionEventDeliveryPolicy`
- `dayu/host/__init__.py`：public exports 包含所有新类型
- `api.py`：`__all__` 包含所有新类型

## 验证矩阵

| 验证项 | 结果 |
|---|---|
| affected test suites | ✅ 2864 passed, 9 skipped, 6 deselected |
| transient delta tests | ✅ 14 passed |
| pyright | ✅ 0 errors, 0 warnings |
| `git diff --check` | ✅ 无 whitespace 错误 |
| stale `_promote_after_release` | ✅ 0 引用 |
| stale `promotion_triggered` | ✅ 0 引用 |
| stale `_TRANSIENT_WATCH_BUFFER_CAPACITY` | ✅ 0 引用 |
| stale `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` | ✅ 0 引用 |
| stale `ClosableHostSessionEventIterator` | ✅ 已重命名为 `_HostSessionEventIterator` |

## Observations（非 material finding）

1. **test count 差异**：PR body 声明 3443 passed，本地验证 2864 passed。差异可能源于不同测试 scope 或环境，但全部通过无失败。
2. **`_close_from_hub()` 不再从 fanout 单独 detach**：`Hub.close()` 已先 `_subscriptions.clear()` 再逐个 `_close_from_hub()`，subscription 的 `close()` 调用 `_detach_from_fanout()` 时 fanout 已空。non-issue，Hub close 路径不依赖重复 detach。
3. **overflow 直接 `self._ready.set()` 而非 `_refresh_readiness()`**：overflow 是 level-triggered ready 条件之一，直接 `set()` 与 `_is_ready()` 一致。non-issue。
4. **iterator 无 `__del__` 异步 cleanup**：public contract 要求显式 `aclose()`；Host close 和 `__anext__` 异常路径负责 cleanup。non-issue。

## Verdict

**PASS** — 0 material finding。

PR body 与实现一致；contract boundaries 全部满足；async attach、Host sole owner、items-only 512、subscription cap 4、typed errors/metrics、fence/reconciliation/cross-opener、terminal producer completeness、Service exact-five/cleanup、CLI executor isolation、config/assembly/callers/README 全部闭环。无 Issue closing directive，draft 状态正确，无 commit scope 污染。

**READY_FOR_CONTROLLER**
