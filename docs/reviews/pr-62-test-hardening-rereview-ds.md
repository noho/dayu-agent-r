# PR-62 Merge-Before Test Hardening Re-Review (AgentDS)

## Scope

- Mode: Gateflow-governed re-review (read-only)
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/pr-62-test-hardening-rereview-ds.md`
- Review date: 2026-05-19
- Reviewer: AgentDS
- 约束：只读，不改代码，不 commit，不 push，不重新做完整 PR review
- 输入 artifacts:
  - `docs/reviews/pr-62-test-gap-mimo.md`（AgentMiMo）
  - `docs/reviews/pr-62-test-gap-ds.md`（AgentDS F1-F20）
  - `docs/reviews/pr-62-test-hardening-fix-codex.md`（AgentCodex 修复记录）
- 复核范围：当前未提交 diff（17 files, +1217/-24）相对上述 artifacts 的 accepted gap 覆盖

---

## 结论：PASS

所有 must-fix-before-merge 项（含 DS F1 production bug）均已修复且测试覆盖充分。无新增 regression 风险。存在 1 个 maintainability finding（代码重复）和若干已知 deferred 项，不阻塞 merge。

---

## Findings

### 1-已修复-[严重]-DS F1 production bug：dispatch effective decision 已 descriptor-aware

- **入口/函数**: `HostDispatchScheduler._effective_dispatch_decision` (dispatch.py:2152)
- **文件(行号)**: `dayu/host/dispatch.py:2149-2155`
- **原始问题**: `_payload_object(event)` 只做 `json.loads(event.payload_json)`，不跟随 `payload_ref` descriptor。大 payload 的 per-run overrides 被静默丢弃，回退到 host local fallback。
- **修复证据**:
  - `dispatch.py:2152`: `_payload_object(event)` → `event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")`
  - 新增测试 `test_descriptor_payload_dispatch_uses_per_run_override` (test_effective_execution_config.py:451-496)：
    - `payload_inline_threshold_bytes=4096` + `"descriptor prompt " * 600`（~10.8KB > 4KB）
    - 断言 `input_event.payload_ref is not None`
    - 断言 `resolved_payload["user_prompt"] == large_prompt`
    - 断言 `request.runner_spec.model == "descriptor-override-model"`（per-run override 生效）
    - 断言 `request.agent_policy == override_policy`
    - 断言 `request.messages[0].content == "descriptor system prompt"`
    - 断言 `request.runner_spec.model != "baseline-model"`（未回退到 fallback）
- **直接证据**: diff + 测试断言链完整覆盖 admission spill → descriptor 写入 → dispatch 读回 → Engine request 消费
- **影响**: production bug 已根除
- **修复质量**: 高。测试覆盖大 payload + per-run override 的端到端路径，能防止同类回归。
- **严重程度**: 严重（原始）→ 已修复

---

### 2-已修复-[高]-threshold=0 变更已撤回，公共契约束正数

- **入口/函数**: `_require_positive_int` (api.py:93-101), `OpenHostOptions.__post_init__` (api.py:1066-1068), `HostCommandHandleOptions.__post_init__` (api.py:1531-1535)
- **文件(行号)**: `dayu/host/api.py:93-101, 1066-1068, 1531-1535`
- **原始问题**: DS F2 要求 threshold=0 端到端测试，但 threshold=0 违反设计真源
- **修复证据**:
  - `_require_positive_int` 在 line 100 明确 `raises ValueError: value 小于或等于零时抛出`
  - `OpenHostOptions.__post_init__` (line 1066-1068) 和 `HostCommandHandleOptions.__post_init__` (line 1531-1535) 均调用 `_require_positive_int` 校验 `payload_inline_threshold_bytes`
  - `test_public_contracts.py:718`: `replace(_host_command_handle_options(), payload_inline_threshold_bytes=0)` → `pytest.raises(ValueError, match="payload_inline_threshold_bytes")` — threshold=0 被显式拒绝
  - `dayu/host/README.md:157`: "正数 payload inline 阈值约束"
  - 新增边界测试 `test_followup_queue_payload_inline_threshold_boundary` 使用正数阈值精确边界（`payload_size` 与 `payload_size-1`），不涉及 threshold=0
- **直接证据**: `_require_positive_int` 实现 + 公共契约测试 + README 措辞三者一致
- **影响**: EventLog inline guard 不可被 threshold=0 关闭
- **修复质量**: 高。公共契约、测试、文档三者对齐。
- **严重程度**: 高（原始）→ 已修复

---

