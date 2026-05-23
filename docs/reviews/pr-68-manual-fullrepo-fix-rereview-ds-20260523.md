# PR 68 post-draft manual full-repo review repair — 独立复审 (AgentDS)

## 结论：PASS

本轮 9 项 accepted finding 全部正确关闭，无 blocking regression。

---

## 逐项验证

### 1. malformed runtime digest test（repo-review-20260523-193249.md Finding 1）

**修复**: `tests/runtime/test_tools_discovery_digest.py:323` — `required=("company_id",)` → `required=()`。

**验证**: 修复后 `ToolParametersSchema` 构造不再被 `required` 前置拦截，digest 计算能走到 `normalize_json_value` 的非字符串 key 校验路径。测试现在实际覆盖了目标分支。**PASS**。

### 2. engine_ingest current_attempt_id 校验（repo-review-20260523-193334.md Finding 1）

**修复**: `dayu/host/engine_ingest.py:863` — 新增 `or run.current_attempt_id != envelope.attempt_id` 校验条件。

**验证**: steer 后旧 Attempt 的 EngineEvent 被 `_validate_durable_context` 以 `REJECTED` + `stale_execution_id` 拒绝；新 Attempt 事件正常 `ACCEPTED`。新增测试 `test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts` 完整覆盖 steer 前后两个方向。旧测试 `test_old_attempt_run_failed_after_recovery_is_stale_diagnostic` 和 `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` 的拒绝 reason 由 `terminal_already_closed` 更新为 `stale_execution_id`，与新增同源校验一致。**PASS**。

### 3. tool_call_aggregator synthetic/native index collision（repo-review-20260523-193334.md Finding 2）

**修复**: `dayu/engine/runners/openai/tool_call_aggregator.py` — 合成 index 改用负数 keyspace（-1, -2, ...），新增 `_sorted_partial_indices` 分区排序（原生非负在前，合成负数在后），新增 `_index_by_position` position fallback 映射。

**验证**:
- `_allocate_synthetic_index` 从 -1 向负方向分配，不会与 provider 原生非负 index 碰撞。
- `finalize()` 通过 `_sorted_partial_indices` 将负数排到正数之后，`index_in_iteration` 仍从 0 开始顺序赋值，公共 API 不变。
- 新增测试 `test_synthetic_index_does_not_collide_with_later_native_index` 验证缺 index delta（合成 key=-1）与后续 index=0 delta 不合并。
- 既有测试的 delta `tool_call_index` 期望值更新为负数（-1, -2），completed `index_in_iteration` 仍为非负。**PASS**。

### 4. service weak typing guard（repo-review-20260523-193249.md Finding 6）

**修复**: 新建 `tests/service/test_weak_typing_guard.py`，AST 扫描 `Any` / `object` / 无类型注解 / 裸容器。

**验证**: 测试文件结构与 `tests/engine/`、`tests/host/`、`tests/runtime/` 的弱类型守卫风格一致。覆盖参数注解、返回值注解、类字段注解、裸 builtin 容器检测。**PASS**。

### 5. service import boundary dayu.config（repo-review-20260523-193249.md Finding 7）

**修复**: `tests/service/test_import_boundary.py:11` — `SERVICE_FORBIDDEN_PREFIXES` 新增 `"dayu.config"`。

**验证**: 禁止前缀与 host import boundary 对齐。测试函数重命名为 `test_service_does_not_import_forbidden_layers`，docstring 更新为覆盖 config 包。**PASS**。

### 6. engine api key marker（repo-review-20260523-193249.md Finding 8）

**修复**: `dayu/engine/agent.py:181` — `_SENSITIVE_EXCEPTION_MARKERS` 新增 `"api key"` 空格变体。

**验证**: 新增测试 `test_exception_diagnostic_message_redacts_api_key_with_space` 验证 `"provider rejected api key sk-secret-value"` 被正确脱敏为 `"RuntimeError: exception message redacted"`。**PASS**。

### 7. llm_compaction token/secret redaction（repo-review-20260523-193249.md Finding 12）

**修复**: `dayu/host/llm_compaction.py:72` — `_ASSIGNMENT_SECRET_PATTERN` 新增 `secret|token`。

**验证**: 测试 `test_llm_context_compactor_sanitizes_failed_runner_outcome` 的失败 outcome 消息新增 `token=tokensecret` 和 `secret=secretvalue`，并验证两者均被脱敏。**PASS**。

### 8. SSE all non-dict choices protocol error（repo-review-20260523-193334.md Finding 8）

**修复**: `dayu/engine/runners/openai/sse_parser.py:401-434` — 新增 `handled_choice` 计数器；当所有 choices 均非 dict 且无 valid usage 时，以 `RunnerProtocolErrorData(error_code="sse_missing_choices")` + `RunnerDoneData(finish_reason=ERROR)` 收口。

