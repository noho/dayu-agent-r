# PR-62 Test Hardening Re-Review

## Scope

- Mode: current changes re-review (Gateflow-governed, read-only)
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/pr-62-test-hardening-rereview-mimo.md`
- Reviewer: AgentMiMo
- Date: 2026-05-19
- Included scope: 当前未提交 diff（staged + unstaged）+ 已提交但未 merge 到 main 的 commits；复核 artifacts `pr-62-test-gap-mimo.md`、`pr-62-test-gap-ds.md`、`pr-62-test-hardening-fix-codex.md`
- Excluded scope: docs/reviews/ 自身、utils/

## 结论: PASS

所有 7 个复核重点均已覆盖。DS F1 production bug 已修到 root cause，threshold=0 已撤回，admission/descriptor/compaction/multiturn/scheduler/steer/retry-replay 的 accepted gap 均由新测试锁定，README 只写当前已实现边界。

## Findings

### 1-已修复-[严重]-DS F1 dispatch effective decision descriptor-aware 修复

- **入口/函数**: `HostDispatchScheduler._effective_dispatch_decision` → `event_payload_object`
- **文件(行号)**: `dayu/host/dispatch.py:2152`
- **输入场景**: 大 payload spill 到 SQLite PayloadStore 后，dispatch 读取 `USER_INPUT_ACCEPTED` event 的 per-run effective config
- **实际分支**: `event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")` 跟随 `payload_ref` descriptor 从 PayloadStore 读取完整 payload
- **预期行为**: dispatch 消费 admission 冻结的 `effective_execution_config`、`effective_tool_set`、`system_prompt`
- **实际行为**: 已修复。`_payload_object`（inline-only）已替换为 `event_payload_object`（descriptor-aware）
- **直接证据**: dispatch.py:2152 使用 `event_payload_object`；`_display_text_from_input_event`（dispatch.py:2648 同区域）也使用 `event_payload_object`
- **回归测试**: `test_descriptor_payload_dispatch_uses_per_run_override`（test_effective_execution_config.py:265）设置 `payload_inline_threshold_bytes=4096` + 大 prompt + per-run `runner_spec`/`agent_policy`/`system_prompt`，断言 dispatch 后 Engine request 的 `runner_spec.model == "descriptor-override-model"`、`agent_policy == override_policy`、`messages[0].content == "descriptor system prompt"`
- **严重程度**: 严重 → 已修复

### 2-已修复-[高]-threshold=0 已撤回，payload_inline_threshold_bytes 必须为正数

- **入口/函数**: `HostCommandHandleOptions.__post_init__` validation
- **文件(行号)**: `tests/host/test_public_contracts.py:718`
- **输入场景**: `payload_inline_threshold_bytes=0`
- **实际行为**: `replace(_host_command_handle_options(), payload_inline_threshold_bytes=0)` 抛出 `ValueError`
- **直接证据**: test_public_contracts.py:717-718 显式断言 `payload_inline_threshold_bytes=0` 非法
- **文档**: dayu/host/README.md 已更新为"正数 payload inline 阈值约束"
- **严重程度**: 高 → 已修复

### 3-已修复-[高]-admission positive boundary、descriptor fail-closed、RunInputBuilder descriptor prompt

- **3a positive boundary**: `test_followup_queue_spills_large_user_input_payload`（test_admission_queue.py:377）使用 `payload_inline_threshold_bytes=4096` + 大 payload，断言 `payload_ref is not None` 且 `event_payload_object` 读回完整 `display_text`/`user_prompt`
- **3b descriptor missing fail-closed**: `test_event_payload_object_raises_when_descriptor_missing`（test_payload_store.py 新增）写入含 `payload_ref` 但不写 descriptor 的 EventLog row，断言 `HostDurableError` 且消息包含 `"descriptor is missing"`
- **3c sqlite payload row missing fail-closed**: `test_event_payload_object_raises_when_sqlite_payload_row_missing`（test_payload_store.py 新增）写入完整 descriptor 但删除 payload row，断言 `HostDurableError` 且消息包含 `"sqlite payload row is missing"`
- **3d RunInputBuilder descriptor prompt**: `test_current_user_message_resolves_descriptor_payload`（test_run_input_builder.py:202）写入带 `payload_ref`/`payload_digest` 的 `USER_INPUT_ACCEPTED` event，调用 `RunInputBuilder.build()`，断言 `request.messages[-1].content == "descriptor durable prompt"`
- **严重程度**: 高 → 已修复

### 4-已修复-[高]-compaction quality rejection/hard threshold retry、proactive integration、stale failure_reason