### 3-已修复-[高]-admission 正边界、descriptor fail-closed、RunInputBuilder descriptor prompt

- **入口/函数**: `_write_user_input_payload_if_needed` (admission), `event_payload_object` (payload_resolution), `RunInputBuilder.build()` (run_input)
- **文件(行号)**: `dayu/host/admission.py:2960-2990`, `dayu/host/payload_resolution.py:17-55`, `dayu/host/run_input.py:525`
- **原始问题**: MiMo F1（正边界无测试）、DS F3/F4（fail-closed 无测试）、MiMo F2/F7（RunInputBuilder descriptor/字段收缩无测试）
- **修复证据**:
  - 正边界：`test_followup_queue_payload_inline_threshold_boundary` (test_admission_queue.py:425-460)，计算 canonical JSON UTF-8 长度 L，设 threshold=L 断言 `payload_ref is None`（inline），设 threshold=L-1 断言 `payload_ref is not None`（descriptor）
  - descriptor fail-closed：`test_event_payload_object_raises_when_descriptor_missing` (test_payload_store.py:647-672)，断言 `HostDurableError` + `"USER_INPUT_ACCEPTED payload descriptor is missing"`
  - sqlite payload row fail-closed：`test_event_payload_object_raises_when_sqlite_payload_row_missing` (test_payload_store.py:675-727)，绕过 FK 删除 row，断言 `HostDurableError` + `"USER_INPUT_ACCEPTED sqlite payload row is missing"`
  - RunInputBuilder descriptor prompt：`test_current_user_message_resolves_descriptor_payload` (test_run_input_builder.py:1065-1087)，断言 `input_event.payload_ref is not None`、`request.messages[-1].content == "descriptor durable prompt"`
  - inline payload 字段收缩正向断言：在 `test_followup_queue_spills_large_user_input_payload` 中新增 `assert "display_text" not in inline_payload` / `"user_prompt" not in inline_payload` / `"system_prompt" not in inline_payload` / `"effective_execution_config" not in inline_payload` / `"effective_tool_set" not in inline_payload`
- **直接证据**: 5 个新增/增强测试，覆盖了正边界、两种 fail-closed 路径、RunInputBuilder descriptor 消费链和 inline payload 字段收缩
- **影响**: admission descriptor 的写入/读回/失败全路径被保护
- **修复质量**: 高。
- **严重程度**: 高（原始）→ 已修复

---

### 4-已修复-[高]-compaction quality rejection/hard threshold retry、proactive integration、stale failure_reason

- **入口/函数**: `run_compaction_operation` (compaction_operation), `_execute_proactive_compaction` (dispatch)
- **文件(行号)**: `dayu/host/compaction_operation.py:117-163`, `dayu/host/dispatch.py:916-998`
- **原始问题**: MiMo F3/F4（quality reject/hard threshold retry 无测试）、DS F5/F6（同上+集成测试缺失）、DS F7（stale failure_reason 断言缺失）
- **修复证据**:
  - quality rejection retry (operation 层): `test_run_compaction_operation_retries_quality_rejection` (test_compaction_operation.py:233-248)，`_QualityRejectOnceCompactor` 首次返回 `retained_current_user_input_ref="wrong-input"` 触发 quality rejection，断言 `calls==2`、`failure_category=="quality_check_rejected"`、`repairable is True`、`accepted_candidate is not None`
  - hard threshold retry (operation 层): `test_run_compaction_operation_retries_hard_threshold_after_compact` (test_compaction_operation.py:251-270)，`_HardThresholdOnceCompactor` 首次 `budget_after_compact >= hard_threshold_tokens`，断言 `failure_category=="hard_threshold_after_compact"`、`repairable is True`、`accepted_candidate is not None`
  - proactive integration: `test_proactive_compaction_retries_quality_rejection_before_accept` (test_dispatch_scheduler.py:2262-2324)，完整 scheduler 路径，断言 `calls==2`、`CONTEXT_COMPACTION_ATTEMPT_REJECTED` count==1、`CONTEXT_COMPACTED` count==1、事件顺序 rejected < compacted < RUN_STARTED、Run 终态 RUNNING
  - stale failure_reason: 在 `test_compaction_stale_result_does_not_write_compacted_event` 中新增断言 `_event_payload(failed)["failure_reason"] == "stale_compaction_result"` (test_dispatch_scheduler.py:2260-2263)
