# PR-62 fullrepo accepted-fix re-review

## Scope

- Mode: current changes
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/pr-62-fullrepo-accepted-fix-rereview-mimo-20260519.md`
- Included scope: `dayu/host/compaction_budget.py`、`dayu/host/llm_compaction.py`、`dayu/host/fake_compaction.py`、`dayu/host/engine_ingest.py`、`dayu/host/tool_runtime.py`、`dayu/host/waiting.py`、`dayu/host/dispatch.py`、`dayu/host/durable/_validation.py`、`dayu/engine/agent.py`、`dayu/contracts/tool_await.py`、`dayu/contracts/tool_outcome.py`、相关 tests、README、docs/reviews 新 artifact
- Excluded scope: `dayu/fins/`（财报领域能力，本次未覆盖）, `dayu/service/`, `dayu/ui/`（未实现）, `utils/`, `workspace/`

## Findings

未发现实质性问题。

所有 accepted fixes 均已正确实现，测试覆盖完整，pyright 类型检查通过。

## 验证结果

### 测试验证

```
154 passed in 1.43s
```

覆盖的测试文件：
- `tests/host/test_llm_compaction.py` - LLM compactor 测试
- `tests/host/test_compaction_contract.py` - compaction contract 测试
- `tests/host/test_compaction_operation.py` - compaction operation 测试
- `tests/host/test_durable_validation.py` - durable validation 测试
- `tests/contracts/test_tool_outcome_exhaustive.py` - tool outcome 穷尽匹配测试
- `tests/host/test_toolruntime_executor.py` - ToolRuntime executor 测试
- `tests/host/test_resolve_wait_command.py` - resolve wait command 测试
- `tests/host/test_engine_ingest_mapping.py` - engine ingest mapping 测试
- `tests/engine/test_agent_phase2.py` - agent phase2 测试
- `tests/host/test_public_cancel_smoke.py` - public cancel smoke 测试
- `tests/host/test_public_tool_wiring_smoke.py` - public tool wiring smoke 测试
- `tests/host/test_import_boundary.py` - import boundary 测试

### pyright 验证

```
0 errors, 0 warnings, 0 informations
```

验证的文件：
- `dayu/contracts/tool_await.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/engine/agent.py`
- `dayu/host/compaction_budget.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/_validation.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/fake_compaction.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/waiting.py`

## Accepted Fixes 逐项验证

### 1. compaction budget 估算修复（Finding 1/4/12 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- 新增 `dayu/host/compaction_budget.py`，统一使用 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN`（3 chars/token）
- `estimate_compacted_context_budget` 函数覆盖 summary + preserved refs + current input + system prompt
- `_estimate_preserved_share_from_budget` 按保留引用占比从 compact 前预算估算，取两种估算方式的较大值
- `FakeContextCompactor` 已复用同一 helper
- `LLMContextCompactor` 使用 `_budget_after_compact(request, summary)` 调用统一 helper

**测试验证**：
- `test_llm_context_compactor_budget_counts_preserved_context`: 验证 budget >= 80
- `test_fake_compactor_reports_budget_above_hard_threshold_when_preserved_refs_dominate`: 验证不被 hard threshold 截断

**关键代码路径**：
- `compaction_budget.py:16-35`: `estimate_compacted_context_budget` 入口
- `compaction_budget.py:49-72`: `_estimate_preserved_context_tokens` 估算保留上下文
- `compaction_budget.py:93-114`: `_estimate_preserved_share_from_budget` 按占比估算

### 2. unsupported EngineEvent ingest fail closed（Finding 3 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `engine_ingest.py:823-828` unsupported 分支设置 `stop_worker_stream=True`
- 不误伤正常 non-terminal 事件（preview events 正常处理）

**测试验证**：
- `test_preview_event_rejects_missing_or_wrong_data`: 验证 `stop_worker_stream is True`
- `test_preview_event_accepts_matching_type_and_data`: 验证正常 preview event 仍正常写入