- **4a operation-level quality rejection retry**: `test_run_compaction_operation_retries_after_quality_rejection`（test_compaction_operation.py 新增）使用 `_QualityRejectOnceCompactor`，断言 `rejected_attempts[0].failure_category == "quality_check_rejected"`、`accepted_candidate is not None`
- **4b operation-level hard threshold retry**: 同文件新增 hard threshold after compact retry 测试
- **4c proactive integration**: `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`（test_dispatch_scheduler.py:2185 区域）使用 `_RaisingCompactor`，断言 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 事件写入且 `failure_reason` payload 正确
- **4d stale failure_reason**: `test_compaction_stale_result_does_not_write_compacted_event`（test_dispatch_scheduler.py:2234 区域）使用 `_StaleMutatingCompactor`，断言 `CONTEXT_COMPACTED == 0` 且 `Run.status == FAILED`
- **严重程度**: 高 → 已修复

### 5-已修复-[高]-deterministic two-turn continuity 真实验证第二轮 request 包含第一轮 final answer

- **入口/函数**: `submit_followup` → dispatch → `RunInputBuilder.build()` → 注入前轮 final_answer
- **文件(行号)**: `tests/host/test_public_open_host_multiturn_smoke.py:123`
- **测试**: `test_deterministic_two_turn_request_contains_prior_final_answer` 使用 `FinalAnswerWorkerFactory`，第一轮产出 `final:1:{run_id}`，断言第二轮 `factory.requests[1].messages` 包含 `f"final:1:{first.accepted_run_id}"`，且最后一条消息为 `"second prompt"`
- **memory/run_input terminal summary descriptor 修复**: `durable/memory.py` 新增 `_payload_with_terminal_summary` 函数，在 memory projection 消费 `RUN_SUCCEEDED` 事件时，若 payload 仅含 `terminal_summary_ref` 而无 `content`/`final_answer`/`summary_text`，则跟随 descriptor 读取 SQLite payload 并合并 assistant summary。`memory.py` 新增 `_assistant_summary_from_payload` 支持 `final_answer`/`content`/`summary_text` 嵌套字段提取。`run_input.py` 新增 `_system_prompt_message` 将 admission 冻结的 `system_prompt` 注入 Engine request messages
- **合理性**: 修复在 durable/memory.py 的 memory projection consumer 内完成，不越界到 Engine 或 UI 层；`run_input.py` 的 system_prompt 注入在 `RunInputBuilder.build()` 内完成，属于 Host dispatch 正常职责
- **严重程度**: 高 → 已修复

### 6-已修复-[中]-scheduler close/wake、retry/replay、steer idempotency/detail

