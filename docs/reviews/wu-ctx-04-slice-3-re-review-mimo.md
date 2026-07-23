# WU-CTX-04 Slice 3 Code Re-Review（AgentMiMo）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- fix artifact：`docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`
- adjudication：`docs/reviews/wu-ctx-04-slice-3-code-review-controller-adjudication.md`
- accepted findings：`CTRL-S3-001`、`CTRL-S3-002`、`CTRL-S3-003`
- re-review decision：`pass`
- new actionable findings：0

## Verdict

**pass**。三项 accepted findings 均已 root-cause closure，production 修复完整、测试直接覆盖、无新
actionable regression。

## Finding-by-finding verification

### CTRL-S3-001 — High — execution-owner cancel poll 被不相关的 proactive compactor 阻塞

**verdict：fixed**

**Production 修复证据**

- `dayu/host/dispatch.py` 新增独立 `_active_worker_cancel_reconciliation_loop()`。该 loop 每
  `dispatch_poll_interval_seconds` 仅调用 `reconcile_active_worker_cancels_once(fixed_now=...)`，
  不进入 `reconcile_owned_sessions_once()`、promotion 或 proactive compactor await 链。
  `dispatch.py:3703-3732`。
- task 通过 `_start_critical_task(...)` 以稳定 component
  `active_cancel_owner_reconciliation` 接入 shared health supervisor。`dispatch.py:3321-3338`。
- scheduler open 在启动 Session reconciliation 前启动 owner cancel task
  （`dispatch.py:1334`），确保 `scheduler.close()` 的 `except BaseException` 路径会取消并
  await 已启动 task。
- scheduler close 的 mandatory background task 集合显式包含
  `_active_worker_cancel_reconciliation_task`（`dispatch.py:3227`），与 Session reconciliation
  task 一起先 cancel、后逐个 await。`dispatch.py:3220-3249`。
- `_owned_session_reconciliation_loop()` 现在只拥有 attachment-authorized new-work
  reconciliation，不含 execution-owner cancel poll。`dispatch.py:3679-3702`。

**反例构造验证**

Controller 要求的反例：Session A 持有 stable active worker，Session B 阻塞在 proactive
compactor → 旧 opener 的共享 loop 阻塞 → Session A detach 后 fresh opener cancel → 旧 owner
不传播。修后：Session B compactor 阻塞只影响 `_owned_session_reconciliation_loop`；独立
`_active_worker_cancel_reconciliation_loop` 仍按 interval 执行 exact identity durable
reconcile 并传播 cancel。

**直接测试证据**

- `test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks`：用
  `_BlockingOwnedSessionReconciliation` barrier 确定性阻塞 Session reconciliation；另一个
  registry 接受 durable cancel 后，独立 periodic owner task 仍把 canonical reason
  `"user_stop"` 传播到旧 local handle（`assert handle.cancel_reasons == ["user_stop"]`）。
  随后 `scheduler.close()` 必须收口两个 task，阻塞 task 可观察到 cancellation。
  `test_active_cancel_dispatch.py:307-494`。
- `test_owner_cancel_task_is_joined_when_later_scheduler_open_step_fails`：在 owner task
  启动后注入后续 open step 失败，断言 failed-open 返回前 task 已 done。
  `test_active_cancel_dispatch.py:496-594`。
- 空 registry 快照直接返回不打开 durable read：
  `test_owner_cancel_reconcile_empty_snapshot_skips_durable_read`。
  `test_active_cancel_dispatch.py:307-355`。

### CTRL-S3-002 — Medium — 跨 opener token/hook 丢失 canonical cancel reason

**verdict：fixed**

**Production 修复证据**

- `dayu/host/durable/run_transition.py` 新增 `OwnedAttemptCancelDelivery(target, reason)` 与
  `read_exact_owned_attempt_cancel_deliveries(...)`。同一个 strict linked-event validator
  `_validate_exact_owned_cancel_requested_event()` 现在返回已验证的 exact six-field payload
  `reason`。`run_transition.py:2409-2614`。
- `read_exact_owned_attempt_cancel_targets(...)` 继续提供 accepted target contract，复用
  同一 strict validation/source of truth，不暴露 EventLog raw row。
  `run_transition.py:2357-2407`。
- `dayu/host/dispatch.py` 的 `reconcile_active_worker_cancels_once()` 只读取 typed
  deliveries，把 `delivery.reason` 交给 `ActiveCancelMessage`。
  `dispatch.py:3130-3155`。
