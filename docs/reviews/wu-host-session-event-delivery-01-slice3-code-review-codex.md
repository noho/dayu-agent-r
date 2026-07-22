# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Review（AgentCodex）

## Verdict

**PASS WITH 1 MATERIAL FINDING** — 1 correctness gap（`_fail_recovering_run` 缺失 terminal notice），1 maintainability concern（`_terminal_notice_from_transition` 四模块重复），其余 7 项 adversarial 检查全部通过。

## 审查范围

- **Accepted base**: `b33bb80b`
- **审查 Diff**: 27 files, +2966/-418 lines（production 9 + test 17，另 1 new）
- **排除**: `docs/host/issues-implementation-control.md`（Controller-owned dirty change，不审查）
- **Methodology**: 逐文件 read/diff + grep 验证 + 测试执行 + pyright + stale/source scan

---

## Finding 1（Material）: `_fail_recovering_run` 返回 `terminal_notice=None`，terminal 事实未通知 coordinator

**Severity**: Material — correctness gap（本地 terminal 已 durable commit 但 delivery coordinator 未获通知）

**File/Line**: `dayu/host/engine_ingest.py:2606-2613`

**直接代码证据**:

```python
# dayu/host/engine_ingest.py:2576-2613
def _fail_recovering_run(self, transaction, context, failed_event, error_code, message):
    result = fail_recovering_run_in_transaction(
        transaction, self._event_log_store, FailRecoveringRunInput(...)
    )
    if result.status != StateMutationStatus.UPDATED:
        return EngineIngestResult(..., terminal_notice=None, ...)  # OK: CAS_LOST
    rows = _existing_rows(...)
    return EngineIngestResult(
        status=EngineIngestStatus.ACCEPTED,
        events=rows,
        terminal_closeout=True,     # ← durable 层已确认 terminal
        terminal_notice=None,        # ← BUG: 未构造 notice
        reason=_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED,
        transient_delta=None,
    )
```

**Owner/Root Cause**: `_fail_recovering_run` 的两个 caller（`_fail_recovering_run_without_request` at line 1741-1752 和 `_handle_reactive_recovery` at line 2094-2124）都直接使用 `run_failed.terminal_notice` / `fail_result.terminal_notice` 向上传播，但该方法本身在 transition 成功（UPDATED）时未从 `result.run_event` 构造 notice。

**可执行反例**: 构造一个 context_compaction → recovery 启动失败 → `_fail_recovering_run` 成功提交 terminal 的场景：
1. Run RECOVERING → `fail_recovering_run_in_transaction` → UPDATED（Run 变为 FAILED，slot 已释放）
2. 预期：`_finish_ingest` 中 `result.terminal_notice is not None` → 调用 coordinator `notify_terminal_post_commit`
3. 实际：`terminal_notice=None` → coordinator 未被通知 → watcher 只能通过 durable reconciliation timeout 发现此 terminal

**修复要求**: 在 `_fail_recovering_run` 的 UPDATED 分支中，从 `result` 构造 notice：
```python
terminal_notice=_terminal_notice_from_transition(
    result,
    wake_queue_promotion=True,  # RECOVERING→FAILED 释放 active slot
),
```

**Plan Flag 对照**: plan 5.3 将 `EngineEventIngestor._fail_recovering_run` 列入 terminal producer manifest，flag 规则 `wake_queue_promotion=True`（single-run recovering cancel / active closeout 首次释放 active slot）。

---

## Finding 2（Maintainability）: `_terminal_notice_from_transition` 在 4 个模块中重复定义

**Severity**: Non-material — maintainability / code quality（不影响运行时正确性，但违反编码约束且将成为未来重构风险）

**直接代码证据**:

