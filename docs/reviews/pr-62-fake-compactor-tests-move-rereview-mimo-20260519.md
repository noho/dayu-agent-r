# PR-62 Fake Compactor Tests-Move Targeted Re-Review

- Reviewer: AgentMiMo
- Date: 2026-05-19
- Scope: 未提交 workspace changes（feat/host-p10-5-public-contract-freeze）
- Verdict: **PASS**

---

## Review Scope

| 类型 | 文件 |
|---|---|
| 删除 | `dayu/host/fake_compaction.py` |
| 新增 | `tests/host/fake_compaction.py` |
| 修改 | `tests/host/test_compact_artifact_store.py` |
| 修改 | `tests/host/test_compaction_contract.py` |
| 修改 | `tests/host/test_compaction_operation.py` |
| 修改 | `tests/host/test_dispatch_scheduler.py` |
| 修改 | `tests/host/test_engine_ingest_mapping.py` |
| 修改 | `docs/host/implementation-control.md` |
| 修改 | `docs/host/phase10-context-governance-plan.md` |
| 修改 | `docs/host/host-owned-compactor-plan.md` |
| 修改 | `tests/README.md` |

---

## Criterion 1: 生产包不再暴露/包含 FakeContextCompactor

| Check | Result |
|---|---|
| `dayu/host/fake_compaction.py` 文件不存在 | PASS |
| `dayu/` 全树 grep `fake_compaction` 零匹配 | PASS |
| `dayu/` 全树 grep `FakeContextCompactor` 零匹配 | PASS |
| `dayu/host/__init__.py` 无 re-export | PASS |

**结论：** 生产包已彻底清除 `FakeContextCompactor` / `fake_compaction`。

---

## Criterion 2: 生产代码不得 import tests helper

| Check | Result |
|---|---|
| `dayu/` 全树无 `from tests.host.fake_compaction` import | PASS |
| `dayu/` 全树无 `import tests.host.fake_compaction` | PASS |

**结论：** 无反向依赖。

---

## Criterion 3: 测试 helper 保留 F1 修复语义

| 语义要求 | Result | Evidence |
|---|---|---|
| 复用 production `BudgetEstimator` | PASS | `from dayu.host.compaction_budget import estimate_compacted_context_budget`；不自行实现预算逻辑 |
| Cap 到 hard-threshold 内 | PASS | `_cap_budget_within_hard_threshold` 返回 `min(estimated, hard_threshold - 1)` |
| 不放宽 Host hard-threshold recheck | PASS | docstring 明确 "不能生成会被 Host hard-threshold recheck 拒绝 的 accepted candidate"；`test_compaction_operation.py::test_run_compaction_operation_retries_hard_threshold_after_compact` 验证 Host 正确拒绝超标 candidate |

**结论：** F1 修复语义完整保留。

---

## Criterion 4: 活文档表达清楚 — fake compactor 是 tests helper

| 文件 | 明确声明测试专用 | 无 stale 生产路径 | 指向 tests 路径 |
|---|---|---|---|
| `tests/host/fake_compaction.py` | PASS ("Host 测试专用...生产代码不得导入") | PASS | PASS |
| `docs/host/host-owned-compactor-plan.md` | PASS ("low-level test seam") | PASS | PASS |
| `docs/host/phase10-context-governance-plan.md` | PASS ("测试用...生产代码不得导入") | PASS | PASS |
| `docs/host/implementation-control.md` | PASS ("不得导入或隐式使用") | PASS | PASS |
| `tests/README.md` | PASS ("测试专用...生产代码不得导入") | PASS | PASS |

**注意：** `docs/reviews/` 下的历史 review artifact 仍引用旧路径 `dayu/host/fake_compaction.py`，但这些是不可变历史记录，不要求重写。PASS。

**结论：** 活文档表达一致且清晰。

---

## Criterion 5: CLI/Web/GUI findings out of scope

不涉及，N/A。

---

## Import Path Verification

| 测试文件 | Import 路径 | Correct? |
|---|---|---|
| `test_compact_artifact_store.py` | `from tests.host.fake_compaction import FakeContextCompactor` | YES |
| `test_compaction_contract.py` | `from tests.host.fake_compaction import FakeContextCompactor` | YES |
| `test_compaction_operation.py` | `from tests.host.fake_compaction import FakeContextCompactor` | YES |
| `test_dispatch_scheduler.py` | `from tests.host.fake_compaction import FakeContextCompactor` | YES |
| `test_engine_ingest_mapping.py` | `from tests.host.fake_compaction import FakeContextCompactor` | YES |

---

## Validation Results

| Check | Result |
|---|---|
| pytest (5 files, 99 tests) | **99 passed in 1.18s** |
| pyright (production + test files) | **0 errors, 0 warnings, 0 informations** |

---

## Minor Finding

`dayu/host/__pycache__/fake_compaction.cpython-311.pyc` 残留。无害（`.py` 已删除，不会被 import），但建议 `git clean -fd` 清理以避免困惑。不阻塞。

---

## Verdict

**PASS**

所有五项 review criteria 均通过。生产包已彻底清除 `FakeContextCompactor`，测试 helper 保留 F1 修复语义，活文档表达清晰一致，验证全部通过。