- `_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 常量与 `durable_cancel_requested` 字符串已从
  production 和 tests 中完全删除。stale grep 零命中。

**反例构造验证**

Controller 要求的反例：用户以 reason `cross_opener_cancel` 取消旧 opener worker → caller
registry miss → 旧 owner 收到 `durable_cancel_requested` 而非用户 reason。修后：旧 owner
通过 `read_exact_owned_attempt_cancel_deliveries(...)` 从 canonical `CANCEL_REQUESTED`
event 投影 `reason="cross_opener_cancel"`，`ActiveCancelMessage.reason` 等于该值。

**直接测试证据**

- `test_cross_opener_cancel_reaches_detached_execution_owner`：真实 public 双 opener
  路径，owner scheduler 通过 `reconcile_active_worker_cancels_once()` 传播 cancel。断言
  `factory.cancel_reasons == ["cross_opener_cancel"]` 与
  `factory.active_snapshot.cancellation_token.cancel_reason() == "cross_opener_cancel"`。
  `test_public_session_attachment.py:1084-1182`。
- `test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks` 同时断言
  owner-level hook 收到 producer 的 canonical `"user_stop"`。
- `test_exact_owned_cancel_query_fails_closed_for_bad_linked_fact`：10 种损坏类型
  （missing/event_class/event_type/session_id/run_id/attempt_id/execution_id/payload_ref/
  event_body_digest/payload_shape）均 fail closed，不静默跳过。
  `test_run_attempt_transitions.py:2043-2383`。

### CTRL-S3-003 — Medium — dynamic VALUES 依赖 SQLite bind 上限

**verdict：fixed**

**Production 修复证据**

- `dayu/host/durable/state.py` 定义保守 batch size：
  `_SQLITE_LEGACY_DEFAULT_MAX_VARIABLE_NUMBER=999`，`_OWNED_CANCEL_IDENTITY_PARAMETER_COUNT=5`，
  `_OWNED_CANCEL_FIXED_PARAMETER_COUNT=1`，
  `_OWNED_CANCEL_QUERY_BATCH_SIZE=(999-1)//5=199`。`state.py:142-152`。
- `read_owned_attempt_cancel_candidates()` 在执行任何 batch 前对完整 tuple 先校验 owner id、
  每个 identity 的四个 non-empty 字段以及全局 duplicate；empty tuple 直接返回空结果。
  `state.py:2224-2260`。
- 每个 batch 使用相同 `HostTransaction`，global `request_order` 从原 tuple 的绝对下标生成
  （`enumerate(batch, start=batch_start)`）；batch 内 `ORDER BY request_order` 后按连续
  batch 追加，因此过滤 stale/wrong-owner 项后仍严格保持全局输入顺序。
  `state.py:2260-2350`。

**反例构造验证**

Controller 要求：合法完整输入不应因单 statement bind 上限被拒绝。修后：205 个 identity
（超过 199 batch size）透明分两批查询，结果保持全局顺序。

**直接测试证据**

- `test_exact_owned_cancel_query_batches_preserve_global_order_and_filter_stale`：创建
  205 个真实 typed cancel targets，以逆序输入跨越 199 条边界，并分别在不同 batch 注入
  wrong dispatch owner 与 stale current Attempt。断言完整 typed output 精确等于过滤后的
  全局输入顺序。`test_run_attempt_transitions.py:2383-2435`。
- 既有 terminal truth、wrong owner、stale execution/current Attempt、duplicate 与 strict
  bad-link fail-closed cases 全部继续通过（12 parameterized cases）。

## Adversarial regression checklist

| 检查项 | 结果 | 证据 |
|---|---|---|
| 不恢复 workspace-wide scan | ✅ | `read_cancelling_runs()` 已删除；owner cancel 用 `snapshot_identities()` local registry；stale grep 零命中 |
| 不制造第二 terminal producer | ✅ | `_tick_active_cancel_watchdog` 唯一 terminal producer；`_read_exact_owned_active_cancel_watchdog_candidate` 在写事务内重验 |
| 不用下游 fallback/替代 reason | ✅ | `_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 已删除；reason 由 run-transition typed projection 唯一提供 |
| 不破坏 attachment ownership | ✅ | fix 不修改 `session_attachment.py` 或 registry contract |
| stale identity/owner fail-closed | ✅ | stale 只过滤不误配；坏 link 抛 `HostDurableError`；12 种 fail-closed cases |
| task health/lifecycle | ✅ | `_start_critical_task()` 接入 health supervisor；close 包含 owner cancel task；test 验证 close join |
| 并发与异常路径 | ✅ | 独立 loop 不被 Session reconcile/compactor 阻塞；空 snapshot 不开事务；close 时 cancelled 透传 |

## 测试证据

```text
targeted tests (7 files):                          304 passed
extended matrix (10 files):                        324 passed
terminal producer manifest:                          7 passed
full Host suite:                                 2150 passed, 2 skipped, 6 deselected
pyright (changed production files):     0 errors, 0 warnings, 0 informations
git diff --check:                               pass
stale grep (durable_cancel_requested):          zero hits
stale grep (read_cancelling_runs):              zero hits
stale grep (_ACTIVE_CANCEL_OWNER_RECONCILE_REASON): zero hits
```

## Residual risks

1. **existing accepted runtime boundary**：独立 task 消除了 compactor await 的无界阻塞，但
   physical propagation 仍依赖 configured poll interval、SQLite transaction 可用性与 opener
   event loop 调度；durable failure 由 health supervisor fail closed。
   分类：`covered by existing runtime health owner`。

2. **external execution boundary**：本地 token/hook 传播不等价于远端 provider physical
   exactly-once 停止；迟到结果继续由既有 identity/terminal fence 拒绝。
   分类：`assigned to existing provider boundary`。

3. **custom SQLite build/runtime limit**：batch 以 SQLite 历史默认 999 为支持环境的保守依据；
   若未来明确支持把 connection variable limit 主动降到 999 以下的定制 runtime，应由独立
   runtime-policy WU 增加 connection-specific limit owner。
   分类：`assigned to later work unit if support scope expands`。

## Blocking questions

None。三项 accepted findings 均已 root-cause closure；fix artifact 完整、测试覆盖直接、无新
actionable gap。下一 gate 为 Controller 最终裁决，随后可创建 accepted Slice 3 commit。
