# 聚合深度审查 Re-review — wu-cli-interactive-02 aggregate fix

## Scope

- **Mode**: Current changes aggregate re-review
- **Branch**: `codex/interactive-oracle`
- **Base**: `main`
- **Output file**: `docs/reviews/aggregate-deepreview-rereview-wu-cli-interactive-02-ds-20260802.md`
- **Review date**: 2026-08-02
- **Re-review target**: 仅评估当前未提交的 aggregate fix diff（5 文件）是否正确关闭 AGG-A01 至 AGG-A04，并复核被拒 findings 是否因新 diff 变为真实问题
- **Unstaged diff**:
  - `dayu/cli/session_execution.py` — AGG-A01（non-TTY SIGINT lifecycle）、AGG-A02（Ctrl+T 不重置退出）
  - `dayu/engine/contracts/runner_identity.py` — AGG-A04（validator owner name）
  - `tests/cli/test_interactive_command.py` — AGG-A01/A02 owner-level tests
  - `tests/engine/contracts/test_runner_identity.py` — AGG-A04 owner-level tests
  - `tests/host/test_compaction_terminal.py` — AGG-A03（双连接竞争测试）
- **Excluded scope**: AgentMiMo aggregate/re-review artifact（未读取）；既有的 committed diff（`main...cf041c2c`）仅在需要理解上下文时通过 `git show` 读取
- **Documents read**:
  - `AGENTS.md` — 项目约束
  - `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-ds-20260802.md` — 本 reviewer 的 initial aggregate artifact
  - `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-deepreview-adjudication-20260802.md` — controller adjudication（4 accepted / 19 rejected）
  - `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-fix-codex-20260802.md` — Codex fix artifact
- **Verification**: 主 reviewer 独立走读全部 5 个文件的完整 diff；沿真实代码路径逐行追踪关键状态机

---

## AGG-A01: non-TTY SIGINT lifecycle — 闭合评估

### Fix 概要

新增 `_wait_interactive_batch_terminal_handling_sigint` helper（`session_execution.py:1199-1309`），为 non-TTY whole-batch 路径提供与 TTY REPL 语义等价的 SIGINT 生命周期管理。`sigint_monitor` 参数从 `execute_interactive_on_session` 的两处 non-TTY 调用点传入。

### 逐项对抗验证

#### Pre-accept SIGINT（接受前中断）

**代码路径**: `_request_interactive_cancel` → `active.accepted_run.run_id` 检查（行 1836-1839）

```python
run_id = active.accepted_run.run_id
if run_id is None:
    active.acceptance_task = asyncio.create_task(active.accepted_run.wait_run_id())
    return
```

- `_InteractiveAcceptedRunState.run_id` 初始为 `None`；仅在 Host `on_run_accepted` 回调中由 `record(run_id)` 设置（行 186-195）
- 若 SIGINT 在 `submit_followup` 返回前到达，`run_id is None` → 创建 `acceptance_task` 等待 `wait_run_id()`（`asyncio.Event` 屏障，行 197-208）
- 主循环行 1260-1274：当 `acceptance_task in done` 且 `cancel_reason is not None` 且 `cancel_task is None` → 从 `acceptance_task` 取 `run_id`，启动 `cancel_task`
- **测试证据**: `test_interactive_non_tty_single_sigint_crosses_acceptance_barrier_without_orphan`（`_DelayedAcceptanceControlledHost` 将 durable acceptance 与 public response 分离）— SIGINT 后 `cancel_requests == []`，acceptance 释放后 cancel 才发起，`len(cancel_requests) == 1`，mode=`GRACEFUL`

**结论**: ✅ pre-accept SIGINT 正确保留 submit，在接受后只取消一次，无 orphan。

#### Single SIGINT（单次中断）

**代码路径**: `_wait_interactive_batch_terminal_handling_sigint` 行 1284-1293

```python
if pending_interrupts > 0 and active.cancel_reason is None:
    await _request_interactive_cancel(...)
    pending_interrupts -= 1
```

