# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Review（AgentMiMo）

## 结论

**PASS — 无 material finding。**

- Gate：`code-review-slice-3`
- Review base：`b33bb80b` → 当前未提交 workspace
- 角色：独立 Slice 3 code reviewer
- 排除项：`docs/host/issues-implementation-control.md` 是 Controller-owned dirty change，已排除出被审查实现与 finding

## 逐项 adversarial 检查

### 1. RunTransitionResult required exact same-tx run_event/stable ref

**结论：通过。**

- `RunTransitionResult.run_event` 是新增 required field（`run_transition.py:918`），无默认值。
- 所有 30+ 个 transition 调用点显式填充 `run_event=`：写 Run event 时传入同一 transaction append 返回的 exact row，无 Run event 时显式 `None`。
- `read_terminal_run_event_in_transaction`（`run_transition.py:2322`）沿 `RunRow.terminal_event_id/terminal_event_sequence` stable ref 精确读取并校验 id、sequence、session_id、run_id 全部一致。
- `confirm_terminal_run_in_transaction`（`run_transition.py:2355`）要求 `run.status in TERMINAL_RUN_STATUSES`，结果中的 `run_event` 只沿 stable ref 读取。
- terminal replay 路径（`_terminal_closeout_replay_result`、`_active_cancel_watchdog_replay_result`）新增 `transaction`/`event_log_store` 参数，在 replay 结果中通过 `read_terminal_run_event_in_transaction` 填充 exact row。
- 无 latest/max/readback 推断。无 commit 后回读。

### 2. 全 terminal producer manifest、flag、post-commit 时点、无 direct promotion/session-id-only 旁路

**结论：通过。**

- `test_terminal_post_commit.py::test_static_terminal_producer_manifest_is_exact` 以 AST 遍历冻结 21 个 terminal transition producer（admission 9、waiting 3、engine_ingest 4、recovery 2、dispatch 3），与 plan 5.3 闭集精确相等。
- `test_direct_queue_promotion_allowlist_is_exact` 冻结 5 个 ordinary direct promotion 调用，terminal producer scope 内无 `wake_queue_promotion`。
- `test_source_has_no_run_ref_notice_or_optional_production_port` 扫描确认无 `_terminal_notice_from_run_ref`、无 `terminal_post_commit_port: TerminalPostCommitPort | None`、无 `set_terminal_post_commit_port`。
- flag 规则符合 plan 4.2：
  - `True`：single-run pre-dispatch/waiting/recovering cancel、active closeout、首次 wait failed/lost/expiry、Engine 首次 terminal/worker lost、watchdog 首次 closeout、worker startup closeout、startup recovery 首次释放 slot。
  - `False`：queued cancel、terminal ack/replay/duplicate、session-scope tuple、attempt-free failure。
  - 无 notice：resume、recovering、dispatch-ready、active cancel request。
- 删除了 `_promote_after_release`、`_with_terminal_promotion_retry`、`queue_promotion_session_id`、`EngineIngestResult.promotion_triggered`、`CancelRunResult.released_active_slot`、`QueuePromotionWakeupPort` 等旁路。
- 所有 producer 在 `run_write` 返回后、commit 后调用 `terminal_post_commit_port.notify_terminal_post_commit`，不直接调用 `wake_queue_promotion`。

### 3. Coordinator watermark/promotion dedupe

**结论：通过。**

- `_TerminalPostCommitCoordinator`（`open_host.py:369`）维护 per-session `_promotion_watermarks` dict。
- 每个 notice 先 `max` advance delivery watermark，再按独立 promotion watermark 处理。
- `False` notice 仍推进 delivery watermark 但不改变 promotion watermark。
- `True` notice 只在 `sequence > promotion_watermark` 时更新 watermark 并调用 promotion。
- same-sequence duplicate 幂等（delivery hub 返回 `False` 时不 advance）。
- newer `False` 不更新 promotion watermark → 不吞 older `True`。
- newer `True` 覆盖 older `True`。
- `test_coordinator_watermark_before_promotion_and_independent_dedupe` 直接覆盖：false/duplicate、older/newer、非 owner thread、close 前排队 notice（`call_soon` + barrier）、close 后调用、低基数 outcome 日志（`delivery_advanced`/`promotion_woken`/`duplicate`/`closing`）。
- close 使用 `call_soon` barrier 确保 owner-loop 已排队 callback 完成后才标记 closed。
- 日志只含 `event=terminal_notice outcome=X [reason=coordinator_closing]`，无 identity、sequence、capacity 或 payload。

### 4. Scheduler construction-only factory/single bind/failure cleanup 与 Host close order

**结论：通过。**

- `HostDispatchScheduler.open`（`dispatch.py:1141`）：
  1. 先 `_initialize_inert` 创建不可运行 scheduler。
  2. `terminal_post_commit_port_factory.create_terminal_post_commit_port(promotion_port=scheduler)` 取得 promotion capability 并创建 coordinator。
  3. `_bind_terminal_post_commit_port` 一次性绑定。
  4. 才 `_start_host_instance_heartbeat` / `_start_active_cancel_watchdog_loop`。
  5. 异常时 `close_after_failed_scheduler_open` + `scheduler.close()` 清理。
