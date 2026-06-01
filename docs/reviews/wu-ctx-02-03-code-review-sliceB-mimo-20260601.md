# WU-CTX-02 + WU-CTX-03 Slice B code review

## Gate / Scope

- Gate: WU-CTX-02 + WU-CTX-03 Slice B code review
- Scope: `CONTEXT_COMPACTION_FAILED` payload 诊断字段补足（operation_id、attempt_count、retry_repair_budget_exhausted、fallback fields、fallback_action validator、proactive/reactive failed append helpers、tests）
- Implementation artifact: `docs/reviews/wu-ctx-02-03-implementation-sliceB-codex-20260601.md`
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Review date: 2026-06-01

## Diff 概要

### `dayu/host/context_events.py`

- 新增 `_FIELD_ATTEMPT_COUNT`、`_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED` 和 5 个 fallback 字段常量。
- `_FAILED_REQUIRED_FIELDS` 扩展为包含所有新字段。
- `build_context_compaction_failed_payload` 签名新增 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted` 和 5 个 fallback 参数（默认值为 `None` / `not_applicable`）。
- `validate_context_compaction_failed_payload` 新增 `_required_text(operation_id)`、`_required_non_negative_int(attempt_count)`、`_required_bool(retry_repair_budget_exhausted)`、`_required_text(fallback_action)` 和 fallback action 枚举校验。
- 新增 `_validate_failed_fallback_fields`：`not_applicable` 时要求 4 个 fallback 字段全为 `None`；`dispatch` / `fail_closed` 时要求非空。
- 新增 `_FALLBACK_ACTIONS` frozenset 和三个 action 常量。

### `dayu/host/dispatch.py`

- 新增 `_precondition_compaction_operation_id` helper，使用 `f"precondition:{failure_reason}:{estimate.estimator_digest}"` 生成稳定 id。
- `_append_compaction_failed_event` 签名新增 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`。
- 3 处 precondition failure 调用点传入 `operation_id=_precondition_compaction_operation_id(...)`、`attempt_count=0`、`retry_repair_budget_exhausted=False`。
- 2 处 operation result 调用点（stale / failed）传入 `operation_id=pending.operation_id`、`attempt_count=len(result.rejected_attempts)`。
- stale result 的 `retry_repair_budget_exhausted=False`；operation failure 的 `retry_repair_budget_exhausted=(len(result.rejected_attempts) > 0)`。

### `dayu/host/engine_ingest.py`

