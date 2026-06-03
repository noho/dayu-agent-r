# WU-ENG-02 Slice 1 Re-Review — AgentDS

## Gate / Work Unit / Slice

- gate: deepreview (re-review)
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 — Engine Contract And Agent Identity
- reviewer: AgentDS
- review type: re-review of fix gate output
- implementation artifact: `docs/reviews/wu-eng-02-slice1-implementation-codex.md`
- code review artifacts: `docs/reviews/wu-eng-02-slice1-code-review-mimo.md`, `docs/reviews/wu-eng-02-slice1-code-review-ds.md`
- fix artifact: `docs/reviews/wu-eng-02-slice1-fix-codex.md`

## Review Target

Current uncommitted workspace changes (post-fix `git diff` vs HEAD). Fix gate changed 4 files:

| File | Nature |
|---|---|
| `dayu/engine/agent.py` | `_validate_batch_bijection` 签名扩展 + 全量 `RunFailedData` site 补齐 `client_correlation_id` |
| `tests/engine/test_agent_phase2.py` | EngineEvent 级 correlation id 断言 + outcome 透传断言 |
| `tests/engine/test_agent_phase3_tool_call.py` | EngineEvent 级 correlation id 断言 + bijection mismatch 测试 |
| `docs/reviews/wu-eng-02-slice1-fix-codex.md` | fix artifact（非代码） |

## Validation Evidence

