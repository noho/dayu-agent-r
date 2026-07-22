# WU-CTX-04 Slice 3 Code Re-Review（AgentDS）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- review gate：code re-review（Slice 3 review fix 后）
- prior artifacts：
  - Slice 3 implementation：`docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
  - Initial reviews：`docs/reviews/wu-ctx-04-slice-3-code-review-mimo.md`、`docs/reviews/wu-ctx-04-slice-3-code-review-ds.md`
  - Controller adjudication：`docs/reviews/wu-ctx-04-slice-3-code-review-controller-adjudication.md`（decision=`needs-fix`，3 accepted findings）
  - Review fix：`docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`
- re-review verdict：**pass**
- actionable findings：**0**
- blocking open questions：**None**

## 审查范围与方法

本 re-review 独立阅读了 AGENTS.md、`docs/host/design.md`（Section 9、25、27 及相关 recovery/cancel contract）、`docs/host/issues-implementation-control.md`（WU-CTX-04 全节）、`docs/reviews/wu-ctx-04-plan-codex.md`、Controller adjudication 与 review fix artifact，并对相对 baseline `4ca0810b` 的完整 workspace diff（19 files, +1866/-190）做了逐文件审查。

验证方法：
- 逐项核对 CTRL-S3-001/002/003 的 production owner 修复位置与 root cause closure
- 执行 Controller 要求的 adversarial regression pass
- 运行 focused test matrix、terminal producer manifest、full canonical test suite、full pyright、per-file coverage 与 stale grep
- 对每个 modified production 文件检查 `getattr`/`hasattr`、反向 import、兼容 wrapper/default、语义所有權漂移与第二真源

## 逐项 accepted finding 核验

### CTRL-S3-001 — High — execution-owner cancel poll 被不相关的 proactive compactor 阻塞

**状态：fixed。root-cause closure 成立。**

**独立 task 证据：**

- `dayu/host/dispatch.py:1331-1334`：scheduler open 在启动 `_start_owned_session_reconciliation_loop` 前先启动 `_start_active_worker_cancel_reconciliation_loop`。后续 open step 失败时，`except BaseException -> scheduler.close()` 会在 mandatory background task 集合中取消并 await 已启动的 owner cancel task。
- `dayu/host/dispatch.py:3321-3339`：`_start_active_worker_cancel_reconciliation_loop` 以独立 critical component `active_cancel_owner_reconciliation` 接入 shared health supervisor。其 loop（`dayu/host/dispatch.py:3703-3733`）只按 `dispatch_poll_interval_seconds` sleep 并调用 `reconcile_active_worker_cancels_once`，**不进入** `reconcile_owned_sessions_once`、promotion、Session reconciliation 或 proactive compactor await 链。
- `dayu/host/dispatch.py:3075-3148`：`reconcile_active_worker_cancels_once` 先快照本地 identities（sync、lock-protected），空集直接返回零值 summary 不开 durable read；非空时以 sync `transaction_runner.run_read` 查询，transaction 外传播 token/hook，再复用唯一 terminal producer `_tick_active_cancel_watchdog` 做 exact target closeout。
- `dayu/host/dispatch.py:3214-3231`：scheduler close 的 mandatory background task 集合显式包含 `_active_worker_cancel_reconciliation_task`，与 Session reconciliation task 一起先 cancel、后逐个 await。lane close、Host instance `STOPPED`、`_close_cleanup_done` 顺序未改变。

**测试证据：**

- `test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks`（`tests/host/test_active_cancel_dispatch.py:+307`）：用 barrier 确定性阻塞 Session reconciliation（`_BlockingOwnedSessionReconciliation`），durable cancel 后独立 owner task 仍传播 canonical reason 到旧 local handle。`scheduler.close()` 必须收口两个 task，阻塞 task 观察到 cancellation。
- `test_owner_cancel_task_is_joined_when_later_scheduler_open_step_fails`（`tests/host/test_active_cancel_dispatch.py:+405`）：owner task 启动后注入后续 open step failure，断言 failed-open 返回前 task 已 done。
- `test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`（`tests/host/test_active_cancel_dispatch.py:+307`）：空 local registry 直接返回零值 summary，monkeypatch 注入 reject read 证明未开启 durable read。

**覆盖范围：** open/failed-open/close 三条路径的 owner cancel task 生命周期均已覆盖，Session reconcile/compactor 阻塞不影响独立 progress。满足 Controller required fix 全部条目。

### CTRL-S3-002 — Medium — 跨 opener token/hook 丢失 canonical cancel reason

**状态：fixed。root-cause closure 成立。**

**Typed projection 证据：**

- `dayu/host/durable/run_transition.py:136-161`：新增 `OwnedAttemptCancelDelivery(target, reason)`，`__post_init__` 校验 reason 非空。`target` 字段保持 accepted plan 的 `OwnedAttemptCancelTarget(identity, cancel_request_event_id)` 不变。
- `dayu/host/durable/run_transition.py:2444-2475`：`read_exact_owned_attempt_cancel_deliveries` 是 canonical cancel reason 的唯一对外投影。它复用 `read_owned_attempt_cancel_candidates`（state owner）做 exact join，然后用 `_validate_exact_owned_cancel_requested_event` 严格验证每个 linked EventLog row。
- `dayu/host/durable/run_transition.py:2478-2512`：`_validate_exact_owned_cancel_requested_event` 严格校验：event_id 精确相等、`EventClass.CANONICAL_FACT`、event type 精确为 `CANCEL_REQUESTED`、`session_id`/`run_id` 与 identity 相等、`attempt_id`/`execution_id`/`payload_ref`/`payload_digest` 均为 `None`、`event_body_digest` 完整性通过。任一失败抛 `HostDurableError`。
- `dayu/host/durable/run_transition.py:2515-2572`：`_validate_cancel_requested_payload` 严格解析当前 producer 的 six-field payload（`run_id`、`client_request_id`、`reason`、`mode`、`target_status_at_accept`、`call_context_digest`），字段集合精确匹配、逐字段类型/枚举/非空/digest 校验。`client_request_id` 额外验证与 EventLog row 列一致。
- `dayu/host/dispatch.py:3122-3129`：`reconcile_active_worker_cancels_once` 读取 `delivery.reason` 并交给 `ActiveCancelMessage.reason`。不存在 `durable_cancel_requested`、`_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 或任何 dispatch 侧自行生成的 reason 常量。
- stale grep `durable_cancel_requested|_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 在 `dayu tests` 中零命中。

**测试证据：**

- `test_cross_opener_cancel_reaches_detached_execution_owner`（`tests/host/test_public_session_attachment.py:+1084`）：真实 public 双 opener 路径，断言 `factory.cancel_reasons == ["cross_opener_cancel"]` 且 `factory.active_snapshot.cancellation_token.cancel_reason() == "cross_opener_cancel"`。同时覆盖了 token reason 与 handle hook reason，解决了 Controller 指出的"cross-opener 测试只断言 cancel_count"缺口。
- `test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks` 同时断言 owner-level hook 收到 canonical `"user_stop"`，不是 registry/open 时序相关的替代值。
- `test_exact_owned_cancel_query_fails_closed_for_bad_linked_fact` 覆盖 10 种 linked fact 损坏类型（missing、event_class、event_type、session_id、run_id、attempt_id、execution_id、payload_ref、event_body_digest、payload_shape），全部 fail closed。

**token/hook 一致性：** `CancelMode`、`RunStatus` 枚举的 strict parse（`run_transition.py:2552-2566`）确保 canonical fact 的 `mode` 与 `target_status_at_accept` 字段在 projection 前已通过类型验证。`call_context_digest` 也通过 `_require_sha256_digest` 校验。run-transition owner 是唯一 canonical cancel fact validator，dispatch 不解析 raw payload。

### CTRL-S3-003 / DS-M-01 — Medium — dynamic VALUES 依赖 SQLite bind 上限

**状态：fixed。root-cause closure 成立。**

**Batch-safe SQL 证据：**

- `dayu/host/durable/state.py:144-150`：模块级常量以 SQLite 3.32.0 之前默认 `SQLITE_MAX_VARIABLE_NUMBER=999` 为保守参数预算，推导 batch size `(999 - 1) // 5 = 199`。注释明确引用 SQLite 官方 limits 文档 URL，并声明该 batch size 不是 public capacity 限制。
- `dayu/host/durable/state.py:2227-2313`：`read_owned_attempt_cancel_candidates` 在任何 batch 执行前先对完整输入 tuple 做全量校验：
  - `owner_host_instance_id` 非空（line 2249-2251）
  - 每个 identity 的四个字段逐项 `_require_non_empty_text`（lines 2253-2258）
  - 全局 duplicate 检测 `len(set(identities)) != len(identities)`（line 2259-2260）
  - 空 tuple 直接返回 `()`（line 2261-2262）
