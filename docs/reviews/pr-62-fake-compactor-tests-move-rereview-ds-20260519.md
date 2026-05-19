# PR-62 Fake Compactor Tests Move — Targeted Re-review

**Reviewer**: AgentDS
**Date**: 2026-05-19
**Scope**: fake compactor 从 `dayu/host/` 迁移到 `tests/host/` 的当前未提交变更
**Verdict**: **PASS**

## 检查清单

### C1: 生产包不暴露 FakeContextCompactor

- `dayu/host/fake_compaction.py` 已删除（untracked deletion）。
- `rg fake_compaction\|FakeContextCompactor dayu/` 返回零匹配。
- **PASS**。

### C2: 生产代码不 import tests.host.fake_compaction

- `rg "from tests\.|import tests\." dayu/` 返回零匹配。
- **PASS**。

### C3: 测试 helper 保留 F1 修复语义

`tests/host/fake_compaction.py` L202-L242 `_budget_after_compact` 与 `_cap_budget_within_hard_threshold`：

- 复用 `estimate_compacted_context_budget`（生产级保守估算）。
- 以 `hard_threshold_tokens - 1` 为可接受天花板，不构造会被 Host hard-threshold recheck 拒绝的 candidate。
- hard_threshold ≤ 0 时返回非负下界 0，避免构造非法负预算。
- 对 Host `check_compaction_candidate` 的 hard-threshold recheck 无放宽、无绕过。

**PASS**。

### C4: 测试 import 迁移

5 个测试文件 import 已从 `dayu.host.fake_compaction` 迁移到 `tests.host.fake_compaction`：

- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`

**PASS**。

### C5: 活文档表达

- `docs/host/host-owned-compactor-plan.md`：明确 `tests.host.fake_compaction.FakeContextCompactor` 路径，生产代码不得导入 tests helper。
- `docs/host/implementation-control.md`：两处更新，均使用 `tests.host.fake_compaction.FakeContextCompactor` 路径，增加"不得导入或隐式使用 tests helper"约束。
- `docs/host/phase10-context-governance-plan.md`：四处更新，明确位于 `tests/host/fake_compaction.py`，生产代码不得导入。
- `tests/README.md`：补充"测试专用 deterministic compactor 位于 `tests/host/fake_compaction.py`，生产代码不得导入"。
- 历史 review artifact `docs/reviews/host-owned-compactor-final-review-ds.md` 含旧路径引用 `dayu.host.fake_compaction`，但按用户指令不要求重写历史 docs/reviews 产物。

**PASS**。

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host/test_compact_artifact_store.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py` | 99 passed, 0 failed |
| `pyright` on changed files | 0 errors, 0 warnings |
| `dayu/` 内 `fake_compaction\|FakeContextCompactor` 引用 | 0 matches |
| `dayu/` 内 `from tests\.\|import tests\.` 引用 | 0 matches |

## Residual Notes

- `tests/host/fake_compaction.py` 的 `__all__` 仅导出 `FakeContextCompactor`，模块级私有 helper 不泄露。
- 该 test helper 与生产 `dayu.host.compaction` 之间的 import 关系为单向（test → production），不构成反向依赖。