### Tests

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/test_metadata_boundary.py -q
```

Result: **127 passed, 0 failed** in 0.22s.

### Type Check

```bash
source .venv/bin/activate && pyright
```

Result: **0 errors, 0 warnings, 0 informations**.

## Accepted Finding Status

### Finding 1 (DS, LOW) — EngineEvent / Agent outcome 的 client_correlation_id 值断言未补齐

**Status: 已修复**

Evidence:

| 测试函数 | 新增断言 | 是否为表面断言 |
|---|---|---|
| `test_success_run_lifts_runner_events_and_agent_final` | 遍历 events 找到 `ITERATION_COMPLETED`，断言 `data.client_correlation_id == request_identity.client_correlation_id` | 否，比较实际值 |
| `test_completed_tool_call_injects_messages_and_reaches_final` | 收集 2 个 `ITERATION_COMPLETED` 事件，`strict=True` zip 断言每个事件的 `client_correlation_id` 与对应 `runner.request_identities_seen[i].client_correlation_id` 一致 | 否，比较实际值且验证数量 |
| `test_tool_calls_finish_reason_mismatch_keeps_provider_request_id` | 断言 `iteration_completed.data.client_correlation_id` 和 `terminal.data.client_correlation_id` 均等于 `runner.request_identities_seen[0].client_correlation_id` | 否，验证两个事件携带同一 correlation |
| `test_length_continuation_appends_prompt_and_joins_content` | 收集 2 个 `ITERATION_COMPLETED` 事件，`strict=True` zip 断言每个事件的 `client_correlation_id` 匹配对应 runner identity | 否，比较实际值且验证数量 |
| `test_run_agent_and_wait_preserves_provider_request_id` | 断言 `result.client_correlation_id == expected_client_correlation_id`（`EngineRunOutcomeFailed` 透传） | 否，比较实际值 |

所有新增断言均为值比较（非 `is not None`），覆盖了 success 路径（phase2 + phase3 tool loop + length continuation）、failure 路径（finish reason mismatch）、outcome 透传路径（`run_agent_and_wait`）。force-answer 测试（`test_oversized_tool_message_is_passed_to_force_answer_runner_call`）新增了 runner 级 `runner_call_index` 和 `iteration_id` 断言但未显式验证 EngineEvent 级 `client_correlation_id`，这不影响 pass——force-answer 测试的主要职责是 oversized message 处理，且 fix artifact 未声称覆盖该测试。

---

### Finding 2 (DS, LOW) — _validate_batch_bijection 的 RunFailedData 未携带当前 tool batch client_correlation_id

**Status: 已修复**

Evidence:

1. **签名扩展**：`_validate_batch_bijection` 新增 keyword-only 参数 `client_correlation_id: str | None`，含完整中文 docstring。

2. **两条失败路径均已写入**：
   - duplicate record 路径：`client_correlation_id=client_correlation_id`
   - input/output id set mismatch 路径：`client_correlation_id=client_correlation_id`

3. **调用方传递**：`_execute_tool_batch` 调用 `_validate_batch_bijection` 时传入 `client_correlation_id=decision.client_correlation_id`。

4. **测试覆盖 mismatch 路径**：`test_duplicate_and_executor_exception_paths` 新增 bijection mismatch 子场景：
   - 通过 `_RecordingToolExecutor(records_override=(mismatched_record,))` 触发 `tool_batch_outcome_mismatch`
   - 断言 `mismatch_failed.client_correlation_id == mismatch_runner.request_identities_seen[0].client_correlation_id`
   - 值比较，非 `is not None` 表面断言

---

### 附：MiMo F-01 RunFailedData site 补齐情况（非本次 fix 要求，仅作完整性说明）

Fix 实际补齐了 MiMo F-01 中标注为"可获取 correlation"的全部 3 个 site：

| 原上下文 | 状态 |
|---|---|
| `_validate_batch_bijection` (duplicate + mismatch) | 已修复（Finding 2） |
| `_fallback_after_tools` RAISE_ERROR 分支 | 已修复（附带补齐，`_client_correlation_id_from_state(state)`） |
| `_ERROR_TOOL_EXECUTION_TIMEOUT` | 未修复（不在本次 fix scope，且 DS review 未将其列为 finding） |

`_fallback_after_tools` 路径的附带补齐是合理的——state 可用时携带 correlation id 符合 plan 语义（"when tied to a provider call"），且与 `_client_correlation_id_from_state` helper 的全局应用一致。

---

### 附：AgentDS Finding 3/4 状态确认（非 fix target，无需修复）

| Finding | 原裁决 | 当前状态 |
|---|---|---|
| Finding 3: `_MetadataBoundaryRunner` 未捕获 request_identity | accepted | 不变，metadata boundary 测试职责不包含 identity 验证 |
| Finding 4: `_fallback_after_tools` RAISE_ERROR 不含 correlation 是正确设计 | accepted | 原裁决基础已变化——fix 现已补齐该路径的 `client_correlation_id`。这不改变 accepted 结论，因为补齐后的行为更优 |

---

## Scope Creep / Slice Boundary Check

| 检查项 | 结果 |
|---|---|
| OpenAI header 映射（`X-Client-Request-Id`） | 未实现，仍在 Slice 2 |
| `RunnerSpec` client correlation policy | 未实现，仍在 Slice 2 |
| Host `RunInputBuilder` projection | 未实现，仍在 Slice 3 |
| Host ingest / Tool Trace 持久化 | 未实现，仍在 Slice 3 |
| README 更新 | 未执行，deferred to Slice 4 |
| `_ToolCallsDecision.client_correlation_id` 新增字段 | Slice 1 范围内——Engine 内部决策结构扩展，不对外暴露 |
| `_IterationState.request_identity` 新增字段 | Slice 1 范围内——Engine 内部状态扩展，不对外暴露 |

结论：fix 未引入 Slice 2/3 行为泄漏。

---

## 新增问题检查

### 类型与 docstring

| 检查项 | 结果 |
|---|---|
| `_ToolCallsDecision` — 新增 `client_correlation_id` 字段 | ✅ 有类型注解 `str \| None`，docstring 已更新 |
| `_IterationState` — 新增 `request_identity` 字段 | ✅ 有类型注解 `RunnerRequestIdentity`，docstring 已更新 |
| `_validate_batch_bijection` — 新增参数 | ✅ 有类型注解 + docstring |
| `_client_correlation_id_from_state` — 新函数 | ✅ 完整中文 docstring（参数/返回/异常） |
| `_next_runner_request_identity` — 新方法 | ✅ 完整中文 docstring（参数/返回/异常） |
| `_ToolCallsDecision` 所有构造 site | ✅ `_classify_runner_call_completed` 中唯一构造 site 已传入新字段 |
| pyright | ✅ 0 errors |

### 测试质量

| 检查项 | 结果 |
|---|---|
| 新增断言均为值比较 | ✅ 无不充分的 `is not None` 表面断言 |
| bijection mismatch 测试覆盖真实 mismatch 路径 | ✅ 通过 `records_override` 触发 id set 不一致 |
| EngineEvent correlation 断言使用 `strict=True` zip | ✅ 确保事件数量与 identity 数量一致 |

### 编码规范

| 检查项 | 结果 |
|---|---|
| `Any` / `object` / 无类型签名 | ✅ 无新增 |
| lazy import | ✅ 无新增 |
| 魔法字符串/数字 | ✅ 无新增 |
| 兼容性代码 | ✅ 无新增 |
| provider 字符串治理分支 | ✅ 无新增 |

## Blocking Open Questions

无。

## Residual Risks

### R1: `_ERROR_TOOL_EXECUTION_TIMEOUT` 路径仍未携带 client_correlation_id

- **来源**: MiMo F-01，非 DS review finding
- **影响**: 工具执行超时时 `RunFailedData.client_correlation_id` 为 `None`，caller 有 `decision.client_correlation_id` 可用但未传入
- **严重程度**: Low — 工具超时属于内部超时机制，非 provider 错误；对诊断影响有限
- **建议**: Slice 3/4 中统一处理

### R2: force-answer 测试无 EngineEvent 级 correlation 断言

- **来源**: 本次 re-review 发现
- **影响**: `test_oversized_tool_message_is_passed_to_force_answer_runner_call` 仅验证 runner 级 identity，不验证 emitted `EngineEvent` 的 `client_correlation_id`
- **严重程度**: Low — force-answer 路径的 EngineEvent 发射与其他路径共用同一 helper，行为一致性由 helper 保证
- **建议**: 可在 Slice 4 补齐，非阻塞

### R3: Slice 2/3 未实现项（继承自原始 review）

| 风险 | Owner |
|---|---|
| OpenAI header 映射未实现 | Slice 2 |
| `RunnerSpec.client_correlation_policy` 未定义 | Slice 2 |
| Host `RunInputBuilder` 未投影 `attempt_id/execution_id` | Slice 3 |
| Host ingest / Tool Trace 未持久化 `client_correlation_id` | Slice 3 |

## 结论

**pass**

- 2 条 accepted findings 均已修复，修复质量经代码级验证通过
- 0 条未修复 finding
- 0 条部分修复 finding
- 0 条新增 blocking issue
- 0 条 blocking open questions
- 127 tests passed, pyright 0 errors
- fix 未引入 Slice 2/3 scope creep
- 2 条 Low 级 residual risks（tool timeout 路径、force-answer 测试缺口），均不阻塞 Slice 1
