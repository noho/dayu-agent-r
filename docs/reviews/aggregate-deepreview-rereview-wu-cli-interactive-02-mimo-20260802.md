# Aggregate Deep Review Re-Review: wu-cli-interactive-02

## Scope

- Mode: current changes (re-review)
- Branch: `codex/interactive-oracle`
- Base: `main`
- Output file: `docs/reviews/aggregate-deepreview-rereview-wu-cli-interactive-02-mimo-20260802.md`
- Included scope: AGG-A01–A04 fix diff + controller adjudication closure verification
- Excluded scope: AgentDS aggregate/re-review artifact（按用户要求不读取）
- Parallel review coverage: 无（独立 re-review，聚焦四项 closure）

## 门控历史

本 re-review 覆盖：

1. `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-mimo-20260802.md`（initial aggregate artifact）
2. `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-deepreview-adjudication-20260802.md`（controller adjudication）
3. `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-fix-codex-20260802.md`（Codex fix artifact）
4. `main...HEAD` 生产/测试 diff（5 files changed, +646/-23）

## Overall Verdict

**PASS** — 四项 accepted finding 均由当前 diff 正确关闭。19 项 rejected findings 无一因新 diff 变为真实问题。

---

## AGG-A01: non-TTY SIGINT lifecycle — PASS

### Closure evidence

**入口**: `execute_interactive_on_session` → `_run_interactive_non_tty_batch` → `_wait_interactive_batch_terminal_handling_sigint`

**修复路径**:

1. `sigint_monitor.install()` 在 `execute_interactive_on_session` 中调用（`session_execution.py` L472），invocation 级唯一安装点。
2. `sigint_monitor` 作为显式参数传入 `_run_interactive_non_tty_batch`（L507），再传入 `_wait_interactive_batch_terminal_handling_sigint`（L1173）。
3. `_wait_interactive_batch_terminal_handling_sigint` 创建 `sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))`（L1218），并在 `asyncio.wait` 中与 `active.submit_task`、`active.acceptance_task`、`active.cancel_task` 一起等待。

**Pre-accept SIGINT**:

```python
# L1278-1280
if pending_interrupts > 0 and active.cancel_reason is None:
    await _request_interactive_cancel(...)
    pending_interrupts -= 1
```

`_request_interactive_cancel` 检查 `active.accepted_run.run_id is None`（L1415），此时创建 `active.acceptance_task = asyncio.create_task(active.accepted_run.wait_run_id())`（L1416），保留 submit waiter，等待 acceptance 后再启动 cancel waiter。不取消 submit_task。

**Single SIGINT after acceptance**:

`cancel_reason` 首次设置（`_request_interactive_cancel` L1412），`cancel_task` 由 `_start_interactive_cancel_task` 创建（L1420）。Host canonical cancel waiter 被保留到 submit terminal。

**Double SIGINT → exit_after_cancel**:

```python
# L1281-1283
if pending_interrupts > 0 and not exit_after_cancel:
    exit_after_cancel = True
```

第二次 SIGINT 只登记 `exit_after_cancel = True`，不重复发送 cancel。退出时返回 `EXIT_KEYBOARD_INTERRUPT`（L1296）。

**Third+ SIGINT → absorbed**:

`active.cancel_reason is not None` → 首次 SIGINT 分支被跳过；`exit_after_cancel is True` → 第二次 SIGINT 分支被跳过。信号被静默吸收。

**Cleanup**:

`finally` 块（L1297-1303）取消 `sigint_task`、`acceptance_task`、`cancel_task`、`submit_task`。`execute_interactive_on_session` 的外层 `try/finally`（L576-590）关闭 `sigint_monitor`、`runtime_display` 和 `attachment`。

**验证**: `test_interactive_non_tty_single_sigint_crosses_acceptance_barrier_without_orphan`、`test_interactive_non_tty_second_sigint_waits_terminal_then_returns_130_and_third_is_noop` 均通过。affected regression suite 185 passed。

---

## AGG-A02: Ctrl+T must not erase exit intent — PASS

### Closure evidence

**入口**: `_drive_interactive_tty_repl` → composer event dispatch

**修复路径**:

```python
# session_execution.py L1578-1579
elif event.kind is InteractiveComposerEventKind.TOGGLE_ACTIVITY:
    if current is not None and runtime_display is not None:
        await runtime_display.toggle_activity_display()
```

`TOGGLE_ACTIVITY` 分支**只**调用 `toggle_activity_display()`。不写入 `exit_intent`、不写入 `idle_interrupt_revision`、不写入 `cancel_reason`。

**Second Ctrl+C after CANCELLING Ctrl+T 不得撤销 exit130**:

时序分析：
1. 第一次 Ctrl+C → `CANCEL_ACTIVE` event → `_request_interactive_cancel` → `cancel_reason` 设置 → composer phase 设为 `CANCELLING`
2. CANCELLING phase 中 Ctrl+T → `TOGGLE_ACTIVITY` event → 只 toggle display → `exit_intent` 不变
3. 第二次 Ctrl+C → `CANCEL_ACTIVE` event → `cancel_reason is not None` → `exit_intent = EXIT_AFTER_CANCEL`
4. `exit_intent` 从未被 `TOGGLE_ACTIVITY` 重置为 `CONTINUE`

