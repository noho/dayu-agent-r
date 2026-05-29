# Full-Repo Review Fix Re-Review AgentDS 20260529

## Scope

以 AgentDS 角色对 Controller adjudication FR-F1..FR-F5 fix 做独立复审。不修改文件，不 commit，不 push。

## Inputs

- Controller adjudication: `docs/reviews/repo-review-controller-adjudication-20260529.md`
- AgentCodex fix artifact: `docs/reviews/repo-review-fix-codex-20260529.md`
- AgentDS original full-repo review: `docs/reviews/repo-review-20260529-132719.md`
- AgentMiMo original full-repo review: `docs/reviews/repo-review-20260529-133403.md`
- Uncommitted workspace diff (`git diff`)

## Independent Validation

### Focused pytest (84 cases)

```
tests/host/test_audit_sink.py ................                                      [ 8%]
tests/host/test_tool_trace_projection.py ......                                     [14%]
tests/host/test_outbox_durable.py .......                                           [20%]
tests/host/test_public_outbox_api.py ...                                            [23%]
tests/host/test_public_offline_outbox_smoke.py ...                                  [27%]
tests/engine/runners/openai/test_protocol_error.py ..................               [48%]
tests/host/test_run_attempt_transitions.py ....................................    [100%]

84 passed in 0.99s
```

### Pyright

```
0 errors, 0 warnings, 0 informations
```

### Git diff --check

```
(no output — clean)
```

## FR-F1..FR-F5 Fix Verification

### FR-F1: Audit / Tool Trace JSONL 文件侧幂等

**Fix 验证 — PASS。**

`audit.py:_append_line` 与 `tool_trace.py:_append_line` 现在都在同一文件锁保护下调用 `_append_text_if_absent`，传入 `line_digest` 与 `source_keys`：

- 已存在同一 `line_digest` → 跳过 append，随后仍补写 marker / hot row（幂等 replay 正确）。
- 已存在同一 source key 但 `line_digest` 不同 → 抛 `HostDurableError`，由 ProjectionRunner 记录 failure，不补写 marker / hot row。
- JSONL 扫描不读取 payload，不改变 EventLog / governance truth。

新增测试覆盖：
- `test_jsonl_existing_line_prevents_duplicate_when_marker_missing` — marker 缺失但 JSONL 已有该行时，replay 只补 marker，不重复 append。
- `test_jsonl_source_key_digest_conflict_records_failure_without_marker` — 同 event_id 但 digest 冲突时记录 failure，marker 不写。
- `test_cold_jsonl_source_key_digest_conflict_records_failure_without_hot_row` — 同 source key 但 digest 冲突时记录 failure，hot row 不写。

**注：** `_append_text_if_absent`、`_jsonl_contains_line`、`_json_object_from_jsonl_line`、`_required_line_text` 四个 helper 在 `audit.py` 与 `tool_trace.py` 中各有一份独立实现。当前符合 controller "不引入 public API" 约束，但违反项目编码硬约束"重复逻辑必须抽取"。本 AgentDS 判断这是可接受的已知 trade-off：把这两个模块的 JSONL sink-local 幂等逻辑合并到一个共享 helper 需慎重设计模块边界，不应作为 gate blocker 强行在本次 fix 中引入。**标记为 deferred follow-up，不阻断本次 gate。**

### FR-F2: Outbox projection read state watermark

**Fix 验证 — PASS。**

`_latest_event_sequence` → `_latest_outbox_terminal_event_sequence`。查询从全表 `MAX(event_sequence)` 改为过滤 `event_class = 'canonical_fact' AND event_type IN (RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, RUN_LOST)` 的 `MAX(event_sequence)`。常量提取为 `_EVENT_CLASS_CANONICAL_FACT`、`_TERMINAL_EVENT_TYPES`，语义清晰。

新增测试 `test_projection_state_ignores_non_terminal_eventlog_tail`：checkpoint 追上 terminal fact 后追加 `RUN_ACCEPTED`（非 terminal），projection state 仍为 `CAUGHT_UP`。验证通过。

### FR-F3: Outbox drain pending CAS

**Fix 验证 — PASS。**

