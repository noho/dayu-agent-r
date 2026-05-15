# Host Phase 6 P6-S5 Code Re-Review — AgentDS

- **Review type**: adversarial re-review of accepted findings fix
- **Original review**: `docs/reviews/host-phase6-code-review-s5-ds-20260515.md`
- **Fix description**: `docs/reviews/host-phase6-fix-s5-duplicate-governance-20260515.md`
- **Scope**: P6-S5 uncommitted changes on `feat/host-phase-6-toolruntime`
- **Files re-reviewed**: `dayu/host/tool_runtime.py`, `tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_diagnostics.py`, `dayu/host/README.md`, `tests/README.md`

## Verdict

**All accepted findings are fixed.** DS-F1 到 DS-F4 均已修复且有对应测试证明。DS-F5 和 DS-F6 按 controller 裁决 deferred 为 low-risk tracking，不阻塞 S5 完成。无回归，无新增类型错误或分层违规。

---

## Finding Status

### DS-F1 — Missing test coverage for `require_justification` valid-justification path and downgrade-to-hint path

**Status: FIXED**

**生产代码**: `tool_runtime.py:1552-1558` — `_decision_for_request` 逻辑本身在原始提交中已正确实现，未修改。

**新增测试**:

| 测试 | 覆盖路径 | 断言 |
|---|---|---|
| `test_require_justification_with_valid_argument_allows_execution` (line 312-342) | `require_justification` + 有效 justification 参数 → `ALLOW` | `call_count == 2`, `candidates[1].tool_fact_kind is COMPLETED`, `candidates[1].duplicate_decision is ALLOW` |
| `test_require_justification_without_argument_binding_downgrades_to_hint` (line 345-369) | `require_justification` + 未配置 `justification_argument_names_by_tool_name` → `HINT` | `call_count == 1`, `candidates[1].tool_fact_kind is GOVERNED_ERROR`, `candidates[1].duplicate_decision is HINT` |

**验证**: 两个分支均已覆盖。valid-justification 路径证明 plan §3.7 的 "allow execution only if the model supplied a structured justification" 需求。

---

### DS-F2 — Duplicate index overwrite on governed-error accepted entries

**Status: FIXED**

**生产代码**: `tool_runtime.py:2201-2212` — `_record_duplicate_accepted` 收紧为仅在 `policy_decision.kind is ALLOW` 且 `duplicate_decision.kind is ALLOW` 时才调用 `record_accepted`。

```python
if (
    policy_decision.kind is not ToolPolicyDecisionKind.ALLOW
    or duplicate_decision.kind is not DuplicateDecisionKind.ALLOW
):
    return
```

此 guard 确保：
- HINT/HARD_STOP/REQUIRE_JUSTIFICATION 产生的 governed_error accepted 不会覆盖 original successful result
- 普通 policy rejection（如 scope mismatch、side-effect 缺 key）的 governed_error 不会写入 index
- 只有实际执行了业务 callable 并成功 accepted 的 outcome 才进入 reuse 索引

`record_accepted` 本身的 overwrite 语义未改（line 1527-1528），但因为 caller 已经过滤，`_DuplicateAcceptedEntry` 只会包含 successful tool result。

**新增测试**: `test_governed_duplicate_does_not_overwrite_prior_successful_reuse_source` (line 372-403)
- 步骤 1: call-1 (ALLOW) → accepted → recorded in index
- 步骤 2: call-2 (HINT) → governed error → accepted → **未** recorded (per fix)
- 步骤 3: 修改 policy 为 REUSE → call-3 → 命中 index → 返回 call-1 的 `{"accepted": "prior-success"}`
- `call_count == 1`，`candidates[2].tool_fact_kind is REUSE`，`outcome.result.value == {"accepted": "prior-success"}`

---

### DS-F3 — Diagnostic emitter validation inconsistency

**Status: FIXED**

**生产代码**: `tool_runtime.py:1569-1570` — `DeterministicToolTraceDiagnosticEmitter.emit` 补齐了两行校验：

```python
_require_non_empty_text(record.reason_code, field_name="reason_code")
_require_non_empty_text(record.message, field_name="message")
```

现在三个 emitter 实现 (`Deterministic`, `Noop`, `InMemory`) 在 `emit` 入口处有完全一致的字段非空校验。

**新增测试**: `test_deterministic_diagnostic_emitter_rejects_empty_fields` (line 174-182)
- 空 `reason_code` → `pytest.raises(ValueError, match="reason_code")`
- 空 `message` → `pytest.raises(ValueError, match="message")`

---

### DS-F4 — Prior refs in governed_error from non-duplicate policy rejections

**Status: FIXED**

**生产代码**: 两处修改协作完成修复：