**验证**: 新增测试 `test_sse_all_non_object_choices_end_with_protocol_error`，验证 `choices` 全部为非 dict 时产出 protocol error 事件且 error_code 正确。条件 `not has_valid_usage` 确保有有效 usage 时不会误判。**PASS**。

### 9. host_assembly relative path escape（repo-review-20260523-193334.md Finding 10）

**修复**: `dayu/service/host_assembly.py:1101-1109` — `_resolve_project_path` 新增 `resolved_path.relative_to(resolved_root)` 逃逸校验。

**验证**: 新增 `test_resolve_project_path_rejects_relative_escape` 验证 `"../outside.sqlite3"` 抛出 `ValueError("configured project path escapes workspace root")`。新增 `test_resolve_project_path_keeps_absolute_path` 验证绝对路径保持原行为。**PASS**。

---

## 新增回归检查

### 合成 index 变更的波及范围

合成 index 从非负改为负数，影响 delta 事件的 `tool_call_index` 字段：

| 测试 | 旧值 | 新值 | 语义一致性 |
|------|------|------|-----------|
| `test_tool_call_position_ignores_non_dict_elements` | 0 | -1 | delta index 变为负数，completed index 仍非负 |
| `test_bool_index_tool_calls_stay_separate_by_id` | [0,1,0,1] | [-1,-2,-1,-2] | 四个 delta 仍可区分 |
| `test_aggregator_rejects_bool_index_and_falls_back_to_id` | 0 | -1 | resolved_index 正确区分 |
| `test_sse_parallel_missing_index_tool_call_delta_indices_match` | delta=completed | delta=(-1,-2), completed={0,1} | delta 与 completed index 解耦，符合设计 |

无向外泄漏：`ToolCallRequest.index_in_iteration` 仍在 `finalize()` 中从 0 开始顺序赋值。**无回归**。

### stale_execution_id 收口变更的波及范围

旧 Attempt late event 的拒绝 reason 从 `terminal_already_closed` 更新为 `stale_execution_id`。这是更早收口（在 durable context 校验层而非 late rejection 层），语义更精确。同时新增的 current Attempt 同源校验使拒绝条件一致。**无回归**。

### 其他无回归项

- `handled_choice` 标志：在 `not has_valid_usage` 条件下才触发 protocol error，有 usage 时不误判。
- `_resolve_project_path` 的 `resolve()` 调用：在 `relative_to` 之前 resolve，正确处理 symlink 场景。
- `_sorted_partial_indices` 排序逻辑：`(index < 0, -index if index < 0 else index)` 保证稳定性。
- 所有既有测试的预期更新均为有意识的语义适配，非退化。

---

## 未覆盖的 deferred 项（非本轮阻塞）

以下议题已由总控 deferred 或用户裁决，本轮不检查：

- durable/memory import 边界（repo-review-20260523-193249.md Finding 2）
- durable/api import 边界（repo-review-20260523-193249.md Finding 5）
- AgentPolicy merge 层退化为两层（repo-review-20260523-193334.md Finding 4）
- orphan heartbeat_at 解析失败（repo-review-20260523-193334.md Finding 6）
- WAL checkpoint 未显式管理（repo-review-20260523-193334.md Finding 12）
- watch polling 固定 20ms（repo-review-20260523-193334.md Finding 13）
- reactive compaction hard threshold（repo-review-20260523-193334.md Finding 3）

---

## 剩余非阻塞风险

1. **合成 index 负值作为 RunnerEvent 内部 key**：`RunnerToolCallDeltaData.tool_call_index` 现在可能为负数。这是内部归属 key，用于 aggregator 内部匹配 delta 到 partial，不暴露给 Agent 协调层（Agent 层使用 `ToolCallRequest.index_in_iteration`，始终 ≥0）。风险在于未来若有人直接依赖 delta `tool_call_index` 做展示或调试，需理解负值语义。

2. **`_resolve_project_path` 的 `resolve()` 语义**：绝对路径经过 `resolve()` 后不经过 `relative_to` 校验（直接返回原始 path）。若绝对路径指向 workspace 外的 symlink target，当前行为不拒绝。这是有意设计（`resolve()` 在相对路径分支才调用），与 `_resolve_prompt_asset_path` 的绝对路径行为一致。

3. **弱类型守卫测试仅覆盖 `dayu.service`**：新增的 `tests/service/test_weak_typing_guard.py` 已覆盖 Service 层，contracts/engine/host/runtime 的弱类型守卫在本次 diff 中未修改。未来若 Service 新增模块，AST 扫描自动纳入。

---

## 验证摘要

- **accepted findings 关闭**: 9/9 PASS
- **新增 blocking regression**: 0
- **非阻塞风险**: 3 项（见上）
- **deferred 项**: 7 项，不在本轮范围