- **直接证据**: 3 个新增测试 + 1 个增强测试，覆盖了 compaction retry loop 的全部三种 rejection 路径（proposal exception、quality rejection、hard threshold）在 operation 层和 scheduler 集成层
- **影响**: compaction semantic repair loop 的核心价值承诺被测试保护
- **修复质量**: 高。
- **严重程度**: 高（原始）→ 已修复

---

### 5-已修复-[高]-deterministic two-turn continuity + memory/run_input terminal summary descriptor

- **入口/函数**: `submit_followup` → dispatch → `RunInputBuilder.build()` / `ConversationMemoryProjectionConsumer`
- **文件(行号)**: `dayu/host/durable/memory.py:181-280`（新增 `_payload_with_terminal_summary`、`_sqlite_payload_object`、`_assistant_summary_from_payload`），`dayu/host/memory.py:1352-1373`（新增 `_assistant_summary_from_payload`），`dayu/host/run_input.py:1925-2013`（新增 `_payload_with_terminal_summary`、`_sqlite_payload_object`）
- **原始问题**: MiMo F5（多轮上下文连续性无 deterministic 测试）、Codex artifact 记录的 terminal summary descriptor 内容未进入 memory continuity
- **修复证据**:
  - deterministic two-turn: `test_deterministic_two_turn_request_contains_prior_final_answer` (test_public_open_host_multiturn_smoke.py:830-870)，使用 `FinalAnswerWorkerFactory`（deterministic），两轮 `submit_followup`，断言第二轮 `factory.requests[1].messages` 中包含 `f"final:1:{first.accepted_run_id}"`（第一轮 final answer 内容），且 `second_contents[-1] == "second prompt"`
  - memory terminal summary: `_payload_with_terminal_summary`（durable/memory.py:204-239）在 memory projection 消费 `RUN_SUCCEEDED` 时，若 inline payload 无直接 `content`/`final_answer`/`summary_text`，则跟随 `terminal_summary_ref` + `terminal_summary_digest` descriptor 从 SQLite PayloadStore 读取 terminal summary，提取 `content` 字段合并进 payload
  - RunInputBuilder inline delta: `_payload_with_terminal_summary`（run_input.py:1925-1970）在 `_memory_projection_event_from_row` 中同理解析 terminal summary descriptor，使 memory delta 的 continuity item 包含可展示 assistant final content
  - `_assistant_summary_from_payload` 支持递归遍历嵌套 `summary` field（memory.py:1352-1373, durable/memory.py:254-274, run_input.py:2407-2418），覆盖 `final_answer` → `content` → `summary_text` → nested `summary` 的回退链
- **直接证据**: 新增 deterministic 测试 + 三处生产代码改动均沿正确的 descriptor 跟随路径
- **影响**: Host 核心 contract（Session 历史连续性）从仅 manual smoke 验证变为 deterministic 测试保护
- **修复质量**: 高，但存在 maintainability 顾虑（见 Finding 8）
- **严重程度**: 高（原始）→ 已修复

---

### 6-已修复-[中]-scheduler close/wake、retry/replay NOT_FOUND/幂等冲突、steer idempotency/detail