1. `tool_runtime.py:2098-2101` — 新增 `duplicate_governed` bool，在 policy_decision 被 duplicate 覆写前捕获：
```python
duplicate_governed = (
    policy_decision.kind is ToolPolicyDecisionKind.ALLOW
    and duplicate_decision.kind is not DuplicateDecisionKind.ALLOW
)
```

2. `tool_runtime.py:4010-4014` — `_tool_fact_accept_candidate` 中 prior refs 条件收紧为双重 guard：
```python
reuse_prior_event_refs=(
    duplicate_decision.prior_event_refs
    if tool_fact_kind is ToolFactKind.GOVERNED_ERROR and duplicate_governed
    else ()
),
```

只有同时满足"canonical fact kind 是 GOVERNED_ERROR"且"governed outcome 由 duplicate governance 触发"时，prior refs 才进入 candidate。

**新增测试**: `test_plain_policy_rejection_does_not_carry_duplicate_prior_refs` (line 406-433)
- call-1: 正常 scope → ALLOW → recorded in index
- call-2: `run_id="run-mismatch"` → scope mismatch → policy GOVERNED_ERROR
- 断言: `candidates[1].duplicate_decision is HARD_STOP`（index 命中），但 `candidates[1].reuse_prior_event_refs == ()`（duplicate_governed=False）
- 断言: `candidates[1].policy_decision.reason_code == "tool_call_not_allowed_in_scope"`（真正的拒绝原因是 scope mismatch，不是 duplicate）

---

### DS-F5 — `semantic_duplicate_key` missing dedicated test

**Status: DEFERRED** (controller 裁决)

`sensantic_duplicate_key` 默认关闭（`semantic_duplicate_key_argument_name=None`），当前测试中的工具 policy 均未启用。后续 policy provider 启用此字段时需补充专项测试。不阻塞 S5。

### DS-F6 — `GOVERNED_ERROR` candidate `duplicate_decision` field not validated in `__post_init__`

**Status: DEFERRED** (controller 裁决)

当前所有代码路径均正确设置了 `duplicate_decision`，运行时无影响。防御性校验可在后续 ToolRuntime hardening 阶段统一处理。不阻塞 S5。

---

## Validation

### Test Execution

```
$ pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q
24 passed in 0.20s   (+5 vs original review)

$ pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q
46 passed in 0.23s   (+5 vs original review)
```

新增 5 个测试（+4 duplicate governance, +1 diagnostics），全部通过，无回归。

### Type Check

```
$ python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations
```

### Fix-Specific Verification Matrix

| Finding | 生产变更 | 新增测试 | 覆盖率 |
|---|---|---|---|
| DS-F1 | 无（逻辑已正确） | `test_require_justification_with_valid_argument_allows_execution`, `test_require_justification_without_argument_binding_downgrades_to_hint` | `_decision_for_request` line 1552-1558 全分支 |
| DS-F2 | `_record_duplicate_accepted` 收紧 guard | `test_governed_duplicate_does_not_overwrite_prior_successful_reuse_source` | ALLOW-only record semantic |
| DS-F3 | `DeterministicToolTraceDiagnosticEmitter.emit` 补齐校验 | `test_deterministic_diagnostic_emitter_rejects_empty_fields` | 3 个 emitter 校验一致 |
| DS-F4 | `duplicate_governed` bool + double guard | `test_plain_policy_rejection_does_not_carry_duplicate_prior_refs` | scope mismatch + prior refs=() |

### Regression Check (Original Tests)

原始 review 中全部 19 个 S5 测试和 41 个 full P6 测试仍然通过，P6-S1~S4 测试无回归。

---

## Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| `duplicate_decision` field 在非 duplicate-governed 的 candidate 中仍反映 duplicate index 原始查找结果（如 scope mismatch rejection 中 `duplicate_decision=HARD_STOP`） | LOW | P6-S6 或 hardening | 不影响正确性（prior refs 已隔离），但 audit payload 可解释性有改进空间 |
| `record_accepted` 底层仍为 overwrite 语义 | INFO | — | caller 已过滤，overwrite 只发生在 ALLOW+ALLOW 场景下更新同 key 的 newer result，语义合理 |
| DS-F5 semantic_duplicate_key 无测试 | LOW | P12 或后续 policy provider | 当前默认关闭，启用时需补充测试 |
| DS-F6 defensive validation | LOW | ToolRuntime hardening | 当前代码路径安全，后续统一处理 |

---

## Summary

DS-F1 到 DS-F4 四个 accepted findings 全部 fix confirmed。生产代码修改量小且精准：`_record_duplicate_accepted` 增加 3 行 guard、`_tool_fact_accept_candidate` 增加 `duplicate_governed` 参数、`DeterministicToolTraceDiagnosticEmitter.emit` 增加 2 行校验。新增 5 个测试精确覆盖每个 fix 路径。24/24 S5 tests + 46/46 full P6 tests passed，pyright clean。DS-F5/F6 按 controller 裁决 deferred 合理，不阻塞 S5 completion。
