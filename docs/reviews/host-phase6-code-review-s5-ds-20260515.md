# Host Phase 6 P6-S5 Adversarial Code Review — AgentDS

- **Review type**: adversarial deep review (AgentDS independent review)
- **Scope**: uncommitted P6-S5 changes on `feat/host-phase-6-toolruntime`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Plan truth**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` P6-S5
- **Implementation notes**: `docs/reviews/host-phase6-implementation-s5-duplicate-governance-20260515.md`
- **Files reviewed**: `dayu/host/tool_runtime.py`, `tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_diagnostics.py`, `dayu/host/README.md`, `tests/README.md`
- **Verification**: pytest 19/19 (S5) + 41/41 (full P6) passed; pyright 0 errors, 0 warnings, 0 informations

## Verdict

**Approve with observations.** P6-S5 正确落地了 run-local duplicate governance 与最小 diagnostic emitter interface。核心语义正确：duplicate key 排除 `index_in_iteration`，reuse 不调用 callable 也不追加第二个 `TOOL_RESULT_ACCEPTED`，ToolRuntime 新实例不继承旧索引，diagnostic refs 只是 typed refs 不写 durable trace projection。未发现数据泄漏、EventLog 污染或分层违规。发现 2 个中等严重度遗漏（测试覆盖缺口与索引覆盖写语义偏差）和 4 个低严重度发现；均可在 P6-S6 integration 或后续 slice 中修复，不构成 stop condition。

---

## Findings

### F1 — Missing test coverage for `require_justification` valid-justification path and downgrade-to-hint path (MEDIUM)

**文件**: `dayu/host/tool_runtime.py:1552-1558`

`_decision_for_request` 有两个未覆盖分支：

1. **line 1553** `return DuplicateDecisionKind.HINT`：当 `require_justification` 工具在 `justification_argument_names_by_tool_name` 中无配置时降级为 HINT。此分支未被任何测试触发。
2. **line 1556-1557** `return DuplicateDecisionKind.ALLOW`：当调用参数包含合法 justification 字符串时，duplicate 决策应降级为 ALLOW 并允许执行 callable。此路径在 plan §3.7 中明确要求（"accept governance event and allow execution only if the model supplied a structured justification in arguments"），但无测试覆盖。

当前唯一覆盖 `REQUIRE_JUSTIFICATION` 的测试 `test_duplicate_governed_matrix_produces_diagnostics` 只在无 justification 参数的情况下验证 `REQUIRE_JUSTIFICATION → governed_error` 路径。

**建议**: 在 `test_toolruntime_duplicate_governance.py` 中新增两个参数化用例：
- `require_justification_with_valid_justification_allows_execution`：调用携带合法 justification 参数时 callable 被调用
- `require_justification_without_justification_argument_name_downgrades_to_hint`：未配置 justification 参数名时降级为 HINT

**严重级别**: MEDIUM — 属于 plan completion signal 覆盖缺口（"duplicate action matrix is covered"），当前 matrix 的 `require_justification → allow` 路径未证明。

---

### F2 — Duplicate index overwrite on governed-error accepted entries (MEDIUM)

**文件**: `dayu/host/tool_runtime.py:1527-1531`

`InMemoryRunLocalDuplicateGovernance.record_accepted` 对相同 duplicate key 无条件覆盖写入：

```python
self._entries_by_key[duplicate_key] = _DuplicateAcceptedEntry(...)
```

`_record_duplicate_accepted`（line 2218-2236）对 ALLOW、HINT、HARD_STOP、REQUIRE_JUSTIFICATION 都调用 `record_accepted`（仅跳过 REUSE）。这导致以下时序：

1. call-1: ALLOW → accepted → index[key] = (actual_success_result, ...)
2. call-2: HARD_STOP → governed_error → accepted → index[key] = (governed_error_outcome, ...) **覆盖 call-1**
3. call-3: 若 policy 变更为 REUSE → 返回 governed_error_outcome 而非 call-1 的原始成功结果

在当前静态 per-tool policy 下，同一工具的 decision 不会从 HARD_STOP 变成 REUSE，因此实际触发概率极低。但这构成了"last-writer-wins"语义，与 plan §3.7 的 `reuse` 要求（"return a tool result message derived from prior accepted result"）的直觉含义不一致——plan 暗示 `reuse` 应返回 actual result，而非任何 accepted entry 的最新覆盖值。

`_DuplicateAcceptedEntry` 未记录原始 `tool_fact_kind`，因此无法在 `record_accepted` 时区分"首次成功"与"后续 governed error"。

**建议**: 两种修复方案择一：
a) `record_accepted` 改为 `setdefault` 语义（不覆盖已有条目），确保 reuse 始终返回首次 accepted 的实际结果。
b) `_record_duplicate_accepted` 只为 ALLOW（即 `duplicate_decision.kind is ALLOW`）调用 `record_accepted`，跳过 HINT/HARD_STOP/REQUIRE_JUSTIFICATION。

方案 (b) 更保守且更符合 plan 语义。无论选哪种，需要对应测试证明覆盖写不会把 governed error 当作 reuse 来源。

**严重级别**: MEDIUM — 语义偏差，在 policy churn / 多 policy profile 场景下可能导致 reuse 返回错误结果。

---

### F3 — Diagnostic emitter validation inconsistency across implementations (LOW)

**文件**: `dayu/host/tool_runtime.py:1564-1577` vs `1583-1606` vs `1629-1642`

三个 `ToolTraceDiagnosticEmitter` 实现的输入验证不一致：

| 实现 | reason_code 验证 | message 验证 |
|---|---|---|
| `DeterministicToolTraceDiagnosticEmitter` | **无** | **无** |
| `NoopToolTraceDiagnosticEmitter` | `_require_non_empty_text` | `_require_non_empty_text` |
| `InMemoryToolTraceDiagnosticEmitter` | `_require_non_empty_text` | `_require_non_empty_text` |

`DeterministicToolTraceDiagnosticEmitter` 直接对 record 做 sha256 摘要而不先验证字段非空。空字符串会通过并产生确定性但无意义的 digest。这不影响安全性，但违反接口 contract 一致性——同一 protocol 的不同实现不应有不同的 validation 行为。

**建议**: 在 `DeterministicToolTraceDiagnosticEmitter.emit` 开头加入与 noop/in-memory 一致的字段验证，或把验证提升到 protocol 文档中说明"由调用方保证"。当前代码倾向"实现侧验证"，因此应补齐。

**严重级别**: LOW — 不影响功能正确性，但损害 contract 一致性与可维护性。

---

### F4 — `reuse_prior_event_refs` carried in governed_error from non-duplicate policy rejections (LOW)

**文件**: `dayu/host/tool_runtime.py:3994-3997`

`_tool_fact_accept_candidate` 中：

```python
reuse_prior_event_refs=(
    duplicate_decision.prior_event_refs
    if tool_fact_kind is ToolFactKind.GOVERNED_ERROR
    else ()
),
```

当 policy port 拒绝调用（如 side-effect 缺幂等 key）且 duplicate index 中存在先前 accepted 条目时，`duplicate_decision.prior_event_refs` 非空。此时 governed_error candidate 会携带与拒绝原因（side-effect 缺 key）无关的 prior refs。

实际触发路径：
1. call-1: ALLOW + idempotency key → accepted → index 有 entry
2. call-2: 相同 arguments 但缺 idempotency key → policy port 返回 GOVERNED_ERROR → `_tool_fact_accept_candidate` 中 `tool_fact_kind is GOVERNED_ERROR` → 携带 call-1 的 prior refs

这些 prior refs 在 EventLog payload 中语义模糊——看 payload 会以为 duplicate governance 参与了拒绝，但实际上拒绝来自 side-effect policy。

**建议**: 在 `_tool_fact_accept_candidate` 中将条件收窄为 `tool_fact_kind is ToolFactKind.GOVERNED_ERROR and duplicate_decision.kind is not DuplicateDecisionKind.ALLOW`，确保 prior refs 只在 duplicate governance 确实产生非 ALLOW 决策时才被携带。

**严重级别**: LOW — 极端边缘情况，不影响数据正确性或安全，但 EventLog payload 可解释性受损。

---

### F5 — `semantic_duplicate_key` lacking dedicated test (LOW)

**文件**: `dayu/host/tool_runtime.py:3837-3847` (`_semantic_duplicate_key`) 和 `695-704` (`_duplicate_key`)

`DuplicateGovernanceRequest.semantic_duplicate_key` 字段会参与 `_duplicate_key` 的 sha256 摘要，允许工具提供的语义 key 在参数规范化相同时区分不同类型调用。但无测试证明：

- 两条相同 normalized args 但不同 `semantic_duplicate_key` 的调用产生不同的 duplicate key
- `_semantic_duplicate_key` 在参数缺少对应 key 或值为非字符串时正确返回 `None`
- `semantic_duplicate_key` 为空格的字符串时正确返回 `None`

当前测试中的工具 policy 未设置 `semantic_duplicate_key_argument_name`，因此该字段在所有测试中均为 `None`。

**建议**: 新增一个参数化测试验证语义 key 参与 duplicate key 计算且不同语义 key 产生不同决策。

**严重级别**: LOW — plan 中 semantic key 标注为"默认关闭"，当前无测试不影响核心矩阵正确性。

---

### F6 — `GOVERNED_ERROR` candidate `duplicate_decision` field not validated in `__post_init__` (LOW)

**文件**: `dayu/host/tool_runtime.py:378-380`

`ToolFactAcceptCandidate.__post_init__` 对 `GOVERNED_ERROR` 分支只校验了 `outcome_digest`，未校验 `duplicate_decision`。plan §3.5 表中 `duplicate_decision` 字段虽未在 `governed_error` 的"必填"或"必须为空"列中明确出现，但 `duplicate_decision` 为 `hint` / `require_justification` / `hard_stop` 时应有对应的 `duplicate_key`。当前所有代码路径都正确设置了 `duplicate_decision`，因此这只是验证不完整，不影响运行时正确性。

**建议**: 在 `GOVERNED_ERROR` 分支加入 `duplicate_decision` 非 None（或明确允许 None 的策略 reject 路径）的校验。

**严重级别**: LOW — 防御性校验缺失，不影响当前行为。

---

## Validation

### Test Execution

```
$ pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q
19 passed in 0.19s

$ pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q
41 passed in 0.22s
```

### Type Check

```
$ python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations
```

### Plan Completion Signal Verification

| Plan Requirement | Test | Status |
|---|---|---|
| duplicate key normalizes arguments deterministically | `test_duplicate_key_normalizes_arguments_deterministically` | PASS |
| duplicate key excludes `index_in_iteration` | `test_duplicate_key_excludes_index_in_iteration` | PASS |
| `allow` executes and accepts | `test_allow_duplicate_decision_executes_and_accepts_each_call` | PASS |
| `reuse` does not call callable, no new result fact | `test_reuse_references_prior_refs_without_second_result_fact` | PASS |
| `hint`/`require_justification`/`hard_stop` produce governed facts and diagnostic refs | `test_duplicate_governed_matrix_produces_diagnostics` | PASS (partial — see F1) |
| no index inheritance across ToolRuntime instances | `test_new_runtime_does_not_inherit_duplicate_index` | PASS |
| diagnostic emitter typed refs | `test_noop_and_in_memory_diagnostic_emitters_return_typed_refs` | PASS |
| candidate and ack carry diagnostic refs | `test_candidate_and_ack_carry_duplicate_diagnostic_refs` | PASS |
| reject diagnostic refs | `test_rejected_accept_governed_error_emits_diagnostic_ref` | PASS |
| timeout diagnostic refs | `test_timeout_governed_error_emits_diagnostic_ref` | PASS |

### Non-goal Compliance

- [x] 无 durable duplicate ledger
- [x] 无 Memory retrieval 或跨 Run / 跨 Session 复用
- [x] 无 audit / trace projection 写入
- [x] 无 Engine 工具协议语义修改
- [x] 无 `dayu.fins` / `dayu.engine` / `dayu.service` / `dayu.ui` import
- [x] 无 `Any` / `object` / 无类型签名
- [x] 无 wait record, 无 `WAITING`, 无 `resolve_wait`
- [x] 无 durable cursor descriptor
- [x] Diagnostic refs 只是 `ToolTraceDiagnosticRef(ref_id=str)` — 纯 typed ref，不写文件、不写 EventLog、不更新 Run/Attempt

### README Verification

- `dayu/host/README.md`: P6-S1~S4 → P6-S1~S5，新增 S5 描述（duplicate governance matrix + diagnostic emitter），Non-goals 从"完整重复工具事实治理算法"更新为"durable duplicate ledger"——与代码事实一致
- `tests/README.md`: 新增 P6-S5 测试命令和测试覆盖描述——与代码事实一致
- 均未声称 P7/P13/P14 行为已实现

---

## Residual Risks

| Risk | Owner | Mitigation |
|---|---|---|
| **F1** — `require_justification` valid-path untested | P6-S6 或当前 S5 follow-up | 补充两个测试用例 |
| **F2** — Duplicate index overwrite semantic | P6-S6 或当前 S5 follow-up | 选择 setdefault 或仅记录 ALLOW |
| 默认 `DuplicateGovernancePolicy.default_duplicate_decision=ALLOW` 使未显式配置时不改变既有行为 | P6-S6 integration | 集成测试确认默认策略下无回归 |
| `ToolTraceDiagnosticEmitter` 当前生产路径 emit 的 refs 无 durable 存储 | P13 Audit / Tool Trace | P6 只负责 typed refs |
| `semantic_duplicate_key_argument_name` 是 Host 内部 policy 字段，默认关闭 | P12 ToolsDiscovery 或后续 policy provider | 后续启用时必须在 design doc 中明确其与 normalized args digest 的关系 |

---

## Summary

P6-S5 在 867 行 diff 中实现了 run-local duplicate governance 的 5-action matrix 与 3 个 diagnostic emitter 实现。核心语义完整：duplicate key 排除 `index_in_iteration`，reuse 正确引用 prior accepted refs 且不产生第二个 `TOOL_RESULT_ACCEPTED`，ToolRuntime 实例隔离验证通过，diagnostic refs 保持纯引用语义。

2 个 MEDIUM finding (F1/F2) 建议在 P6-S6 集成阶段修复；4 个 LOW finding 不影响当前功能的正确性或安全性。未发现分层违规、scope creep、类型边界问题或数据泄漏。
