# WU-CM-01 Deferred Risk Cleanup Controller Adjudication

## 裁决

- Gate: WU-CM-01 deferred risk cleanup review / re-review
- Implementation artifact: `docs/reviews/wu-cm-01-deferred-risk-cleanup-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-review-mimo.md`
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-review-ds.md`
- Re-review artifacts:
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-rereview-mimo.md`
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-rereview-ds.md`
- Verdict: PASS。

D1 / D2 / D4 / D5 均已完成实现、验证与双路 review。WU-CM-01 PR deferred risk cleanup 可关闭。

## Review 裁决

### AgentMiMo F1

- Finding: `tests/host/test_compaction_operation.py` 中既有 `failure_category == "..."` 断言未全部升级为 enum identity 检查。
- Controller decision: accepted。
- Reason: D2 的目标是把 `CompactionAttemptRejected.failure_category` 从自由字符串收紧为 `StrEnum`。继续用字符串比较会弱化回归测试，修复成本低且不扩 scope。
- Fix: AgentCodex 已将剩余断言改为 `isinstance(..., CompactionFailureCategory)` 与 enum member identity 检查。
- Re-review: AgentMiMo / AgentDS 均 PASS。

### AgentMiMo F2 / AgentDS INFO

- Controller decision: accepted as non-blocking / no fix required。
- Reason: `tests/README.md` 中 `_start_run` 文档修正来自既有工作区变更，描述准确；`memory.py` `__all__` 维护成本、`memory_repair.ProjectionRunner` monkeypatch 耦合均为本轮设计取舍的固有维护成本，不构成 correctness 或 stability risk。

## Deferred Risk Closeout

| Risk | 裁决 | 关闭依据 |
|---|---|---|
| D1 `memory.py` / `context_fallback.py` 缺少 `__all__` | closed | 两模块已增加模块级 `__all__`，包根 `dayu.host.__all__` 未变；`tests/host/test_package_exports.py` exact frozenset 白名单覆盖。 |
| D2 compaction operation string category / decision | closed | `CompactionFailureCategory` 与 `CompactionNextPolicyDecision` 已实现为 `StrEnum`；EventLog payload 边界继续输出既有字符串值；review fix 后测试不再依赖裸字符串比较。 |
| D4 `slice1` 诊断常量命名 | closed | `compact_material.py` 生产代码与相关 docstring 已清理 `slice1` / `Slice 1` 实施切片命名；测试断言 initial diagnostics 不泄漏 slice 名。 |
| D5 测试覆盖增强 | closed for current cleanup | 已补模块导出白名单、typed schema 边界、真实 durable memory repair catch-up、snapshot + checkpoint 同事务提交测试；长期 Conversation Memory evaluation 仍归 issue-80。 |

## 验证

AgentCodex reported:

```bash
pytest tests/host/test_package_exports.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_memory_repair.py tests/host/test_durable_concurrency_matrix.py -q
# 104 passed

pytest tests/host/test_compaction_operation.py -q
# 38 passed

python -m pyright dayu/ tests/ utils/
# 0 errors

git diff --check
# passed
```

Controller final validation should rerun the combined target suite, pyright and `git diff --check` before closeout.
