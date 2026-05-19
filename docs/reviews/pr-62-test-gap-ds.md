# PR-62 Merge-Before Test Gap Review (AgentDS)

## Scope

- Mode: PR review (test-gap focused)
- PR: [#62](https://github.com/noho/dayu-agent-r/pull/62) — Host P10.5 ordinary local multi-turn public contract freeze
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/pr-62-test-gap-ds.md`
- Review date: 2026-05-19
- Reviewer: AgentDS（Gateflow-governed test-gap review）
- 约束：只读，不改代码，不 commit，不 push

### Review focus（用户指定）
1. admission/EventLog payload_inline_threshold / payload descriptor / read-back 组合路径
2. dispatch / RunInputBuilder / engine_ingest 对 descriptor payload 的消费边
3. compaction semantic retry、dirty candidate rejection、stale guard、failed event、artifact/memory 连接
4. public contract export 负面断言
5. async cancellation / task lifecycle / close cleanup
6. manual smoke 与 deterministic tests 的边界

### Parallel review coverage
- Agent A: admission/EventLog payload_inline_threshold / payload descriptor / read-back
- Agent B: dispatch / RunInputBuilder / engine_ingest 消费边
- Agent C: compaction semantic retry、dirty candidate rejection、stale guard
- Agent D: public contract 负面断言、async cancellation / close cleanup

---

## 结论：FAIL

存在 **6 个 must-fix-before-merge** 的测试 blocker，其中包括 **1 个 production bug**（dispatch 中 `_effective_dispatch_decision` 使用不支持 descriptor payload 的 `_payload_object`，导致大 payload 的 per-run 覆盖被静默丢弃）。这些 blocker 必须在 merge 前补齐。

另有 **8 个 defer-with-owner** 项，可在后续 phase 处理，但每个需指定 owner。

---

## Findings

### F1 [must-fix-before-merge] [严重] dispatch 中 `_effective_dispatch_decision` 使用 `_payload_object` 而非 `event_payload_object`，大 payload 时 per-run 覆盖被静默丢弃 —— **PRODUCTION BUG**

- **入口/函数**: `HostDispatchScheduler._effective_dispatch_decision` → `_payload_object(event)` → `_effective_dispatch_decision_from_payload`
- **文件(行号)**: `dayu/host/dispatch.py:2152`
- **输入场景**: 用户 submit_followup 时传入 per-run overrides（runner_spec, agent_policy, system_prompt, tool_set），同时 display_text 足够大（超过 `payload_inline_threshold_bytes`），导致 admission 将完整 payload spill 到 SQLite PayloadStore，EventLog inline payload_json 仅保留 `_referenced_user_input_event_payload` 轻量 descriptor。
- **实际分支与执行路径**:
  1. Admission 层 `_append_user_input_event` (admission.py:2960-2976) 判断 `len(encoded) > threshold` → 写 `PayloadStore.write_sqlite_payload()` + descriptor。
  2. EventLog row 的 `payload_json` 被替换为 `_referenced_user_input_event_payload` (admission.py:2993-3009)，只含 6 个字段：`input_ref`, `input_digest`, `payload_ref`, `payload_digest`, `operation_kind`, `call_context_digest`——不含 `effective_execution_config`, `effective_tool_set`, `system_prompt` 等。
  3. Dispatch 端 `_effective_dispatch_decision` (dispatch.py:2152) 调用 `_payload_object(event)` — 这是 `_event_payload.py:359` 的 `payload_object`，只做 `json.loads(event.payload_json)`，不跟随 `payload_ref` descriptor。
  4. `_effective_dispatch_decision_from_payload` (dispatch.py:2806-2824) 检查 `payload.get("effective_execution_config")` 和 `payload.get("effective_tool_set")`——两者在 descriptor payload 中均为 `None`。
  5. 结果：静默 fallback 到 `fallback_policy_snapshot`（host local 配置）和 `selected_business_tool_names=None`（全量工具）。
- **预期行为**: dispatch 应通过 `event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")` 跟随 descriptor 从 PayloadStore 读取完整 payload，正确消费 admission 冻结的 per-run effective facts。
- **实际行为**: per-run execution config / tool set / system_prompt 覆盖被静默丢弃，Engine 收到的 runner_spec / agent_policy / tool schemas 是 host local 默认值而非用户指定的 per-run 值。
- **直接证据**:
  - `_payload_object` (来自 `_event_payload.py:359-373`): 仅 `json.loads(event.payload_json)`，不处理 `payload_ref` descriptor
  - `event_payload_object` (来自 `payload_resolution.py:17-55`): 正确处理 `payload_ref` → descriptor → PayloadStore 读回
  - 同文件 `_display_text_from_input_event` (dispatch.py:2648) 已正确使用 `event_payload_object`
  - `_referenced_user_input_event_payload` (admission.py:2993-3009): 不包含 `effective_execution_config` / `effective_tool_set` / `system_prompt` 等字段
- **影响**: 当用户 submit_followup 传入大 display_text + per-run overrides 时，per-run 覆盖被静默忽略——与手工 smoke 暴露的 admission 大 payload 问题同根。
- **建议改法和验证点**:
  - 生产代码修复：将 `dispatch.py:2152` 的 `_payload_object(event)` 改为 `event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")`
  - 测试：新增测试，设置 `payload_inline_threshold_bytes=10`，通过 submit_followup 传入 per-run overrides 和大 display_text，断言 dispatch 后 Engine request 中的 runner_spec / agent_policy / system_prompt 匹配 per-run 指定值
- **修复风险（中）**: 调用侧需要 transaction（当前已有，在 `_operation` lambda 内），不改变事务语义
- **严重程度（严重）**: 功能正确性 bug——per-run contract 在特定 payload 大小下静默失效

---

### F2 [must-fix-before-merge] [高] `payload_inline_threshold=0` 的 admission 端到端路径无测试

- **入口/函数**: `_write_user_input_payload_if_needed` → `submit_followup_queue` / `start_run` 完整链路
- **文件(行号)**: `dayu/host/admission.py:2960-2976`
- **输入场景**: `payload_inline_threshold_bytes=0`，任何非空 JSON payload 都会触发 spill 到 PayloadStore
- **现有测试证据**: `test_admission_queue.py:380-415` 使用 threshold=4096 的大 payload 场景；`test_event_log_store.py:128-209` 用 threshold=8 直接测 append_event 拒绝 oversized inline；`test_public_contracts.py:718` 只测 threshold=0 的 type 校验（ValueError）
- **具体缺口**: 不存在以 `threshold=0` 通过 `HostAdmissionService.submit_followup_queue` 或 `start_run` 做完整 admission → 读回的端到端测试。当 threshold=0 时，即使 `{"ok":true}` 也会溢出，"最极端合法值"的路径未被验证。
- **为什么不是泛泛覆盖率**: threshold=0 是合法配置值（`HostCommandHandleOptions` 不拒绝值=0），生产环境可能用它强制所有 canonical fact payload 走 PayloadStore。这是 admission 主链路的边界。
- **建议新增测试与断言**: `test_start_run_spills_user_input_payload_at_zero_threshold`，使用 `_options_with_payload_inline_threshold(tmp_path, 0)`，验证 `payload_ref is not None`，并通过 `event_payload_object` 读回完整 display_text 与 user_prompt
- **严重程度（高）**

---

### F3 [must-fix-before-merge] [高] EventLog payload descriptor 丢失时 `event_payload_object` fail-closed 路径无测试

- **入口/函数**: `event_payload_object`
- **文件(行号)**: `dayu/host/payload_resolution.py:34-35` — `"payload descriptor is missing"`
- **输入场景**: EventLog row 写了 `payload_ref` 但对应 `TABLE_PAYLOAD_DESCRIPTORS` 行不存在（bug、手动清理、schema migration 遗漏）
- **现有测试证据**: `test_payload_store.py:381-423` 覆盖 descriptor 存在的 happy path；`test_payload_store.py:426-465` 覆盖 digest mismatch 抛错。无测试命中 `"payload descriptor is missing"` 错误消息。
- **具体缺口**: fail-closed 行为未验证——错误消息和错误类型是否符合预期全靠代码 review，无法防止回归。
- **为什么不是泛泛覆盖率**: descriptor 是 EventLog→PayloadStore 的唯一条带外引用。引用断裂是真实 durability 风险，fail-closed 语义必须在测试中显式保护。
- **建议新增测试与断言**: `test_event_payload_object_raises_when_descriptor_missing`，手动写入含 `payload_ref` 但不写 descriptor 的 EventLog 行，调用 `event_payload_object`，断言 `HostDurableError` 且消息包含 `"descriptor is missing"`
- **严重程度（高）**

---

### F4 [must-fix-before-merge] [高] descriptor 存在但 sqlite_payload 行丢失时 `event_payload_object` fail-closed 路径无测试

- **入口/函数**: `event_payload_object`
- **文件(行号)**: `dayu/host/payload_resolution.py:49-51` — `"sqlite payload row is missing"`
- **输入场景**: descriptor 存在且 `payload_kind == SQLITE_PAYLOAD` 且 `sqlite_payload_id is not None`，但 `TABLE_SQLITE_PAYLOADS` 中对应行被删除
- **现有测试证据**: `test_payload_store.py:292-334` 只用原始 INSERT 测 FK 约束，未通过 `event_payload_object` 读取缺失 payload row 的路径
- **具体缺口**: 与 F3 同理，payload row 缺失的 fail-closed 路径无测试。`"sqlite payload row is missing"` 是运行时 corruption 的防御线。
- **为什么不是泛泛覆盖率**: descriptor→payload row 不一致是另一类 durability 故障模式，与 F3 的故障原因和恢复路径不同
- **建议新增测试与断言**: `test_event_payload_object_raises_when_sqlite_payload_row_missing`，写入完整 descriptor 但不写 payload row，通过 `event_payload_object` 读回，断言错误消息包含 `"sqlite payload row is missing"`
- **严重程度（高）**

---

### F5 [must-fix-before-merge] [高] compaction quality rejection 在 retry loop 中完全未被测试

- **入口/函数**: `run_compaction_operation` retry loop → quality rejection 分支
- **文件(行号)**: `dayu/host/compaction_operation.py:117-139`
- **输入场景**: compactor 返回合法 `CompactionCandidate` 但 quality check 失败（如 `retained_current_user_input_ref=None` 触发 `CURRENT_USER_INPUT_MISSING`），`repairable=True`
- **现有测试证据**: `test_run_compaction_operation_retries_async_proposal_failure` (test_compaction_operation.py:63) 仅使用 `_FailOnceCompactor` 测 proposal exception；`test_run_compaction_operation_fails_after_async_attempt_budget` (test_compaction_operation.py:83) 使用始终异常的 compactor。两个测试都不涉及 quality rejection。
- **具体缺口**: retry loop 有三种 rejection：proposal exception、quality check rejected、hard threshold after compact。仅 proposal exception 被测试。`not quality.accepted + repairable=True → continue` 路径从未被触发。
- **为什么不是泛泛覆盖率**: quality rejection retry 有独特副作用：设置 `last_budget = candidate.budget_after_compact`，构造 `CompactionAttemptRejected` 时使用 `_FAILURE_QUALITY_CHECK_REJECTED`。这些值在现有测试中从未被断言。
- **建议新增测试与断言**: `test_run_compaction_operation_retries_after_quality_rejection`，使用 `_DirtyThenCleanCompactor`（attempt 1 返回 dirty candidate，attempt 2 返回合法 candidate），断言 `len(result.rejected_attempts) == 1`、`result.accepted_candidate is not None`、`result.failure_reason is None`
- **严重程度（高）**

---

### F6 [must-fix-before-merge] [高] compaction quality rejection retry 的 dispatch 层集成测试缺失

- **入口/函数**: `HostDispatchScheduler._execute_proactive_compaction`
- **文件(行号)**: `dayu/host/dispatch.py:916-998`
- **输入场景**: dispatch scheduler 执行 proactive compact，compactor 第一次返回被 quality check 拒绝的 candidate，第二次返回 accepted candidate。预期写入一次 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` + 一次 `CONTEXT_COMPACTED`，Run 最终为 RUNNING。
- **现有测试证据**: `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` (test_dispatch_scheduler.py:2220) 使用 `_RaisingCompactor` 覆盖 full proposal failure；`test_compaction_contract.py` 覆盖 `check_compaction_candidate` 层面的 quality rejection。所有集成测试要么始终成功，要么始终失败。
- **具体缺口**: `rejected_attempts` 非空但 `accepted_candidate` 也非空的交叉路径从未在集成层被测试。`_execute_proactive_compaction` 中 rejected_attempts 迭代（dispatch.py:959-965）和 accepted/failure 分支（dispatch.py:966-998）的交叉组合路径无覆盖。
- **为什么不是泛泛覆盖率**: 集成层中 rejected + accepted 组合是 retry 机制的核心价值。如果不测，无法验证 rejected attempt event 的写入时机、与后续 accepted event 的顺序关系
- **建议新增测试与断言**: `test_proactive_compaction_retries_after_quality_rejection_integration`，创建 `_DirtyOnceCompactor`，通过 scheduler 运行 queue promotion，断言 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 事件计数为 1，`CONTEXT_COMPACTED` 为 1，Run 状态为 RUNNING
- **严重程度（高）**

---

### F7 [must-fix-before-merge] [中] stale guard 测试未断言 `CONTEXT_COMPACTION_FAILED` 的 `failure_reason` payload

- **入口/函数**: `_execute_proactive_compaction` → stale guard → `_append_compaction_failed_event`
- **文件(行号)**: `dayu/host/dispatch.py:947-958`
- **输入场景**: compact 执行期间 Run 状态被外部改变（如被 cancel），stale guard 触发 `run.status != pending.expected_status`
- **现有测试证据**: `test_compaction_stale_result_does_not_write_compacted_event` (test_dispatch_scheduler.py:2189) 断言 `CONTEXT_COMPACTED == 0` 和 `Run.status == FAILED`
- **具体缺口**: 测试未断言 `CONTEXT_COMPACTION_FAILED` 事件已被写入且 payload 中 `failure_reason == "stale_compaction_result"`。这意味着测试无法区分 "stale guard 正确写入 failed event" 与 "stale guard 静默跳过"
- **为什么不是泛泛覆盖率**: 这是一个 order-implies-causality 断言。没有它，未来重构成可能移除 failed event 写入而测试仍通过
- **建议新增测试与断言**: 在现有 `test_compaction_stale_result_does_not_write_compacted_event` 中增加：读取 `CONTEXT_COMPACTION_FAILED` 事件，断言 `payload["failure_reason"] == "stale_compaction_result"`
- **严重程度（中）**

---

### F8 [defer-with-owner] [中] `_referenced_user_input_event_payload` 字段收缩无显式安全断言

- **入口/函数**: `_referenced_user_input_event_payload`
- **文件(行号)**: `dayu/host/admission.py:2993-3009`
- **现有测试证据**: `test_admission_queue.py:413` 只断言 `"long prompt" not in input_event.payload_json`
- **具体缺口**: 未显式验证轻量 payload 只有 6 个字段且不包含 `display_text`, `user_prompt`, `system_prompt`, `effective_execution_config`, `effective_tool_set`。如果未来有人在此函数中意外泄露敏感字段，当前测试不捕获
- **建议**: 在 `test_followup_queue_spills_large_user_input_payload` 中增加显式字段白名单断言
- **严重程度（中）** — defer，不阻塞 merge，但应在后续 phase 补齐安全审计测试

---

### F9 [defer-with-owner] [低] 多进程 admission 测试完全未覆盖 payload spill 场景

- **入口/函数**: `test_admission_multiprocess.py` 全部 5 个测试
- **现有测试证据**: 全部使用默认阈值的小 payload（`"start input"`、`"queued input {n}"`）
- **具体缺口**: 并发 admission 场景下 payload store 的跨连接读回正确性未测试
- **建议**: 在 `test_multiprocess_queued_followups_promote_by_accepted_sequence` 中引入 1 个大 payload worker
- **严重程度（低）** — defer，当前单进程已覆盖

---

### F10 [defer-with-owner] [中] `_effective_dispatch_decision_from_payload` 的 start_run fallback 路径（None/None）无单元测试

- **入口/函数**: `_effective_dispatch_decision_from_payload`
- **文件(行号)**: `dayu/host/dispatch.py:2792-2824`
- **现有测试证据**: `test_effective_execution_config.py` 中的测试通过 open_host/submit_followup 覆盖有 per-run overrides 的路径。start_run 路径（`effective_execution_config=None, effective_tool_set=None`）未被 dispatch 层测试。
- **具体缺口**: 分支 1（payload 不是 Mapping）、分支 2（`effective_execution_config` 缺失）、分支 3（`effective_tool_set` 缺失）均未单独测试
- **建议**: 新增 3 个单元测试，直接调用 `_effective_dispatch_decision_from_payload`
- **严重程度（中）** — defer，F1 修复后此路径的行为应正确

---

### F11 [defer-with-owner] [低] `system_prompt=None` 时 RunInputBuilder 消息布局无集成断言

- **入口/函数**: `RunInputBuilder.build()` → `_system_prompt_message`
- **文件(行号)**: `dayu/host/run_input.py:1320, 2109-2120`
- **现有测试证据**: `test_field_level_partial_merge_uses_baseline_for_omitted_fields` 验证了非 None 情形。无测试断言 `system_prompt=None` 时分派请求中不存在 SystemMessage
- **具体缺口**: 需要一条集成测试显式验证 `system_prompt=None` 时 `request.messages[0]` 不是 SystemMessage
- **严重程度（低）** — defer

---

### F12 [defer-with-owner] [低] stale guard `input_event_sequence` 条件未被测试

- **入口/函数**: `_execute_proactive_compaction` stale guard
- **文件(行号)**: `dayu/host/dispatch.py:942-946`
- **现有测试证据**: `_StaleMutatingCompactor` 仅测试 run status 改变（第二个析取项）
- **具体缺口**: 第三个析取项 `run.input_event_sequence != pending.expected_input_event_sequence`（compact 期间新的 USER_INPUT_ACCEPTED 事件推进了 sequence）未测试。这是并发场景下真实的竞争条件。
- **建议**: `test_compaction_stale_input_sequence_does_not_write_compacted_event`
- **严重程度（低）** — defer，生产环境中概率低

---

### F13 [defer-with-owner] [低] `run is None` stale 分支无测试

- **入口/函数**: `_execute_proactive_compaction` stale guard
- **文件(行号)**: `dayu/host/dispatch.py:942-944`
- **现有测试证据**: 无
- **具体缺口**: `run is None`（Run 在 compact 期间被删除）时返回 None 且不写入 COMPACTION_FAILED 事件。这是三个 stale 条件中唯一不产生 EventLog 痕迹的。需要确认是 intentional silent-skip 还是 bug。
- **建议**: `test_compaction_stale_run_deleted_during_compact`，确认行为
- **严重程度（低）** — defer

---

### F14 [must-fix-before-merge] [中] `wake_dispatch` / `wake_queue_promotion` 在 `close()` 后抛出 RuntimeError 的测试缺失

- **入口/函数**: `HostDispatchScheduler.wake_dispatch` / `wake_queue_promotion`
- **文件(行号)**: `dayu/host/dispatch.py:590-591, 614-615`
- **输入场景**: scheduler 已 close → 调用方尝试 wake_dispatch 或 wake_queue_promotion
- **现有测试证据**: 无。`test_dispatch_scheduler.py` 和 `test_active_cancel_dispatch.py` 中所有 close 后测试都是验证 lane release / registry unregister / task cancel
- **具体缺口**: `_closed = True` 后的 guard 是否真正阻断了后续 dispatch 路径未验证
- **建议**: `test_wake_dispatch_after_close_raises_runtime_error` 和 `test_wake_queue_promotion_after_close_raises_runtime_error`
- **严重程度（中）**

---

### F15 [must-fix-before-merge] [中] `HostDispatchScheduler.close()` 的幂等重复关闭未被测试

- **入口/函数**: `HostDispatchScheduler.close()`
- **文件(行号)**: `dayu/host/dispatch.py:1515-1516` — `if self._closed: return`
- **输入场景**: 重复调用 `await scheduler.close()`
- **现有测试证据**: 所有 close 测试都只调一次
- **具体缺口**: 生产环境中 `Host.handle.close()` 和 scheduler close 可能通过不同路径到达。未验证重复 close 不抛异常、不残留资源
- **建议**: `test_scheduler_double_close_is_idempotent`
- **严重程度（中）**

---

### F16 [must-fix-before-merge] [中] `retry_run` / `replay_run` 源 Run 不存在（NOT_FOUND）的 public facade 测试缺失

- **入口/函数**: `HostAdmissionService.retry_run` / `replay_run`
- **文件(行号)**: `dayu/host/admission.py:640, 679` — docstring 明确声明 `raises HostApiError: 源 Run 缺失`
- **输入场景**: 传入不存在的 `run_id`
- **现有测试证据**: `test_public_retry_replay.py` 中所有测试都通过 submit_followup 创建合法源 Run
- **具体缺口**: `HostApiError(NOT_FOUND)` 是 public contract 的明确承诺。缺失测试意味着这个错误路径可能在未来重构中被打破
- **建议**: `test_retry_run_rejects_nonexistent_source` 和 `test_replay_run_rejects_nonexistent_source`，断言 `HostApiErrorCode.NOT_FOUND`
- **严重程度（中）**

---

### F17 [must-fix-before-merge] [中] `retry_run` 的幂等冲突（digest mismatch）路径缺少测试

- **入口/函数**: `_RetryRunOperation.__call__` → `_raise_if_digest_conflict`
- **文件(行号)**: `dayu/host/admission.py` (retry transaction body)
- **输入场景**: 同一 `client_request_id` 但不同 request 参数（不同 reason）发起两次 retry
- **现有测试证据**: `test_retry_run_replays_same_client_request_id_idempotently` 覆盖幂等成功重放（同一 digest）
- **具体缺口**: `HostApiErrorCode.IDEMPOTENCY_CONFLICT` 在 retry 路径的生产级幂等冲突无独立断言
- **建议**: `test_retry_run_idempotency_conflict_on_digest_mismatch`
- **严重程度（中）**

---

### F18 [must-fix-before-merge] [中] steer 的幂等重放路径和 `SteerConflictDetail` detail 断言缺失

- **入口/函数**: `_SubmitFollowupSteerOperation.__call__` → 幂等路径 + `_require_steer_target_run` → `SteerConflictDetail`
- **文件(行号)**: `dayu/host/admission.py` (steer transaction body)
- **现有测试证据**: `test_steer_terminal_race_rejects_non_active_target` 只验证了 `code == INVALID_STATE`，未验证 `detail` 字段
- **具体缺口**: steer 的幂等重放完全无测试；`SteerConflictDetail` 作为 `HostApiErrorDetail` 的唯一使用场景，detail 字段的正确填充未验证
- **建议**: 在现有 steer 测试中增加 `assert isinstance(exc_info.value.detail, SteerConflictDetail)` 和字段断言；新增 `test_steer_idempotent_replay`
- **严重程度（中）**

---

### F19 [not-needed] `_execution_config_projection.py` 投影函数是纯函数，无需额外测试

- Agent B 确认：`effective_execution_config_json` 和 `effective_execution_snapshot_from_json` 是纯 JSON 投影函数，不涉及 payload descriptor 解析。现有测试足够。
- **严重程度**: not-needed

---

### F20 [not-needed] `EngineEventCandidate` 不携带 effective 配置，设计正确

- Agent B 确认：effective 配置在 dispatch 阶段完全消费。engine_ingest 不需要。`test_engine_ingest_mapping.py` 测试了事件映射，无缺口。
- **严重程度**: not-needed

---

## 汇总表

| # | 严重度 | 类别 | 简述 |
|---|--------|------|------|
| F1 | **严重** | **BUG + must-fix** | dispatch `_payload_object` 不支持 descriptor payload，per-run 覆盖静默丢弃 |
| F2 | **高** | must-fix | `threshold=0` 的 admission 端到端路径无测试 |
| F3 | **高** | must-fix | payload descriptor 丢失 fail-closed 无测试 |
| F4 | **高** | must-fix | sqlite payload row 丢失 fail-closed 无测试 |
| F5 | **高** | must-fix | compaction quality rejection retry 无测试 |
| F6 | **高** | must-fix | quality rejection retry dispatch 层集成测试缺失 |
| F7 | **中** | must-fix | stale guard failed event failure_reason 断言缺失 |
| F8 | 中 | defer | 轻量 payload 字段收缩无安全断言 |
| F9 | 低 | defer | 多进程 admission payload spill 未覆盖 |
| F10 | 中 | defer | start_run dispatch fallback 无单元测试 |
| F11 | 低 | defer | system_prompt=None 消息布局无断言 |
| F12 | 低 | defer | stale guard input_event_sequence 条件未测试 |
| F13 | 低 | defer | run is None stale 分支无测试 |
| F14 | 中 | must-fix | close 后 wake_dispatch RuntimeError 无测试 |
| F15 | 中 | must-fix | close 幂等重复调用无测试 |
| F16 | 中 | must-fix | retry/replay NOT_FOUND 无测试 |
| F17 | 中 | must-fix | retry 幂等冲突 digest mismatch 无测试 |
| F18 | 中 | must-fix | steer 幂等重放和 SteerConflictDetail 无断言 |
| F19 | — | not-needed | 投影函数纯函数，现有测试足够 |
| F20 | — | not-needed | EngineEventCandidate 设计正确 |

**must-fix-before-merge**: F1, F2, F3, F4, F5, F6, F7, F14, F15, F16, F17, F18（共 12 项，其中 F1 是 production bug）
**defer-with-owner**: F8, F9, F10, F11, F12, F13（共 6 项）
**not-needed**: F19, F20（共 2 项）

---

## Manual Smoke 与 Deterministic Tests 的边界

以下路径**只能在 manual smoke 中验证**（依赖真实 LLM runner / 网络 / 超时）：

| 路径 | 原因 |
|------|------|
| Engine worker 超时后 cancel 信号传播到 LLM provider | 需真实 HTTP 超时或 mock provider cancel |
| Lane heartbeat 过期后的 takeover | 依赖 SQLite lane 协调器时间驱动行为 |
| close() 期间 Engine 正在 streaming token | 需真实 streaming runner |
| compact LLM 调用在事务外的并发行为 | LLM 调用语义需真实 runner 验证 |
| 大 display_text 触发 spill 后的完整 trace 可视化 | 需真实 render |

以下路径**应该在 deterministic 测试中覆盖但缺失**：

| 路径 | 对应 Finding |
|------|-------------|
| threshold=0 的 admission 端到端 | F2 |
| descriptor 丢失 fail-closed | F3 |
| sqlite payload row 丢失 fail-closed | F4 |
| compaction quality rejection retry | F5, F6 |
| stale guard failed event payload | F7 |
| close 后 guard 行为 | F14, F15 |
| retry/replay public contract 负面路径 | F16, F17 |
| steer 幂等重放 | F18 |

---

## Open Questions

1. F1 中 `_effective_dispatch_decision` 的 bug 是否也影响 `start_run` 路径？`start_run` 的 `effective_execution_config` 在 admission 中设为 None——确认 payload 大小是否可能导致 start_run 的 `effective_*` 字段在某些边界下为 None 但 dispatch 期望它们存在。
2. F13 中 `run is None` 时 silent-skip（不写入 COMPACTION_FAILED event）是 intentional 还是 bug？需 owner 确认。
3. `_selected_tool_names_from_effective_tool_set` 中 `selector="none"` 的 `effective_business_tool_names` 缺失是否会抛错？当前 admission 端始终写入空列表，但 dispatch 端解析器没有显式 `if selector == "none"` 防御分支。

---

## Residual Risk

1. F1 修复后，所有受影响的 dispatch 路径（queue promotion、compact after catch-up、direct start）需逐一验证 descriptor payload 的读回正确性。
2. 多进程并发下 payload store 的跨连接读回尚未在 stress 场景下验证（F9）。
3. 组合路径（retry + dirty + stale 三重交互）未覆盖，概率低但在生产高负载下可能暴露。
4. Lane 协调器在 compaction 与 dispatch 并发场景下的行为未验证。