- **入口/函数**: `HostDispatchScheduler.wake_dispatch/wake_queue_promotion/close` (dispatch), `HostAdmissionService.retry_run/replay_run` (admission), `_require_steer_target_run` (admission)
- **文件(行号)**: `dayu/host/dispatch.py:590-615, 1515-1516`, `dayu/host/admission.py:640-679, 3667-3715`
- **原始问题**: DS F14/F15（close 后 wake RuntimeError / close 幂等）、DS F16/F17（retry/replay NOT_FOUND / 幂等冲突）、DS F18（steer 幂等/SteerConflictDetail）
- **修复证据**:
  - scheduler close/wake + 幂等: `test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent` (test_dispatch_scheduler.py:2186-2213)，断言 close 后 `wake_dispatch` 和 `wake_queue_promotion` 均抛出 `RuntimeError("HostDispatchScheduler is closed")`，且重复 close 不抛异常
  - retry/replay NOT_FOUND: `test_retry_and_replay_missing_source_run_return_not_found` (test_public_retry_replay.py:909-937)，断言 `retry_run("missing-run", ...)` 和 `replay_run("missing-run", ...)` 均抛出 `HostApiErrorCode.NOT_FOUND`
  - retry 幂等冲突: `test_retry_run_same_client_request_id_different_digest_conflicts` (test_public_retry_replay.py:940-973)，第一次 retry 成功，第二次同 `client_request_id` 不同 `reason` 返回 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`
  - steer 幂等重放: `test_steer_replays_same_client_request_id_idempotently` (test_public_steer.py:996-1029)，断言同 key 同语义重放返回同一 `accepted_run_id` 和 `accepted_input_ref`
  - SteerConflictDetail: `_require_steer_target_run` (admission.py:3667-3715) 三个 `INVALID_STATE` 分支均填充 `detail=_steer_conflict_detail(...)`；`_steer_conflict_detail` (admission.py:3718-3738) 构造完整 `SteerConflictDetail`；现有测试 `test_steer_terminal_race_rejects_non_active_target` 新增 `assert isinstance(detail, SteerConflictDetail)` + `target_run_id`/`target_run_status`/`current_active_run_id`/`current_active_run_status` 字段断言 (test_public_steer.py:210-213)
- **直接证据**: 5 个新增测试 + 1 个增强测试 + 生产代码 detail 填充
- **影响**: public contract 的 close 语义、retry/replay 负面路径、steer 幂等与冲突详情均被测试保护
- **修复质量**: 高。
- **严重程度**: 中（原始）→ 已修复

---

### 7-已修复-[低]-README/tests README 已同步到当前实现边界

- **入口/函数**: README documentation
- **文件(行号)**: `dayu/host/README.md`, `tests/README.md`
- **修复证据**:
  - `dayu/host/README.md`:
    - Conversation Memory 段新增：`RUN_SUCCEEDED` terminal summary descriptor 在 memory projection 与 RunInputBuilder inline delta 中读取 SQLite payload descriptor 的描述（准确反映当前行为）
    - EventLog 段："正数 payload inline 阈值约束"；"descriptor 缺失、digest 不匹配或 SQLite payload row 缺失都会 fail closed"；"dispatch" 加入 descriptor 跟随消费者列表
    - admission 命令段：`submit_followup_steer` 新增 `SteerConflictDetail` 描述
  - `tests/README.md`:
    - public run API 段：新增 "steer 幂等重放 / SteerConflictDetail 负面详情"、"retry_run 缺失源 NOT_FOUND / 幂等冲突"、"replay_run 缺失源 NOT_FOUND"
    - public smoke 段：新增 "deterministic 两轮 final answer continuity"
    - durable foundation 段：新增 "payload inline threshold 正数精确边界"、"payload descriptor 读取与 descriptor / sqlite row 缺失 fail-closed"、"compaction operation quality rejection retry / hard-threshold retry"、"terminal summary descriptor continuity"、"RunInputBuilder descriptor prompt"、"scheduler close 后 wake RuntimeError / close 幂等"、"proactive compact rejection retry / stale failure_reason"
  - 无残留旧术语、无"未来设计"、无越界职责
- **直接证据**: diff 中 README 改动与生产代码/测试改动一一对应
- **影响**: 文档准确反映当前实现
- **修复质量**: 高。
- **严重程度**: 低 → 已修复

---

### 8-部分修复-[中]-terminal summary descriptor 解析在 durable/memory 与 run_input 间存在显著代码重复

- **入口/函数**: `_payload_with_terminal_summary`, `_sqlite_payload_object`, `_assistant_summary_from_payload`
- **文件(行号)**:
  - `dayu/host/durable/memory.py:204-280`（~75 行）
  - `dayu/host/run_input.py:1925-2013`（~90 行）
  - `dayu/host/memory.py:1352-1373`（~20 行）
- **输入场景**: 未来修改 terminal summary 解析逻辑（如新增 fallback field、修改 descriptor 跟随语义）
- **实际分支**: N/A（当前行为正确）
- **预期行为**: terminal summary descriptor 解析逻辑应有单一真源，或提取为公共 helper
- **实际行为**: `_payload_with_terminal_summary`、`_sqlite_payload_object` 在 `durable/memory.py` 和 `run_input.py` 中各有一份近乎相同的实现（~65 行重复）。`_assistant_summary_from_payload` 在 `memory.py`、`durable/memory.py` 和 `run_input.py` 中各有一份语义相同但 helper 不同的实现。
- **直接证据**:
  - `durable/memory.py:204-280` vs `run_input.py:1925-2013`：`_payload_with_terminal_summary` 和 `_sqlite_payload_object` 逻辑几乎逐行对应，仅 helper 函数名不同（`_optional_str` vs `_optional_payload_text`）
  - `memory.py:1352-1373` vs `durable/memory.py:254-274` vs `run_input.py:2407-2418`：`_assistant_summary_from_payload` 三份实现，递归逻辑相同，仅底层 value reader 不同
- **影响**: 后续修改 terminal summary 解析语义时需同步修改 2-3 处，漏改任一位置会导致 memory projection 与 RunInputBuilder delta 的行为分歧
- **建议改法和验证点**: 将 `_payload_with_terminal_summary` 和 `_sqlite_payload_object` 提取到 `dayu.host.durable.memory` 或新的公共 helper 模块，`run_input.py` 通过 import 复用。公共函数接收 `transaction` 和 `event_type`/`payload` 作为参数，不耦合具体调用上下文。
- **修复风险（低）**: 纯重构，不改变行为
- **严重程度（中）**: 不阻塞 merge，但应在后续 phase 清理

---

## 未覆盖的已知 Deferred 项（非 blocker）

以下项在 MiMo/DS artifacts 中标记为 defer-with-owner，且 Codex artifact 确认未在本次修复中覆盖。均不阻塞 merge。

| # | 来源 | 描述 | 严重度 |
|---|------|------|--------|
| D1 | DS F9/MiMo F6 | 多进程 admission payload spill 场景 | 低 |
| D2 | DS F10 | `_effective_dispatch_decision_from_payload` start_run fallback 单元测试 | 中 |
| D3 | DS F11 | `system_prompt=None` 消息布局集成断言 | 低 |
| D4 | DS F12 | stale guard `input_event_sequence` 条件测试 | 低 |
| D5 | DS F13 | `run is None` stale 分支测试 | 低 |
| D6 | MiMo F9 | `_consume_worker_events` CancelledError finally 资源释放测试 | 中 |
| D7 | MiMo F10 | `HostEvent` public type 负面断言扩展 | 中 |
| D8 | MiMo F11 | `OpenHostOptions` 全量负面验证矩阵 | 中 |
| D9 | DS F8 | `_referenced_user_input_event_payload` 显式字段白名单（已在 Finding 3 中以负向断言形式覆盖） | 低 |

---

## Production Bug 修复验证：DS F1 根因分析

### 根因链条（已确认修复）

```
用户 submit_followup(display_text > 4KB, runner_spec=override, agent_policy=override)
  → admission._write_user_input_payload_if_needed: len(encoded) > threshold
  → PayloadStore.write_sqlite_payload() + descriptor
  → EventLog.payload_json = _referenced_user_input_event_payload()  [不含 effective_execution_config]
  → dispatch._effective_dispatch_decision: 原用 _payload_object(event)
    → json.loads(event.payload_json) → 只有 6 个轻量字段
    → payload.get("effective_execution_config") → None
    → 静默回退到 fallback_policy_snapshot (host local 默认值)