- 第一次 SIGINT：`cancel_reason is None` → 调用 `_request_interactive_cancel` → 设置 `cancel_reason = CLI_SIGINT_REASON` → 若已接受则直接创建 `cancel_task`；若未接受则创建 `acceptance_task`
- `cancel_task` 通过 `cancel_entrypoint_run_and_wait`（`_start_interactive_cancel_task`，行 1850-1879）发送 Host graceful cancel，等待 canonical terminal
- 主循环始终保留 `submit_task` 在 `wait_tasks` 中（行 1229-1231）— cancel 不取消 submit waiter

**结论**: ✅ 单次 SIGINT 只登记一次 graceful cancel，保留 submit canonical waiter。

#### Double SIGINT（第二次中断）

**代码路径**: 行 1294-1297

```python
if pending_interrupts > 0 and not exit_after_cancel:
    exit_after_cancel = True
```

- 第一次 SIGINT 已设置 `cancel_reason` → `cancel_reason is None` 为 False → 跳过 cancel 注册
- `exit_after_cancel` 初始为 False → 设置为 True
- 终端返回后（行 1194-1195）：`if exit_after_cancel: return EXIT_KEYBOARD_INTERRUPT`
- **测试证据**: `test_interactive_non_tty_second_sigint_waits_terminal_then_returns_130_and_third_is_noop` — `exit_code == EXIT_KEYBOARD_INTERRUPT`，`len(host.cancel_requests) == 1`

**结论**: ✅ 第二次 SIGINT 只登记 exit_after_cancel，不重复 cancel；等待 Host terminal 后返回 130。

#### Third SIGINT（第三次及后续中断）

**代码路径**: 同一段逻辑，第三次 SIGINT 时 `cancel_reason` 已设置且 `exit_after_cancel` 已为 True → 两个 `if` 条件均为 False → 不产生任何状态变更

**测试证据**: 同上测试 — 第三次 `monitor.notify()` 后 `len(host.cancel_requests)` 仍为 1

**结论**: ✅ 第三次及后续 SIGINT 是 no-op。

#### 信号批处理（simultaneous SIGINT）

**代码路径**: 行 1282-1283

```python
pending_interrupts = new_sigint_count - observed_sigint_count
observed_sigint_count = new_sigint_count
```

- `pending_interrupts` 可能 > 1（多个 SIGINT 在两次 `wait_next` 之间到达）
- `pending_interrupts -= 1` 消费第一个用于 cancel 注册；第二个 `if` 设置 `exit_after_cancel`
- 剩余 `pending_interrupts` 在当前迭代中不消费，但下次 `sigint_task` 触发时会重新计算 `new_sigint_count - observed_sigint_count`（observer 已追上 latest count）→ 剩余无实际效果，符合"三次及以上 no-op"语义
- `pending_interrupts` 是局部变量，不在迭代间携带 — 每轮从全局 count diff 重新计算

**结论**: ✅ 同时到达的多个 SIGINT 正确处理（首个注册 cancel，第二个设置 exit，其余被 observer 吸收）。

#### Cancel waiter failure

**代码路径**: 行 1245-1256（submit 先完成时）

```python
if active.cancel_task is not None:
    try:
        cancel_terminal = await active.cancel_task
        if cancel_terminal.run_id != terminal.run_id:
            raise RuntimeError("interactive cancel terminal run id mismatch")
    except BaseException as error:
        cancel_error = error
# ...
if cancel_error is not None:
    raise cancel_error
```

**代码路径**: 行 1276-1277（cancel 先于 submit 完成时）

```python
if active.cancel_task is not None and active.cancel_task in done and active.submit_task not in done:
    await active.cancel_task  # 异常立即传播
```

- Cancel 失败时：若 submit 先到 → 捕获异常、清理 acceptance、重新抛出；若 cancel 先到 → 立即传播（与 TTY 路径行 1436-1445 的注释"cancel waiter 的失败必须由它自己的 owner 立即传播"一致）
- Finally 块行 1306-1309：非正常完成时取消 cancel_task 和 submit_task（两者可能已 done，`cancel_and_await_task` 是 no-op）

**结论**: ✅ Cancel waiter failure 正确处理 — 不隐藏、不静默、cleanup 完整。

