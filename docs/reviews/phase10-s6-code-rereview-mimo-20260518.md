# Phase 10 Slice 6 Re-Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: F2 / F4 review fix verification

## Verdict

**PASS**

## Summary

Slice 6 review fix 正确关闭了两个 accepted finding：

- **F2**：`HostCommandHandleOptions.context_window_size` 与 `reserved_output_tokens` 已移除默认值，改为必填 typed input；所有构造点显式传入正整数；`_validate_command_context_budget_fields` 的 fallback 改为基于显式 options 值而非旧常量。
- **F4**：`test_dispatch_scheduler.py` 新增 `test_multi_turn_proactive_compact_feeds_subsequent_run_input`，覆盖 4 轮场景：follow-up 观察 recent raw turn、小 budget 触发 proactive compact、compact artifact 进入 Engine request、后续 Run 观察 pinned state / episode summary / recent raw turn 顺序。

controller 验证：81 + 180 = 261 passed，pyright 0 errors。

---

## F2 Verification: Required Budget Inputs

### 1. 字段是否真正必填（无 silent default）

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| `context_window_size` 声明 | `api.py:1173` `context_window_size: int` — 无默认值 | **PASS** |
| `reserved_output_tokens` 声明 | `api.py:1174` `reserved_output_tokens: int` — 无默认值 | **PASS** |
| `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` 是否残留 | grep 全库：仅出现在 review artifact 文档中，production/test 代码已完全移除 | **PASS** |
| `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 是否残留 | 同上 | **PASS** |
| 构造时缺少字段是否报错 | `test_host_command_handle_options_require_explicit_budget_inputs` 验证 `field.default is MISSING` | **PASS** |

### 2. Fallback 是否基于显式 options 而非常量

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| `_validate_command_context_budget_fields` fallback | 使用 `DEFAULT_MINIMUM_PROTECTION_TOKENS`（来自 `context_policy`），不再依赖旧 `HOST_*_DEFAULT` 常量 | **PASS** |
| `_minimum_protection_tokens_from_options` fallback | `default_context_budget_policy(context_window_size=options.context_window_size, reserved_output_tokens=options.reserved_output_tokens)` — 使用显式传入值 | **PASS** |
| composition helper | `compose_host_local_execution_options` 直接读取 `options.context_window_size` / `options.reserved_output_tokens` 构造 policy | **PASS** |

### 3. 所有构造点是否显式传入

| 文件 | 证据 | 结论 |
| --- | --- | --- |
| `test_public_contracts.py` | `_host_command_handle_options()` helper 显式传入 `context_window_size=8192, reserved_output_tokens=1024` | **PASS** |
| `test_dispatch_scheduler.py` | `_options()` helper 显式传入 | **PASS** |
| `test_phase5_local_execution_integration.py` | `_options()` helper 显式传入 | **PASS** |
| 其他 10 个 test 文件 | 所有 `_options()` / `_command_options()` helper 均显式传入 | **PASS** |

---

## F4 Verification: Multi-Turn E2E Test

### 1. 测试是否覆盖 production path

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| 入口路径 | `_seed_accepted_run` → `scheduler.wake_queue_promotion` — 走 production governance gate | **PASS** |
| Worker | `_FinalAnswerWorkerFactory` 返回 `final_answer`，记录所有 Engine request — 非 mock | **PASS** |
| Compactor | `FakeContextCompactor()` — 通过 scheduler wiring 注入 | **PASS** |
| Compact artifact provider | `DurableCompactArtifactProvider` — scheduler 内部 wiring | **PASS** |
| Memory projection | scheduler 内部 event stream → projection catch-up | **PASS** |

### 2. 测试是否覆盖 plan 要求的完整链路

Plan 要求：
> Run 1 creates raw turns → follow-up under budget includes recent raw turns → later Run over soft threshold triggers proactive compact → CONTEXT_COMPACTED consumed by memory projection → subsequent Run contains pinned state, verified facts, recent raw turns, episode summaries

| Plan 要求 | 测试覆盖 | 结论 |
| --- | --- | --- |
| Run 1 creates raw turns | Turn 1: "first raw turn for memory" → SUCCEEDED | **PASS** |
| Follow-up under budget includes recent raw turns | Turn 2: 验证 Engine request messages 包含 turn 1 text | **PASS** |
| Later Run over soft threshold triggers proactive compact | Turn 3: `_soft_threshold_prompt()` (120 chars) → proactive compact | **PASS** |
| CONTEXT_COMPACTED consumed by memory projection | Turn 3 验证 `CONTEXT_COMPACTED` event 在 `RUN_STARTED` 之前 | **PASS** |
| Subsequent Run contains pinned state | Turn 4 验证 `current_goal=`、`confirmed_subject=subject:` | **PASS** |
| Subsequent Run contains episode summary | Turn 4 验证 `title=Session`、`Memory episode summaries:` | **PASS** |
| Ordering: pinned → raw → episode | Turn 4 验证 `goal_index < raw_index < episode_index` | **PASS** |

### 3. Soft threshold 数学验证

治理门控 `_run_pre_start_governance` 使用 `estimate_context_budget(policy, BudgetEstimateInput(...))` 估算当前输入 token 数。每个 message fragment 的 token 估算为：

```python
_estimate_text_tokens(text) + DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS
= ceil(len(text) / DEFAULT_ESTIMATOR_CHARS_PER_TOKEN) + 12
= ceil(len(text) / 3) + 12
```

Turn 3 的 prompt 为 `_soft_threshold_prompt()` = `"x" * 120`：

```
estimated_input_tokens = ceil(120 / 3) + 12 = 40 + 12 = 52
input_budget = context_window_size - reserved_output_tokens = 110 - 10 = 100
soft_threshold = max(1, floor(100 * (1 - 0.5))) = max(1, floor(50)) = 50
hard_threshold = 80 (显式 hard_threshold_tokens)

