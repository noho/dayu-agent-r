# WU-CTX-04 Slice 3 Code Review（AgentMiMo）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- review scope：未提交 workspace diff（production + tests + README）
- reviewer：AgentMiMo
- decision：**pass**
- blocking questions：None
- findings：0 actionable

## Review dimensions

### 1. Correctness — 契约与状态机一致性

**结论：PASS**

逐项核对 plan Slice 3 exact changes：

1. `AttemptExecutionIdentity`（`state.py:345-368`）与 `OwnedAttemptCancelCandidate`（`state.py:371-383`）作为 frozen dataclass 落在 state owner。`read_owned_attempt_cancel_candidates`（`state.py:2217-2325`）的 SQL 三表 JOIN 使用 `session_id`、`run_id`、`current_attempt_id`、`execution_id` 与 `owner_host_instance_id` 全五字段精确匹配，不按 terminal status 过滤。duplicate identity 检测与 empty tuple early return 均到位。

2. `OwnedAttemptCancelTarget`（`run_transition.py:136-147`）与 `read_exact_owned_attempt_cancel_targets`（`run_transition.py:2388-2430`）落在 cancel fact owner。linked event 严格校验覆盖 event_id、canonical class、CANCEL_REQUESTED type、Session/Run identity、Run-scoped（attempt_id/execution_id 均 None）、inline-only（payload_ref/payload_digest 均 None）、完整 body digest 重算与六字段 typed payload 解析。任一不匹配抛 `HostDurableError`，无 skip/soft 路径。

3. `ActiveWorkerRegistry` 新增 `AttemptExecutionIdentity` 作为 entry identity（`dispatch.py:721-735`），`register` 新增 required `session_id`，`cancel` 用四元全等匹配（`dispatch.py:823-837`），`snapshot_identities`（`dispatch.py:840-858`）稳定排序返回。`cancel_all`（`dispatch.py:868-880`）正确从 identity 提取 session_id。

4. caller fast path（`command.py:1648-1660`）先 `registry.cancel(target)` 后按去重 session_id 唤醒 watchdog；`wake_active_cancel_watchdog` 签名改为 required `session_id`（`command.py:1655-1660`、`dispatch.py:1406-1421`）。

5. workspace-wide `tick_active_cancel_watchdog`（无 session 参数）已从 production 删除；watchdog loop（`dispatch.py:3400-3442`）改为纯 event-driven，无 periodic timeout。`read_cancelling_runs`（无 session filter）已从全仓删除，仅保留 `read_cancelling_runs_for_session`。

6. `reconcile_active_worker_cancels_once`（`dispatch.py:3071-3141`）按本地 registry 快照做 read transaction 查询，对每个 target 传播 token/hook 后在写事务内重验 exact target 并复用 `_tick_active_cancel_watchdog` 唯一 terminal producer。空 registry 直接返回全零摘要，不开启 durable read（`dispatch.py:3091-3100`）。

### 2. 并发 / 事务竞态

**结论：PASS**

- watchdog loop 的 `_active_cancel_watchdog_session_ids` 在 asyncio 单线程下操作，`add`/`set`/`snapshot`/`clear` 均在 cooperative yield 之间完成，无数据竞态。tick 期间到达的新 wake 通过 `event.set()` 驱动下一轮。
- `reconcile_active_worker_cancels_once` 在 read transaction 中获取精确 target，再在独立 write transaction 中做 watchdog closeout——两次事务间 identity/owner 可能变化，但 write 内 `_read_exact_owned_active_cancel_watchdog_candidate` 重新执行完整 state+fact 重验，stale 时返回空集合，不会误写 terminal。
- `_tick_active_cancel_watchdog` 写事务内的 `_read_active_cancel_watchdog_candidates`（session scope）或 `_read_exact_owned_active_cancel_watchdog_candidate`（owned scope）均在同 snapshot 内完成，`active_cancel_watchdog_closeout_in_transaction` 使用 CAS 条件更新。caller watchdog 先把 Run 置为 CANCELLED 时，owner reconcile 的 owned-scope 重验仍从 durable cancel link 读取并传播——terminal status 不抹掉 control truth。
- dispatch poll loop（`dispatch.py:3669-3676`）调用 `reconcile_active_worker_cancels_once` 后再调用 `reconcile_owned_sessions_once`，共用同一 `fixed_now`，无 TOCTOU。

### 3. Semantic owner 边界

**结论：PASS**

| 语义 | owner | 消费者 |
|---|---|---|
| exact execution identity 四元组 | `dayu.host.durable.state` | dispatch, run_transition |
| owned cancel candidate SQL join | `dayu.host.durable.state` | run_transition |
| CANCEL_REQUESTED canonical fact 校验 | `dayu.host.durable.run_transition` | dispatch |
| active worker registry exact identity | `dayu.host.dispatch` | command |
| caller cancel propagation + session-scoped watchdog wake | `dayu.host.command` | open_host |
| thread-safe scheduler wakeup bridge | `dayu.host.open_host` | command |

