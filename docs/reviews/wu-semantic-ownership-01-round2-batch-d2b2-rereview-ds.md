# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Re-Review — AgentDS

## Re-Review Context

- Reviewer: AgentDS
- Trigger: D2b2 code-review fix re-review，只验证 F1/F2 minor docstring findings 关闭状态
- Original artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-ds.md`
- Scope: 仅 F1、F2，不重新展开 D2b2 全 scope

## Findings Verification

### F1: `EvidenceBackedFactCandidateVNext.__post_init__` stale docstring — 已关闭 ✅

**Location**: `dayu/host/compaction.py:1184-1189`

**原始 Issue**: docstring 声明 `:raises TypeError: enum 类型非法时抛出。`，但 `evidence_kind` 字段与 `isinstance` 校验已移除。

**当前状态**:
```python
def __post_init__(self) -> None:
    """校验 vNext evidence-backed fact candidate。

    :returns: ``None``。
    :raises ValueError: 文本或 labels 非法时抛出。
    """
```

`:raises TypeError:` 行已移除，docstring 仅声明 `ValueError`，与 `_require_non_empty` / `_require_non_empty_unique_string_tuple` / `_require_unique_string_tuple` 实际抛出的异常类型一致。

**结论**: 已关闭。

### F2: `_parse_fact` docstring `evidence kind` 引用 — 已关闭 ✅

**Location**: `dayu/host/compact_payload.py:294`

**原始 Issue**: docstring 声明 `:raises ValueError: fact shape、文本、labels 或 evidence kind 非法时抛出。`，但 `evidence_kind` 已不再是 fact 字段。

**当前状态**:
```python
:raises ValueError: fact shape、未知字段、文本或 labels 非法时抛出。
```

`evidence kind 非法时抛出` 已替换为 `未知字段非法时抛出`。措辞准确描述 `_require_exact_fields` 的实际行为：拒绝 `_FACT_FIELDS` 之外的 unknown/unsupported 字段（包括残留的 `evidence_kind`），错误信息为 `"{field} is not supported"`。

**结论**: 已关闭。

## 新问题检查

文本级 docstring 修改未引入新 import、新逻辑分支或新异常路径。`git diff --check` 已通过。未发现新实质性问题。

## Findings

未发现实质性问题。

## 结论

F1、F2 均已正确关闭。docstring 与实现一致，无遗漏、无扩散、无新引入问题。

## Artifact

- DS: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-rereview-ds.md`