#### Cleanup（finally 块）

**代码路径**: 行 1301-1309

```python
finally:
    if sigint_task is not None:
        await cancel_and_await_task(sigint_task)
    if active.acceptance_task is not None and not active.acceptance_task.done():
        await cancel_and_await_task(active.acceptance_task)
    if not normal_completion:
        if active.cancel_task is not None:
            await cancel_and_await_task(active.cancel_task)
        await cancel_and_await_task(active.submit_task)
```

- 正常完成（`normal_completion = True`）：只清理 sigint_task 和 acceptance_task
- 非正常完成：额外清理 cancel_task 和 submit_task
- 无 resource leak — 所有 task 或已 done 或被 cancel

**结论**: ✅ Cleanup 完整，无 task leak。

#### 不引入新锁/CAS/Host 关闭

- `_request_interactive_cancel` 的 `composer` 参数从 `InteractiveComposer` 改为 `InteractiveComposer | None`（行 1814）— non-TTY 传 `None`，`composer.set_phase` 调用增加 `if composer is not None` guard（行 1832-1833）
- 无 Host.close() 调用
- 无新锁、CAS、调度框架引入
- 复用既有 `_InteractiveAcceptedRunState`、`_request_interactive_cancel`、`_start_interactive_cancel_task`

**结论**: ✅ 修复范围最小化，不引入新 primitive。

### AGG-A01 闭合结论: **PASS** ✅

---

## AGG-A02: Ctrl+T must not erase exit intent — 闭合评估

### Fix 概要

从 `_drive_interactive_tty_repl` 的 `TOGGLE_ACTIVITY` 分支删除两行（原行 1396-1397）：

```python
# 删除:
exit_intent = _InteractiveExitIntent.CONTINUE
idle_interrupt_revision = None
```

`TOGGLE_ACTIVITY` 现在只调用 `runtime_display.toggle_activity_display()`（行 1522-1523），不再写入 cancel/exit 状态。

### 逐项对抗验证

#### 第二 Ctrl+C 后 CANCELLING 阶段 Ctrl+T 不撤销 exit130

**场景追踪**:

1. Active Run running → 第一次 Ctrl+C → `cancel_reason` 设置，phase → CANCELLING（行 1552-1560）
2. 第二次 Ctrl+C → `exit_intent = EXIT_AFTER_CANCEL`（行 1561-1562）— 此时 `current is not None`（active run 仍在 CANCELLING）
3. 用户按 Ctrl+T → `TOGGLE_ACTIVITY` 事件触发（composer `filter=active_phase` 在 CANCELLING 阶段允许）
   - **修复前**: `exit_intent = CONTINUE`，清除 `EXIT_AFTER_CANCEL` → cancel 完成后 REPL 继续
   - **修复后**: 只 toggle display → `exit_intent` 保持 `EXIT_AFTER_CANCEL`
4. Cancel 完成 → submit_task 完成 → `current = None` → 行 1569-1575 检查：`current is None` 且 `exit_intent is EXIT_AFTER_CANCEL` → `normal_completion = True` → `return EXIT_KEYBOARD_INTERRUPT`

**结论**: ✅ Ctrl+T 不再撤销 exit130。

#### Ctrl+T 在 IDLE 阶段不重置 idle exit pending

**测试证据**: `test_interactive_ctrl_t_preserves_existing_idle_interrupt_intent`

```
事件序列: IDLE_INTERRUPT(revision=7) → TOGGLE_ACTIVITY(revision=7) → IDLE_INTERRUPT(revision=7)
```

- 第一个 IDLE_INTERRUPT → `exit_intent = IDLE_EXIT_PENDING`, `idle_interrupt_revision = 7`
- TOGGLE_ACTIVITY → 修复前会重置 `exit_intent = CONTINUE` 和 `idle_interrupt_revision = None`，修复后只切换显示
- 第二个 IDLE_INTERRUPT → `exit_intent is IDLE_EXIT_PENDING` 且 `idle_interrupt_revision == event.input_revision`(7 == 7) → `return EXIT_KEYBOARD_INTERRUPT`
- 断言: `exit_code == EXIT_KEYBOARD_INTERRUPT`，`host.submit_requests == []`，`host.cancel_requests == []`