| Module | Line | Parameter name | Error message |
|--------|------|---------------|---------------|
| `admission.py` | 4699 | `wake_queue_promotion` | "terminal transition result is missing exact Run event" / "terminal transition exact Run event is inconsistent" |
| `engine_ingest.py` | 3886 | `wake_queue_promotion` | "terminal ingest transition is missing exact Run event" / "terminal ingest exact Run event is inconsistent" |
| `recovery.py` | 963 | `wake_queue_promotion` | "terminal recovery transition is missing exact Run event" / "terminal recovery exact Run event is inconsistent" |
| `dispatch.py` | 4429 | `should_wake_queue_promotion` | "terminal transition exact Run event is inconsistent"（无两阶段消息分离） |

**Owner/Root Cause**: `RunTransitionResult.run_event` 的 notice 构造逻辑没有抽取到 `run_transition.py`（`RunTransitionResult` 的 owner module）。plan 未明确要求统一放置，但 AGENTS.md "重复逻辑必须抽取" 构成硬约束。

**修复要求**: 将 `_terminal_notice_from_transition` 定义为 `dayu/host/durable/run_transition.py` 的模块级公开函数（或至少是 `_build_terminal_notice_from_transition`），四个 producer 模块统一 import。统一参数名为 `wake_queue_promotion: bool`。两个阶段的错误消息统一为：
- `"transition result is missing exact Run event"`
- `"transition exact Run event is inconsistent"`

各模块的上下文（ingest/recovery/等）已在调用栈与日志中包含，无需在 error message 中重复。

---

## 检查清单逐项确认

### 1. RunTransitionResult required same-tx run_event/replay stable ref ✓

- `RunTransitionResult.run_event` 已改为 required field。
- 所有 70 处 `RunTransitionResult(...)` 构造均显式填充（grep 确认）。
- 新增 `read_terminal_run_event_in_transaction` 和 `confirm_terminal_run_in_transaction` 通过 `RunRow.terminal_event_id/sequence` stable ref 精确读取。
- `_terminal_closeout_replay_result` 和 `_active_cancel_watchdog_replay_result` 改为接受 `transaction + event_log_store` 并通过 `read_terminal_run_event_in_transaction` 在同一 transaction 读取 exact row。
- 未发现 post-commit latest/max/status 推断。

### 2. 全 terminal producer manifest、flag、post-commit 时点、无 direct promotion/session-id-only 旁路 ✓

- AST manifest 闭集 21 个 producer（admission 9 + waiting 3 + engine_ingest 4 + recovery 2 + dispatch 3），测试 `test_static_terminal_producer_manifest_is_exact` 精确断言。
- Ordinary direct promotion allowlist 精确 5 个调用（admission governance 1 + recovery batch 1 + coordinator 1 + threadsafe bridge 2），测试 `test_direct_queue_promotion_allowlist_is_exact` 精确断言。
- `_promote_after_release`、`queue_promotion_session_id`、`_with_terminal_promotion_retry`、`EngineIngestResult.promotion_triggered`、`CancelRunResult.promotion`、`CancelRunResult.released_active_slot`、`TerminalCloseoutResult.promotion` 全部删除（grep 确认 admission/waiting 无残留）。
- 所有 producer 在 `run_write` 返回后才调用 `notify_terminal_post_commit`（admission、waiting、engine ingest、recovery batch、dispatch 均已验证）。
- **例外：Finding 1** 中 `_fail_recovering_run` 缺少 notice。

### 3. Coordinator watermark/promotion dedupe、close in-flight 与 coordinator_closing ✓