```

### 修复后链路（已验证）

```
用户 submit_followup(display_text > 4KB, runner_spec=override, agent_policy=override)
  → admission._write_user_input_payload_if_needed: spill → descriptor
  → dispatch._effective_dispatch_decision: event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")
    → payload_ref is not None → read_payload_descriptor → PayloadStore 读回完整 payload
    → payload["effective_execution_config"] → 用户指定的 override
    → Engine request 携带正确的 runner_spec / agent_policy / system_prompt
```

测试 `test_descriptor_payload_dispatch_uses_per_run_override` 覆盖了此完整链路。

---

## Open Questions

- OQ1（来自 DS）：`_effective_dispatch_decision` 的 descriptor-aware 修复是否也影响 `start_run` 路径？`start_run` 的 `effective_execution_config` 在 admission 中设为 `None`——大 payload start_run 的 dispatch 行为在本次未单独测试（deferred D2），但因为与 followup 共享 `_effective_dispatch_decision` 入口，修复应同时覆盖。
- OQ2（本次复查）：`durable/memory.py` 和 `run_input.py` 中 `_sqlite_payload_object` 的 error message 固定以 "terminal summary" 为前缀，但函数签名是通用的。若未来其他 event type 也需要 descriptor 跟随，error message 会产生误导。建议重构时一并修正。

---

## Residual Risk

1. **代码重复风险**（Finding 8）：`_payload_with_terminal_summary` / `_sqlite_payload_object` / `_assistant_summary_from_payload` 在 2-3 处重复，后续修改可能遗漏同步。
2. **多进程 descriptor 并发**（deferred D1）：`PayloadStore` 在跨进程并发 spill + read-back 场景下未在 stress 测试中验证。
3. **组合交互路径**：compaction quality retry + descriptor payload dispatch 的组合路径（compact 触发 catch-up dispatch，且 catch-up 的 RunInputBuilder 消费 descriptor payload）未在集成测试中显式覆盖。概率低但生产高负载下可能暴露。
4. **terminal summary artifact descriptor**：Codex artifact 提到 "Artifact-backed terminal summary descriptors are still fail-closed because current Engine terminal summaries are written as SQLite payload descriptors." 当前实现只处理 SQLite payload descriptor，若未来 Engine 改用 artifact descriptor，需要新增解析路径。

---

## 复核方法说明

- 逐条对照 MiMo F1-F14、DS F1-F20 与 Codex artifact 的 claim，沿实际 diff 代码路径验证修复是否真实存在、测试断言是否充分。
- 所有 "已修复" 结论均附直接证据（diff 行号、测试函数名、断言内容）。
- 未发现 Codex artifact 声称修复但实际未修复的情况。
- 未发现测试断言不足以证明修复目标的情况。

---

# 补充 Re-Review：Maintainability Cleanup 去重验证

## Scope

- Mode: Gateflow-governed supplementary re-review (read-only)
- 触发: PASS 后的 maintainability cleanup — terminal summary descriptor 解析与 assistant summary 提取去重
- 复核文件:
  - `dayu/host/terminal_summary_payload.py`（新增）
  - `dayu/host/payload_resolution.py`（新增 `sqlite_payload_object`）
  - `dayu/host/durable/memory.py`（去重后）
  - `dayu/host/run_input.py`（去重后）
  - `dayu/host/memory.py`（去重后）
  - `docs/reviews/pr-62-test-hardening-fix-codex.md`（更新）
- 约束：只读，不改代码

## 结论：PASS

去重行为等价，无 import cycle，无 durable schema 依赖泄漏，无重复 helper 残留。`text_policy` 差异（`LENIENT_NON_EMPTY` / `STRICT_NON_EMPTY` / `STRICT_ALLOW_EMPTY`）是各调用上下文的语义需求，不是去重遗漏。原 Finding 8 已降级为 residual risk。

---

## 补充 Findings

### S1-已修复-[中]-`sqlite_payload_object` 从 3 份重复收敛为 `payload_resolution.py` 单一真源

- **入口/函数**: `sqlite_payload_object`
- **文件(行号)**: `dayu/host/payload_resolution.py:41-80`
- **去重前**: 同段 descriptor 跟随逻辑在 `durable/memory.py`、`run_input.py`、`payload_resolution.py` 中各有一份，合计 ~70 行重复代码
- **去重后**:
  - `payload_resolution.py:41-80`：共享 `sqlite_payload_object(transaction, *, payload_ref, payload_digest, payload_label)` — 参数化错误消息前缀
  - `event_payload_object` (payload_resolution.py:17-38) 在跟随 descriptor 时委托给 `sqlite_payload_object`（line 33-38），不再内联 descriptor 逻辑
  - `durable/memory.py`：通过 `from dayu.host.payload_resolution import sqlite_payload_object` 复用，自身不再包含 descriptor → SQLite 读回逻辑
  - `run_input.py`：通过 `from dayu.host.payload_resolution import sqlite_payload_object` 复用，自身不再包含 descriptor → SQLite 读回逻辑
- **行为等价验证**:
  - descriptor 缺失 → `HostDurableError(f"{payload_label} payload descriptor is missing")` ✓
  - `payload_kind` 非 SQLITE → `HostDurableError(f"{payload_label} payload must be sqlite payload")` ✓
  - digest 不匹配 → `HostDurableError(f"{payload_label} payload digest mismatch")` ✓
  - `sqlite_payload_id` 缺失 → `HostDurableError(f"{payload_label} sqlite payload id is missing")` ✓
  - sqlite row 缺失 → `HostDurableError(f"{payload_label} sqlite payload row is missing")` ✓
  - JSON 解析失败 → `HostDurableError(f"{payload_label} payload JSON is invalid")` ✓
  - JSON 非 object → `HostDurableError(f"{payload_label} payload JSON must be object")` ✓
- **直接证据**: `payload_resolution.py` diff 将 `event_payload_object` 体量从 ~50 行缩减到 ~38 行（提取 `sqlite_payload_object`），`durable/memory.py` 和 `run_input.py` 各删除了自己的 `_sqlite_payload_object` 实现
- **修复质量**: 高。单一真源，参数化 payload_label，行为完全等价。
- **严重程度**: 中（原始 Finding 8 重复）→ 已修复

---

### S2-已修复-[中]-`assistant_summary_from_payload` 从 3 份重复收敛为 `terminal_summary_payload.py` 单一真源

- **入口/函数**: `assistant_summary_from_payload`
- **文件(行号)**: `dayu/host/terminal_summary_payload.py:31-58`
- **去重前**: `_assistant_summary_from_payload` 在 `memory.py`、`durable/memory.py`、`run_input.py` 中各有一份语义相同但 helper 不同的实现，field fallback 链（`final_answer` → `content` → `summary_text` → nested `summary`）完全一致
- **去重后**:
  - `terminal_summary_payload.py:31-58`：共享 `assistant_summary_from_payload(payload, *, text_policy)` — 单一真源
  - `PayloadSummaryTextPolicy` 枚举（line 18-28）参数化三种读取策略：
    - `STRICT_ALLOW_EMPTY`：字段非文本抛错，空文本作为有效摘要
    - `STRICT_NON_EMPTY`：字段非文本抛错，空文本按缺失处理
    - `LENIENT_NON_EMPTY`：字段非文本/空文本均按缺失处理
  - `memory.py`：使用 `LENIENT_NON_EMPTY`（最宽松——memory 层消费已由 durable 层校验的数据）
  - `durable/memory.py::_payload_with_terminal_summary`：使用 `STRICT_ALLOW_EMPTY`（memory projection 上下文，空 content 是合法的 "无内容" 标记）
  - `run_input.py::_payload_with_terminal_summary`：使用 `STRICT_NON_EMPTY`（RunInputBuilder 上下文，空文本不应注入为 assistant 消息）
  - `run_input.py::_continuity_message_from_event`：使用 `STRICT_NON_EMPTY`（同上）
- **text_policy 差异分析**:
  - 三个调用上下文使用三种不同策略，是有意设计而非去重遗漏
  - `LENIENT_NON_EMPTY` 在 memory.py 中是正确选择：memory 层已在 `_optional_payload_str` 中原生支持 lenient 行为（非字符串返回 None）
  - `STRICT_ALLOW_EMPTY` vs `STRICT_NON_EMPTY` 的区别：memory projection 允许空 content（标记 "无内容"），RunInputBuilder 不允许（避免注入空 assistant 消息）
- **行为等价验证**:
  - field fallback 链：`final_answer` → `content` → `summary_text` → nested `summary` ✓（三份原始实现完全一致）
  - 递归 nested `summary`：行为保持不变 ✓
  - `memory.py._assistant_conclusion_from_projection_event`：旧代码只检查 `final_answer` 单字段，新代码走完整 fallback 链 — 行为增强（非回归）
- **直接证据**: `run_input.py` 删除了 `_assistant_summary_from_payload` 函数（原 line 2309-2327），`memory.py` 删除了 `_PAYLOAD_FIELD_FINAL_ANSWER` 常量并从 `terminal_summary_payload` 导入
- **修复质量**: 高。`PayloadSummaryTextPolicy` 枚举把三种语义差异显式化，未来新增 call site 必须显式选择策略。
- **严重程度**: 中（原始 Finding 8 重复）→ 已修复

---

### S3-已修复-[低]-`_PAYLOAD_FIELD_FINAL_ANSWER` 从 `memory.py` 清理，无残留

- **入口/函数**: `dayu/host/memory.py` 模块级常量
- **文件(行号)**: `dayu/host/memory.py`（diff 删除 line 59 `_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"`）
- **去重前**: `_PAYLOAD_FIELD_FINAL_ANSWER` 在 `memory.py` 中定义，仅在 `_assistant_conclusion_from_projection_event` 中使用
- **去重后**: `memory.py` 不再直接引用 `_PAYLOAD_FIELD_FINAL_ANSWER`，通过 `assistant_summary_from_payload` 间接使用（该函数内部定义在 `terminal_summary_payload.py:13`）
- **残留检查**: `grep '_PAYLOAD_FIELD_FINAL_ANSWER' dayu/host/memory.py` → 零匹配 ✓
- **`_PAYLOAD_FIELD_SUMMARY_TEXT`**: 仍在 `memory.py:62` 保留，因为该常量在 memory.py 中用于其他函数（lines 1959, 1972, 2237，与 terminal summary 无关），正确保留
- **修复质量**: 高。
- **严重程度**: 低 → 已修复