**关键代码路径**：
- `engine_ingest.py:815-828`: unsupported event 分支

### 3. Runner close once 语义修复（Finding 5 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `agent.py:2404-2405` 在 `finally` 块中设置 `self._closed = True`
- 保证一次 close 尝试后不重复 close 同一 Runner

**测试验证**：
- `test_close_runner_once_marks_closed_after_close_error`: 验证幂等性

**关键代码路径**：
- `agent.py:2380-2405`: `_close_runner_once` 实现

### 4. require_optional_non_empty_text isinstance 守卫（Finding 6 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `_validation.py:40-41` 添加 `isinstance` 守卫
- 对非字符串非 None 值抛出清晰 `HostDurableError`

**测试验证**：
- `test_require_optional_non_empty_text_rejects_runtime_non_text_values`: 验证对 `int`、`bytes` 等非文本值抛出 `HostDurableError`

**关键代码路径**：
- `_validation.py:29-43`: `require_optional_non_empty_text` 实现

### 5. ToolAwaitSnapshot.__post_init__ 校验（Finding 8 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `tool_await.py:75-83` 添加 `__post_init__` 校验空 `snapshot_id`
- 与包内其他含 string ID 的 dataclass 保持一致

**测试验证**：
- 测试覆盖空 `snapshot_id` 抛出 `ValueError`

**关键代码路径**：
- `tool_await.py:60-83`: `ToolAwaitSnapshot` 实现

### 6. ALLOWED_TOOL_CANCELLED_REASONS 类型标注（Finding 9 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `tool_outcome.py:51` 标注为 `frozenset[ToolCancelledReason]`
- 保留字面量精度，支持 pyright 穷尽性检查

**关键代码路径**：
- `tool_outcome.py:51-57`: `ALLOWED_TOOL_CANCELLED_REASONS` 定义

### 7. import boundary 测试更新（Finding 14 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `test_import_boundary.py:51` 白名单包含 `llm_compaction.py`
- 只允许 Host-owned LLM compaction 依赖 Engine public entry / contracts
- 未放开反向依赖（Engine 仍不导入 Host）

**关键代码路径**：
- `test_import_boundary.py:46-54`: `HOST_ENGINE_CONTRACT_ALLOWED_MODULES` 定义

### 8. active cancel clean EOF race 修复（Finding 15 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- `dispatch.py:2478-2490` 在 clean EOF 时检查 cancellation token
- 如果已取消，合成 `run_cancelled` ingest
- 非取消 clean EOF 仍按 lost closeout 处理

**关键代码路径**：
- `dispatch.py:2476-2510`: clean EOF 处理逻辑

### 9. event id 格式断言更新（Finding 16 from repo-review-20260519-182226）

**状态：✅ 已正确实现**

**实现验证**：
- 测试断言已更新匹配当前 event_id 格式 `event-tool-result-accepted-`

### 10. awaiting accept timeout diagnostic refs（Finding 1 from repo-review-20260519-182223）

**状态：✅ 已正确实现**

**实现验证**：
- `tool_runtime.py:2833-2843` timeout path 传递 `diagnostic_refs`
- `tool_runtime.py:2848-2853` 发射诊断 ref 并放入 `ToolAwaitingAcceptTimedOut.diagnostic_refs`

**关键代码路径**：
- `tool_runtime.py:2813-2860`: `_accept_awaiting_with_retry` 实现

### 11. duplicate governance 清理（Finding 2 from repo-review-20260519-182223）

**状态：✅ 已正确实现**

**实现验证**：
- `tool_runtime.py:2473-2479` 合并为单次条件判断
- 删除冗余的 `duplicate_governed` 赋值，直接在条件分支内覆写 `policy_decision`

**关键代码路径**：
- `tool_runtime.py:2465-2479`: duplicate governance 逻辑

### 12. resolve wait event ref fail closed（Finding 3 from repo-review-20260519-182223）

**状态：✅ 已正确实现**