**idle Interrupt path 同样安全**:

```python
# L1581-1588
elif event.kind is InteractiveComposerEventKind.IDLE_INTERRUPT:
    if current is None:
        if (
            exit_intent is _InteractiveExitIntent.IDLE_EXIT_PENDING
            and idle_interrupt_revision == event.input_revision
        ):
            normal_completion = True
            return EXIT_KEYBOARD_INTERRUPT
```

`IDLE_INTERRUPT` 只检查 `input_revision` 相同才退出；`TOGGLE_ACTIVITY` 不修改 `idle_interrupt_revision`，因此中间插入的 Ctrl+T 不会干扰 idle exit。

**验证**: `test_interactive_ctrl_t_preserves_existing_idle_interrupt_intent` 发送 IDLE_INTERRUPT → TOGGLE_ACTIVITY → IDLE_INTERRUPT（同 `input_revision=7`），断言 `exit_code == EXIT_KEYBOARD_INTERRUPT`。`test_interactive_ctrl_t_toggles_without_cancel` 在 active phase 发送 TOGGLE_ACTIVITY，断言无 submit/cancel。

---

## AGG-A03: deterministic writer competition proof — PASS

### Closure evidence

**入口**: `test_two_competing_terminal_writers_commit_exactly_one_canonical_terminal`

**竞争证明**:

1. **两个独立真实 SQLite connection**: `_CompetingTerminalWriter.__call__` 中每个 writer 调用 `open_host_durable_store(self.options)` → `store.connect()`，获得独立 `sqlite3.Connection`（`test_compaction_terminal.py` L200-204）。
2. **共用同一 DB**: 两个 writer 使用相同 `HostDurableStoreOptions`（同一 `tmp_path` 下的 DB 文件）。
3. **production owner**: `_commit_terminal` 调用 `begin_compaction_terminal_commit_in_transaction`（L232），使用 production `HostTransactionRunner.run_write`（L208）。
4. **确定性 barrier 排序**:
   - `winner_ready` / `loser_ready`: 两个 writer 各自完成 connection + runner 准备
   - `winner_start.set()`: winner 先获得执行许可
   - `winner_has_permit.wait()`: 等待 winner 取得 permit（即 winner 已执行 `BEGIN IMMEDIATE` 并获得写锁）
   - `loser_start.set()`: loser 开始执行（此时 loser 的 `BEGIN IMMEDIATE` 必然被 SQLite 写锁阻塞）
   - `loser_begin_attempted.wait()`: 确认 loser 已尝试 `BEGIN IMMEDIATE`（通过 SQLite trace callback `set_trace_callback`，L203）
   - 确认 `not loser_future.done()`: loser 仍阻塞在 `BEGIN IMMEDIATE`
   - `release_winner.set()`: winner 释放 permit，提交 terminal

5. **单 terminal 证明**:
   ```python
   # L408
   assert len(terminal_rows) == 1
   assert terminal_rows[0].event_type == CONTEXT_COMPACTED
   ```

**无 flaky/deadlock 风险**:

- SQLite `BEGIN IMMEDIATE` 在写锁已被持有时阻塞，不抛异常。winner 持有写锁期间，loser 必然阻塞。
- `begin_attempted` barrier 通过 `set_trace_callback` 捕获实际 SQL 语句，不是轮询。
- `_COMPETITION_TIMEOUT_SECONDS = 5.0`，对单次 `BEGIN IMMEDIATE` 阻塞足够。
- loser 不设 `release_permit`（`release_permit=None`），因此 `begin_compaction_terminal_commit_in_transaction` 返回 permit 后直接 append terminal，无额外阻塞。

---

## AGG-A04: validation owner message — PASS

### Closure evidence

**入口**: `dayu/engine/contracts/runner_identity.py` → `_validate_non_empty_text`

**修复前**:

```python
# 旧代码
raise ValueError(f"RunnerRequestIdentity.{field_name} must be non-empty")
```

硬编码 `RunnerRequestIdentity`，但该函数同时被 `SuccessfulRunnerResponseIdentity.__post_init__` 调用。

**修复后**:

```python
# L269-284
def _validate_non_empty_text(
    owner_name: str,
    field_name: str,
    value: str,
) -> None:
    if value.strip() == "":
        raise ValueError(f"{owner_name}.{field_name} must be non-empty")
```

调用点：

- `RunnerRequestIdentity.__post_init__` → `_validate_identity_inputs` → `_validate_non_empty_text(_RUNNER_REQUEST_IDENTITY_OWNER, ...)`（L238-241）
- `SuccessfulRunnerResponseIdentity.__post_init__` → `_validate_non_empty_text(_SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER, ...)`（L123-131）

owner 名称模块级常量：

```python
# L24-27
_RUNNER_REQUEST_IDENTITY_OWNER: str = "RunnerRequestIdentity"
_SUCCESSFUL_RUNNER_RESPONSE_IDENTITY_OWNER: str = "SuccessfulRunnerResponseIdentity"
```

