# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Re-Review（AgentMiMo）

## 结论

**PASS — 0 new material finding。S3-CR-F01 和 S3-CR-F02 均已关闭。**

- Gate：`code-review-fix-slice-3`
- Accepted base：`b33bb80b` → 当前未提交 workspace
- 角色：独立 Slice 3 re-review，确认两项 accepted findings 修复且无新 material finding
- 排除项：`docs/host/issues-implementation-control.md` 是 Controller-owned dirty change，已排除出被审查实现与 finding

## S3-CR-F01 逐项确认：关闭

### Finding 要求

`_fail_recovering_run` 的 `StateMutationStatus.UPDATED` 分支必须从 same-tx exact result 生成 `wake_queue_promotion=True` notice；`CAS_LOST`/`INVALID_STATE` 必须零 notice。

### 代码证据

1. **`dayu/host/engine_ingest.py:2551-2616`**：`_fail_recovering_run` 实现
   - 第 2576-2591 行：调用 `fail_recovering_run_in_transaction(...)` 获得 `result`
   - 第 2592-2600 行：`result.status != UPDATED` 时返回 `terminal_notice=None`（CAS_LOST/INVALID_STATE 零 notice）
   - 第 2610-2613 行：`UPDATED` 分支正确调用 `terminal_notice_from_transition(result, wake_queue_promotion=True)`

2. **`dayu/host/durable/run_transition.py:940-970`**：`terminal_notice_from_transition` 实现
   - 只消费 `RunTransitionResult.run_event`（same-tx exact result）
   - 校验 Run stable terminal ref 与 exact event 一致
   - 无 latest/max/readback 推断

3. **`dayu/host/engine_ingest.py:861-897`**：`_finish_ingest` 实现
   - 第 871-874 行：`result.terminal_notice is not None` 时调用 `terminal_post_commit_port.notify_terminal_post_commit`
   - commit 后且 exact，符合要求

### 测试证据

1. **`tests/host/test_engine_ingest_mapping.py::test_reactive_fallback_over_budget_fails_closed_without_lost`**
   - 验证 `result.terminal_notice is observation.notice`
   - 验证 `notice.session_id == seeded.session_id`
   - 验证 `notice.wake_queue_promotion is True`
   - 验证 `run.status is RunStatus.FAILED`
   - 验证 `run_event == result.events[-1]`（exact same-tx）
   - 验证 `notice.terminal_event_sequence == run.terminal_event_sequence == run_event.event_sequence`

2. **`tests/host/test_engine_ingest_mapping.py::test_reactive_fail_closed_propagates_recovering_fail_rejection`**
   - 参数化 `CAS_LOST` 和 `INVALID_STATE`
   - 验证 `terminal_notice is None`
   - 验证 `terminal_port.notices == []`
   - 验证 `RUN_FAILED` 事件数为 0

### 结论

**S3-CR-F01 已关闭。** `_fail_recovering_run` 的 `UPDATED` 分支从 same-tx exact result 生成 `wake_queue_promotion=True` notice；`CAS_LOST`/`INVALID_STATE` 返回零 notice。`_finish_ingest` 在 commit 后且 exact 调用 port。

## S3-CR-F02 逐项确认：关闭

### Finding 要求

`run_transition` 必须有唯一 typed owner helper；四个 consumer 无本地 wrapper/alias/re-export；参数名、docstring、校验稳定。

### 代码证据

1. **`dayu/host/durable/run_transition.py:940-970`**：唯一 `terminal_notice_from_transition` 定义
   - required 输入：`RunTransitionResult` + `wake_queue_promotion: bool`
   - 完整中文 docstring，含参数/返回值/异常
   - 校验 Run stable terminal ref 与 exact event 完全一致

2. **四个 consumer 全部从 owner 模块直接 import**：
   - `dayu/host/admission.py:100`：`from dayu.host.durable.run_transition import terminal_notice_from_transition`
   - `dayu/host/engine_ingest.py:184`：同上
   - `dayu/host/recovery.py:33`：同上
   - `dayu/host/dispatch.py:77`：同上

3. **无本地 helper**：`grep -rn "_terminal_notice_from_transition" dayu/host/` 返回零结果

4. **参数名稳定**：所有调用点使用 `wake_queue_promotion`（无 `should_wake_queue_promotion` 漂移）

### 测试证据