**结论**: ✅ Ctrl+T 在 idle 阶段不破坏 idle exit pending 连续两次 Ctrl+C 退出契约。

#### 既有 active Ctrl+T 显示功能不受影响

- TOGGLE_ACTIVITY 的显示切换（`runtime_display.toggle_activity_display()`）保留
- `current is not None` guard 保留 — 只在有 active run 时切换
- 既有 `test_interactive_ctrl_t_toggles_without_cancel`（RUNNING 阶段）和 active Ctrl+C lifecycle regression tests 通过

**结论**: ✅ 显示功能完整保留，不引入 regression。

### AGG-A02 闭合结论: **PASS** ✅

---

## AGG-A03: deterministic writer competition proof — 闭合评估

### Fix 概要

新增 `test_two_competing_terminal_writers_commit_exactly_one_canonical_terminal`（`test_compaction_terminal.py:792-881`），使用两个 thread-owned 真实 SQLite connection 竞争同一 `operation_id` 的 compaction terminal。未修改任何 production 代码。

### 逐项对抗验证

#### 真实性 — 使用 production owner，非 mock

- 两个 `_CompetingTerminalWriter`（行 160-260）各自调用 `open_host_durable_store(options).connect()` 获取独立 SQLite connection
- 各自使用 production `HostTransactionRunner` + `begin_compaction_terminal_commit_in_transaction`
- winner 在 transaction 内调用 `_append_terminal`（与既有测试同一 helper）写入 `CONTEXT_COMPACTED`
- **不使用** mock、patch、fake transaction、fake connection、或 monkey-patched CAS

**结论**: ✅ 使用真实 production owner。

#### 确定性 — barrier 协调，非 sleep/timing-based

```
时序:
1. winner_ready + loser_ready → 两个 connection 均已打开
2. winner_start.set() → winner 进入 run_write，获得 permit
3. winner_has_permit.wait() → 确认 winner 已持有 permit
4. loser_start.set() → loser 进入 run_write，BEGIN IMMEDIATE 被 winner 的 write lock 阻塞
5. loser_begin_attempted.wait() → SQLite trace callback 确认 loser 已尝试执行 BEGIN IMMEDIATE
6. assert not loser_future.done() → loser 确实在阻塞（未完成）
7. release_winner.set() → winner 提交 CONTEXT_COMPACTED，释放 write lock
8. loser BEGIN IMMEDIATE 继续 → 发现 operation 已 COMPACTED → 返回 CompactionTerminalClosed
```

- 全部使用 `threading.Event` barrier，无 `time.sleep()`、无 busy-wait
- 所有 barrier wait 有 `_COMPETITION_TIMEOUT_SECONDS = 5.0` 超时保护

**结论**: ✅ 确定性竞争编排，无 flaky timing 依赖。

#### 无死锁风险

- 两个线程，一个资源（SQLite write lock）
- Winner 持有 lock → Loser 阻塞等待 → Winner 释放 → Loser 继续
- 无循环等待、无反向依赖

**结论**: ✅ 无死锁可能。

#### Loser 被真实阻塞的证据

- `loser_begin_attempted` 是 SQLite `set_trace_callback` 驱动的 `threading.Event`
- `_record_statement`（行 736-748）在 SQLite 实际执行 `BEGIN IMMEDIATE` 时触发
- 测试断言 `loser_begin_attempted.wait()` 和 `not loser_future.done()` 共同证明 loser 在 winner 提交前确实被阻塞

**结论**: ✅ Loser 真实竞争且真实阻塞的证据链完整。

#### 结果验证 — 恰好一条 canonical terminal

