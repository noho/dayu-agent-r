# WU-CM-01 Deferred Risk Cleanup — AgentDS Focused Re-Review (MiMo-F1 Fix)

## Gate

- Review agent: AgentDS
- Scope: MiMo-F1 fix only — `test_compaction_operation.py` raw string `failure_category` assertions → typed enum assertions
- Source: Controller accepted AgentMiMo F1 Low; AgentCodex implemented fix
- Prior DS review: `docs/reviews/wu-cm-01-deferred-risk-cleanup-review-ds.md` (PASS)

## 结论

**PASS** — MiMo-F1 已完整修复。`test_compaction_operation.py` 中所有 `CompactionAttemptRejected.failure_category` 原始字符串断言已替换为 `isinstance` + enum identity 检查。无残留类型不安全的断言。

---

## Findings

### F1 [RESOLVED] 全部 `failure_category` 原始字符串断言已替换

**证据**：

| 测试函数 | 行号 | 旧断言 | 新断言 |
|---|---|---|---|
| `test_run_compaction_operation_retries_quality_rejection` | 437-452 | `== "quality_check_rejected"` | `isinstance(..., CompactionFailureCategory)` + `is ...QUALITY_CHECK_REJECTED` |
| `test_run_compaction_operation_retries_hard_threshold_after_compact` | 484-491 | `== "hard_threshold_after_compact"` | `isinstance(..., CompactionFailureCategory)` + `is ...HARD_THRESHOLD_AFTER_COMPACT` |
| `test_run_compaction_operation_stops_before_retry_when_cancelled` | 559-566 | `== "cancellation_requested"` | `isinstance(..., CompactionFailureCategory)` + `is ...CANCELLATION_REQUESTED` |
| `test_vnext_quality_reject_records_rejected_attempt` | 804-811 | `== "quality_check_rejected"` | `isinstance(..., CompactionFailureCategory)` + `is ...QUALITY_CHECK_REJECTED` |

**验证**：
- `grep 'failure_category == "' tests/host/test_compaction_operation.py` → 零匹配
- `grep 'next_policy_decision == "' tests/host/test_compaction_operation.py` → 零匹配
- 所有 `failure_category` 引用（9 处）均为 `isinstance` 类型检查或 `is` enum identity 断言

### F2 [INFO] quality_rejection 测试额外补了 D2 完整断言

**证据**：`test_compaction_operation.py:446-465` — 在原有 `failure_category` 修复基础上，额外增加了 `next_policy_decision` 的 `isinstance` + `is` enum identity 检查（行 441-444），以及 `build_context_compaction_attempt_rejected_payload` 的 payload 字符串值断言（行 453-464）。

**分析**：这是对 D2 的补充覆盖——不仅修复了 MiMo 指出的 `failure_category` 问题，还补全了同一 rejected attempt 的 `next_policy_decision` typed 断言和 EventLog payload 字符串兼容性断言。属于合理扩展，不构成 scope creep。

### F3 [VERIFIED] 实现 artifact 已同步

**证据**：`docs/reviews/wu-cm-01-deferred-risk-cleanup-implementation-codex.md:37-39` — MiMo-F1 finding 记录为 "已修复"，描述了修复方式。

### F4 [VERIFIED] 验证通过

AgentCodex 报告：
- `pytest tests/host/test_compaction_operation.py -q`: 38 passed
- `python -m pyright dayu/ tests/ utils/`: 0 errors
- `git diff --check`: passed

## AGENTS.md 合规

| 规则 | 状态 |
|---|---|
| 严格类型 | ✓ 测试断言使用 `isinstance` + enum identity，不再依赖隐式字符串比较 |
| 禁止魔法字符串扩散 | ✓ 消除了测试中的自由字符串字面量 |
| pyright / test 验证 | ✓ AgentCodex 报告通过 |