---

### S4-证据失效-[中]-原 Finding 8（代码重复）已修复，降级为 residual risk

- **入口/函数**: 原 `_payload_with_terminal_summary` / `_sqlite_payload_object` / `_assistant_summary_from_payload` 跨文件重复
- **文件(行号)**: N/A（已去重）
- **原问题**: `durable/memory.py` 和 `run_input.py` 各有 ~65 行近乎相同的 `_sqlite_payload_object` 实现，`_assistant_summary_from_payload` 在 3 处重复
- **去重后状态**:
  - 重量级 I/O 逻辑（`sqlite_payload_object`）→ 单一真源 `payload_resolution.py`
  - 纯提取逻辑（`assistant_summary_from_payload`）→ 单一真源 `terminal_summary_payload.py`
  - 剩余 `_payload_with_terminal_summary` 两份实例是 thin orchestrator（各 ~35 行），差异在于：
    1. 输入类型不同（`ProjectionEventView` vs `EventLogRow`）
    2. `text_policy` 不同（`STRICT_ALLOW_EMPTY` vs `STRICT_NON_EMPTY`）
    3. payload 访问方式不同（`event.payload` vs `_payload_object(row)`）
  - 这两份轻量 wrapper 的差异是调用上下文的本征需求，不可进一步合并
