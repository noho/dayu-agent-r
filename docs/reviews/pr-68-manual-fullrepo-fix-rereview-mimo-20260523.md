# PR 68 post-draft manual full-repo fix re-review

## 审查范围

- 审查对象：`feat/phase-12-5-conversation-memory-optimize` 分支未提交 diff
- 审查目标：确认本轮修复正确关闭总控 accepted findings，且不引入新的 blocking regression
- 参照文档：
  - `docs/reviews/repo-review-20260523-193249.md`（Findings 1, 6, 7, 8, 10, 12）
  - `docs/reviews/repo-review-20260523-193334.md`（Findings 1, 2, 8, 10）
  - `docs/reviews/pr-68-manual-fullrepo-fix-codex-20260523.md`

## 结论：PASS

本轮修复正确关闭了 10 项 accepted findings，未引入新的 correctness / stability / maintainability blocking regression。

## 逐项验证

### 1. malformed runtime digest test（repo-193249 Finding 1）

- **修复**：`tests/runtime/test_tools_discovery_digest.py:323` 将 `required=("company_id",)` 改为 `required=()`
- **验证**：`ToolParametersSchema` 构造不再被 `required` 校验拦截，测试现在能走到 `normalize_json_value` 的非字符串 key `TypeError` 路径。修复正确。

### 2. engine_ingest current_attempt_id 校验（repo-193334 Finding 1）

- **修复**：`dayu/host/engine_ingest.py:863` 在 `_validate_durable_context` 中增加 `run.current_attempt_id != envelope.attempt_id` 条件
- **验证**：当旧 Attempt 的 worker event 到达时，`_validate_durable_context` 返回 `None`，走 `_REASON_STALE_EXECUTION_ID` 拒绝路径。新增测试 `test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts` 验证 steer 后旧 Attempt 被拒、新 Attempt 正常接收。既有测试 `test_old_attempt_run_failed_after_recovery_is_rejected` 和 `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` 的 reason 断言从 `terminal_already_closed` 更新为 `stale_execution_id`，与新增校验同源。修复正确。

### 3. tool_call_aggregator synthetic/native index 碰撞（repo-193334 Finding 2）

- **修复**：`dayu/engine/runners/openai/tool_call_aggregator.py` 将 `_next_synthetic_index` 从 `0` 改为 `-1`，向负方向分配；新增 `_index_by_position` 映射支持 position fallback；新增 `_sorted_partial_indices` 保证 finalize 时原生非负 index 在前、合成负数 index 在后
- **验证**：
  - 合成 index（-1, -2, ...）与 provider 原生 index（0, 1, 2, ...）使用独立 keyspace，不会碰撞
  - `_sorted_partial_indices` 排序 key `(index < 0, -index if index < 0 else index)` 确保原生 index 升序在前、合成 index 按分配顺序在后
  - `finalize()` 中 `result_index` 从 0 开始连续递增，`index_in_iteration` 语义不变
  - 新增测试 `test_synthetic_index_does_not_collide_with_later_native_index` 验证首个 delta 缺 index（合成 -1）与后续 delta 有 index=0（原生 0）不合并
  - `test_old_protocol_parity_regressions.py` 断言更新为 `(-1, -2)` / `{0, 1}` 与新 keyspace 一致
  - `test_sse_tool_call_stream.py` 中多个测试的期望 index 从 0/1 更新为 -1/-2
  - 修复正确。

### 4. service weak typing guard（repo-193249 Finding 6）

- **修复**：新增 `tests/service/test_weak_typing_guard.py`，AST 扫描 `dayu/service/` 禁止 `Any`/`object`/未注解/裸容器
- **验证**：结构与 contracts/engine/host/runtime 的弱类型守卫一致，覆盖函数签名、方法签名、类字段注解。修复正确。

### 5. service import boundary dayu.config（repo-193249 Finding 7）

- **修复**：`tests/service/test_import_boundary.py` 在 `SERVICE_FORBIDDEN_PREFIXES` 中增加 `"dayu.config"`
- **验证**：与 host 的 `HOST_FORBIDDEN_PREFIXES` 对齐，测试函数重命名为 `test_service_does_not_import_forbidden_layers`。修复正确。

### 6. engine api key marker（repo-193249 Finding 8）

