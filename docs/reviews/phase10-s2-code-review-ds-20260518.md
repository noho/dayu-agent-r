# Phase 10 Slice 2 Code Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Verdict: CHANGES_REQUESTED**

## Scope

Review of Phase 10 Slice 2 compactor typed contracts, fake compactor, quality checker, and compact artifact store:
- `dayu/host/compaction.py`
- `dayu/host/fake_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compact_artifact.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compact_artifact_store.py`
- `dayu/host/README.md`
- `tests/README.md`

## Verification

- `pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q` — 13 passed
- `pyright` — 0 errors, 0 warnings, 0 informations

---

## Blocking Findings

### B1. `CompactionRequest.__post_init__` 校验顺序导致 `AttributeError` 而非 `TypeError`

**文件:** `dayu/host/compaction.py:202,209`

`CompactionRequest.__post_init__` 在第 202 行访问 `self.current_message_summary.current_user_input_ref`，但 `isinstance(self.current_message_summary, CurrentMessageSummary)` 的类型检查在第 209 行才执行：

```python
# Line 202 — 先访问属性
if self.current_message_summary.current_user_input_ref not in self.input_event_refs:
    raise ValueError("CompactionRequest.input_event_refs must include current input")
# ...
# Line 209 — 后检查类型（太晚）
if not isinstance(self.current_message_summary, CurrentMessageSummary):
    raise TypeError(
        "CompactionRequest.current_message_summary must be CurrentMessageSummary"
    )
```

**影响：** 若 `current_message_summary` 被传入非 `CurrentMessageSummary` 对象（如 `str`、`dict` 等），第 202 行会抛出 `AttributeError: 'str' object has no attribute 'current_user_input_ref'`，而不是预期的 `TypeError`。这破坏了该 `__post_init__` 声明的异常契约（`raises TypeError`）。

**证据：** 当前测试 `_request()` helper 始终传入合法的 `CurrentMessageSummary`，从未覆盖错误类型场景。其他 dataclass（`CompactionCandidate`、`PinnedStatePatchCandidate`、`CompactArtifactWriteRequest`）的 `__post_init__` 均先做 `isinstance` 检查再访问属性，只有 `CompactionRequest` 存在此顺序错误。

**要求：** 将第 202 行的属性访问移到第 209 行的 `isinstance` 检查之后（或在 `isinstance` 检查之前不访问 `current_message_summary` 属性）。

---

## High Findings

（无）

---

## Medium Findings

### M1. 缺少 `CompactionRequest.__post_init__` 错误 `current_message_summary` 类型的测试覆盖

**文件:** `tests/host/test_compaction_contract.py`

当前测试只覆盖了合法 `CompactionRequest` 构造和 quality check 拒绝路径，没有直接测试 `CompactionRequest.__post_init__` 对非法 `current_message_summary` 类型的错误处理。B1 中的校验顺序 bug 可以通过补充一个直测来捕获：

```python
def test_compaction_request_rejects_wrong_current_message_summary_type():
    with pytest.raises(TypeError):
        CompactionRequest(
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            session_id="s1",
            run_id="r1",
            attempt_id=None,
            execution_id=None,
            input_event_refs=("e1", "e2"),
            current_message_summary="not-a-CurrentMessageSummary",  # 非法类型
            ...
        )
```

### M2. 缺少 `CompactQualityCheckResult` acceptance/rejection invariant 直测

**文件:** `dayu/host/compaction.py:815-818`, `tests/host/test_compaction_contract.py`

`CompactQualityCheckResult.__post_init__` 有两个重要 invariant：
- `accepted=True` 且 `rejection_reasons` 非空 → `ValueError`
- `accepted=False` 且 `rejection_reasons` 为空 → `ValueError`

但这些 invariant 没有直接的单元测试覆盖。它们只在 quality checker 的间接路径中被隐式测试（通过构造合法结果）。直接构造违反 invariant 的 `CompactQualityCheckResult` 的测试缺失。

---

## Low Findings

### L1. 重复的私有 helper 函数

**文件:** `dayu/host/compaction.py:872-882` vs `dayu/host/compact_artifact.py:321-331`; `dayu/host/compaction.py:998-1008` vs `dayu/host/compact_artifact.py:295-305`

`_require_optional_non_empty` 和 `_range_list_json` 在两个模块中各有一份实现。这是模块级私有 helper，按项目规则允许存在，且不违反"重复逻辑必须抽取"的约束（因为它们操作的类型来自于各自模块的 import），但若后续有第三个模块需要相同逻辑，应考虑提升到 `_public_validation` 或等效共享位置。

### L2. Quality checker 记录但不拒绝 `open_questions` 丢失

**文件:** `dayu/host/context_governance.py:424-435`

`_open_questions_retained()` 计算了 open questions 是否保留，结果写入 `CompactQualityCheckResult.open_questions_retained`，但不会被用作拒绝原因（没有对应的 `CompactQualityIssue`）。Plan 要求 `CompactQualityCheckResult` "记录... open questions / assumptions refs 是否保留"，当前实现满足了记录要求。但若候选完美丢失所有 open questions（summary 中无、pinned patch 标记为 MISSING），checker 不会拒绝该候选。后续 orchestration slice 应明确此语义是"记录但放行"还是"记录并拒绝"。

---

## Info

