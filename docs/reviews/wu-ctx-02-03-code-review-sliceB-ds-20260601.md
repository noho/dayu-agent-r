# WU-CTX-02 + WU-CTX-03 Slice B Code Review

## Review metadata

- **Review target**: Slice B implementation（`CONTEXT_COMPACTION_FAILED` payload 诊断字段补齐）
- **Diff base**: 当前工作区相对 HEAD
- **Implementation artifact**: `docs/reviews/wu-ctx-02-03-implementation-sliceB-codex-20260601.md`
- **Approved plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- **Review date**: 2026-06-01
- **Reviewer**: DS (deepreview)

## Review scope

审查以下变更的正确性、完整性、边界遵守：

1. `build_context_compaction_failed_payload` / `validate_context_compaction_failed_payload` 新增 required fields 与 validator
2. `fallback_action` 枚举、`_validate_failed_fallback_fields` 一致性校验
3. proactive / reactive failed append helper 签名更新及所有 call site
4. `operation_id` 语义：request fact 路径 vs precondition 路径
5. `attempt_count` / `retry_repair_budget_exhausted` 语义正确性
6. 测试覆盖：no fallback、fallback dispatch、fallback fail closed、非法负数、非法 action、proactive/reactive failure paths
7. Slice B 边界：状态机、durable schema、fallback 实现、raw provider payload、兼容读取
8. README 不更新判断、pyright / tests 可信度

## Evidence summary

### 修改文件

| 文件 | 新增行 | 变更性质 |
|---|---|---|
| `dayu/host/context_events.py` | +87 | payload builder/validator 扩展、fallback 字段常量与校验 |
| `dayu/host/dispatch.py` | +57 | `_precondition_compaction_operation_id` helper、proactive call site 参数补齐 |
| `dayu/host/engine_ingest.py` | +42 | `_reactive_precondition_compaction_operation_id` helper、reactive call site 参数补齐 |
| `tests/host/test_context_compact_events.py` | +121 | 6 个新的/扩展的单元测试 |
| `tests/host/test_dispatch_scheduler.py` | +93 | 5 个集成测试扩展 + `_assert_failed_payload_no_fallback` helper |
| `tests/host/test_engine_ingest_mapping.py` | +75 | 5 个集成测试扩展 + `_assert_failed_payload_no_fallback` helper |

### 独立验证

- **Tests**: `126 passed in 1.21s`（与 artifact 报告的 1.29s 一致）
- **Pyright**: `0 errors, 0 warnings, 0 informations`

---

## Findings

### F1 (LOW): `_assert_failed_payload_no_fallback` 在两个测试模块中逐字重复

**位置**:
- `tests/host/test_dispatch_scheduler.py:4511-4542`
- `tests/host/test_engine_ingest_mapping.py:2773-2804`

**描述**: 完全相同的 32 行测试辅助函数在两个测试模块各自定义了一份。函数签名、docstring、断言逻辑完全一致。

**影响**: 未来若 `CONTEXT_COMPACTION_FAILED` payload 结构再次变更，需要同步修改两处。当前不影响功能正确性。

**建议**: 可提取到 `tests/host/conftest.py` 或 `tests/host/helpers.py`，但不阻塞合并。

---

### F2 (MEDIUM): `_validate_failed_fallback_fields` 拒绝路径缺少显式单元测试

**位置**: `dayu/host/context_events.py:494-518`

**描述**: `_validate_failed_fallback_fields` 实现了两类拒绝逻辑：

1. `fallback_action="not_applicable"` 但任意 fallback 诊断字段非 `None` → `ValueError`
2. `fallback_action="dispatch"/"fail_closed"` 但任意 fallback 诊断字段为 `None` → `ValueError`（由 `_required_text`/`_required_mapping` 抛出）

当前测试仅覆盖：
- `not_applicable` + 全 `None`（合法路径，`test_failed_payload_builder_and_validator_no_fallback`）
- `dispatch` + 全非 `None`（合法路径，`test_failed_payload_builder_and_validator_fallback_dispatch`）
- `fail_closed` + 全非 `None`（合法路径，`test_failed_payload_builder_and_validator_fallback_fail_closed`）
- 非法 `fallback_action` 枚举值（`test_failed_payload_rejects_invalid_fallback_action`）

**未覆盖的拒绝路径**：
- `fallback_action="not_applicable"` + `fallback_policy_decision="some_value"` → 应 `ValueError`
- `fallback_action="dispatch"` + `fallback_input_window=None` → 应 `ValueError`
- `fallback_action="fail_closed"` + `fallback_budget_result=None` → 应 `ValueError`

**影响**: validator 代码逻辑本身正确（已验证代码路径），但缺少回归测试保护。未来若有人修改 validator 逻辑，这些拒绝路径可能被意外削弱。