**Wire shape 不变**: `_validate_non_empty_text` 只改错误消息格式，不改 dataclass 字段、构造参数或序列化行为。

**验证**:

- `test_runner_request_identity_rejects_empty_text_fields` 断言 `str(error_info.value) == f"RunnerRequestIdentity.{field_name} must be non-empty"`（L104-106）
- `test_successful_response_identity_rejects_empty_provider_or_model` 断言 `str(error_info.value) == f"SuccessfulRunnerResponseIdentity.{field_name} must be non-empty"`（L246-248）
- 既有 `test_successful_response_identity_present_and_unavailable_are_strict` 断言 `{field.name for field in dataclasses.fields(present)}` 精确匹配 5 个字段（L176-182），确认 wire shape 未被修改

---

## Rejected Findings Re-Review

逐项检查 19 项 rejected findings 是否因新 diff 变为真实问题：

| Finding | Re-review verdict | 证据 |
|---|---|---|
| MiMo-01 interactive oracle 无 scenarios | **仍为 rejected** | 新 diff 不涉及 oracles.json 或 scenarios.json。G01-G07 calibration boundary 不变。 |
| MiMo-02 terminal guard fail-closed 散落 | **仍为 rejected** | 新 diff 不修改 `compaction_terminal.py` 或 `dispatch.py`。 |
| MiMo-03 readiness counts None | **仍为 rejected** | 新 diff 不涉及 cli_ci_scenarios.json。 |
| MiMo-04 I0554 refs missing | **仍为 rejected** | 新 diff 不涉及 oracles.json scenario_refs。 |
| MiMo-06 terminal coordinator close barrier | **仍为 rejected** | 新 diff 不修改 `open_host.py`。 |
| MiMo-07 resolve_explicit_config_dir dead export | **仍为 rejected** | `session.py` 的 `session` 命令仍使用该 helper。新 diff 只从 prompt/interactive 路径移除 `--config`。 |
| MiMo-08 composer result alias dead | **仍为 rejected** | 新 diff 定义 `InteractiveComposerCompletionResult`（L1504）并在 `_drive_interactive_tty_repl` 的 `wait_tasks` 类型标注中使用（L1561）。 |
| DS-AG001 mixed idle/interrupt count | **仍为 rejected** | 新 diff 不新增 mixed-source idle policy。composer 和 OS SIGINT 路径仍分别独立处理。 |
| DS-AG002 legacy compaction schema | **仍为 rejected** | 新 diff 不涉及 compaction schema 兼容。 |
| DS-AG003 pending promotion set not cleared | **仍为 rejected** | 新 diff 不修改 scheduler close 路径。 |
| DS-AG004 continuation only keeps terminal call identity | **仍为 rejected** | 新 diff 不扩展 identity chain schema。 |
| DS-AG005 stale <= to < | **仍为 rejected** | 新 diff 不修改 stale threshold 逻辑。 |
| DS-AG007 no microsecond stale boundary test | **仍为 rejected** | 新 diff 不涉及 stale boundary 测试。 |
| DS-AG008 unreachable invalid RunnerSpec fallback | **仍为 rejected** | 新 diff 不修改 RunnerSpec。 |
| DS-AG009 force-answer empty failure request id | **仍为 rejected** | 新 diff 不修改 force-answer telemetry。 |
| DS-AG010 promotion helper duplication | **仍为 rejected** | 新 diff 不抽象 promotion helper。 |
| DS-AG013 edit then delete should preserve idle pending | **仍为 rejected** | 新 diff 的 idle interrupt 路径使用 `input_revision` 对齐，不引入"实质编辑"判定。 |
| DS-AG015 binary stdin guards dead | **仍为 rejected** | `_resolve_interactive_binary_stdin`（L1278-1295）在 `effective_binary_stdin is None` 时被调用，正是 non-TTY 路径的 assembly guard。不是 dead code。 |
| DS-AG011 no interactive scenarios | **仍为 rejected** | 新 diff 不涉及 scenario registry。 |

---

## Open Questions

无。

## Residual Risk

- G01-G07、formal interactive scenarios 与外部 provider smoke 的可复跑性继续作为已分类的后续 calibration boundary。
- 四项 closure 均为 owner-level proof，不涉及外部 Host 运行、真实 LLM 调用或持久化状态验证。
- 当前没有 deferred finding、未分类 residual risk 或 blocking open question。

## Validation Summary

| Finding | Closure | Owner | Tests |
|---|---|---|---|
| AGG-A01 | ✅ PASS | `session_execution.py` non-TTY SIGINT lifecycle | 2 new tests (pre-accept, double/third) |
| AGG-A02 | ✅ PASS | `session_execution.py` TTY REPL state machine | 2 new tests (idle toggle, active toggle) |
| AGG-A03 | ✅ PASS | `compaction_terminal.py` SQLite `BEGIN IMMEDIATE` competition | 1 new test (two-writer barrier) |
| AGG-A04 | ✅ PASS | `runner_identity.py` validator owner name | 2 new tests (request/response owner message) |

所有 affected tests 通过（185 passed）。pyright 0 errors。ruff 0 violations。无新增 secret 泄露。