- `_TerminalPostCommitCoordinator._notify_on_owner_loop` 严格先 delivery watermark `max` advance，再按独立 promotion watermark 处理。
- `wake_queue_promotion=False` 只推进 delivery（已验证：duplicate 不触发 promotion）。
- `wake_queue_promotion=True` 且 `sequence > promotion_watermark` 才唤醒 promotion。
- same-sequence duplicate 幂等（delivery_advanced → duplicate 两个日志记录）。
- newer false 不吞 older true：false 不更新 promotion watermark，older true 仍可达（已验证：seq 10 false → 12 false → 11 true，promotion 在 11 处触发）。
- newer true 覆盖 older true（seq 13 true 在 11 true 之后正常触发）。
- `close()` 用 owner-loop barrier（`call_soon(barrier.set_result) + await`）drain 已排队 notice，close 后调用 fail closed + `coordinator_closing` 诊断。
- batch notices 按 sequence 排序（admission session-scope、recovery batch 均 `sorted(key=lambda notice: notice.terminal_event_sequence)`）。
- 低基数日志不含 identity/sequence/payload/capacity dimension。
- 非 owner thread 通过既有 `_run_callback_on_event_loop` bridge marshal。

### 4. Scheduler construction-only factory/single bind/failure cleanup 与 Host close order ✓

- `HostDispatchScheduler.open` 新增 required `terminal_post_commit_port_factory` 参数，在 inert 资源就绪后创建 coordinator，private `_bind_terminal_post_commit_port` 只允许一次 bind。
- 测试 `test_scheduler_terminal_port_failure_closes_each_owner_once_without_tasks` 覆盖 factory failure 与 bind failure 两条路径：
  - `terminal_factory.create_calls == 1`
  - `terminal_factory.close_calls == 1`
  - `lane_close_calls == 1`
  - 所有 critical task（heartbeat、watchdog、drain、promotion_drain、active_tasks、active_handles）均为空/None
  - scheduler `_closed == True`，`_close_cleanup_done == True`
- 源码 scan 确认无临时 no-op port、runtime setter 或 rebind。
- Host close order 精确：public gate → wait poller → actor drain → scheduler close（含 heartbeat/watchdog/drain/worker/ingestor）→ coordinator close → delivery hub close → projection/actor/scheduler store。

### 5. 三条真实 A terminal→B promotion owner barriers ✓

- `test_pre_dispatch_cancel_terminal_precedes_queued_promotion_entry`：pre-dispatch A cancel → A terminal exact sequence == watermark → B RUN_STARTED 不在 A terminal 前 → B 只在 A terminal 后下一次 `anext()` 交付。
- `test_wait_failed_terminal_precedes_queued_promotion_entry`：wait failed A → same barrier 断言。
- `test_wait_expiry_terminal_precedes_queued_promotion_entry`：wait expiry A → same barrier 断言。
- 三个测试均：冻结 worker dispatch（`_ignore_dispatch_wake`）、action 前建立 pending watcher、action 后冻结 `anext()` task、验证 promotion 后 B 不越过 A。
- `_assert_terminal_before_promoted_start` helper 在循环消费中显式断言 B RUN_STARTED 不先于 A terminal，同时验证 watermark == terminal event_sequence。

### 6. Dual opener C-side 无跨 opener local wake 且 durable reconciliation correctness ✓

- `test_dual_opener_b_fence_catches_up_pages_before_terminal_handoff`：
  - A/C 各自绑定实例级 `_TerminalWatermarkHookCallCounter`，A 本地 hook 可推进（`hook_calls_a.call_count >= 1`，A watermark > pre_action），C 本地 watermark 保持 pre_action（0），C watcher pending，C page read 为空。
  - 本地 hook counter 不跨 opener 记录，通过 hub identity 校验路由正确性。
  - B fence 迫使 C catch-up 多页后 A terminal 先于 B terminal。
  - shared DB/lane DB、independent opener runtime/worker、cleanup 顺序保留。
- 跨 opener isolation 断言收窄为 C-side 局部证据（plan S3 amendment R2 要求），全局 hook 总调用数零断言已移除。

### 7. Local-only 边界、低基数 metrics、AGENTS 类型/docstring/owner 约束、测试真实性 ✓