**建议**: 在 `test_context_compact_events.py` 补充 2-3 个 `pytest.raises` 测试覆盖上述拒绝路径。建议在 Slice C 中补齐，不阻塞 Slice B 合并。

---

### F3 (INFO): `context_budget_policy_missing` 与 `input_event_missing` 前置条件路径无集成测试

**位置**: `dayu/host/engine_ingest.py:1122-1140`

**描述**: reactive 前置条件失败共 4 条路径：
1. `context_budget_policy_missing` — 无集成测试
2. `input_event_missing` — 无集成测试
3. `reactive_compact_count_unreadable` — `test_reactive_compact_corrupt_count_fact_fails_closed` 覆盖
4. `reactive_compact_limit_reached` — `test_reactive_compact_count_limit_fails_closed_without_second_attempt` 覆盖

路径 1、2 是边缘条件（policy 未配置、input event 丢失），在正常集成环境中不会触发。Payload builder/validator 在单元测试层覆盖了这些字段的语义。风险较低。

**影响**: 低。这 2 条路径的 failed payload 结构与其他 precondition 路径完全一致（synthetic operation_id + attempt_count=0 + retry_repair_budget_exhausted=False），且 `_fail_reactive_recovery_without_request` 方法逻辑统一。

---

### F4 (PASS): 所有 12 条 `CONTEXT_COMPACTION_FAILED` 写入路径均正确传递新增 required fields

**已验证 call site 清单**:

| # | 来源 | failure_reason | operation_id 来源 | attempt_count | retry_repair_exhausted |
|---|---|---|---|---|---|
| 1 | dispatch | `hard_threshold_before_dispatch` | synthetic precondition | 0 | false |
| 2 | dispatch | `proactive_compact_count_unreadable` | synthetic precondition | 0 | false |
| 3 | dispatch | `proactive_compact_limit_reached` | synthetic precondition | 0 | false |
| 4 | dispatch | `compactor_or_artifact_store_missing` | `requested.event_id` | 0 | false |
| 5 | dispatch | `stale_compaction_result` | `pending.operation_id` | len(rejected) | false |
| 6 | dispatch | `compaction_failed` (operation) | `pending.operation_id` | len(rejected) | len>0 |
| 7 | engine_ingest | `context_budget_policy_missing` | synthetic precondition | 0 | false |
| 8 | engine_ingest | `input_event_missing` | synthetic precondition | 0 | false |
| 9 | engine_ingest | `reactive_compact_count_unreadable` | synthetic precondition | 0 | false |
| 10 | engine_ingest | `reactive_compact_limit_reached` | synthetic precondition | 0 | false |
| 11 | engine_ingest | `stale_compaction_result` | `pending.operation_id` | len(rejected) | false |
| 12 | engine_ingest | `compaction_failed` (operation) | `pending.operation_id` | len(rejected) | len>0 |

**验证方法**: 逐行审查 diff 中每个 `_append_compaction_failed_event` / `_append_reactive_compaction_failed_event` call site，确认全部 5 个新增 required 参数均已显式传递。

---

### F5 (PASS): `operation_id` 语义正确且稳定

**Request fact 路径**（路径 4、5、6、11、12）:
- 使用 `requested.event_id` 或 `pending.operation_id`（两者等价，均为已写入 `CONTEXT_COMPACTION_REQUESTED` 的 event_id）
- 正确关联 failed fact 到其 request fact

**Precondition 路径**（路径 1、2、3、7、8、9、10）:
- Proactive: `_precondition_compaction_operation_id(failure_reason=..., estimate=...)` → `"precondition:{failure_reason}:{estimator_digest}"`
- Reactive: `_reactive_precondition_compaction_operation_id(context=..., failure_reason=...)` → `"reactive_precondition:{failure_reason}:{engine_event_ref}"`
- 两个 helper 均为纯函数，输入确定则输出确定，不依赖外部状态
- `estimator_digest` 是 sha256 digest，`engine_event_ref` 基于 candidate 的 execution_id + worker_event_index，均保证稳定性
- 不会改变状态机，不新增 request fact

---

### F6 (PASS): `attempt_count` / `retry_repair_budget_exhausted` 语义正确

| 场景 | attempt_count | retry_repair_budget_exhausted | 语义验证 |
|---|---|---|---|
| 前置条件失败（无 request fact） | 0 | false | 正确：无 operation 故无 attempt |
| compactor 缺失（有 request fact，未执行） | 0 | false | 正确：request 已写但未执行 |
| stale result | len(rejected_attempts) | false | 正确：保留 attempt 诊断但不标记预算耗尽 |
| operation failure（有 rejected attempts） | len(rejected_attempts) | true | 正确：有 rejected attempts 且最终失败 |
| operation failure（无 rejected attempts） | 0 | false | 正确：首次尝试即失败 |