### I1. `_evidence_ids` 在 quality checker 中被计算两次

**文件:** `dayu/host/context_governance.py:45-46, 181-182`

`_evidence_ids(candidate.preservation_evidence)` 在 `_evidence_anchors_retained()` 第 181 行和第 48 行（通过 `_pinned_patch_valid()` 传递 `evidence_ids`）各计算一次。对于小型 evidence tuple 影响可忽略，仅记录供参考。

---

## Plan Compliance Summary

| 计划要求 | 状态 | 证据 |
|---------|------|------|
| Typed contracts 避免 Any/object/untyped bag | PASS | 所有 dataclass 使用 frozen slots + 精确类型；pinned patch 使用 `PinnedPatchOperation` 三态枚举表达 missing/clear/replace |
| `CompactionRequest.__post_init__` 校验顺序 | FAIL (B1) | `current_message_summary` 属性访问在 isinstance 检查之前 |
| Quality checker 拒绝 missing current input | PASS | `context_governance.py:110-124` |
| Quality checker 拒绝 missing tool fact refs | PASS | `context_governance.py:127-137` |
| Quality checker 拒绝 summary 伪造 verified fact | PASS | `context_governance.py:140-158` 三重检查 |
| Quality checker 拒绝缺 preservation evidence | PASS | `context_governance.py:59-60` |
| Quality checker 拒绝 evidence anchor 未保留 | PASS | `context_governance.py:171-197` 全面检查 |
| Quality checker 拒绝 pinned patch 引用未知 evidence | PASS | `context_governance.py:390-410` |
| Artifact store 只写 artifact + descriptor，不写 EventLog | PASS | `compact_artifact.py:137-173` |
| Artifact canonical JSON 包含计划要求字段 | PASS | `compact_artifact.py:188-207` 全部13个字段 |
| Expected digest 失败不写 descriptor | PASS | `test_compact_artifact_store.py:107-148` |
| Fake compactor 仅测试/本地注入，不进 production 默认路径 | PASS | `fake_compaction.py:1-6` 模块文档；无 production re-export |
| README 同步 | PASS | `dayu/host/README.md` 新增 Context Governance Boundary 章节；`tests/README.md` 新增测试命令和覆盖描述 |

---

## Test Coverage Assessment

**覆盖强度：** 良好，13 个测试覆盖了核心路径。

**覆盖盲区：**
- `CompactionRequest.__post_init__` 错误类型注入（M1）
- `CompactQualityCheckResult` invariant 直测（M2）
- `CompactionRequest` reactive trigger 时 attempt_id/execution_id 不为 None 的校验路径（`_require_optional_non_empty` 只检查非空，不检查 reactive 时必填——plan 要求 "Reactive trigger 必须带 attempt/execution；proactive 可以不带"，当前 `__post_init__` 不区分 trigger source 做此校验）

---

## Residual Risks

1. **R1 — 校验顺序 fix 后测试应同步更新（B1 修复后）：** 修复 B1 后，建议添加 M1 的直测以确保路径被覆盖。
2. **R2 — Reactive compact attempt/execution 必填校验缺失：** 当前 `CompactionRequest.__post_init__` 不区分 proactive/reactive trigger source，不对 reactive 场景强制要求 `attempt_id` 和 `execution_id` 非 None。Plan 明确要求 "Reactive trigger 必须带 attempt/execution；proactive 可以不带"。此校验若不在本 slice 补齐，后续 orchestration slice 需要额外防御。
3. **R3 — Quality checker 对 open_questions 的行为后续 slice 需明确（L2 延伸）：** 若后续 orchestration 期望 open_questions_retained=False 时拒绝候选，需在 Slice 3/4 补充拒绝逻辑。
4. **R4 — Fake compactor 产生 `proposed_verified_fact_refs=()` 始终为空：** 依靠 `EpisodeSummaryCandidate` 的默认 `field(default_factory=_empty_string_tuple)`。如果真实 LLM compactor adapter 的 `proposed_verified_fact_refs` 非空，quality checker 会正确拒绝（`test_quality_rejects_summary_pretending_to_create_verified_fact` 已验证）。

---

## File Index

| 文件 | 行数 | 关键区域 |
|------|------|---------|
| `dayu/host/compaction.py` | 1061 | B1 在 :202,209；M2 相关在 :815-818 |
| `dayu/host/fake_compaction.py` | 199 | 无 finding，PASS |
| `dayu/host/context_governance.py` | 438 | L2 在 :424-435 |
| `dayu/host/compact_artifact.py` | 340 | 无 finding，PASS |
| `tests/host/test_compaction_contract.py` | 201 | M1 盲区 |
| `tests/host/test_compact_artifact_store.py` | 303 | 无 finding，PASS |
| `dayu/host/README.md` | — | PASS，同步 |
| `tests/README.md` | — | PASS，同步 |

---

## Summary

- **Verdict:** CHANGES_REQUESTED
- **Findings:** 1 blocking, 0 high, 2 medium, 2 low, 1 info
- **Tests:** 13 passed, 0 failed
- **Pyright:** 0 errors

唯一阻塞项 B1 是 `CompactionRequest.__post_init__` 校验顺序导致的异常类型错误。修复范围仅限于调整两行代码顺序（将 `isinstance` 检查移到属性访问之前），不应影响现有测试通过或类型检查结果。