drain UPDATE SQL 增加 `AND item_state = ?` 绑定 `_ITEM_STATE_PENDING`。`result.rowcount != 1` 时抛 `HostDurableError("outbox drain item pending CAS failed")`，事务回滚，避免写入 drain idempotency row 或覆盖 metadata。

新增测试 `test_drain_pending_cas_prevents_second_request_metadata_overwrite`：第一轮 drain 成功后，第二轮不同 `drain_request_id` 触达 CAS 失败，stored item 保留第一轮 metadata（`drained_at`、`last_drain_request_id` 不变）。验证通过。

### FR-F4: SSE parser all invalid choices

**Fix 验证 — PASS。**

`_handle_chunk_object` 行 414 条件从 `if not handled_choice and not has_valid_usage:` 改为 `if not handled_choice:`。

逻辑流确认：
- 行 371-372: `has_valid_choices = isinstance(choices, list) and len(choices) > 0`；`has_valid_usage = isinstance(usage, dict)`
- 行 373-399: 当且仅当 BOTH choices 和 usage 都无效时才 protocol error——usage-only chunk 不被此分支拦截。
- 行 400: `if isinstance(choices, list) and choices:` 仅在 choices 非空列表时进入——空 choices 的 usage-only chunk 正确跳过。
- 行 414: 在非空 choices 块内，`not handled_choice` 触发 protocol error，不再被 `has_valid_usage` 掩盖。
- `has_valid_usage` 仍在行 373 条件中引用，无 orphaned 变量。

新增测试 `test_sse_all_non_object_choices_with_usage_protocol_error`：choices 非空（`["bad-choice", None]`）且 usage 合法 → `PROVIDER_PROTOCOL_ERROR + RUNNER_DONE(ERROR)`。既有 `test_sse_usage_only_chunk_does_not_protocol_error` 无回归。

### FR-F5: startup orphan recoverable closeout contract

**Fix 验证 — PASS。**

当前生产代码已有 validation 拒绝 `recoverable=True + expected_run_status != RUNNING`（`run_transition.py:429`）。AgentCodex 确认无需修改生产代码，仅补充 durable transition test 锁定合约。

新增测试 `test_startup_orphan_recoverable_rejects_cancelling_expected_status`：`recoverable=True + expected_run_status=CANCELLING` 触发 `HostDurableError("only running orphan Run can become recovering")`，事务回滚且无 `ATTEMPT_LOST` EventLog 事件。验证通过。

## Deferred Findings 复审

对照 controller adjudication deferred findings 清单逐一核实：

| Finding | 状态 | 说明 |
|---------|------|------|
| StdlibPidLivenessProbe 无 PID start token | 仍 deferred | 当前 fix 未触及，accepted risk |
| ProjectionRunner failure 后 checkpoint 停滞 | 仍 deferred | deferred design decision |
| pinned state current_goal first-write-wins | 仍 deferred | deferred memory design refinement |
| ToolRuntime / EngineIngest / memory 模块过长 | 仍 deferred | deferred refactor |
| monkeypatch / sleep / e2e 测试质量问题 | 仍 deferred | accepted test debt |
| Outbox idempotency key 全局唯一 | 仍 deferred | 中风险项 |
| fallback_mode 常量重复 | 仍 deferred | 中风险项 |
| read transaction retry 配置复用 | 仍 deferred | 中风险项 |

**无 deferred finding 被 fix 意外升级为 blocking issue。** 无 deferred finding 因本次 fix 引入新 correctness 问题。

## 增量发现

### D1 — 低 — `_append_text_if_absent` 等四个 helper 在 audit.py / tool_trace.py 重复实现

入参语义与实现逻辑完全相同。Controller 已裁决"不引入 public API"，将这两个模块的 sink-local 幂等逻辑提升为共享 helper 需权衡内部模块边界。**不阻断本次 gate**，标记为 deferred follow-up。

## Verdict: PASS

FR-F1 至 FR-F5 五个 accepted blocking findings 均已 fix。独立 validation（84 focused tests + pyright + git diff --check）全部通过。无 deferred finding 被升级为 blocking。无新增 correctness 问题。

下一步：AgentMiMo re-review PASS 后，Controller 更新 full-repo review fix gate 为 PASS。