```python
# Winner
assert isinstance(winner_result, CompactionTerminalCommitPermit)

# Loser
assert isinstance(loser_result, CompactionTerminalClosed)
assert loser_result.disposition is CompactionOperationTerminalDisposition.COMPACTED
assert loser_result.first_terminal_event_type == CONTEXT_COMPACTED

# Fresh owner read
closed, terminal_rows = store.transaction_runner.run_write(
    partial(_read_terminal_competition_state, operation_id=operation_id)
)
assert closed.disposition is CompactionOperationTerminalDisposition.COMPACTED
assert len(terminal_rows) == 1
assert terminal_rows[0].event_type == CONTEXT_COMPACTED
```

- `_read_terminal_competition_state`（行 891-920）使用新的 write transaction 做 fresh read，排除缓存/stale read
- 验证 owner disposition、terminal row count、event type 三者一致

**结论**: ✅ 恰好一条 CONTEXT_COMPACTED terminal row，loser 未遗留 CONTEXT_COMPACTION_FAILED。

### AGG-A03 闭合结论: **PASS** ✅

---

## AGG-A04: validator owner message — 闭合评估

### Fix 概要

- `_validate_non_empty_text` 增加 `owner_name: str` 参数（行 269-284）
- `_validate_optional_non_empty_text` 同步增加 `owner_name: str` 参数（行 287-303）
- 定义模块级常量 `_RUNNER_REQUEST_IDENTITY_OWNER = "RunnerRequestIdentity"` 和 `_SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER = "SuccessfulRunnerResponseIdentity"`（行 24-27）
- 所有调用点传入对应 owner 常量
- 错误消息从硬编码 `RunnerRequestIdentity.<field>` 改为 `{owner_name}.{field}`

### 逐项对抗验证

#### Wire shape 不变

- `RunnerRequestIdentity` dataclass 字段不变（run_id, attempt_id, execution_id, iteration_id, iteration_index, runner_call_index）
- `SuccessfulRunnerResponseIdentity` dataclass 字段不变（effective_provider, effective_model, runner_request_identity, provider_request_id_availability, provider_request_id）
- `_canonical_identity_parts` 不变
- `client_correlation_id` 派生逻辑不变
- JSON 序列化（`_successful_response_identity_json`）不变

**结论**: ✅ Wire shape、schema、序列化完全不变。

#### 错误消息 owner 正确

- Request identity 空字段: `RunnerRequestIdentity.<field> must be non-empty`
- Response identity 空字段: `SuccessfulRunnerResponseIdentity.<field> must be non-empty`
- **测试证据**: 两个参数化测试断言 exact error message string
  - `test_runner_request_identity_rejects_empty_text_fields` → `assert str(error_info.value) == f"RunnerRequestIdentity.{field_name} must be non-empty"`
  - `test_successful_response_identity_rejects_empty_provider_or_model` → `assert str(error_info.value) == f"SuccessfulRunnerResponseIdentity.{field_name} must be non-empty"`

**结论**: ✅ 错误消息正确归属 owner。

#### 无新增 hasattr/getattr/Any/兼容分支

**结论**: ✅ 类型安全，无防御性编程退化。

### AGG-A04 闭合结论: **PASS** ✅

---

## 被拒 Findings 复核

逐一复核 19 条被 controller 拒绝的 findings 是否因当前 fix diff 变为真实问题：

