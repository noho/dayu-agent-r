# Phase 12.3 Slice 2 Code Review — AgentDS — 2026-05-22

## Verdict

**PASS** — 无 blocking finding。

实现符合 Phase 12.3 Slice 2 plan 的全部 acceptance criteria，未引入 plan non-goals。Engine usage contract 未被修改，USAGE_REPORTED 保持 PROJECTION_SIGNAL 语义，Usage observation 降级路径全部正确，Run / Attempt 状态不变，diagnostic helper 类型约束严格。以下 3 个 advisory findings 建议在后续 slice 或 phase 修复。

## 审查范围与真源

- 设计真源：`docs/host/design.md`（第 1556、2623-2633 行）
- 实施计划：`docs/host/phase12-3-config-usage-governance-plan.md`（Slice 2，第 227-318 行）
- 实施报告：`docs/reviews/phase12-3-slice2-implementation-codex-20260522.md`
- 审查文件：
  - `dayu/host/context_budget.py`（+113 行）
  - `dayu/host/engine_ingest.py`（+156 行）
  - `tests/host/test_context_budget.py`（+72 行）
  - `tests/host/test_engine_ingest_mapping.py`（+174 行）
  - `dayu/host/README.md`（+2 行）

## 逐项检查结果

### 1. Engine contract 不变性

- ✅ `git diff HEAD -- dayu/engine/` 无输出，Engine `RunnerUsageRecordedData`（`runner_events.py:134`）和 `UsageReportedData`（`engine_events.py:274`）字段未改
- ✅ 未引入 `provider_request_id` 到 Engine `UsageReportedData` 字段中
- ✅ 未引入 `usage_enabled`、`collect_usage`、`include_usage`、`supports_usage` 到 Host config 或 Engine 合约
- ✅ Engine `include_usage`（`_types.py:35`）和 `supports_stream_usage`（`runner_spec.py:238`）行为保持不变

### 2. USAGE_REPORTED 事件分类

- ✅ `engine_ingest.py:2057`：`event_class=EventClass.PROJECTION_SIGNAL`
- ✅ `engine_ingest.py:2058`：`event_type="USAGE_REPORTED"`
- ✅ 不是 canonical fact，Run / Attempt 状态机不受此事件修改

### 3. Payload 字段完整性

- ✅ 保留原字段：`attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`
- ✅ 新增字段：`session_id`、`run_id`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`、`prompt_token_delta`
- ✅ `provider_request_id` 恒为 `None`，因为 Engine `UsageReportedData` 不提供此字段（plan 设计决定）

### 4. 降级路径

- ✅ **policy 缺失**：`policy_ref="none"`，`estimator_digest=None`，`estimated_input_tokens=None`，`usage_observation_status="estimate_unavailable"`，projection 仍提交，test 验证通过（`test_usage_reported_without_policy_keeps_projection_non_failing`）
- ✅ **input event 缺失**：`read_event_by_id` 返回 `None` → `_estimate_usage_observation_input` 返回 `None` → `estimate_unavailable`，projection 仍提交（`test_usage_reported_missing_input_event_keeps_projection_non_failing`）
- ✅ **input event payload 不可读**：`_display_text_from_input_event` 抛出 `HostDurableError` → `except Exception` 捕获 → `None` → `estimate_unavailable`，projection 仍提交（`test_usage_reported_unreadable_input_event_keeps_projection_non_failing`）
- ✅ **usage token 异常**：`prompt_tokens=-1` 时 `UsageObservation.__post_init__` 抛出 `ValueError` → `except (TypeError, ValueError)` 捕获 → `usage_invalid`，projection 仍提交（`test_usage_reported_invalid_tokens_keeps_projection_non_failing`）
- ✅ 所有降级路径均不修改 Run / Attempt 状态（断言 `RunStatus.RUNNING` / `AttemptStatus.RUNNING`）

### 5. Diagnostic helper 形态

- ✅ `UsageObservationDiagnostic` 是 `@dataclass(frozen=True, slots=True)`，字段全部严格类型，无 `Any` 或 extra payload bag
- ✅ `build_usage_observation_diagnostic` 不调用 `decide_context_budget`，不修改 `BudgetEstimate`
- ✅ `test_usage_observation_diagnostic_reports_prompt_delta` 验证：helper 不对已有 estimate decision 产生影响（断言 `decide_context_budget(estimate) == COMPACT_SOFT_THRESHOLD` 在 diagnostic 计算前后一致）
- ✅ `_require_int` 新 helper 使用严格 `isinstance` 校验（禁用 `bool` 伪装 `int`），类型安全

### 6. 错误处理与 digest 稳定性

- ✅ `_usage_observation_digest` 和 `_invalid_usage_observation_digest` 均使用 `sha256_digest_json` + `canonical_json_dumps`，digest 格式稳定
- ✅ `UsageObservation.observed_at` 源于 `candidate.observed_at`，已被 `_validate_observed_at` 校验为 UTC
- ✅ `provider_request_id` 在 digest 中使用 `None`（JSON `null`），两个 digest 函数格式一致

### 7. README

- ✅ `dayu/host/README.md` 只描述 Host 当前稳定行为：usage projection 是 post-call observation、缺少估算不影响 Run / Attempt、不回改 dispatch decision
- ✅ Engine governance 未写入 Host README
- ✅ `dayu/engine/README.md` 未修改（Engine usage 说明仍准确且未被本 slice 改变）

## Advisory Findings

### F1（中）— `_estimate_usage_observation_input` 使用 `except Exception` 过宽

**文件**：`dayu/host/engine_ingest.py:2191`

**证据**：

```python
except Exception:
    _LOGGER.debug(...)
    return None