- 分批逻辑（lines 2265-2313）：
  - 按 `_OWNED_CANCEL_QUERY_BATCH_SIZE` 步进
  - 每 batch 生成 `(request_order, session_id, run_id, attempt_id, execution_id)` 五元组
  - `request_order` 从原 tuple 绝对下标 `batch_start` 开始连续递增
  - SQL 使用 `WITH ... AS (VALUES ...)` CTE + `ORDER BY requested.request_order ASC`
  - 同一 `HostTransaction` 内按 batch 连续追加到 `candidates` list
  - 最终 `tuple(candidates)` 严格保持全局输入顺序

**测试证据：**

- `test_exact_owned_cancel_query_batches_preserve_global_order_and_filter_stale`（`tests/host/test_run_attempt_transitions.py:+2207`）：
  - 创建 205 个真实 typed cancel targets（跨越 199 条 batch 边界）
  - 以**逆序**输入 identities（`tuple(reversed(identities))`）
  - 在 index 1 注入 wrong dispatch owner（`host-instance-other`）
  - 在 index 202 注入 stale current Attempt（`current_attempt_id = NULL`）
  - 断言 typed output 精确等于过滤后的全局输入顺序
- `test_exact_owned_cancel_query_keeps_terminal_control_truth_and_filters_stale` 覆盖 terminal 后仍可读、wrong owner 过滤、duplicate 拒绝
- `test_exact_owned_cancel_query_filters_durable_identity_change` 参数化 `current_attempt` 与 `dispatch_owner` 两个 stale field