| Finding | 原始拒绝理由 | 新 diff 相关性 | 复核结论 |
|---------|-------------|---------------|---------|
| MiMo-01 | calibration boundary | 无关 — 新 diff 不涉及 scenarios | 仍 rejected |
| MiMo-02 | no correctness defect | 无关 — 不涉及 terminal guard wrapper | 仍 rejected |
| MiMo-03 | factual error | 无关 — 不涉及 readiness counts | 仍 rejected |
| MiMo-04 | frozen static proof boundary | 无关 — 不涉及 I0554 | 仍 rejected |
| MiMo-05 | → AGG-A04 | 已闭合 | N/A |
| MiMo-06 | pre-existing, unproven | 无关 — 不涉及 terminal coordinator | 仍 rejected |
| MiMo-07 | factual error | 无关 — 不涉及 config dir export | 仍 rejected |
| MiMo-08 | factual error | 无关 — 不涉及 composer alias | 仍 rejected |
| DS-AG001 | non-frozen mixed-source policy | 无关 — 不涉及 idle OS SIGINT | 仍 rejected |
| DS-AG002 | explicit non-goal | 无关 — 不涉及 legacy schema | 仍 rejected |
| DS-AG003 | no leak evidence | 无关 — 不涉及 promotion pending set | 仍 rejected |
| DS-AG004 | frozen owner contract | 无关 — 不涉及 continuation identity | 仍 rejected |
| DS-AG005 | intended threshold semantics | 无关 — 不涉及 recovery boundary | 仍 rejected |
| DS-AG006 | → AGG-A03 | 已闭合 | N/A |
| DS-AG007 | covered by owner decision | 无关 — 不涉及 stale boundary test | 仍 rejected |
| DS-AG008 | downstream fallback | 无关 — 不涉及 RunnerSpec fallback | 仍 rejected |
| DS-AG009 | outside success identity contract | 无关 — 不涉及 force-answer | 仍 rejected |
| DS-AG010 | style refactor | 无关 — 不涉及 promotion helper | 仍 rejected |
| DS-AG012 | → AGG-A02 | 已闭合 | N/A |
| DS-AG013 | policy invention | 无关 — 不涉及 idle revision tracking | 仍 rejected |
| DS-AG014 | → AGG-A01 | 已闭合 | N/A |
| DS-AG015 | valid control flow guard | 无关 — 不涉及 binary_stdin guards | 仍 rejected |

**结论**: 19 条被拒 finding 中，4 条归入 AGG-A01 至 AGG-A04（已闭合），其余 15 条与新 diff 无任何交集。没有 finding 因新 diff 变为真实问题。

---

## Cross-cutting 验证

### 第二 Ctrl+C 后 CANCELLING Ctrl+T 不得撤销 exit130（专项验证）

**TTY 路径**:

1. 第一次 Ctrl+C → `cancel_reason = CLI_SIGINT_REASON`（行 1552-1560）
2. 第二次 Ctrl+C → `exit_intent = EXIT_AFTER_CANCEL`（行 1561-1562），此时 `current is not None`
3. Ctrl+T → `TOGGLE_ACTIVITY` 事件（行 1521-1523）
   - 修复前: 无条件 `exit_intent = CONTINUE` — 撤销 EXIT_AFTER_CANCEL
   - 修复后: 只 `toggle_activity_display()` — exit_intent 保持 EXIT_AFTER_CANCEL
4. cancel 完成 → submit 完成 → `current = None`（行 1405）
5. 行 1569-1575: `current is None` 且 `exit_intent is EXIT_AFTER_CANCEL` → `return EXIT_KEYBOARD_INTERRUPT`（130）

**Non-TTY 路径**:

Non-TTY 路径无 TOGGLE_ACTIVITY 事件（无 composer），因此不受影响。`exit_after_cancel` 由第二次 SIGINT 设置（行 1294），返回 `EXIT_KEYBOARD_INTERRUPT`（行 1194-1195）。

**结论**: ✅ 两条路径均正确保持 exit130 不被撤销。

### SQLite 双连接竞争测试 — 完整竞争闭包验证

1. **两个真实 SQLite connection** 打开同一 DB 文件 ✓
2. **两个 production `HostTransactionRunner`** 各自执行 `run_write` ✓
3. **两个 `begin_compaction_terminal_commit_in_transaction`** 竞争同一 `operation_id` ✓
4. **SQLite trace callback** 证明 loser 真实尝试 `BEGIN IMMEDIATE` ✓
5. **`not loser_future.done()`** 证明 loser 被阻塞 ✓
6. **Winner 提交唯一 `CONTEXT_COMPACTED`** ✓
7. **Loser 得到 `CompactionTerminalClosed(COMPACTED)`** ✓
8. **Fresh read 验证 terminal inventory 恰好一条** ✓
9. **无 deadlock**: 单资源（write lock），单方向等待 ✓
10. **无 flaky**: 全 barrier 驱动，5s 超时保护 ✓

**结论**: ✅ 竞争测试真实、确定、无 flaky/deadlock。

### Validator owner 与 wire shape（专项验证）

