# PR-62 Test Gap Review

## Scope

- Mode: PR test-gap review (Gateflow-governed, read-only)
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/pr-62-test-gap-mimo.md`
- Reviewer: AgentMiMo
- Date: 2026-05-19
- Included scope: PR-62 diff (`main...HEAD`) production code + corresponding tests
- Excluded scope: docs/, README/, utils/, review artifacts

## 结论: FAIL

存在 5 个 must-fix-before-merge 测试 blocker，涉及 inline/descriptor 边界、compaction retry 分支、descriptor payload 消费链和多轮上下文连续性。

## Findings

### F1-must-fix-[高]-inline/descriptor 边界阈值精确边界无测试

- **入口/函数**: `admission.py:2976` `_write_user_input_payload_if_needed` 分支 `if len(encoded.encode("utf-8")) <= transaction.payload_inline_threshold_bytes`
- **文件(行号)**: `dayu/host/admission.py:2976`
- **输入场景**: payload 序列化后 UTF-8 字节长度恰好等于阈值，或恰好等于阈值+1
- **实际分支**: `<=` 操作符是正确性敏感边界。等于阈值应 inline（返回 None），超阈值应走 descriptor
- **预期行为**: 边界值行为被 deterministic 测试锁定
- **实际行为**: 所有测试只用默认阈值（payload inline）或 threshold=4096 + `"long prompt " * 600`（~7200 bytes，远超阈值）。无人构造 payload 使序列化长度恰好等于阈值
- **直接证据**: `test_followup_queue_spills_large_user_input_payload`（test_admission_queue.py:380）用 threshold=4096 + 7200 bytes payload，远超边界。无测试用精确边界值
- **影响**: 若 `<=` 被误改为 `<`，恰好等于阈值的 payload 会从 inline 变成 descriptor，引入静默行为变化
- **建议改法和验证点**: 新增 `test_user_input_payload_at_inline_threshold_boundary`：计算已知小 payload 的 canonical JSON UTF-8 字节长度 L，设置 threshold=L 断言 `payload_ref is None`，设置 threshold=L-1 断言 `payload_ref is not None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F2-must-fix-[高]-RunInputBuilder 对 descriptor payload 的消费链无端到端测试

- **入口/函数**: `DurableCurrentRunFactProvider._load_current_run_facts_tx`（run_input.py:525）调用 `event_payload_object(transaction, user_input_event, ...)`
- **文件(行号)**: `dayu/host/payload_resolution.py:17-55`, `dayu/host/run_input.py:525`
- **输入场景**: `USER_INPUT_ACCEPTED` event 的 `payload_ref is not None`，即大 payload 走 descriptor 路径
- **实际分支**: `payload_resolution.event_payload_object` 的 descriptor 跟随路径（line 29-55）
- **预期行为**: `RunInputBuilder.build()` 能正确解析 descriptor 引用的 payload 并返回完整 user_prompt
- **实际行为**: 所有 `test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_public_run_api.py` 写入 `EventLogAppendRequest` 时 `payload_ref=None` 全部走 inline 路径。`test_payload_store.py` 测试写入原语但不调用 `event_payload_object`。descriptor 跟随路径从未通过 `RunInputBuilder` 端到端验证
- **直接证据**: grep 所有测试文件，`payload_ref` 赋值只出现在 `test_admission_queue.py:411` 的断言行和 `test_payload_store.py` 的原语测试中。`RunInputBuilder.build()` 从未消费过 descriptor 引用的 event
- **影响**: 生产中大 payload 走 descriptor 路径时，若 descriptor 读取链断裂（digest mismatch、sqlite payload missing），`RunInputBuilder` 会抛 `HostDurableError`，但此错误传播路径从未被测试验证
- **建议改法和验证点**: 新增 `test_run_input_builder_resolves_descriptor_payload`：写入带 `payload_ref`/`payload_digest` 的 `USER_INPUT_ACCEPTED` event，调用 `RunInputBuilder.build()`，断言 resolved `user_prompt` 匹配 descriptor 存储内容
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F3-must-fix-[高]-compaction quality_check_rejected semantic retry 路径无测试