52 >= 50 → SOFT_THRESHOLD → proactive compact ✓
52 < 80 → 未达 HARD_THRESHOLD ✓
```

**数学正确：52 tokens > soft_threshold 50，触发 proactive compact 且未达 hard threshold。**

### 4. 测试是否脆弱

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| Threshold 计算是否依赖硬编码 magic number | `_SOFT_*` 常量集中定义，注释说明与 policy 的关系 | **PASS** |
| Prompt 长度是否精确踩 threshold | 120 chars → ceil(120/3)+12 = 52 tokens > soft_threshold 50，有 2 token 余量 | **PASS** |
| 索引断言是否依赖实现细节 | `goal_index < raw_index < episode_index` 是 ordering contract，不是实现细节 | **PASS** |
| 是否依赖 timing | 使用 `_wait_for_final_request_count` 同步，非 sleep | **PASS** |

---

## README / Docs 一致性

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| `dayu/host/README.md` | 已更新：必填 budget fields、composition data flow、budget/memory policy 分离 | **PASS** |
| `tests/README.md` | 已更新：multi-turn proactive compact coverage 标注 | **PASS** |
| Fix artifact | `phase10-s6-review-fix-codex-20260518.md` 准确描述 F2/F4 修改 | **PASS** |

---

## 新增风险检查

| 检查项 | 证据 | 结论 |
| --- | --- | --- |
| pyright | controller 验证 0 errors | **PASS** |
| Docstring | `_FinalAnswerWorker` / `_FinalAnswerWorkerFactory` 有中文 docstring | **PASS** |
| `__all__` | 无新增 public symbol | **PASS** |
| 移除的常量是否被外部引用 | `HOST_*_DEFAULT` 不在 `__all__` 中，无外部依赖 | **PASS** |

---

## Findings Summary

**无新增 blocking / high / medium / info defect。**

F2 和 F4 均已正确关闭：

| Finding | Status | 验证结论 |
| --- | --- | --- |
| F2 — 默认值削弱显式输入 | **CLOSED** | 字段必填，所有构造点显式传入，fallback 基于显式 options |
| F4 — 缺失 multi-turn E2E test | **CLOSED** | 4 轮场景覆盖 production path，soft threshold 数学正确，ordering 断言清晰 |

---

## Residual Risks

沿用原 review 的 residual risks，无新增：

1. **F1 — 无 production entry 调用**：`compose_host_local_execution_options` 只有 test 调用方。等待 composition root 接入。
2. **F3 — Fake compactor test wiring**：composition helper 不注入 fake compactor，S4/S5 测试通过直接构造绕过。
3. **Production compactor adapter**：未实现，compactor 未配置时 fail closed。
4. **Provider-specific tokenizer / retrieval**：不在范围内。
