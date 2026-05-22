# Phase 12.3 Slice 2 Re-review — AgentDS — 2026-05-22

## Verdict

**PASS** — 三个 advisory findings (P12.3-S2-F1/F2/F3) 均已正确修复，原 review 中 PASS 结论不变，无新增 blocking finding。

## Review Sources

- Controller adjudication: `docs/reviews/phase12-3-slice2-code-review-controller-adjudication-20260522.md`
- Implementation artifact (+ Fix Addendum): `docs/reviews/phase12-3-slice2-implementation-codex-20260522.md`
- Original DS review: `docs/reviews/phase12-3-slice2-code-review-ds-20260522.md`

## Fix Verification

### F1: `_estimate_usage_observation_input` 异常范围收窄

**文件**: `dayu/host/engine_ingest.py:2192`

**旧代码**: `except Exception:`
**新代码**: `except (HostDurableError, TypeError, ValueError):`

**验证**: 调用链 `_display_text_from_input_event`（抛出 `HostDurableError`）+ `estimate_context_budget`（抛出 `TypeError`/`ValueError`）实际抛出的异常类型全部被 `(HostDurableError, TypeError, ValueError)` 覆盖。`AttributeError`、`KeyError`、`RecursionError` 等编程错误不再被吞掉。降级语义不变（仍返回 `None` → `estimate_unavailable`）。

**结果**: ✅ PASS

### F2: `UsageObservation` 纳入 `iteration_id`

**文件**: `dayu/host/context_budget.py:248`、`dayu/host/context_budget.py:621`、`dayu/host/engine_ingest.py:3120`

**变更**:
- `UsageObservation` 新增字段 `iteration_id: str`（`context_budget.py:248`），含 `_require_non_empty` 校验（`context_budget.py:269`）
- `_usage_observation_digest` 的 observation payload 包含 `"iteration_id": observation.iteration_id`（`context_budget.py:621`）
- `_invalid_usage_observation_digest` 的 observation payload 包含 `"iteration_id": data.iteration_id`（`engine_ingest.py:3120`）
- `_usage_observation_diagnostic` 构造 `UsageObservation` 时传入 `iteration_id=data.iteration_id`（`engine_ingest.py:327`）
- 已存测试 `test_usage_observation_does_not_adjust_threshold_decision` 补上 `iteration_id="iter-budget"`

**测试覆盖** (`tests/host/test_context_budget.py:346-367`):
- 同一 attempt、不同 iteration (`iter-budget` vs `iter-budget-next`) 产生不同 `observation_digest`
- `next_iteration_diagnostic.observation_digest != diagnostic.observation_digest`

**结果**: ✅ PASS

### F3: `_display_text_from_input_event` docstring 异常类型修正

**文件**: `dayu/host/engine_ingest.py:3087`

**旧**: `:raises ValueError: payload 缺少展示文本时抛出。`
**新**: `:raises HostDurableError: payload 缺少展示文本或无法解析时抛出。`

**验证**: `event_payload_object` 和 `_required_payload_text` 实际抛出 `HostDurableError`，docstring 与实现一致。

**结果**: ✅ PASS

## 防线检查

- ✅ Engine contract 不变：`git diff HEAD -- dayu/engine/` 无输出
- ✅ 未引入 usage config override / `supports_usage` / `usage_enabled`
- ✅ `USAGE_REPORTED` 保持 `EventClass.PROJECTION_SIGNAL`
- ✅ 未新增 Host public API、durable state machine schema 或 durable table
- ✅ 仅 5 个文件变更，均在 Slice 2 allowed files 范围内，无 Slice 3 scope 渗透

## 验证结果

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` | 62 passed |
| `pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` | 11 passed |
| `python -m pyright dayu/host/context_budget.py dayu/host/engine_ingest.py tests/host/test_context_budget.py tests/host/test_engine_ingest_mapping.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无输出 |

## Conclusion

P12.3-S2-F1/F2/F3 全部正确修复。原 review 中 PASS 结论维持。无新增 residual risk。
