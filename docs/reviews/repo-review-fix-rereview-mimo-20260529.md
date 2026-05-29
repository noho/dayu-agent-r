# Repo Review Fix Re-Review AgentMiMo 20260529

## Scope

- Mode: Full-repo fix re-review
- Branch: `feat/phase-13-audit-trace-outbox`
- Diff: uncommitted working tree changes against staged/HEAD
- Artifacts reviewed:
  - `docs/reviews/repo-review-controller-adjudication-20260529.md`
  - `docs/reviews/repo-review-fix-codex-20260529.md`
  - `docs/reviews/repo-review-20260529-133403.md`
  - `docs/reviews/repo-review-20260529-132719.md`
- Focus: FR-F1..FR-F5 accepted blocking findings; deferred findings 不作为本 gate blocker，除非 fix 引入新 correctness 问题。

## Validation 复核

| Check | Fix Doc Claim | Re-Review Result |
|-------|--------------|-----------------|
| focused pytest | 84 passed | 84 passed |
| pyright | 0 errors | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed | passed |

## FR-F1 Audit / Tool Trace JSONL 文件侧幂等

### 修复逻辑核验

**Audit (`dayu/host/audit.py`):**

- `_append_line` 改为调用 `_append_text_if_absent`，在文件锁保护下先扫描目标 JSONL。
- `_jsonl_contains_line` 逐行解析 JSONL，按 `line_digest` 匹配：命中则跳过 append（幂等）。
- 同 `event_id`（source key）但 `line_digest` 不同时抛 `HostDurableError`，ProjectionRunner 记录 failure，不补 marker。
- `apply_event` 中 `_append_line` 仍在 `insert_audit_sink_marker_if_absent` 之前调用，但因幂等检查，replay 时已存在行会被跳过，随后 marker 被补齐。正确。
- 不读 payload，不改变 EventLog/governance truth。符合约束。

**Tool Trace (`dayu/host/tool_trace.py`):**

- 逻辑与 Audit 对称。`_append_line` 改为 `_append_text_if_absent`。
- source keys 包含 `event_id` 和 `cold_trace_ref` 两个字段。
- 同 source key 但 digest 不同时抛 `HostDurableError`，ProjectionRunner 记录 failure，不补 hot row。
- `apply_event` 中 hot row INSERT 在 cold line append 之前；因幂等检查，replay 安全。

**重复代码注意项:**

`_jsonl_contains_line`、`_json_object_from_jsonl_line`、`_append_text_if_absent` 在 `audit.py` 和 `tool_trace.py` 中近乎完全相同。属于 deferred refactor 范畴（原始 review 06/17/29 等已覆盖），不构成本 gate blocker。

### 测试覆盖核验

- `test_jsonl_existing_line_prevents_duplicate_when_marker_missing`：模拟"JSONL 已有 line 但 DB marker 缺失"的 replay 场景。删除 marker 和 checkpoint 后重跑 projection，确认 JSONL 仍只有一行且 marker 被补齐。正确。
- `test_jsonl_source_key_digest_conflict_records_failure_without_marker`：手动篡改 JSONL 行的 `line_digest` 为冲突值，重跑 projection 确认 `result.failures == 1`、marker 仍为 None、failure 记录了正确的 event_id。正确。
- `test_projection_rebuild_from_event_log_restores_hot_rows`（更新）：增加 JSONL 行数断言 `assert [line["event_id"] ...] == ["event-requested"]`，验证 rebuild 路径也受幂等保护。
- `test_cold_jsonl_source_key_digest_conflict_records_failure_without_hot_row`：Tool Trace 侧对应测试，逻辑与 audit 冲突测试对称。正确。

### 结论

FR-F1 fix 正确。幂等检查覆盖了 `line_digest` 匹配（跳过）和 source key 冲突（failure）两种路径。测试可复现且充分。无新 blocking finding。

## FR-F2 Outbox projection read state watermark

### 修复逻辑核验

- `read_outbox_terminal_projection_state` 中 `_latest_event_sequence` 重命名为 `_latest_outbox_terminal_event_sequence`。
- 查询从 `SELECT MAX(event_sequence) FROM host_event_log` 改为 `WHERE event_class = 'canonical_fact' AND event_type IN ('RUN_SUCCEEDED', 'RUN_FAILED', 'RUN_CANCELLED', 'RUN_LOST')`。
- 语义：只比较 checkpoint 与最新 Outbox terminal canonical fact sequence，而非全局 EventLog watermark。
- 常量 `_TERMINAL_EVENT_TYPES` 和 `_EVENT_CLASS_CANONICAL_FACT` 定义清晰。

### 测试覆盖核验

- `test_projection_state_ignores_non_terminal_eventlog_tail`：
  1. 追加 terminal event（RUN_SUCCEEDED）→ advance checkpoint 到该 sequence。
  2. 追加 non-terminal event（RUN_ACCEPTED）。
  3. 读 projection state → 断言 `CAUGHT_UP`。
  - 正确覆盖了 FR-F2 的核心场景：非 terminal EventLog tail 不应导致 LAGGED 误报。

### 结论

FR-F2 fix 正确。watermark 比较范围已收窄到 Outbox terminal canonical facts。测试充分。无新 blocking finding。

## FR-F3 Outbox drain pending CAS

### 修复逻辑核验

- `drain_outbox_terminal_items` 中 UPDATE SQL 增加 `AND item_state = 'pending'`。
- 对 `result.rowcount != 1` 抛 `HostDurableError("outbox drain item pending CAS failed")`，当前 transaction 回滚。
- 不同 `drain_request_id` 无法覆盖已 drained item 的 metadata。

### 测试覆盖核验