- `_bind_terminal_post_commit_port` 重复绑定抛 `RuntimeError`。
- `_required_terminal_post_commit_port` 未绑定时抛 `RuntimeError`。
- `test_scheduler_terminal_port_failure_closes_each_owner_once_without_tasks` 参数化 `factory`/`bind` 两阶段失败，断言 critical task count=0、coordinator 关闭一次、lane 关闭一次、scheduler 不 return。
- Host close 顺序（`_PublicHostHandle.close`）：public gate → wait poller → actor drain → scheduler producers → terminal coordinator close → Session Event Delivery → projection → actor → scheduler store。
- coordinator close 在 scheduler producer stop 之后、delivery owner close 之前。

### 5. 三条真实 A terminal→B promotion owner barriers

**结论：通过。**

`test_open_host_runtime.py` 包含三条 barrier 测试：

1. `pre-dispatch cancel A + queued B`
2. `wait failed A + queued B`
3. `wait expiry A + queued B`

每条测试：
- 在 action 前建立 pending watcher。
- 冻结 worker dispatch 但保留真实 durable admission/promotion。
- 断言 A terminal exact sequence 等于 opener-local watermark。
- B 的 promotion `RUN_STARTED` 在 A terminal 前不可见。
- B 只能在 terminal 后下一次 `anext()` 交付。

### 6. Dual opener C-side 无跨 opener local wake 且 durable reconciliation correctness

**结论：通过。**

- `_TerminalWatermarkHookCallCounter` 改为 per-instance（接受 `target_hub` + `hook`），只对目标 opener 的 hub 计数并转发 production hook。
- `_record_instance_terminal_watermark_hook` 路由调用到正确 opener 计数器。
- A terminal 后：`hook_calls_a.call_count >= 1`、A watermark 前进。
- 同时：`hook_calls_c.call_count == 0`、C watermark 保持 `pre_action_c_watermark`、C watcher 仍 pending、C reconciliation clock 未推进时 page read 为空。
- 保留 shared DB/lane DB、独立 opener runtime/worker、durable B fence、multi-page catch-up、A terminal 先于 B、timeout 计数、retained item 与 A/C cleanup 顺序断言。

### 7. Local-only 边界、低基数 metrics、AGENTS 类型/docstring/owner 约束、测试真实性

**结论：通过。**

- `terminal_post_commit.py` 只依赖 `__future__`、`dataclasses`、`typing`，无业务层 import。
- 未从 `dayu.host` public package export `TerminalPostCommitNotice`/`TerminalPostCommitPort`（`test_notice_strict_validation_and_private_package_boundary` 断言）。
- metrics 只含 `event/outcome/reason` closed enum，无 identity/sequence/payload。
- 所有函数提供完整中文 docstring，含参数/返回值/异常。
- 测试使用 production hook 转发而非 mock 固化行为。standalone command handle test 通过独立 SQLite 连接读取已提交 row 验证 notice 发生在 commit 后。

### 8. Scope、>=80% coverage evidence、完整 pyright、README audit

**结论：通过。**

- **Tests**：S3 focused gate 406 passed。完整 host suite 2066 passed, 1 skipped, 6 deselected。
- **pyright**：`0 errors, 0 warnings, 0 informations`。
- **git diff --check**：通过。
- **单文件 coverage**（来自 implementation artifact）：
  - `terminal_post_commit.py`: 95%
  - `run_transition.py`: 93%
  - `admission.py`: 91%
  - `command.py`: 88%
  - `dispatch.py`: 91%
  - `engine_ingest.py`: 91%
  - `open_host.py`: 88%
  - `recovery.py`: 91%
  - `waiting.py`: 89%
  - 全部 ≥80%。
- **Source scans**：
  - `queue_promotion_session_id`/`_promote_after_release`/`_with_terminal_promotion_retry`/`promotion_triggered`/`released_active_slot` 在 production 中已清除（test 中 `test_promote_after_release_reports_delegated_to_governance` 正确断言旧函数已删除）。
  - `wake_queue_promotion` 只出现在 5 个 ordinary 允许位置。
  - `TerminalPostCommit`/`session_event_delivery` 未进入 `dayu/engine`。
  - `dayu.runtime` 无对 Engine/Host/Service/UI/Fins 的 import。
- **README**：S3 修改不在 S3 allowed README modules 内，implementation artifact 正确记录触发审计并交由 S4 统一更新。
- **Scope**：所有 production/test 修改均在 S3 plan allowlist 内。`docs/host/issues-implementation-control.md` 是 Controller-owned dirty change，已排除。

## Residual risks / open questions

无 S3 contract 的已知 residual correctness risk。

Service exact-five、CLI callback execution domain、旧 Service relay 删除及 README 实际更新属于已批准的 S4，不在本 Slice scope 内。

## Artifact 路径

`docs/reviews/wu-host-session-event-delivery-01-slice3-implementation-mimo.md`