**设计决策正确性：** 采用 SQLite legacy default 999 而非当前环境的编译值 250000，是保守且可移植的选择。batch size 199 是模块级私有常量，不暴露为 public API 或配置项。不引入 magic cap、固定超限拒绝或 public capacity contract。满足 Controller correction 全部要求。

## Adversarial regression pass

以下为逐项 regression check 结果，全部通过：

| 检查项 | 结果 | 证据 |
|---|---|---|
| 不恢复 workspace-wide scan | pass | `read_cancelling_runs()`（无 session_id 参数）已删除；`_active_cancel_watchdog_loop` 改为纯 event-driven、只消费 target-scoped commit wake；stale grep 零命中 |
| 不制造第二 terminal producer | pass | `_tick_active_cancel_watchdog` 仍是唯一 terminal transition 入口；`test_static_terminal_producer_manifest_is_exact` 通过（1 passed） |
| 不用下游 fallback/替代 reason | pass | `durable_cancel_requested` 与 `_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 全仓零命中；`reconcile_active_worker_cancels_once` 只消费 `delivery.reason` |
| 不破坏 attachment ownership | pass | `ActiveWorkerRegistry.register()` 与 `cancel()` 均要求 `session_id`；cancel 做四元 identity 全等匹配（含 session_id）；wrong-session cancel 测试通过 |
| stale identity/owner fail-closed | pass | 10 种 linked fact 损坏类型全部抛 `HostDurableError`；stale current Attempt、stale dispatch owner 均被精确过滤不误配 |
| task health/lifecycle | pass | 独立 owner cancel task 由 `active_cancel_owner_reconciliation` critical component 监督；open/failed-open/close 三种生命周期路径均有测试 |
| 并发与异常路径 | pass | 空 registry 快路径避开 durable read；blocking Session reconcile 不阻塞 owner poll；duplicate identity 输入 pre-validate 拒绝 |
| `getattr`/`hasattr` 逃逸 | pass | 5 个 modified production 文件中零命中 |
| 反向 import | pass | `dayu/runtime/native_mutex.py` 对 Engine/Host/Service/UI/Fins 无任何 import |
| 兼容 wrapper/default | pass | `session_id` 为 required 参数，无 default/optional/overload/wrapper；`tick_active_cancel_watchdog()`（无参数版）已删除 |

## 新增 findings

**0 findings。** 对 5 个 modified production 文件、4 个 modified test 文件的逐行审查未发现 correctness、stability、ownership drift、maintainability、adversarial failure 或项目指令（AGENTS.md、CLAUDE.md）违规。

以下为审查中主动检查但确认无问题的边界：

1. **`_active_worker_cancel_reconciliation_loop` 使用 `asyncio.sleep` 而非 event-driven wake**：这是有意的设计选择。execution owner 没有外部 caller 通知其 cancel（旧 opener 可能已 detach），必须周期性 poll durable truth。与 watchdog loop（event-driven wake from commit）职责不同，分工合理。
2. **`reconcile_active_worker_cancels_once` 为 sync 方法但在 async loop 中调用**：其内部 `transaction_runner.run_read` 为 sync SQLite read（WAL mode 下不阻塞 write），`_tick_active_cancel_watchdog` 也为 sync durable write。整个 one-shot 不 await 任何外部资源，不会让出 event loop 给 Session reconciliation 的 compactor await 链。这是正确的隔离设计。
3. **`_read_exact_owned_active_cancel_watchdog_candidate` 在写事务内二次调用 `read_exact_owned_attempt_cancel_targets`**：这是 watch transaction 内的 re-verification，防止 transaction 外 read 与 transaction 内 write 之间的 stale 窗口。正确性成立。
4. **`_active_cancel_watchdog_session_ids` 为普通 `set[str]` 而非 threadsafe 容器**：watchdog loop 只在 opener event loop 上运行，wake 调用方也在同一 event loop（通过 `_ThreadsafeSchedulerWakeupPort`），不存在跨线程竞争。

## 测试证据汇总

| 测试命令 | 结果 |
|---|---|
| focused Slice 3 matrix（7 files, 304 cases） | 304 passed |
| terminal producer manifest | 1 passed |
| canonical full suite | 5593 passed, 11 skipped, 6 deselected |
| full pyright | 0 errors, 0 warnings, 0 informations |
| per-file coverage（5 key production files） | dispatch.py 90%, run_transition.py 93%, state.py 88%, command.py 88%, open_host.py 89% |
| stale grep（3 组） | 全部零命中 |

## 残余风险

1. **跨平台 native mutex**：本机为 macOS，只验证了 POSIX `flock` backend；Windows `msvcrt.locking` 路径需在 Windows Python 3.11 环境执行 `tests/runtime/test_native_mutex.py`。unsupported/未知 errno 策略为 fail closed。
2. **poll-based physical propagation 延迟**：无 IPC/proxy 条件下，跨 opener cancel 的 physical propagation 最多等待一个 `dispatch_poll_interval_seconds`。caller durable acceptance 不依赖该 poll，target watchdog closeout 也不依赖 owner reconcile。分类：`covered by existing runtime health owner`。
3. **provider-side exactly-once 停止**：本地 token/hook 传播不等价于远端 provider physical exactly-once 停止；迟到结果继续由既有 identity/terminal fence 拒绝。分类：`assigned to existing provider boundary`。
4. **SQLite build variance**：batch size 199 基于 SQLite 3.32.0 之前默认 999。若未来支持 `SQLITE_MAX_VARIABLE_NUMBER` 低于 999 的定制 build，需由独立 runtime-policy WU 增加 connection-specific limit owner。分类：`assigned to later work unit if support scope expands`。

以上均为已接受设计边界内的残余风险，无 blocking 性质。

## 审查结论

CTRL-S3-001、CTRL-S3-002、CTRL-S3-003 三项 accepted findings 均已 root-cause closure，有 production-owner 修复、直接回归测试与 adversarial regression pass 证据。未发现新 actionable findings。全量 pytest、pyright、per-file coverage、stale grep 与 `git diff --check` 均通过。

**verdict：pass。**
