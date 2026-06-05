# WU-CM-01 Deferred Risk Cleanup Review — AgentMiMo

## 结论

**PASS** — D1 / D2 / D4 / D5 实现与 adjudication 边界一致，无阻断性问题。两项低/informational 发现不阻断合入。

## Gate

- Review scope: 当前工作区未提交 diff（13 files, +616 / -53）
- Reviewer: AgentMiMo
- Source artifacts:
  - `docs/reviews/wu-cm-01-pr-deferred-risk-controller-adjudication.md`
  - `docs/host/wu-cm-01-deferred-risk-cleanup-plan.md`
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-implementation-codex.md`
- 验证: pyright 0 errors, pytest 71 passed, `git diff --check` clean

## Findings

### F1 — Low: `test_compaction_operation.py` 三处 pre-existing 断言未升级为 enum identity 检查

文件: `tests/host/test_compaction_operation.py` lines 484, 552, 790

当前写法:

```python
# line 484
assert result.rejected_attempts[0].failure_category == "hard_threshold_after_compact"
# line 552
assert result.rejected_attempts[1].failure_category == "cancellation_requested"
# line 790
assert result.rejected_attempts[0].failure_category == "quality_check_rejected"
```

这些断言在 `CompactionFailureCategory` 是 `StrEnum` 时隐式通过（`StrEnum.__eq__` 对 `str` 生效），但它们不验证字段实际是 enum 类型而非裸 `str`。本 diff 修改的 `test_run_compaction_operation_retries_quality_rejection` (line 437) 已正确使用 `isinstance` + `is` identity 检查，但其余三处 pre-existing 测试未同步升级。

影响: 测试质量一致性。若未来有人将字段类型意外回退为 `str`，这三处测试仍会通过，只有修改过的测试会捕获回归。

建议: 可选修复，将这三处改为与 line 437 一致的 `isinstance` + enum member identity 检查。不阻断合入。

### F2 — Informational: `tests/README.md` 包含 D1-D5 scope 外的 `_start_run` 引用变更

文件: `tests/README.md` lines 127, 136

diff 中将 `start_run` 改为 `_start_run`（内部 admission primitive），这是文档准确性修正而非 D1/D2/D4/D5 scope 内容。`_start_run` 确实存在于 `dayu/host/admission.py` 和 `dayu/host/command.py`，描述准确。变更无害但属于 scope creep。

建议: 无需处理。仅记录。

## D1 审计: `memory.py` / `context_fallback.py` `__all__`

| 检查项 | 结果 |
|---|---|
| `memory.__all__` 包含 71 个符号，全部对应真实模块级定义 | PASS |
| `memory.__all__` 无下划线前缀 helper 泄漏 | PASS |
| `memory.__all__` 包含所有导出 dataclass 字段类型所依赖的 enum（如 `MemoryClaimStatus`, `MemoryProducerKind` 等） | PASS |
| `context_fallback.__all__` 包含 18 个符号，全部对应真实定义 | PASS |
| `context_fallback.__all__` 无下划线前缀 helper 泄漏 | PASS |
| 未修改 `dayu.host.__all__`，未将 memory / fallback 符号提升到包根 | PASS |
| `test_package_exports.py` 新增两个 frozenset 精确相等测试 + 下划线泄漏检查 | PASS |

## D2 审计: `CompactionAttemptRejected` StrEnum 化

| 检查项 | 结果 |
|---|---|
| `CompactionFailureCategory(StrEnum)` 定义 5 个成员，值与原 `_FAILURE_*` 常量一致 | PASS |
| `CompactionNextPolicyDecision(StrEnum)` 定义 2 个成员，值与原 `_NEXT_DECISION_*` 常量一致 | PASS |
| `CompactionAttemptRejected.failure_category` 类型为 `CompactionFailureCategory` | PASS |
| `CompactionAttemptRejected.next_policy_decision` 类型为 `CompactionNextPolicyDecision` | PASS |
| `dispatch.py` line 1966/1970/1974 使用 `.value` 写 EventLog reason/payload | PASS |
| `engine_ingest.py` line 1938/1941/1947 使用 `.value` 写 EventLog reason/payload | PASS |
| `context_events.py` `build_context_compaction_attempt_rejected_payload` 参数类型为 `str`，调用方传 `.value` | PASS |
| `_attempt_rejected()` line 435 使用 `failure_category.value` 拼 diagnostic_ref | PASS |
| `_log_rejected_attempt()` line 500/503 使用 `.value` 输出日志 | PASS |
| `run_compaction_operation()` 所有 failure_reason 赋值使用 `.value` | PASS |
| 两个 enum 类型均纳入 `compaction_operation.__all__` | PASS |
| `test_compaction_operation.py` 验证 isinstance + enum identity + payload 字符串值 | PASS |

## D4 审计: `slice1` 诊断常量清理

| 检查项 | 结果 |
|---|---|
| `_INITIAL_POLICY_DIGEST` 从 `"slice1-initial-policy"` 改为 `"initial-compact-material-policy"` | PASS |
| 5 个 `_INITIAL_REASON_*` 从 `"slice1_*"` 改为 `"initial_*"` | PASS |
| 模块 docstring 从 "Phase 12.6 Slice 1" 改为语义描述 | PASS |
| `InitialHistoryMaterial` docstring 从 "Slice 1 初始" 改为 "初始 trace" | PASS |
| `InitialEvidenceMaterial` docstring 从 "Slice 1 初始" 改为 "初始" | PASS |
| 4 个函数 docstring 清理 "Slice 1" 引用 | PASS |
| 生产代码中无残留 `slice1`、`Slice 1`、`Phase 12` 字符串 | PASS |
| 未扩展为真实 policy digest 派生设计（adjudication 边界） | PASS |
| `test_compaction_contract.py` 断言诊断值不含 `slice1` | PASS |

## D5 审计: 测试覆盖增强

| 测试 | 覆盖目标 | 评估 |
|---|---|---|
| `test_memory_module_all_matches_typed_contract_boundary` | memory `__all__` 白名单 | frozenset 精确相等 + 下划线泄漏检查。PASS |
| `test_context_fallback_module_all_matches_helper_boundary` | context_fallback `__all__` 白名单 | 同上。PASS |
| `test_vnext_candidate_schema_rejects_missing_required_source_label` | 缺失 source label typed 边界 | 通过 typed dataclass 构造验证 ValueError，未伪造非法对象。PASS |
| `test_initial_segment_selection_diagnostics_do_not_expose_slice_name` | slice1 诊断泄漏 | 子串检查 policy_digest + reason_codes。PASS |
| `test_catch_up_uses_real_durable_store_and_writes_snapshot` | 真实 durable memory repair catch-up | 使用 `open_host_durable_store` + `RealProjectionRunner`，验证 snapshot 内容/游标/checkpoint。PASS |
| `test_memory_snapshot_write_and_checkpoint_commit_together` | snapshot + checkpoint 同事务提交 | 单事务写入后读回验证原子性。PASS |
| `test_run_compaction_operation_retries_quality_rejection` (修改) | enum 字段类型 + payload 字符串值 | isinstance + identity + payload 断言。PASS |

脆弱性检查:

| 检查项 | 结果 |
|---|---|
| 是否有测试直接构造 `CompactionAttemptRejected` 非法对象？ | 否。仅 `_attempt_rejected()` 生产代码构造。PASS |
| 是否有测试过度耦合私有实现？ | 否。所有测试通过公共 API 或 typed 边界。PASS |
| 是否有伪造非法 typed object 绕过验证？ | 否。source label 测试通过 typed 构造的 ValueError 覆盖。PASS |

## AGENTS.md 合规检查

| 约束 | 结果 |
|---|---|
| 中文 docstring | PASS。所有新增/修改的 class/function 有完整中文 docstring |
| 严格类型，无 `Any`/`object`/无类型签名 | PASS。pyright 0 errors |
| 无兼容 facade / re-export | PASS。无兼容性代码 |
| 无魔法字符串扩散 | PASS。enum 值为定义处字面量，常量值为 module-private 诊断字符串 |
| README 触发规则 | PASS。`tests/README.md` 已更新；`dayu/host/README.md` 无需更新 |
| pyright 验证 | PASS。0 errors, 0 warnings |
| test 验证 | PASS。71 tests passed |

## 裁决

PASS。建议合入。F1 为可选 follow-up，F2 为 informational。
