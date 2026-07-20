# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Re-Review — MiMo

## Review Context

- Reviewer: AgentMiMo
- Baseline: D2b2 code-review fix commit (docstring-only changes)
- Original artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-ds.md`
- Scope: verify closure of F1 and F2 minor docstring findings only; no re-opening of D2b2 full scope.

## Findings Verified

### F1: `EvidenceBackedFactCandidateVNext.__post_init__` stale docstring ✅ CLOSED

**Original issue** (MiMo F1): docstring at `compaction.py:1188` still declared `:raises TypeError: enum 类型非法时抛出。`，但 `evidence_kind` 字段与 `isinstance` 校验已移除，当前 `__post_init__` 不可能抛出 `TypeError`。

**Fix applied**: `compaction.py:1188` now reads:

```python
:raises ValueError: 文本或 labels 非法时抛出。
```

**Verification**:
- Stale `TypeError` 行已移除。
- 当前 `__post_init__` 调用 `_require_non_empty`、`_require_non_empty_unique_string_tuple`、`_require_unique_string_tuple`，三者均抛出 `ValueError`。docstring 准确声明 `ValueError`。
- `evidence_kind` 引用已完全清除。

**结论**: F1 关闭，docstring 与实现一致。

---

### F2: `_parse_fact` stale docstring ✅ CLOSED

**Original issue** (MiMo F2 / DS F2): docstring at `compact_payload.py:294` 声明 `:raises ValueError: fact shape、文本、labels 或 evidence kind 非法时抛出。`，但 `evidence_kind` 已不再是 fact 字段。

**Fix applied**: `compact_payload.py:294` now reads:

```python
:raises ValueError: fact shape、未知字段、文本或 labels 非法时抛出。
```

**Verification**:
- `evidence kind` 引用已替换为 `未知字段`，准确描述 `_require_exact_fields` 拒绝未知字段的行为。
- 措辞与 `_FACT_FIELDS` 不含 `evidence_kind` 的当前 schema 一致：含 `evidence_kind` 的旧 payload 会被 `_require_exact_fields` 拒绝，错误信息为 `"evidence_kind is not supported"`。

**结论**: F2 关闭，docstring 准确描述当前校验行为。

---

## New Material Issue Check

本次修改仅涉及两处 docstring 文本变更，无代码行为变更。

- 未引入新的类型错误、逻辑错误或 contract 缺口。
- 未修改任何函数签名、异常类型或返回值。
- Implementation artifact (`docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-implementation-codex.md`) 的 Code Review Fix 段（line 96-101）准确记录了本次修复。

**未发现实质性问题。**

## 结论

F1、F2 均已正确关闭。docstring 现在与实现一致，无新 material issue。D2b2 code-review fix 可以 accepted。

## Artifact

- MiMo: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-rereview-mimo.md`