- **直接证据**: `payload_resolution.py` 新增 `sqlite_payload_object`（~40 行），`terminal_summary_payload.py` 新增 `assistant_summary_from_payload` + `PayloadSummaryTextPolicy`（~95 行），`durable/memory.py` 和 `run_input.py` 各自缩减 ~50-65 行
- **影响**: 未来修改 descriptor 跟随或 summary 提取逻辑只需改一处
- **严重程度**: 中（原始）→ 已修复，降级为 residual risk

---

## 依赖图验证（无 import cycle）

```
dayu.contracts.json_value           dayu.host.durable.errors
            ↓                                ↓
   dayu.host.terminal_summary_payload  ←──  (leaf, no host imports)

dayu.host.durable.{schema, payload, event_log, transaction}
            ↓
   dayu.host.payload_resolution  (sqlite_payload_object, event_payload_object)
        ↓                    ↓
dayu.host.durable.memory  dayu.host.run_input
        ↓
   dayu.host.memory  ←──  imports terminal_summary_payload (LENIENT_NON_EMPTY)
```

- `terminal_summary_payload.py` 是纯 leaf 模块，只依赖 `dayu.contracts` 和 `dayu.host.durable.errors`
- `payload_resolution.py` 不导入 `terminal_summary_payload` 或 `memory`
- `memory.py` 通过 `terminal_summary_payload` 使用 `assistant_summary_from_payload`，不直接依赖 `dayu.host.durable.schema` 或 `dayu.host.durable.payload`
- 无 `dayu.host.durable.*` → `dayu.host.memory` 的反向导入
- 所有导入遵循 `durable → payload_resolution → (durable.memory / run_input) → memory` 方向 ✓