- `test_drain_pending_cas_prevents_second_request_metadata_overwrite`：
  1. 插入 pending item。
  2. 第一次 drain（drain-request-1）成功，item 变为 drained。
  3. 第二次 drain（drain-request-2）抛 `HostDurableError`（match "pending CAS failed"）。
  4. 验证 item 仍为 drained 状态，metadata 未被覆盖。
  - 正确。覆盖了 CAS miss 的核心场景。

### 结论

FR-F3 fix 正确。pending CAS 保证了不同 drain request 不会静默覆盖已 drained metadata。测试充分。无新 blocking finding。

## FR-F4 SSE parser all invalid choices

### 修复逻辑核验

- 条件从 `if not handled_choice and not has_valid_usage` 改为 `if not handled_choice`。
- 效果：只要 `choices` 非空列表且没有任何 dict choice，无论 usage 是否合法，都触发 protocol error + `runner_done(ERROR)`。
- 不影响真正 usage-only chunk：当 `choices` 为 None 或空列表 `[]` 时，`isinstance(choices, list) and choices` 为 False，整个 choices 分支被跳过，直接走到 usage 处理。

### 测试覆盖核验

- `test_sse_all_non_object_choices_with_usage_protocol_error`：
  - `choices: ["bad-choice", None]` + 合法 `usage` → 断言输出 `[PROVIDER_PROTOCOL_ERROR, RUNNER_DONE]`，error_code 为 `sse_missing_choices`，finish_reason 为 `ERROR`。
  - 正确覆盖了 FR-F4 核心场景。
- 既有 `test_sse_usage_only_chunk_does_not_protocol_error` 未被修改，确认真正 usage-only chunk 仍合法。

### 结论

FR-F4 fix 正确。非空 choices 全不可解析时 protocol error 不再被 usage 合法性掩盖。usage-only chunk 合法路径不受影响。测试充分。无新 blocking finding。

## FR-F5 startup orphan recoverable closeout contract

### 修复逻辑核验

- `run_transition.py:5311-5312` 已有生产代码校验：`if request.recoverable and request.expected_run_status != RunStatus.RUNNING: raise HostDurableError("only orphan Run can become recovering")`。
- Fix 不修改生产代码，仅补充 transition test 锁定该合约。

### 测试覆盖核验

- `test_startup_orphan_recoverable_rejects_cancelling_expected_status`：
  1. 种子化 RUNNING run。
  2. 尝试 `close_startup_orphan_attempt_in_transaction` with `recoverable=True, expected_run_status=CANCELLING`。
  3. 断言 `HostDurableError` match "only running orphan Run can become recovering"。
  4. 断言 `ATTEMPT_LOST` 事件计数不变（确认非法组合不写任何事件）。
  - 正确。测试同时验证了错误路径不产生副作用。

### 结论

FR-F5 fix 正确。生产代码已有 validation，补充测试锁定合约防止回归。测试覆盖了错误路径和副作用隔离。无新 blocking finding。

## Deferred Findings 状态确认

以下 deferred findings 在本次 fix 中未被触及，仍保持 deferred 状态。Re-Review 确认无一项因 fix 引入新 correctness 问题：

| Deferred Item | Status |
|---------------|--------|
| StdlibPidLivenessProbe 无 PID start token | 未触及，仍 deferred |
| ProjectionRunner failure 后 checkpoint 停滞 | 未触及，仍 deferred |
| pinned state current_goal / constraints 去重 | 未触及，仍 deferred |
| ToolRuntime / EngineIngest / memory 模块过长 | 未触及，仍 deferred |
| monkeypatch / sleep / e2e 测试质量问题 | 未触及，仍 deferred |
| Outbox idempotency key 全局唯一 | 未触及，仍 deferred |
| fallback_mode 常量重复 | 未触及，仍 deferred |
| read transaction retry 配置复用 | 未触及，仍 deferred |
| JSONL 幂等扫描随文件增长的性能开销 | 已在 fix doc 记录，可接受 |
| drain CAS fail-fast 语义对 cursor 推进的影响 | 已由既有 public outbox 测试覆盖 |

## New Findings

### 新发现 1-低-Audit/ToolTrace JSONL 扫描 helper 重复实现

- **文件**: `dayu/host/audit.py` 和 `dayu/host/tool_trace.py`
- **描述**: `_jsonl_contains_line`、`_json_object_from_jsonl_line`、`_append_text_if_absent` 三个函数在两模块中近乎完全相同，仅 error message 和 source_keys 构造略有差异。
- **影响**: 低。属于 deferred refactor（模块过长 / 重复逻辑）范畴，不构成本 gate blocker。
- **建议**: 后续 phase 抽取为共用 helper。

### 新发现 2-低-Outbox terminal event type 常量与 EventLog schema 命名耦合

- **文件**: `dayu/host/durable/outbox.py:68-76`
- **描述**: `_TERMINAL_EVENT_TYPES` 硬编码 4 个 event type 字符串。若 EventLog schema 中 event type 枚举变更，此处需同步。
- **影响**: 低。当前 event type 已稳定，且有测试覆盖。
- **建议**: 可考虑从 contracts 层引用 event type 枚举，但非阻塞。

以上两个新发现均为低严重度，不构成本 gate blocker。

## Verdict

**PASS**

FR-F1..FR-F5 全部修复正确：
- 幂等逻辑、watermark、CAS、protocol error、合约校验均按 adjudication 要求实现。
- 84 focused tests 全部通过，pyright 0 errors，git diff --check 通过。
- Deferred findings 保持原状，无 fix 引入的新 correctness 问题。
- 新发现仅 2 项低严重度，不阻塞 gate。