- **入口/函数**: `run_compaction_operation`（compaction_operation.py:119-132）`quality_check_rejected` 分支
- **文件(行号)**: `dayu/host/compaction_operation.py:119-132`, `tests/host/test_compaction_operation.py`
- **输入场景**: compactor 返回的 candidate 未通过 quality check（如缺少 tool_fact_refs），然后重试成功
- **实际分支**: `not quality.accepted` → `failure_category=_FAILURE_QUALITY_CHECK_REJECTED` → `repairable=True` → `continue`
- **预期行为**: 首次 candidate 被 quality check 拒绝后，semantic retry 产生合格 candidate 并被接受
- **实际行为**: `test_compaction_operation.py` 只测试了 `proposal_failed`（compactor 抛异常）的 retry。`quality_check_rejected` 分支（line 119-132）零覆盖。`_FAILURE_QUALITY_CHECK_REJECTED` 和 `_NEXT_DECISION_RETRY_REPAIR` 常量在测试中从未被触发
- **直接证据**: `test_compaction_operation.py` 仅有两个测试：`test_run_compaction_operation_retries_async_proposal_failure`（测试 proposal_failed retry）和 `test_run_compaction_operation_fails_after_async_attempt_budget`（测试耗尽）。无测试构造 quality check 失败场景
- **影响**: compaction 的核心价值承诺（semantic repair loop）无测试保护。若 quality check 拒绝逻辑回归，retry 循环会静默跳过或错误终止
- **建议改法和验证点**: 新增 `_QualityRejectOnceCompactor`（attempt 1 返回缺少 tool_fact_refs 的 candidate，attempt 2 返回合格 candidate）。断言 `rejected_attempts[0].failure_category == "quality_check_rejected"`、`repairable is True`、`next_policy_decision == "retry_semantic_repair"`、`accepted_candidate is not None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F4-must-fix-[高]-compaction hard_threshold_after_compact 拒绝+retry 路径零覆盖

- **入口/函数**: `run_compaction_operation`（compaction_operation.py:140-163）`hard_threshold_after_compact` 分支
- **文件(行号)**: `dayu/host/compaction_operation.py:140-163`
- **输入场景**: compactor 返回的 candidate 通过 quality check 但 `budget_after_compact >= hard_threshold_tokens`
- **实际分支**: `candidate.budget_after_compact >= request.budget_before_compact.hard_threshold_tokens` → reject + retry
- **预期行为**: 超 hard threshold 的 candidate 被拒绝，触发 semantic retry
- **实际行为**: 零测试覆盖。`_FAILURE_HARD_THRESHOLD_AFTER_COMPACT` 常量在测试中从未被触发
- **直接证据**: grep `test.*hard_threshold` 只命中 `test_context_budget.py` 和 `test_context_policy.py` 的 budget 估计测试，不涉及 `run_compaction_operation` 的 rejection 分支
- **影响**: budget safety guarantee 的拒绝路径无测试保护。若 hard threshold 检查逻辑回归，超预算 candidate 会被错误接受
- **建议改法和验证点**: 新增测试：compactor attempt 1 返回 `budget_after_compact >= hard_threshold_tokens` 的 candidate，attempt 2 返回合格 candidate。断言 `failure_category == "hard_threshold_after_compact"`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F5-must-fix-[高]-多轮上下文连续性无 deterministic 测试

- **入口/函数**: `submit_followup` → dispatch → `RunInputBuilder.build()` → 注入前轮 final_answer 为历史上下文
- **文件(行号)**: `dayu/host/dispatch.py`（RunInputBuilder 消费链）, `tests/host/test_public_open_host_multiturn_smoke.py:27`
- **输入场景**: Run 2 的 request messages 应包含 Run 1 的 final_answer 内容
- **实际分支**: 多轮上下文注入路径
- **预期行为**: deterministic 测试证明 Run 2 的 request messages 包含 Run 1 的 final_answer
- **实际行为**: `test_real_runner_no_tool_two_turn_public_path` 走真实 LLM 验证两轮，但 `skip_if_provider_terminal_failed` 机制意味着网络问题时测试被跳过而非失败。deterministic 测试只验证单轮 final answer 和 idempotency，无任何多轮上下文传递断言
- **直接证据**: `test_public_open_host_multiturn_smoke.py` 仅一个测试且依赖真实 LLM。`test_public_tool_wiring_smoke.py` 验证 tool fact 进入 memory 但只验证单轮
- **影响**: Host 核心 contract（Session 历史连续性）无 deterministic 保护。回归时只有 manual smoke 能发现，且 smoke 可被 skip 掩盖
- **建议改法和验证点**: 新增 deterministic 测试：`FinalAnswerWorkerFactory` 记录两轮 request，断言 `requests[1]` 的 messages 包含 round 1 的 final answer 内容
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F6-defer-with-owner-[中]-`start_run` 大 payload descriptor 路径无测试

- **入口/函数**: `start_run` → `_create_accepted_admission_result` → `_append_user_input_event` → `_write_user_input_payload_if_needed`
- **文件(行号)**: `dayu/host/admission.py:2960-2990`
- **输入场景**: `start_run` 的 `display_text` 超 `payload_inline_threshold_bytes`
- **实际分支**: `_CreateAdmissionRequest.from_start_request`（line 2222）构造的 payload shape（`system_prompt=None`, `operation_kind="start_run"`）与 followup path 不同
- **预期行为**: `start_run` 大 payload 也走 descriptor 路径并可 round-trip
- **实际行为**: 只有 `test_followup_queue_spills_large_user_input_payload` 测试 followup path。`start_run` 的 descriptor 路径未测试
- **直接证据**: `test_admission_queue.py` 无 `test_start_run_spills_*` 测试
- **影响**: 低——共享 `_append_user_input_event` 路径，但 payload shape 差异可能导致 `_referenced_user_input_event_payload` 产出不同
- **建议改法和验证点**: 新增 `test_start_run_spills_large_user_input_payload`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F7-defer-with-owner-[中]-descriptor EventLog inline payload 正向字段断言缺失

- **入口/函数**: `_referenced_user_input_event_payload`（admission.py:2993-3009）
- **文件(行号)**: `dayu/host/admission.py:2993-3009`
- **输入场景**: 大 payload 走 descriptor 后的轻量 inline payload 字段
- **实际分支**: `_referenced_user_input_event_payload` 产出只含 `input_ref`/`input_digest`/`payload_ref`/`payload_digest`/`operation_kind`/`call_context_digest`
- **预期行为**: 测试正向断言 inline payload 包含哪些字段、不包含哪些字段
- **实际行为**: `test_followup_queue_spills_large_user_input_payload` 只有负向断言 `"long prompt" not in input_event.payload_json`，无正向字段断言
- **直接证据**: test_admission_queue.py:413 只检查 `"long prompt" not in`
- **影响**: 回归时若 `_referenced_user_input_event_payload` 错误内联全部字段或遗漏关键字段，现有测试无法捕获
- **建议改法和验证点**: 补充 `json.loads(input_event.payload_json)` 正向断言：必须含 `input_digest`/`operation_kind`/`call_context_digest`，不得含 `display_text`/`system_prompt`/`effective_execution_config`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F8-defer-with-owner-[中]-descriptor payload 损坏/缺失通过 RunInputBuilder 的错误传播路径未测试

- **入口/函数**: `payload_resolution.event_payload_object`（payload_resolution.py:31-55）
- **文件(行号)**: `dayu/host/payload_resolution.py:31-55`
- **输入场景**: descriptor 引用的 payload 在写入后被删除或损坏
- **实际分支**: descriptor missing / digest mismatch / sqlite payload missing → `HostDurableError`
- **预期行为**: `RunInputBuilder.build()` 传播 `HostDurableError` 并带有清晰消息
- **实际行为**: `test_payload_store.py` 在原语层测试 digest mismatch，但无集成测试通过 `RunInputBuilder` 触发这些错误
- **直接证据**: grep 无测试同时涉及 `RunInputBuilder` 和 `HostDurableError`
- **影响**: 生产 descriptor 损坏时，错误语义未被测试验证
- **建议改法和验证点**: 新增测试：seed descriptor-referenced event，删除 `TABLE_SQLITE_PAYLOADS` row，断言 `RunInputBuilder.build()` 抛 `HostDurableError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F9-defer-with-owner-[中]-`_consume_worker_events` CancelledError cleanup 路径未验证资源释放