**特别验证**:
- `retry_repair_budget_exhausted` 仅在 `len(result.rejected_attempts) > 0` 时为 `true`，语义为"存在 semantic retry/repair 尝试且最终失败"
- validator 使用 `_required_non_negative_int` 校验 `attempt_count`，拒绝负数（含 `-1`），有 `test_failed_payload_rejects_negative_attempt_count` 覆盖

---

### F7 (PASS): `fallback_action` validator 足够严格

**枚举约束**（`context_events.py:197-203`）:
```python
_FALLBACK_ACTIONS = frozenset(("dispatch", "fail_closed", "not_applicable"))
```

**一致性校验**（`_validate_failed_fallback_fields`）:

| fallback_action | fallback 诊断字段约束 | 实现 |
|---|---|---|
| `not_applicable` | 全部 4 个字段必须为 `None` | `is not None` 检查 |
| `dispatch` | 全部 4 个字段必须非 `None`（非空 text / mapping） | `_required_text` + `_required_mapping` |
| `fail_closed` | 同上 | 同上 |
| 其他任意值 | 拒绝 | `ValueError("fallback_action must be dispatch, fail_closed or not_applicable")` |

**边界情况验证**:
- 空字符串 `""` 作为 `fallback_action` → 不在 `_FALLBACK_ACTIONS` 中 → `ValueError`
- `not_applicable` 但 `fallback_policy_decision=""` → `"" is not None` → `ValueError`（正确拒绝）
- 执行顺序：先 `_require_fields` 确保字段存在 → `_required_text` 校验 `fallback_action` 非空 → 枚举检查 → 一致性校验。顺序安全。

---

### F8 (PASS): Slice B 边界严格遵守

**未改变**:
- 状态机：未新增 transition
- Durable schema：未改变 EventLog 表结构
- Fallback 实现：未实现 fallback selection、budget re-estimate、fallback dispatch/fail_closed E2E
- Raw provider payload：未加入
- 兼容读取：未读旧 failed payload，未做兼容性读取
- Public API：未改变任何公开接口签名（builder/validator 新增参数均为 keyword-only，向后兼容的调用方不受影响——但实际上所有 call site 均已更新）

**已改变（在 Slice B 范围内）**:
- `CONTEXT_COMPACTION_FAILED` payload required fields 从 6 个扩展到 13 个
- Builder 签名新增 6 个参数（1 required + 5 optional with defaults）
- Validator 新增 6 个字段的类型与语义校验
- Proactive / reactive failed append helper 签名各新增 3 个 required 参数

---

### F9 (INFO): 冗余括号

**位置**: `dispatch.py:1626-1628`, `engine_ingest.py:1744-1746`

```python
retry_repair_budget_exhausted=(
    retry_repair_budget_exhausted
),
```

多余的括号不产生语义差异，纯为风格问题。不阻塞合并。

---

## Conclusion

**结论: PASS**

Slice B 实现正确补齐了 `CONTEXT_COMPACTION_FAILED` payload 的诊断字段。所有 12 条写入路径均正确传递新增 required fields；`operation_id` 语义对 request fact 路径使用真实 event_id、对 precondition 路径使用稳定 synthetic id；`attempt_count` / `retry_repair_budget_exhausted` 语义与 plan 一致；`fallback_action` validator 严格且正确；Slice B 边界未越界实现 fallback、未改状态机、未改 durable schema。

## Residual risks

1. **F2 未覆盖的 validator 拒绝路径**：`not_applicable` + 非 null fallback fields、`dispatch`/`fail_closed` + null fallback fields 缺少显式单元测试。validator 代码逻辑本身正确，风险在于缺乏回归保护。
2. **Fallback 字段尚无生产调用方**：当前所有 call site 均使用默认 `not_applicable`。`dispatch`/`fail_closed` 路径仅通过单元测试的 builder→validator 往返覆盖，未经集成测试验证。这对 Slice B 是正确的（fallback 实现在后续 Slice），但后续 Slice 需要补齐集成覆盖。
3. **`context_budget_policy_missing` / `input_event_missing` 路径无集成测试**：这 2 个 reactive 前置条件路径仅通过 `_fail_reactive_recovery_without_request` 的统一逻辑间接覆盖。

## Test gaps

| Gap | 严重度 | 建议 |
|---|---|---|
| `_validate_failed_fallback_fields` 拒绝路径 | Medium | Slice C 补齐 2-3 个 `pytest.raises` 测试 |
| `hard_threshold_before_dispatch` 集成测试 | Low | 可选；当前仅单元测试覆盖 |
| `context_budget_policy_missing` / `input_event_missing` 集成测试 | Low | 可选；边缘条件，统一 helper 已间接保证 |

## Blocking questions

无。建议在 Slice C 中处理 F2（补齐 validator 拒绝路径测试）。

## Artifact path

- `docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md`
