# Phase 12.3 Slice 2 Re-Review - AgentMiMo - 2026-05-22

## Verdict

**PASS** — F1/F2/F3 修复正确，无新增 blocker。

## 审查范围

Controller adjudication 裁决的 P12.3-S2-F1/F2/F3 窄 fix，涉及：

- `dayu/host/context_budget.py` — `UsageObservation` 新增 `iteration_id` 字段、digest 纳入 `iteration_id`
- `dayu/host/engine_ingest.py` — `_estimate_usage_observation_input` 异常收窄、`_display_text_from_input_event` docstring 修正、`_usage_observation_diagnostic` / `_invalid_usage_observation_digest` 传入 `iteration_id`
- `tests/host/test_context_budget.py` — 同 attempt 不同 iteration digest 不同断言
- `tests/host/test_engine_ingest_mapping.py` — 现有 usage 测试覆盖 `iteration_id`

## 逐项确认

### F1: 收窄 `_estimate_usage_observation_input` 异常捕获

**PASS**。`engine_ingest.py:2192` 从 `except Exception` 改为 `except (HostDurableError, TypeError, ValueError)`。

调用链分析：
- `_display_text_from_input_event` → `event_payload_object` / `_required_payload_text` → 可抛 `HostDurableError`
- `estimate_context_budget` → `BudgetEstimateInput.__post_init__` → 可抛 `TypeError` / `ValueError`
- `_estimate_json_tokens` → `canonical_json_dumps` → 可抛 `ValueError`

三个异常类型覆盖了调用链所有可预期的失败路径。`AttributeError`、`KeyError` 等编程错误不再被吞掉，会向上传播。降级语义不变：返回 `None` → `estimate_unavailable`。

### F2: `iteration_id` 纳入 `UsageObservation` 与 digest

**PASS**。

- `context_budget.py:248` — `UsageObservation` 新增 `iteration_id: str` 字段，`__post_init__` 中 `_require_non_empty` 校验 ✓
- `context_budget.py:621` — `_usage_observation_digest` payload 的 `observation` 块包含 `iteration_id` ✓
- `engine_ingest.py:314` — `_usage_observation_diagnostic` 构造 `UsageObservation` 时传入 `data.iteration_id` ✓
- `engine_ingest.py:444` — `_invalid_usage_observation_digest` payload 包含 `iteration_id` ✓
- `engine_ingest.py:2064` — projection payload 仍保留 `iteration_id` ✓
- `test_context_budget.py` — `test_usage_observation_diagnostic_reports_prompt_delta` 中构造两个仅 `iteration_id` 不同的 observation，断言 `observation_digest` 不同 ✓
- 所有 existing usage observation 构造点已补 `iteration_id` ✓

### F3: `_display_text_from_input_event` docstring 修正

**PASS**。`engine_ingest.py:3087` 从 `:raises ValueError:` 改为 `:raises HostDurableError:`。`event_payload_object` 和 `_required_payload_text` 均通过 `HostDurableError` 报告 payload 缺失或解析失败，docstring 现在与实际异常一致。

### 边界检查

- Engine `UsageReportedData` / `RunnerUsageRecordedData` contract 未修改 ✓（`git diff HEAD -- dayu/engine/` 无输出）
- 未新增 usage config override / `supports_usage` ✓
- 未新增 Host public API ✓
- 未触及 Slice 3 scope ✓
- `USAGE_REPORTED` 仍为 `EventClass.PROJECTION_SIGNAL` ✓

## 验证结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 62 passed ✓ |
| `pytest tests/engine/runners/openai/... -q` | 11 passed ✓ |
| `pyright dayu/host tests/host tests/engine/runners/openai` | 0 errors, 0 warnings, 0 informations ✓ |
| `git diff --check` | clean ✓ |

## 与首次 review 的对比

首次 review 的 non-blocking 建议（`except Exception` 过宽）已被 F1 修复采纳。F2 增强了 digest 碰撞隔离。F3 修正了误导性 docstring。三个 fix 均为窄修复，未引入新风险。