- **入口/函数**: `_consume_worker_events`（dispatch.py:2546-2554）finally block
- **文件(行号)**: `dayu/host/dispatch.py:2546-2555`
- **输入场景**: scheduler close 取消 `_active_tasks`，`_consume_worker_events` 捕获 `CancelledError` 后 finally 释放资源
- **实际分支**: `CancelledError` → re-raise → finally: `handle.close()` + `token.release()`
- **预期行为**: 取消后 `handle.closed == True`，lane claim 释放
- **实际行为**: `test_active_cancel_dispatch.py:362` 测试 cooperative cancel（`RUN_CANCELLED` terminal），不测试 `CancelledError` finally 路径。无测试断言 `handle.closed` 或 lane claim 释放
- **直接证据**: `_CancelAwareHandle` mock 跟踪 `closed` 但无测试在 scheduler close 后检查
- **影响**: close-during-active 场景下 lane claim 泄漏或 handle 未关闭
- **建议改法和验证点**: 新增测试：创建有 active `_CancelAwareHandle`（terminal="hang"）的 scheduler，dispatch 后调用 `scheduler.close()`，断言 `handle.closed is True` 且 lane claim count 为 0
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F10-defer-with-owner-[中]-`HostEvent` public type 负面断言稀疏

- **入口/函数**: `_validate_host_event_terminal_payload`（api.py:2527-2544）
- **文件(行号)**: `dayu/host/api.py:2527-2544`
- **输入场景**: PROGRESS kind 搭配 terminal_status；FAILED kind 搭配 None terminal_status；kind/terminal_status 不匹配
- **实际分支**: line 2527-2531（PROGRESS + terminal）、line 2534-2536（kind/terminal mismatch）
- **预期行为**: 这些不合法组合被 `ValueError` 拒绝
- **实际行为**: `test_public_host_event.py` 只测试 SUCCEEDED/FAILED/CANCELLED 的合法组合。PROGRESS + terminal_status、kind/terminal_status mismatch、`HostFinalAnswerView(terminal_status=FAILED)` 三个 guard 全部未触发
- **直接证据**: `test_public_host_event.py` 仅 3 个测试，全部用合法参数构造
- **影响**: public type invariant guard 回归时无测试捕获
- **建议改法和验证点**: 新增 3 个负面测试：`test_progress_event_rejects_terminal_status`、`test_failed_event_requires_matching_terminal_status`、`test_host_final_answer_view_rejects_non_succeeded_status`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F11-defer-with-owner-[中]-`OpenHostOptions` 负面验证覆盖极稀疏