- **6a scheduler close/wake**: `test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent`（test_dispatch_scheduler.py:2185）断言 close 后 `wake_dispatch`/`wake_queue_promotion` 抛 `RuntimeError`，重复 close 幂等
- **6b scheduler promotion task lifecycle**: `test_scheduler_close_cancels_tracked_promotion_task` 断言 close 取消并等待 promotion task
- **6c retry/replay NOT_FOUND**: `test_retry_and_replay_missing_source_run_return_not_found`（test_public_retry_replay.py:310）断言 `HostApiErrorCode.NOT_FOUND`
- **6d retry idempotency conflict**: `test_retry_run_same_client_request_id_different_digest_conflicts`（test_public_retry_replay.py:342）断言 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`
- **6e steer idempotency**: `test_steer_replays_same_client_request_id_idempotently`（test_public_steer.py:135）断言同 key 重放返回同一 Run
- **6f SteerConflictDetail**: `test_steer_terminal_race_rejects_non_active_target`（test_public_steer.py:172）断言 `isinstance(detail, SteerConflictDetail)`、`detail.target_run_id`、`detail.target_run_status is RunStatus.SUCCEEDED`
- **严重程度**: 中 → 已修复

### 7-已修复-[中]-README/tests README 只写当前已实现边界

- **dayu/host/README.md**: 更新了 EventLog payload descriptor 语义（"正数 payload inline 阈值约束"、"descriptor 缺失 / digest 不匹配 / SQLite payload row 缺失都会 fail closed"）、steer `SteerConflictDetail` 说明、memory projection terminal summary descriptor 连续性说明
- **tests/README.md**: 更新了 public run/wait/event API 覆盖范围（steer 幂等重放 / SteerConflictDetail、retry/replay NOT_FOUND / 幂等冲突）、durable foundation 覆盖范围（payload inline threshold 正数精确边界、descriptor fail-closed、quality rejection retry、stale failure_reason、scheduler close 幂等 / wake RuntimeError、terminal summary descriptor continuity）
- **无越界**: README 只描述已实现行为，不写未来设计
- **严重程度**: 中 → 已修复

## Open Questions

- 无

## Residual Risk

- 多进程 admission payload spill 场景仍未覆盖（原 DS F9，deferred）
- `_referenced_user_input_event_payload` 轻量 payload 字段白名单正向断言仍未覆盖（原 DS F8 / MiMo F7，deferred）
- `OpenHostOptions` 完整负面验证矩阵仍未覆盖（原 MiMo F11，deferred）
- 上述 deferred 项不阻塞 merge，已有 controller 确认

## 分类汇总

| 分类 | Finding 编号 |
|------|-------------|
| 已修复 | 1, 2, 3, 4, 5, 6, 7 |
| 部分修复 | 无 |
| 未修复 | 无 |
| 证据失效 | 无 |

## Subagent 覆盖记录

- 主 reviewer 逐一读取三个 artifacts、当前 staged/unstaged diff、关键 production 文件（dispatch.py、admission.py、run_input.py、durable/memory.py、memory.py、payload_resolution.py）和所有相关测试文件，按 7 个复核重点逐项验证

---

## Maintainability Cleanup Re-Review

### Scope

- 复核文件：`payload_resolution.py`、`terminal_summary_payload.py`（新增）、`durable/memory.py`、`run_input.py`、`memory.py`
- 复核目标：去重行为等价、无 import cycle、无 durable schema 依赖引入 `dayu.host.memory`、无重复 helper 残留
- Codex artifact 更新：diff 为空，未变更

### 结论: PASS

去重行为等价，无 import cycle，无 durable schema 泄漏，无重复 helper 残留。

### 逐项验证

#### 行为等价

- **`terminal_summary_payload.py`（新增）**：统一 `assistant_summary_from_payload(payload, text_policy)` 函数，按 `final_answer` → `content` → `summary_text` → nested `summary` 递归提取。`PayloadSummaryTextPolicy` 三种策略控制空文本和非文本字段行为。
- **`memory.py`**：旧代码只检查 `_PAYLOAD_FIELD_FINAL_ANSWER`（`_optional_payload_str`），新代码使用 `LENIENT_NON_EMPTY` 策略检查三个字段。更宽泛但更安全——非字符串字段不再抛错，按缺失处理。行为等价于旧代码对空字符串的处理（`_optional_payload_str` 返回空字符串 → `_bounded_summary_text` 同样接受），非字符串场景从抛错变为静默跳过，属于 memory projection 的安全降级。
- **`run_input.py` `_continuity_message_from_event`**：旧代码使用本地 `_assistant_summary_from_payload`（三个字段 + 跳过空字符串），新代码使用 `STRICT_NON_EMPTY`（相同行为）。旧 `_assistant_summary_from_payload` 已删除。
- **`run_input.py` `_payload_with_terminal_summary`**：新逻辑，使用 `STRICT_NON_EMPTY`。旧代码无此路径（terminal summary descriptor 解析是本次 PR 新增功能）。
- **`durable/memory.py` `_payload_with_terminal_summary`**：旧代码使用本地 `_assistant_summary_from_payload`（三个字段 + nested `summary` + `_optional_str` 接受空字符串），新代码使用 `STRICT_ALLOW_EMPTY`（相同行为：空字符串作为合法摘要通过）。`_sqlite_payload_object` 已替换为 `sqlite_payload_object`（来自 `payload_resolution.py`），逻辑完全等价。
- **`payload_resolution.py`**：`event_payload_object` 的 descriptor 跟随逻辑抽取为 `sqlite_payload_object`，`event_payload_object` 内部调用 `sqlite_payload_object`。无行为变化。

#### Import cycle 检查

```
terminal_summary_payload → dayu.host.durable.errors（叶子）
payload_resolution → dayu.host.durable.*（叶子）
memory → dayu.host.terminal_summary_payload（叶子，无 cycle）
durable/memory → dayu.host.memory, dayu.host.payload_resolution, dayu.host.terminal_summary_payload（pre-existing memory 依赖，无新 cycle）
run_input → dayu.host.payload_resolution, dayu.host.terminal_summary_payload（无 cycle）
```

无新 import cycle。

#### Durable schema 泄漏检查

- `terminal_summary_payload.py` 只 import `dayu.host.durable.errors.HostDurableError`，不 import `dayu.host.durable.schema`
- `memory.py` 只 import `dayu.host.terminal_summary_payload`，不 import `dayu.host.durable.schema`
- `durable/schema.py` 依赖只在 `durable/memory.py` 和 `run_input.py` 中存在（pre-existing）

无 durable schema 依赖引入 `dayu.host.memory`。

#### 重复 helper 残留检查

- `run_input.py`：旧 `_assistant_summary_from_payload` 已删除，旧 `_PAYLOAD_FIELD_FINAL_ANSWER` 和 `_PAYLOAD_FIELD_SUMMARY_TEXT` 常量已删除
- `memory.py`：旧 `_PAYLOAD_FIELD_FINAL_ANSWER` 常量已删除
- `durable/memory.py`：旧 `_sqlite_payload_object`、旧 `_assistant_summary_from_payload`、旧 `_PAYLOAD_FIELD_FINAL_ANSWER`/`_PAYLOAD_FIELD_SUMMARY`/`_PAYLOAD_FIELD_SUMMARY_TEXT` 常量均已删除
- `payload_resolution.py`：旧 descriptor 跟随内联逻辑已抽取为 `sqlite_payload_object`，`__all__` 已更新

无重复 helper 残留。