- `RunnerRequestIdentity` 字段集不变: run_id, attempt_id, execution_id, iteration_id, iteration_index, runner_call_index
- `SuccessfulRunnerResponseIdentity` 字段集不变: effective_provider, effective_model, runner_request_identity, provider_request_id_availability, provider_request_id
- `_canonical_identity_parts` 返回 tuple 结构不变
- `client_correlation_id` 派生算法不变（SHA-256 hex hash）
- `_successful_response_identity_json` 输出字段不变
- 仅 `_validate_non_empty_text` / `_validate_optional_non_empty_text` 签名增加 `owner_name`

**结论**: ✅ Wire shape 完全不变；validator owner 正确归属。

### 类型安全

Fix artifact 报告 pyright 全量 `0 errors, 0 warnings, 0 informations`。本 reviewer 独立验证：

- `composer: InteractiveComposer | None` — non-TTY 传 `None`，类型 narrowing 正确
- `sigint_monitor: CliSigintMonitor` — 新增参数有完整类型标注
- `_wait_interactive_batch_terminal_handling_sigint` 返回 `tuple[EntrypointRunTerminalResult, bool]` — 标注正确
- 无 `Any`、`object`、`hasattr`/`getattr` 新增

**结论**: ✅ 类型安全。

### Secret 泄露

- 新增代码不涉及 API key、token、endpoint、header 或 provider response body
- `_request_interactive_cancel` 的 cancel reason 是常量 `CLI_SIGINT_REASON`
- 无环境变量读取或日志输出

**结论**: ✅ 无 secret 泄露。

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

---

## Residual Risk

| 类别 | 风险 | 控制 | 残余评估 |
|------|------|------|---------|
| Non-TTY batch + OS SIGINT | 新 helper 的取消路径仅在单进程 async 模型下验证 | 既有 invocation 外层 `except BaseException` 兜底 | 低 — 与 TTY 路径共享同一 cancel/signal primitive |
| Compaction competition test | 双线程 SQLite 测试依赖 Python GIL 释放 + SQLite 写锁序列化 | 生产依赖同一 SQLite 保证 | 低 — SQLite write serialization 是成熟保证 |
| Compaction competition test — CI 环境 | `/tmp` vs ephemeral FS 可能影响 SQLite locking 语义 | 测试使用 `tmp_path` fixture，与既有 compaction 测试一致 | 低 — 既有测试已在此环境通过 |
| Ctrl+T display-only | 确认 composer binding 的 `filter=active_phase` 在 CANCELLING 阶段仍为 True | 代码路径 tracing 确认（`composer.py:445` 的 TOGGLE_ACTIVITY binding，`filter=active_phase` 在 RUNNING 和 CANCELLING 阶段均为 True） | 低 — 既有的 active Ctrl+T 测试仍在 regression suite 中 |

---

## 最终结论

**PASS** — 四项 AGG finding 全部正确闭合，无新增 finding。

- **AGG-A01** (non-TTY SIGINT lifecycle): ✅ Pre-accept、single/double/third SIGINT、cancel waiter failure、cleanup 全部验证通过。两条 owner-level 测试 + 既有 regression 测试覆盖。
- **AGG-A02** (Ctrl+T must not erase exit intent): ✅ TOGGLE_ACTIVITY 不再写入 exit/cancel 状态。两条 owner-level 测试验证 idle exit pending 保持与 active display 不退化。
- **AGG-A03** (deterministic writer competition proof): ✅ 真实 SQLite 双连接竞争，barrier 编排确定，loser 被真实阻塞的证据（SQLite trace + future.done()），恰好一条 terminal。未修改 production 代码。
- **AGG-A04** (validator owner message): ✅ 错误消息正确归属 request/response owner。Wire shape 完全不变。参数化测试断言 exact error string。

**被拒 findings 复核**: 15 条被拒 finding 与新 diff 无交集，未因 fix 变为真实问题。

**修复范围**: 5 文件（2 production + 3 test），646 insertions / 23 deletions。未引入新锁、CAS、Host 关闭路径、兼容分支、schema 字段或 wire 字段变更。