## 去重统计

| 符号 | 去重前副本数 | 去重后副本数 | 单一真源位置 |
|------|------------|------------|------------|
| `sqlite_payload_object` | 3 (durable.memory, run_input, payload_resolution) | 1 | `payload_resolution.py` |
| `assistant_summary_from_payload` | 3 (memory, durable.memory, run_input) | 1 | `terminal_summary_payload.py` |
| `_payload_with_terminal_summary` | 2 (durable.memory, run_input) | 2 | thin wrapper, 输入类型与 text_policy 不同 |
| `_PAYLOAD_FIELD_FINAL_ANSWER` | 2 (memory, terminal_summary_payload) | 1 | `terminal_summary_payload.py` |

## Updated Residual Risk

原 Finding 8（代码重复）已修复。更新后的 residual risks：

1. **`_payload_with_terminal_summary` wrapper 残留**（低风险）：两个 thin wrapper 因输入类型和 `text_policy` 不同无法合并，但体量小（各 ~35 行）且核心逻辑已共享。未来若 `ProjectionEventView` 和 `EventLogRow` 的 payload 访问统一，可进一步去重。
2. **多进程 descriptor 并发**（deferred D1）：未变更。
3. **组合交互路径**（低概率）：未变更。
4. **terminal summary artifact descriptor**：未变更。
5. **`_optional_str` vs `_optional_payload_text` 不对称**（低风险）：`durable/memory.py` 使用 strict `_optional_str`（非字符串抛错），`run_input.py` 使用 lenient `_optional_payload_text`（非字符串返回 None）读取 `terminal_summary_ref`/`terminal_summary_digest`。两者在 `None`/缺失时行为一致（返回 None → 跳过 descriptor 解析），仅在非字符串时不同（strict 抛错 vs lenient 静默继续）。不构成功能 bug，但建议统一为 strict（非字符串的 ref/digest 始终是数据损坏）。
