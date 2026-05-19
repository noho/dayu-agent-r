# P10.5 Slice 5 Code Review — AgentDS

## 结论

**PASS — 0 blocking**

5 tests passed，pyright 0 errors/warnings/informations。实现正确性满足 Slice 5 核心目标，但测试覆盖存在 7 个 notable gap（N1-N7），建议 Slice 6 补齐或在 Slice 5 fix round 中补测。无 blocking 级别问题。

---

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_retry_replay.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_cancel_smoke.py -q
# 5 passed in 0.35s

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations
```

---

## Findings（按严重度排序）

### N1 — steer WAITING 路径未测试（notable，建议 fix round 补测）

**证据**：
- `_SubmitFollowupSteerOperation.__call__` 明确分支：
  - `target_run.status == RunStatus.RUNNING` → `steer_running_attempt_row` CAS + `ATTEMPT_STEERED` 事件
  - else（即 `WAITING`）→ `cancel_active_wait_records_for_run` CAS + 无 `ATTEMPT_STEERED` 事件
- `test_steer_running_run_creates_new_attempt_public_path` 只覆盖 RUNNING 分支，WAITING 分支完全未测。
- plan §Slice 5 Tests 明确要求 steer 覆盖 RUNNING / WAITING。

**影响**：WAITING steer CAS、wait record 取消与 Attempt 状态推进的正确性未经测试验证。

**建议**：新增 `test_steer_waiting_run_creates_new_attempt`，构造 WAITING Run，验证 steer 后 wait records 被 cancel、新 Attempt 创建、事件正确。

---

### N2 — steer terminal race 未测试（notable，建议 fix round 补测）

**证据**：
- `_SubmitFollowupSteerOperation` 有两处 CAS 可能因 terminal race 失败：
  1. `steer_running_attempt_row` CAS 失败 → `INVALID_STATE` "Run terminal race won before steer"
  2. `steer_active_run_row` CAS 失败 → `INVALID_STATE` "Run terminal race won before steer"
- plan §Slice 5 Tests 明确要求 "Terminal race tests for steer vs terminal"。
- 当前无任何 terminal race 测试。

**影响**：steer 与 terminal closeout 并发时的 CAS 语义未经测试。

**建议**：新增 `test_steer_loses_terminal_race`，构造 RUNNING Run 同时在另一事务 closeout，验证 steer 返回 `INVALID_STATE`。

---

### N3 — retry 幂等未测试（notable，建议 fix round 补测）

**证据**：
- `_RetryRunOperation` 通过 `_idempotency_scope(operation=_OPERATION_RETRY_RUN, scope_id=self.run_id, idempotency_key=self.request.client_request_id)` 实现 `(source_run_id, client_request_id)` 幂等。
- `test_retry_failed_run_creates_related_run_public_path` 只测试成功路径，不测试重复 `(source_run_id, client_request_id)` 幂等 replay。
- plan §Slice 5 Tests 明确要求 "Retry idempotency conflict and successful related Run dispatch"。

**影响**：幂等逻辑（digest check、幂等 replay 不重复创建 Run）未经测试。

**建议**：新增 `test_retry_idempotent_replay_same_source_and_client_request_id`，两次同一 `(source_run_id, client_request_id)` 调用返回同一新 Run snapshot。

---

### N4 — retry policy limit 未测试（notable，建议 fix round 补测）

**证据**：
- `_RetryRunOperation` 通过 `count_runs_by_source_relation(..., SourceRunRelation.RETRY) >= _MAX_ORDINARY_RETRY_RUNS_PER_SOURCE (1)` 限制每个源 Run 只允许一个 ordinary retry。
- 当前无任何测试触发此 limit 分支。
- plan §Slice 5 明确 retry 需验证 "policy limit"。

**影响**：limit 检查逻辑未经测试，可能 CAS 错误导致 limit 不生效或误触发。

**建议**：新增 `test_retry_policy_limit_reached_for_source_run`，第一次 retry 成功，第二次 retry 返回 `INVALID_STATE`。

---

### N5 — replay 幂等未测试（notable，建议 fix round 补测）

**证据**：
- `_ReplayRunOperation` 与 retry 同模式实现 `(source_run_id, client_request_id)` 幂等。
- `test_replay_succeeded_run_no_tool_public_path` 不测试幂等 replay。

**影响**：replay 幂等逻辑未经测试。

**建议**：新增 `test_replay_idempotent_replay_same_source_and_client_request_id`。

---

### N6 — cancel pre-dispatch 与 session-scope isolation 未覆盖（notable，建议 Slice 6 或 fix round 补测）

**证据**：
- 当前只有 `test_cancel_accepted_queued_and_active_public_path`（1 个 test），覆盖 queued cancel + active cancel via `cancel_session_runs`。
- plan unified coverage table 要求 Slice 5 覆盖：
  - `test_cancel_accepted_and_queued_runs_public_path`
  - `test_pre_dispatch_cancel_visible_in_watch`
  - `test_active_cancel_emits_public_cancel_event`（Slice 5 + Slice 6）
  - `test_cancel_session_runs_scoped_to_session`（Slice 5 + Slice 6）
- pre-dispatch cancel（STARTING Attempt 在 dispatch 前被 cancel）未显式测试。
- session-scope cancel 跨 Session 隔离未测试（同一 opener 两个 Session 的 cancel_session_runs 不应影响另一 Session）。

**影响**：pre-dispatch cancel 路径与 session-scope 隔离未经测试。Slice 6 可分担部分，但 pre-dispatch cancel 是 Slice 5 独有要求。

**建议**：pre-dispatch cancel 建议在 fix round 补测；session-scope isolation 可在 Slice 6 补齐。

---

### N7 — retry/replay 非目标状态 rejection 未测试（low）

**证据**：
- `_require_source_run_for_relation` 对 retry 要求 `RunStatus.FAILED`，对 replay 要求 `RunStatus.SUCCEEDED`，其他状态（包括 `LOST`、`RECOVERING`、`CANCELLED`）返回 `INVALID_STATE`。
- 当前测试只验证成功路径，不验证 SUCCEEDED Run 调用 retry 被拒绝、FAILED Run 调用 replay 被拒绝、LOST/RECOVERING Run 调用 retry 被拒绝。

**影响**：边界错误路径未经测试，但 admission CAS 语义本身健壮——错误状态不会通过 `expected_status` 校验。

**建议**：低优先级，可在 Slice 6 或后续补齐。

---

## 逐点回答 review 重点问题

### 1. submit_followup(steer) 覆盖度

- **RUNNING**：✅ 已实现 + 已测试。`steer_running_attempt_row` CAS → `ATTEMPT_STEERED` → 新 Attempt / dispatch。
- **WAITING**：✅ 已实现、❌ 未测试。`cancel_active_wait_records_for_run` CAS → 新 Attempt / dispatch。见 N1。
- **same Run new Attempt**：✅ `steer_active_run_row` CAS 确保同一 Run，新 `attempt_id` / `execution_id` / `dispatch_record_id`。
- **terminal race durable order**：✅ CAS 链路（Attempt status + Run status + terminal_event_id IS NULL）确保 terminal race 时 steer 失败。❌ 未测试。见 N2。
- **Recovery 越界**：✅ 未越界。`_require_steer_target_run` 只接受 `RUNNING` / `WAITING`，不含 `RECOVERING`。

### 2. FAILED retry 实现

- **source Run immutable**：✅ retry 创建关联新 Run，不修改源 Run 任何字段。
- **associated new Run**：✅ `_create_source_related_admission_result` 创建新 Run 并通过 `set_new_run_source_relation_row` 写入 `(source_run_id, RETRY)`。
- **new Attempt / execution id**：✅ 与普通 `submit_followup(queue)` 同路径生成。
- **idempotency by (source_run_id, client_request_id)**：✅ `_idempotency_scope(operation=retry_run, scope_id=run_id, idempotency_key=request.client_request_id)`。❌ 未测试。见 N3。
- **policy limit**：✅ `count_runs_by_source_relation(..., RETRY) >= 1`。❌ 未测试。见 N4。
- **只限 ordinary FAILED**：✅ `_require_source_run_for_relation(expected_status=RunStatus.FAILED)` 拒绝 `LOST`、`RECOVERING`。

### 3. SUCCEEDED replay 实现

- **no-tool**：✅ admission 层 `_replay_effective_execution_config` → `replace(agent_policy, allow_tool_calls=False)` + `_no_tool_effective_tool_set_json()`；dispatch 层 `_is_replay_run` → `ToolExecutionMode.NO_TOOL_REPLAY`。
- **source Run immutable**：✅ 同 retry，创建关联新 Run。
- **repair instruction**：✅ `ReplayRunRequest.repair_instruction` 作为新 Run `display_text`。
- **无新 tool facts**：✅ test 验证 replay 后 `TOOL_RESULT_ACCEPTED` count 不变。
- **runtime/dispatch 防工具**：✅ 双防线 — admission 冻结 no-tool config + dispatch 选择 `NO_TOOL_REPLAY` mode。test 验证 `disable_tools=True` 和 `tool_schemas=()`。
- **rejected candidate context**：源码 Run `USER_INPUT_ACCEPTED` payload 保留 `system_prompt` 和 `effective_execution_config` 供 replay 使用。

### 4. resolve_wait under open_host

- **醒 scheduler**：✅ `resolve_wait` admission commit 后 `_wake_dispatch_if_needed` 唤醒 scheduler。
- **new Attempt resume**：✅ 复用既有 `resolve_wait` admission 路径（未在 Slice 5 中修改 `resolve_wait` admission 逻辑）。
- **WAITING outcomes 覆盖**：✅ test 验证 completed outcome → RUNNING → SUCCEEDED。resolve_wait 的 failed/tool-cancelled/lost outcome 由既有 `test_resolve_wait_command.py`（964 lines）覆盖。

### 5. cancel public opener path

- **accepted / queued / active visibility / session-scope**：✅ test 覆盖 queued cancel（直接 CANCELLED）+ active cancel via shared registry（CANCELLING/CANCELLED）。❌ 缺少 pre-dispatch cancel 和 session-scope isolation。见 N6。
- **close boundary**：✅ 不在本 Slice 范围；Slice 2 已覆盖。

### 6. 越界检查

- **LOST/RECOVERING retry**：✅ 未实现，`_require_source_run_for_relation` 拒绝。
- **startup recovery**：✅ 未实现。
- **positive orphan proof**：✅ 未实现。
- **stuck cancel watchdog**：✅ 未实现。
- **callback/poller**：✅ 未实现。
- **interrupt API**：✅ 未新增。
- **schema 兼容**：✅ 无 schema 变更，使用既有 durable schema 字段 `source_run_id` / `source_run_relation`。
- **未授权文件**：✅ 未触碰。

### 7. 测试覆盖评价

- **跨 test helper import**：`test_public_steer.py`、`test_public_cancel_smoke.py`、`test_public_resolve_wait_resume.py` 均从 `test_public_retry_replay.py` 导入 `_options`、`_SequencedWorkerFactory`、`_wait_for_run_status` 等。这是合理的 test support 复用，但 `_options` 定义在 retry_replay 文件中使其成为隐式 test support module。低优先级。
- **5 tests 覆盖缺口**：happy path 完整，idempotency / terminal race / policy limit / WAITING steer / pre-dispatch cancel 共 7 个缺口（N1-N7），建议在 Slice 6 或 fix round 补齐。
- **README 准确性**：✅ `dayu/host/README.md` 正确新增 steer/retry/replay 说明，保留了 LOST/RECOVERING retry、startup recovery、orphan proof、stuck cancel watchdog 为 deferred。`tests/README.md` 正确新增 public run/wait/event API 覆盖面。

---

## 残余风险

| 风险 | 严重度 | Owner |
|------|--------|-------|
| WAITING steer 路径未测试 | Medium | Slice 5 fix 或 Slice 6 |
| steer terminal race CAS 未测试 | Medium | Slice 5 fix 或 Slice 6 |
| retry/replay 幂等未测试 | Medium | Slice 5 fix 或 Slice 6 |
| retry policy limit 未测试 | Low-Medium | Slice 5 fix 或 Slice 6 |
| pre-dispatch cancel 未测试 | Low-Medium | Slice 5 fix 或 Slice 6 |
| session-scope cancel isolation 未测试 | Low | Slice 6 |
| retry/replay 非目标状态 rejection 未测试 | Low | Slice 6 |
| ordinary retry policy 硬编码为 1（非可配置） | Low | 后续 phase |