**实现验证**：
- `waiting.py:2020-2042` `_resolve_created_event_ref` 在 `event_id` 或 `event_sequence` 为 `None` 时抛出 `HostApiError`
- resume 路径和 terminal 路径都有明确的错误消息

**测试验证**：
- 测试覆盖 `started_event_id` 为 `None` 的场景

**关键代码路径**：
- `waiting.py:2020-2042`: `_resolve_created_event_ref` 实现

### 13. TruncationManager docstring（Finding 4 from repo-review-20260519-182223）

**状态：✅ 已正确实现**

**实现验证**：
- Host README 已更新说明 cursor 为 run-scoped、短生命周期、单次使用
- `tests/README.md` 已同步更新

## Controller Adjudication 评估

controller 对 deferred findings 的裁决理由合理：

### Deferred findings 评估

1. **Finding 2 (ToolFactAcceptCandidate God dataclass)**：维护性风险，非 correctness blocker，适合作为独立重构切片。裁决合理。

2. **Finding 7 (compact 失败最终降级路径)**：当前已有 failure reason 返回和 fail-unstarted 收口，reactive/proactive 策略仍值得单独做端到端 failure matrix。裁决合理。

3. **Finding 10 (LaneController close/acquire 竞态)**：有 TTL 兜底，属于 runtime 并发 primitive，不在 PR-62 Host accepted-fix 主路径。裁决合理。

4. **Finding 11 (_execute_batch 异常日志)**：不影响 Host 终态一致性，后续可做 Engine observability 小切片。裁决合理。

5. **Finding 13 (log.py import 副作用)**：低风险全局 logging 命名注册，非 Host/Engine correctness blocker。裁决合理。

6. **Finding 5 (durable bootstrap DDL 原子性)**：IF NOT EXISTS 与 schema version 已具备恢复能力，改事务边界需覆盖 bootstrap / fresh DB 测试。裁决合理。

7. **Finding 6 (after-commit callback 多错误诊断聚合)**：不影响 committed durable truth，属于 observability 改善。裁决合理。

8. **Finding 7 (service/ui 测试缺失)**：当前仓库未实现 service/ui Python 层，finding 对当前代码不可执行。裁决合理。

9. **Finding 8 (Host crash recovery 端到端测试)**：需要多进程/强杀式测试设计，超出 accepted-fix 范围。裁决合理。

10. **Finding 9 (敏感异常 marker 精度)**：偏保守 redaction 只会过度脱敏，非 correctness blocker。裁决合理。

11. **Finding 10 (open_host fallback 常量)**：已有内部 fallback 说明，生产应显式传入 policy。裁决合理。

12. **Finding 11 (session watch 20ms 轮询)**：性能优化项，当前无 correctness 回归证据。裁决合理。

13. **Finding 12 (import boundary 测试 helper 重复)**：测试维护性重构，非 PR-62 blocker。裁决合理。

## Open Questions

无。

## Residual Risk

1. **ToolFactAcceptCandidate God dataclass**（deferred）：22 字段 dataclass 维护性风险，后续应拆分为子结构体。
2. **compact 失败最终降级路径**（deferred）：reactive/proactive 策略的端到端 failure matrix 未覆盖。
3. **LaneController close/acquire 竞态**（deferred）：有 TTL 兜底，但后续应以 runtime lane 独立并发测试切片处理。
4. **Host crash recovery 端到端测试**（deferred）：需要多进程/强杀式测试设计，超出当前范围。
5. **大文件维护性**：`dayu/host/durable/state.py`（5460 行）、`dayu/host/tool_runtime.py`（5359 行）等文件规模较大，模块级 God module 风险存在。

## 结论

**PASS**

所有 accepted fixes 均已正确实现，测试覆盖完整（154 passed），pyright 类型检查通过（0 errors, 0 warnings）。controller 对 deferred findings 的裁决理由合理。README 只写当前稳定说明，无未来计划或实现细节。import boundary 变更只允许 Host-owned LLM compaction 合理依赖 Engine public entry / contracts，未放开反向依赖。