1. **`tests/host/test_run_attempt_transitions.py::test_terminal_closeout_appends_concrete_terminal_events`**
   - 验证 `terminal_notice_from_transition` 投影正确
   - 验证 exact sequence/stable Run ref/Session 一致
   - 验证 missing `run_event` 和 inconsistent stable sequence 时抛出 `HostDurableError`

2. **`tests/host/test_terminal_post_commit.py::test_terminal_notice_projection_has_single_durable_owner`**
   - AST 断言 owner 模块恰好一个 `terminal_notice_from_transition` 定义
   - AST 断言四个 consumer 都从 owner 模块直接 import，无本地同名/旧私有 helper 定义

### 结论

**S3-CR-F02 已关闭。** `run_transition` 有唯一 typed owner helper；四个 consumer 无本地 wrapper/alias/re-export；参数名、docstring、校验稳定。

## 新 Material Finding Scan

对全部最终 diff 进行新 material finding scan，包括：

- targeted/focused/pyright/boundary scans
- producer manifest、flag、post-commit 时点
- coordinator watermark/dedupe
- scheduler construction-only factory
- Host close order
- 三条真实 A→B promotion owner barriers
- dual opener isolation
- local-only 边界
- 低基数 metrics
- AGENTS 类型/docstring/owner 约束
- 测试真实性

### 逐项检查

1. **Terminal producer manifest**：`test_static_terminal_producer_manifest_is_exact` 冻结 21 个 producer，与 plan 5.3 闭集精确相等。通过。

2. **Flag 规则**：`True`（single-run pre-dispatch/waiting/recovering cancel、active closeout、首次 wait failed/lost/expiry、Engine 首次 terminal/worker lost、watchdog 首次 closeout、worker startup closeout、startup recovery 首次释放 slot）；`False`（queued cancel、terminal ack/replay/duplicate、session-scope tuple、attempt-free failure）；无 notice（resume、recovering、dispatch-ready、active cancel request）。符合 plan 4.2。通过。

3. **Post-commit 时点**：所有 producer 在 `run_write` 返回后、commit 后调用 `terminal_post_commit_port.notify_terminal_post_commit`，不直接调用 `wake_queue_promotion`。通过。

4. **Coordinator watermark/dedupe**：`_TerminalPostCommitCoordinator` 维护 per-session watermarks，`False` notice 不更新 promotion watermark，`True` notice 只在 `sequence > promotion_watermark` 时更新。通过。

5. **Scheduler construction-only factory**：`_bind_terminal_post_commit_port` 一次性绑定，重复绑定抛 `RuntimeError`。通过。

6. **Host close 顺序**：public gate → wait poller → actor drain → scheduler producers → terminal coordinator close → Session Event Delivery → projection → actor → scheduler store。通过。

7. **三条真实 A→B barrier**：pre-dispatch cancel A + queued B、wait failed A + queued B、wait expiry A + queued B，均验证 A terminal exact sequence 等于 opener-local watermark，B promotion 在 A terminal 前不可见。通过。

8. **Dual opener isolation**：A terminal 后 hook_calls_a >= 1、hook_calls_c == 0、C watermark 保持。通过。

9. **Local-only 边界**：`terminal_post_commit.py` 只依赖 `__future__`、`dataclasses`、`typing`，无业务层 import。未从 `dayu.host` public package export。通过。

10. **低基数 metrics**：只含 `event/outcome/reason` closed enum，无 identity/sequence/payload。通过。

11. **AGENTS 约束**：所有函数提供完整中文 docstring；测试使用 production hook 转发而非 mock 固化行为。通过。

12. **测试验证**：
    - S3 focused gate：407 passed
    - 完整 host suite：2067 passed, 2 skipped, 6 deselected
    - pyright：0 errors, 0 warnings, 0 informations
    - 单文件 coverage：全部 ≥80%

### 结论

**未发现新的 material finding。**

## 旧旁路清除验证

- `queue_promotion_session_id`/`_promote_after_release`/`_with_terminal_promotion_retry`/`promotion_triggered`/`released_active_slot` 在 production 中已清除
- `wake_queue_promotion` 只出现在 5 个 ordinary 允许位置（terminal producer scope 内无 `wake_queue_promotion`）
- `QueuePromotionWakeupPort` 已删除

## Residual Risks / Open Questions

无 S3 contract 的已知 residual correctness risk。

Service exact-five、CLI callback execution domain、旧 Service relay 删除及 README 实际更新属于已批准的 S4，不在本 Slice scope 内。

## Artifact 路径

`docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-mimo.md`