- **修复**：`dayu/engine/agent.py:181` 在 `_SENSITIVE_EXCEPTION_MARKERS` 中增加 `"api key"`（空格形式）
- **验证**：新增测试 `test_exception_diagnostic_message_redacts_api_key_with_space` 验证 `"provider rejected api key sk-secret-value"` 被脱敏。修复正确。

### 7. llm_compaction token/secret redaction（repo-193249 Finding 12）

- **修复**：`dayu/host/llm_compaction.py:72` 将 `_ASSIGNMENT_SECRET_PATTERN` 从 `api[_-]?key|authorization` 扩展为 `api[_-]?key|authorization|secret|token`，与 `compaction_operation.py` 对齐
- **验证**：测试 `test_llm_context_compactor_sanitizes_failed_runner_outcome` 扩展了 `token=tokensecret` 和 `secret=secretvalue` 的断言。修复正确。

### 8. SSE all non-dict choices protocol error（repo-193334 Finding 8）

- **修复**：`dayu/engine/runners/openai/sse_parser.py:401-436` 增加 `handled_choice` 计数器，全部 choice 为非 dict 且无有效 usage 时以 `_MISSING_CHOICES_CODE` 协议错误收口
- **验证**：逻辑正确——`handled_choice` 仅在 `isinstance(choice, dict)` 时设为 `True`；循环结束后检查 `not handled_choice and not has_valid_usage`，发出 `RunnerProtocolErrorData` + `RunnerDoneData(FinishReason.ERROR)` 并 return。新增测试 `test_sse_all_non_object_choices_end_with_protocol_error` 覆盖 `choices=["bad-choice",1]` 场景。修复正确。

### 9. host_assembly relative path escape（repo-193334 Finding 10）

- **修复**：`dayu/service/host_assembly.py:1110-1116` 对相对路径增加 `resolved_path.relative_to(resolved_root)` 校验，绝对路径保持原行为
- **验证**：新增测试 `test_resolve_project_path_rejects_relative_escape` 和 `test_resolve_project_path_keeps_absolute_path`。修复正确。

### 10. tests/README.md 更新

- **修复**：更新 Service 测试职责说明，新增 import boundary / weak typing guard 描述；类型守护覆盖范围扩展到 Service
- **验证**：与代码变更一致。修复正确。

## 非阻塞风险

1. **synthetic tool_call_index 为负数**：这是内部 RunnerEvent 归属 key，用于避免与 provider native index 碰撞。`finalize()` 中 `index_in_iteration` 仍保持从 0 开始的连续顺序，对外契约不变。风险可控。

2. **旧 Attempt late event 的拒绝 reason 变更**：从 `terminal_already_closed` 收口为 `stale_execution_id`。这与新增 `current_attempt_id` 校验同源——旧 Attempt 在到达 terminal 检查之前就被 identity 校验拦截。语义更精确，无功能退化。

3. **_resolve_project_path 对绝对路径不做逃逸校验**：这是有意设计——绝对路径由管理员配置，逃逸校验仅防御相对路径注入。与 `_resolve_prompt_asset_path` 的行为一致。

4. **`_sorted_partial_indices` 的排序语义**：原生非负 index 升序在前，合成负数 index 按分配顺序在后。这保证了 `index_in_iteration` 的连续性，但合成 index 的 delta 事件中 `tool_call_index` 为负数——调用方如需使用该值做关联，需注意此行为变更。当前所有调用方均通过 `index_in_iteration` 做最终关联，无影响。

5. **deferred 项未处理**：durable transaction rollback warning、waiting.py digest fallback、reactive compaction hard threshold、AgentPolicy 合并层重构、orphan recovery、WAL checkpoint、watch polling 等已由总控 deferred 或用户裁决，不在本轮范围。

## 验证记录

```bash
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery_digest.py tests/host/test_engine_ingest_mapping.py tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_old_protocol_parity_regressions.py tests/engine/runners/openai/test_protocol_error.py tests/service/test_weak_typing_guard.py tests/service/test_import_boundary.py tests/service/test_host_assembly.py tests/engine/test_agent_phase2.py tests/host/test_llm_compaction.py
```

结果：`146 passed in 2.12s`（来自修复文档记录）。

```bash
source .venv/bin/activate && pyright dayu tests
```

结果：`0 errors, 0 warnings, 0 informations`（来自修复文档记录）。