无跨层泄漏、无下游重算、无 fallback/hasattr。state.py 不 import host 上层模块；run_transition.py 只 import state + codec；dispatch.py import run_transition + state；command.py import dispatch；open_host.py import dispatch。依赖方向正确。

### 4. Strict linked CANCEL_REQUESTED 六字段与 digest 校验

**结论：PASS**

直接代码证据（`run_transition.py:2388-2563`）：

- `read_exact_owned_attempt_cancel_targets`：对每个 state-join 候选调用 `read_event_by_id`，missing event → `HostDurableError`。
- `_validate_exact_owned_cancel_requested_event`：event_id 不匹配、非 CANONICAL_FACT、非 CANCEL_REQUESTED、Session/Run 错链、attempt_id/execution_id 非 None、payload_ref/payload_digest 非 None → `HostDurableError`。调用 body digest 和 payload 校验。
- `_validate_event_body_digest`：按与写路径相同的 16-key dict 和 `sha256_digest_json` 重算 digest，不匹配 → `HostDurableError`。写路径（`event_log.py:1018-1055`）使用相同的 `canonical_json_dumps`（`sort_keys=True, separators=(",", ":")`）+ `sha256`。
- `_validate_cancel_requested_payload`：`json.loads` → 必须 Mapping → `frozenset(payload) == _CANCEL_REQUESTED_PAYLOAD_FIELDS`（严格相等，无多余无缺失）→ 逐字段类型+值校验：`run_id` 必须等于 identity.run_id，`client_request_id` 必须等于 event.client_request_id 且非空，`reason` 非空文本，`mode` 合法 `CancelMode`，`target_status_at_accept` 合法 `RunStatus`，`call_context_digest` 合法 sha256 digest。

测试覆盖 10 种 corruption 场景（`test_run_attempt_transitions.py:2357-2485`）：missing、event_class、event_type、session_id、run_id、attempt_id、execution_id、payload_ref、event_body_digest、payload_shape。全部断言 `HostDurableError`。

### 5. Stale identity filtering

**结论：PASS**

- SQL join（`state.py:2262-2291`）要求 `runs.current_attempt_id = requested.attempt_id`、`attempts.execution_id = requested.execution_id`、`dispatch_records.owner_host_instance_id = ?` 三条件同时满足。current Attempt 变更（`current_attempt_id = NULL`）或 dispatch owner 变更 → 无 JOIN 结果 → stale 过滤。
- 测试（`test_run_attempt_transitions.py:2277-2353`）参数化 `stale_field ∈ {"current_attempt", "dispatch_owner"}`，断言 exact query 返回空。
- terminal status 后 identity 仍精确 → 仍返回 target（`test_run_attempt_transitions.py:2040-2275` 的 `cancelling_targets == terminal_targets == (expected,)`）。

### 6. Terminal 后 physical cancel 传播

**结论：PASS**

设计要求："Run 即使先被 caller watchdog 持久化为 CANCELLED，owner 仍从 durable cancel link 读取并传播；terminal status 不能抹掉 control truth。"

- SQL 不按 status 过滤（`WHERE runs.cancel_request_event_id IS NOT NULL`），terminal Run 仍有 cancel link。
- `_read_exact_owned_active_cancel_watchdog_candidate`（`dispatch.py:5029-5083`）在写事务内重验 exact target 后构造 candidate 并执行 terminal closeout——closeout 是幂等的，Run 已 CANCELLED 时 `active_cancel_watchdog_closeout_in_transaction` 的 CAS 会跳过重复写入，但 candidate 构造本身不依赖 Run 状态。
- 测试 `test_exact_owned_cancel_query_keeps_terminal_control_truth_and_filters_stale`（`test_run_attempt_transitions.py:2040-2275`）：accept cancel → watchdog closeout（Run → CANCELLED）→ 重新读取 exact target → 仍返回。wrong owner → 空。

### 7. 唯一 terminal producer

**结论：PASS**

- `_tick_active_cancel_watchdog` 是 watchdog terminal closeout 的唯一写入点。session-scope 和 owned-target-scope 两条路径都汇聚到该方法。
- 旧的 workspace-wide `tick_active_cancel_watchdog`（无参数）已删除。
- `reconcile_active_worker_cancels_once` 通过 `_tick_active_cancel_watchdog(scope=_ActiveCancelWatchdogOwnedTargetScope(target))` 复用同一 producer。
- 测试 `test_terminal_post_commit.py` 的 terminal producer 闭集未被修改即通过（implementation report 记录）。

### 8. Empty registry 快路径

**结论：PASS**

- `reconcile_active_worker_cancels_once`（`dispatch.py:3091-3100`）：`len(identities) == 0` 时直接返回 `ActiveWorkerCancelReconciliationResult(0, 0, 0, 0)`，不开 durable read。
- 测试 `test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`（`test_active_cancel_dispatch.py:2585-2612`）：用 monkeypatch 替换 `run_read` 为 `_reject_transaction_read`（抛 AssertionError），断言 reconcile 不触发 read 且返回全零。