- `terminal_post_commit.py` 不 public export（测试 `test_notice_strict_validation_and_private_package_boundary` 断言 `hasattr(host_package, "TerminalPostCommitNotice") == False`）。
- Notice 严格校验：拒绝 bool sequence、非正数 sequence、空白 session_id、非 bool flag。
- `test_terminal_contract_module_has_no_upper_layer_dependency` 断言模块仅 import `__future__`、`dataclasses`、`typing`。
- 低基数日志：`event` 只允许 `attach/detach/overflow/terminal_notice`，`outcome/reason` 只允许闭集枚举值，不含 identity/sequence/payload/capacity。
- `_terminal_notice_from_transition` 四模块重复（Finding 2），但每个模块的定义均包含完整中文 docstring 与类型注解。
- 测试均为真实 Host/DB/transaction 路径，非 mock 固化：
  - `test_standalone_factory_delivers_exact_terminal_notice_after_command` 使用独立 SQLite 连接在 callback 后读回 committed EventLog row，证明 notice 发生在 commit 后且 sequence/session 一致。
  - `_TransientThenFinalWorkerFactory` + `_TransientThenFinalHandle` 产出真实 EngineEvent stream，经完整 Host ingest pipeline。
  - Scheduler construction failure 测试通过 `monkeypatch` + 真实 LaneController close recording 验证。

### 8. Scope、≥80% coverage evidence、完整 pyright、README audit 可接受 ✓

- **pyright**: 0 errors, 0 warnings, 0 informations。
- **Tests**: S3 focused gate 388 passed；A→B barrier 3 passed；dual-opener 1 passed；standalone recording fake 1 passed；scheduler construction failure 2 passed。
- **Coverage**（per Codex implementation report，full Host suite）:
  - `admission.py`: 91%, `command.py`: 88%, `dispatch.py`: 91%
  - `run_transition.py`: 93%, `engine_ingest.py`: 91%, `open_host.py`: 88%
  - `recovery.py`: 91%, `terminal_post_commit.py`: 95%, `waiting.py`: 89%
  - 全部 ≥ 80% ✓
- **Stale symbols**: scan 为空（仅 S4 预期的 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` 仍保留）。
- **Reverse dependency**: `dayu.runtime` 无 Engine/Host/Service/UI/Fins import ✓。
- **Engine boundary**: `dayu/engine` 无 TerminalPostCommit/session_event_delivery 引用 ✓。
- **git diff --check**: 通过 ✓。
- **README audit**: 全部 README 文件列为 S4 allowed modules，S3 不修改，交由 S4 实施后统一更新。审计结论与 plan 一致。
- **Scope**: production/test diff 文件均在 S3 allowlist 内；新增 `terminal_post_commit.py` 与 `test_terminal_post_commit.py` 在 S3 授权内。

---

## Residual Risks / Open Questions

1. **Finding 1 修复后需重新验证**: `_fail_recovering_run` 加回 notice 后需验证 `_finish_ingest` → coordinator 的完整 call chain，以及两个 caller 的 `terminal_notice` 传播正确性。建议补充针对 `context_compaction → recovery fail` 路径的 explicit terminal notice test。

2. **`_terminal_notice_from_transition` 四模块重复**: 不影响当前正确性，但按 AGENTS.md 应在后续 S4 或 cleanup PR 中统一到 `run_transition.py`。如果各模块的错误消息差异被认定为有意设计（便于故障定位），则至少应统一参数名（dispatch 的 `should_wake_queue_promotion` → `wake_queue_promotion`）和校验逻辑（admission 的两阶段 None/identity 检查 vs dispatch 的单阶段合并检查）。

3. **`docs/host/issues-implementation-control.md`**: Controller-owned dirty change，本 review 未读取、未审查、未编辑。其 S3 实现状态记录可能未反映 Finding 1 的存在。

---

## 审查统计

- Production files reviewed: 9（+1 new）
- Test files reviewed: 17（+1 new）
- Tests executed: S3 focused gate 388 passed
- Material findings: 1（correctness gap）
- Maintainability findings: 1（code duplication）
- pyright: clean
- Stale/source scans: clean