```

**分析**：调用链 `_display_text_from_input_event → estimate_context_budget → sha256_digest_json` 中实际可能抛出的异常只有 `HostDurableError`（payload 缺失/错误）、`TypeError`（类型校验失败）和 `ValueError`（JSON 编码失败）。当前 `except Exception` 还捕获 `KeyError`、`AttributeError`、`RecursionError` 等编程错误，可能吞掉真实 bug。

**建议**：收窄为 `except (TypeError, ValueError, HostDurableError)`，因为 `HostDurableError` 已在 `engine_ingest.py:110` 导入且正是 `_display_text_from_input_event` 实际抛出的类型（该函数 docstring 中的 `:raises ValueError:` 已过时）。

**严重性评估**：本路径由 `_estimate_usage_observation_input` 的内部 `except` 保护，且调用链高度确定，`estimate_context_budget` 和 `_display_text_from_input_event` 的行为在聚焦测试下是确定的。实际被吞掉的 bug 概率很低，但不收窄违反项目 `禁止局部止血/吞掉真实 bug` 的编码纪律。建议 Slice 4 修复。

### F2（低）— `UsageObservation` 缺少 `iteration_id`，同一 attempt 多 iteration 可能产生 digest 碰撞

**文件**：`dayu/host/context_budget.py:227`（`UsageObservation` dataclass）、`dayu/host/context_budget.py:596`（`_usage_observation_digest`）

**证据**：`_usage_observation_digest` 和 `_invalid_usage_observation_digest` 的 `observation` payload 都不包含 `iteration_id`。`UsageReportedData` 携带 `iteration_id`，但 `UsageObservation` 未建模该字段。

**分析**：同一 Run/Attempt 内可能出现多轮 USAGE_REPORTED（例如 Engine agent loop 中有多轮 runner 调用）。若两次调用的 `prompt_tokens` / `completion_tokens` / `total_tokens` 恰好相同且 `observed_at` 微秒精度内同时到达，digest 会碰撞。`observed_at`（UTC 微秒级）提供了强唯一性保证，且实践中 USAGE_REPORTED 按 sequential event delivery 到达，微秒碰撞概率极低。

**建议**：后续 phase 考虑为 `UsageObservation` 增加 `iteration_id: str` 字段，并纳入 digest payload，以消除理论碰撞窗口。

**严重性评估**：不阻塞当前 slice。USAGE_REPORTED 是 projection signal，非 canonical fact，digest 碰撞仅影响 projection payload 的可区分性，不影响 Run / Attempt 状态正确性。

### F3（低）— `_display_text_from_input_event` docstring 中异常类型标注不准确

**文件**：`dayu/host/engine_ingest.py:3086`

**证据**：docstring 写 `:raises ValueError:`，但实际实现调用 `event_payload_object` 和 `_required_payload_text`，两者均抛出 `HostDurableError`。

**分析**：此为预存问题，非本 slice 引入。但本 slice 在 `_estimate_usage_observation_input` 中依赖该函数的异常类型来决定 `except` 范围，准确的 docstring 有助于后续收窄异常处理。

**建议**：改为 `:raises HostDurableError:`。可与 F1 一起在 Slice 4 批量处理。

**严重性评估**：不阻塞，不影响功能正确性。

## 验证结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 62 passed |
| `pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` | 11 passed |
| `python -m pyright dayu/host/context_budget.py dayu/host/engine_ingest.py tests/host/test_context_budget.py tests/host/test_engine_ingest_mapping.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无输出 |

## 测试覆盖率审查

- ✅ `UsageObservationDiagnostic` 构造、校验（类型错误、空字符串、负 token）被 `UsageObservation.__post_init__` 间接覆盖
- ✅ `prompt_token_delta=prompt_tokens-estimated_input_tokens` 正向/负向均覆盖（delta=140 与 delta=-4）
- ✅ `prompt_token_delta=None` 当 `estimated_input_tokens is None` 时覆盖
- ✅ `build_usage_observation_diagnostic` 对非 `UsageObservation` 输入的 `TypeError` 由 `UsageObservationDiagnostic` 校验覆盖
- ✅ policy 缺失 / input event 缺失 / payload 不可读 / usage token 异常 → 四个降级路径全部有测试
- ✅ Engine usage regression tests（11 passed）确保 Engine contract 未被破坏

## Residual Risk 确认

- `provider_request_id=None` 是设计决定，非 bug；实现 artifact 和 plan 均记录为 residual risk
- Post-call observation estimate 与 dispatch-time estimate 同源（均使用 `display_text` + `ContextBudgetPolicy` + `BudgetEstimateInput` 同一结构），`estimator_digest` 可复现，满足 calibration 使用场景
- 未新增 durable table、未修改 durable state machine schema、未新增 Host public API

## 结论

Phase 12.3 Slice 2 实现正确、测试充分、边界清晰。三个 advisory findings（F1-F3）均不阻塞当前 slice，建议在 Slice 4 aggregate validation 中一并处理。