- **入口/函数**: `OpenHostOptions.__post_init__`（api.py:1027-1152）
- **文件(行号)**: `dayu/host/api.py:1027-1152`
- **输入场景**: 错误类型参数、空字符串、非正数、None 必填字段等
- **实际分支**: 30+ 验证分支
- **预期行为**: 每个 guard 分支有对应负面测试
- **实际行为**: `test_open_host_options_validate_lane_and_baseline`（test_public_open_host_options.py:247）只覆盖 `lane_claim_ttl <= heartbeat` 和 wrong `ordinary_run_baseline` type。其余 30+ 分支未测试
- **直接证据**: test_public_open_host_options.py 仅 6 个测试，大部分是 happy path
- **影响**: public opener 构造边界 guard 回归时，非法 Host config 可达 durable store
- **建议改法和验证点**: 端口化 `test_host_command_handle_options_rejects_*` 模式到 `OpenHostOptions`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F12-not-needed-[低]-stale guard failure_reason 断言深度不足

- **入口/函数**: `dispatch.py:940-955` stale check
- **文件(行号)**: `dayu/host/dispatch.py:940-955`, `tests/host/test_dispatch_scheduler.py:2189`
- **现有测试证据**: stale guard 测试验证 `CONTEXT_COMPACTION_FAILED` event 被写入
- **缺口**: 未断言 payload `failure_reason == "stale_compaction_result"`
- **为什么不需要 merge 前补**: 功能行为已被测试覆盖，断言深度不足但不构成 blocker
- **严重度**: 低

### F13-not-needed-[低]-`HostApiError`/`HostClosedError` 空消息拒绝未测试

- **入口/函数**: `HostApiError.__init__`（api.py:2598）, `HostClosedError.__init__`（api.py:2620）
- **现有测试证据**: 只测试 happy path
- **缺口**: `_require_non_empty(message)` 未被触发
- **为什么不需要 merge 前补**: 防御性 guard，空消息构造在实际调用链中不会发生
- **严重度**: 低

### F14-not-needed-[低]-compact 后 memory projection 保留性无 deterministic 测试

- **入口/函数**: compact 后 memory 注入下轮 request
- **现有测试证据**: `test_public_tool_wiring_smoke.py` 验证 tool fact 进入 memory，但不验证 compact 后保留
- **为什么不需要 merge 前补**: manual smoke 已覆盖此路径，且 compact 本身有独立测试
- **严重度**: 低

## Open Questions

- 无

## Residual Risk

- real runner matrix smoke 测试的 `skip_if_provider_terminal_failed` 机制在 provider 网络故障时将 `FAILED` terminal 静默转为 `pytest.skip`，掩盖了 Host 侧 FAILED 结构体的治理行为。建议后续将 Host 端 FAILED 的 `error_message` 格式和 `event` 结构纳入 deterministic 测试。
- `_dispatch_one` 的 `CancelledError` after lane acquire（dispatch.py:1685-1687）路径在 lane capacity 泄漏场景下有风险，但触发条件需要精确的取消时序竞态，属于低概率事件。

## 分类汇总

| 分类 | Finding 编号 |
|------|-------------|
| must-fix-before-merge | F1, F2, F3, F4, F5 |
| defer-with-owner | F6, F7, F8, F9, F10, F11 |
| not-needed | F12, F13, F14 |

## Subagent 覆盖记录

- admission payload inline/descriptor: subagent 1 (Explore)
- dispatch/RunInputBuilder/engine_ingest descriptor 消费: subagent 2 (Explore)
- compaction retry/dirty/stale guard: subagent 3 (Explore)
- public contract export 负面断言: subagent 4 (Explore)
- async cancellation/lifecycle/cleanup: subagent 5 (Explore)
- smoke vs deterministic 边界: subagent 6 (Explore)
- 主 reviewer 整合、去重、复核证据链、裁决 severity