### 9. Target-only wake / 无 workspace-wide scan

**结论：PASS**

- caller cancel 路径（`command.py:1648-1660`）：先 `registry.cancel(target)` 再按 `{target.session_id for target in targets}` 去重唤醒。不扫描其它 Session。
- watchdog loop（`dispatch.py:3400-3442`）：只处理 `_active_cancel_watchdog_session_ids` 中的 session_id，无 periodic interval，无 workspace-wide scan。
- dispatch poll loop（`dispatch.py:3669-3676`）：`reconcile_active_worker_cancels_once` 只查本地 registry 快照对应的 identity，不扫描其它 worker 或 Session。
- 全仓 grep `read_cancelling_runs(`（无 `_for_session`）：零命中。

### 10. Attachment/new-work authority 不漂移

**结论：PASS**

- `reconcile_active_worker_cancels_once` 的 docstring（`dispatch.py:3078-3080`）明确："不依赖当前 attachment，也不授予 queued promotion 或新 Attempt 治理资格。"
- owned-scope watchdog closeout 只写 terminal cancel facts，不创建新 Attempt、不 promotion、不接管。
- `READ_ONLY` attachment 在 `session_attachment.py` 中拒绝 mutation 的逻辑未被修改。
- README 更新准确描述 attachment 权限边界。

### 11. Scope amendment 是否纯机械

**结论：PASS**

Controller 裁决（`wu-ctx-04-slice-3-scope-amendment-controller.md`）追加 `test_dispatch_scheduler.py` 和 `test_admission_multiprocess.py`。

实际修改：
- `test_dispatch_scheduler.py`：所有 `register(...)` 调用补充 required `session_id`；所有 `ActiveCancelMessage(...)` 构造补充 required `session_id`；`tick_active_cancel_watchdog` 改为 `tick_active_cancel_watchdog_for_session`；`wake_active_cancel_watchdog()` 改为 `wake_active_cancel_watchdog("session-watchdog-probe")`；fakes 的 override 签名同步。
- `test_admission_multiprocess.py`：删除不属于 admission contract 的 `wake_active_cancel_watchdog` / `watchdog_wake_count` 死接口。业务断言不变。

无 production 变更、无新 test behavior、无 allowlist 外文件修改。纯机械契约迁移。

### 12. README 当前契约

**结论：PASS**

- `README.md`：用户可见行为——后进入进程 read-only，需先正常退出旧 owner 再 fresh resume。
- `dayu/README.md`：UI/CLI 持有 attachment，Service watcher 只负责 subscription，Host 拥有 access truth；layer-neutral strict-native mutex 边界。
- `dayu/host/README.md`：public attachment contract、mutation gate、target recovery、scheduler new-work eligibility、execution-owner cancel reconcile、唯一 watchdog terminal owner、proactive single-operation 语义。
- `dayu/config/README.md`：reactive operation 上限与 per-operation semantic proposal attempt budget。
- `dayu/service/README.md`：watcher 统一为 subscription，Service 不调用/缓存/推断 attachment。
- `tests/README.md`：新的 focused regression 命令、native mutex 测试、cross-opener cancel 测试层级。

各 README 的 `Agent更新约束` 均被遵守，只写已实现事实。

### 13. 测试与 residual risk

**结论：PASS**

验证证据（implementation report）：
- 8.4 focused：325 passed
- amendment：110 passed
- 8.5 full regression：5590 passed, 11 skipped, 6 deselected
- 8.5 pyright：0 errors
- 8.6 per-file coverage：21 production .py 均 ≥ 80%（最低 81%）
- 8.7 invariant grep：三组均零命中

Residual risks（均有明确 owner）：
- macOS 本机只验证 POSIX native mutex backend；Windows `msvcrt.locking` 路径由 Windows CI 验证。
- 跨 opener cancel 物理传播最多等待一个 `dispatch_poll_interval_seconds` + durable retry 上界；caller durable acceptance 与 watchdog 不依赖该轮询。
- 本地 token/hook 精确传播 ≠ 远端 provider 物理停止；迟到结果由 identity/terminal fence 拒绝。
- fresh-schema 边界：不兼容旧 DB；未来升级由独立 migration WU 拥有。

## Verdict

**pass**。Slice 3 实现完整覆盖 plan exact changes 与 acceptance criteria。所有 13 个 review 维度均无 actionable finding。execution-owner cancel reconcile 通过严格四元 identity SQL join + linked CANCEL_REQUESTED 六字段 digest 校验实现 fail-closed 传播；target-scoped watchdog 消除 workspace-wide scan；唯一 terminal producer 通过汇聚到 `_tick_active_cancel_watchdog` 保持；空 registry 快路径避免无意义事务；scope amendment 纯机械迁移。blocking questions = None。