- 新增 `_reactive_precondition_compaction_operation_id` helper，使用 `f"reactive_precondition:{failure_reason}:{_engine_event_ref(context.candidate)}"`。
- `_append_reactive_compaction_failed_event` 签名新增 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`。
- 2 处 precondition failure 调用点传入对应 helper、`attempt_count=0`、`retry_repair_budget_exhausted=False`。
- 2 处 operation result 调用点（stale / failed）传入 `pending.operation_id`、`attempt_count=len(operation_result.rejected_attempts)`。
- stale result 的 `retry_repair_budget_exhausted=False`；operation failure 的 `retry_repair_budget_exhausted=(len(operation_result.rejected_attempts) > 0)`。

### 测试文件

- `test_context_compact_events.py`：原 `test_failed_payload_builder_and_validator` 拆分为 5 个测试：no_fallback、fallback_dispatch、fallback_fail_closed、negative_attempt_count、invalid_fallback_action；`test_failed_payload_rejects_missing_required_fields` 更新 expected error message。
- `test_dispatch_scheduler.py`：5 个现有测试更新为断言新字段；新增 `_assert_failed_payload_no_fallback` helper。
- `test_engine_ingest_mapping.py`：5 个现有测试更新为断言新字段；新增 `_assert_failed_payload_no_fallback` helper。

## Findings

### F-01 [INFO] 测试 helper `_assert_failed_payload_no_fallback` 重复定义

- 位置: `tests/host/test_dispatch_scheduler.py:4508` 和 `tests/host/test_engine_ingest_mapping.py:2768`
- 说明: 两个测试文件各自定义了完全相同的 `_assert_failed_payload_no_fallback` helper。违反编码硬约束"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。
- 严重性: INFO（测试代码，不影响生产行为，但应在后续 slice 中抽取到共享测试 util）。
- 建议: 在 Slice C/D/E 或后续 PR 中将该 helper 移至 `tests/host/_test_helpers.py` 或类似共享位置。

### F-02 [INFO] `_precondition_compaction_operation_id` 和 `_reactive_precondition_compaction_operation_id` 结构一致但分散

- 位置: `dayu/host/dispatch.py:231`、`dayu/host/engine_ingest.py:3629`
- 说明: 两个 helper 都使用 `f"{prefix}:{failure_reason}:{stable_ref}"` 格式，但前缀和 stable ref 来源不同（proactive 用 `estimate.estimator_digest`，reactive 用 `_engine_event_ref`）。设计上 proactive 和 reactive 属于不同模块，当前分散是合理的；若后续 fallback 需要统一 operation id 格式，可考虑抽取到 `context_events.py`。
- 严重性: INFO。

### F-03 [PASS] operation_id 稳定性

- proactive precondition failure: `f"precondition:{reason}:{estimate.estimator_digest}"` — 同一 estimate digest 和 reason 产生相同 id，不新增 request fact，不改变状态机。
- reactive precondition failure: `f"reactive_precondition:{reason}:{_engine_event_ref(candidate)}"` — 同一 EngineEvent 和 reason 产生相同 id。
- normal flow: 使用 `requested.event_id`（CONTEXT_COMPACTION_REQUESTED 的 event id），与 plan 一致。
- 结论: 符合 plan "不改变状态机"的 Slice B 边界。

### F-04 [PASS] attempt_count / retry_repair_budget_exhausted 语义

- precondition failure（hard_threshold、compact_count_unreadable、compact_limit_reached、compactor_missing）：`attempt_count=0`、`exhausted=False` — 无 proposal attempt，语义正确。
- stale result：`attempt_count=len(rejected_attempts)`（保留诊断）、`exhausted=False` — stale 不代表 budget exhausted，语义正确。
- operation failure（repair 耗尽、quality rejection 等）：`attempt_count=len(rejected_attempts)`、`exhausted=(len(rejected_attempts) > 0)` — 有 rejected attempts 且最终失败意味着 budget exhausted，语义正确。

### F-05 [PASS] fallback_action validator 严格性

- `not_applicable` 时：4 个 fallback 字段必须全为 `None`，否则 `ValueError`。
- `dispatch` / `fail_closed` 时：`fallback_policy_decision` 和 `fallback_input_digest` 为 required text；`fallback_input_window` 和 `fallback_budget_result` 为 required mapping。
- 非法 action 值被 `_FALLBACK_ACTIONS` frozenset 拒绝。
- 结论: validator 足够严格。

### F-06 [PASS] scope boundary 遵守

- 未实现 fallback dispatch / selection / budget re-estimate。
- 未改变状态机、未新增 `CONTEXT_COMPACTION_REQUESTED`、未改变 Run / Attempt transition。
- 未改 durable schema、未读旧 payload、未加入兼容读取。
- 未加入 raw provider payload。
- fallback 参数默认值为 `None` / `not_applicable`，不影响现有调用方。

### F-07 [PASS] 测试覆盖

- `test_context_compact_events.py`：覆盖 no fallback、fallback dispatch、fallback fail closed、negative attempt_count、invalid fallback_action、missing required fields。
- `test_dispatch_scheduler.py`：覆盖 stale result（proactive）、repair attempt rejection（proactive）、compactor missing（proactive）、compact limit reached（proactive）、corrupted compact count（proactive），均断言新字段。
- `test_engine_ingest_mapping.py`：覆盖 stale result（reactive）、compact failure without lost（reactive）、count limit（reactive）、repeated overflow（reactive）、corrupt count（reactive），均断言新字段。

### F-08 [PASS] README 不更新判断

- implementation artifact 声明：`dayu/host/README.md` 未维护 `CONTEXT_COMPACTION_FAILED` payload 字段清单；`tests/README.md` 已包含 context compact 覆盖。
- 新增字段不会造成 README 与代码不一致。判断成立。

### F-09 [PASS] pyright / tests 可信度

- implementation artifact 声明 pyright `0 errors, 0 warnings, 0 informations`；tests `126 passed in 1.29s`。
- 代码 diff 未引入 `Any`、`object` 或无类型参数。签名完整。
- 所有 docstring 为中文，参数、返回值、异常说明完整。

## Conclusion

**PASS** — Slice B 实现正确落地 plan 要求的 `CONTEXT_COMPACTION_FAILED` payload 诊断字段。所有 failed payload builder/validator 路径都包含新增 required fields；operation_id 语义稳定且不改变状态机；attempt_count / retry_repair_budget_exhausted 语义正确；fallback_action validator 足够严格；scope boundary 遵守良好；测试覆盖全面。

## Blocking questions

无。

## Residual risks

1. **test helper 重复（F-01）**: 两个测试文件各有一份 `_assert_failed_payload_no_fallback`。不影响正确性，但应在后续 slice 中抽取。
2. **Slice B 只补 payload 诊断**: fallback selection、fallback budget re-estimate、fallback dispatch / fail closed E2E 仍由 Slice C/D/E 覆盖。
3. **precondition operation id 格式**: 当前使用模块私有 helper 生成；若后续 fallback 或 durable read 需要统一解析 operation id，需评估格式稳定性。

## Test gaps

- 缺少 `attempt_count=0` + `retry_repair_budget_exhausted=False` 的 operation failure 场景测试（例如 compactor 返回 error 但无 rejected attempts）。当前所有 operation failure 测试路径的 `rejected_attempts` 非空。此组合在 validator 层面可通过（`0 > 0 = False`），但缺少显式覆盖。

## Artifact path

- `docs/reviews/wu-ctx-02-03-code-review-sliceB-mimo-20260601.md`
