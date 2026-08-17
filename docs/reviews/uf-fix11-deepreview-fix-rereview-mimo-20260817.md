# UF-FIX11 Deepreview Fix Re-Review

## Scope

- Mode: targeted re-review of finding 01 fix
- Branch: codex/upload-filing-oracle
- Inputs:
  - `docs/reviews/code-review-20260817-172506.md` finding 01
  - `docs/gateflow/uf-fix11-deepreview-fix-20260817.md`
  - Working tree diff (2 files, +223/-6)
- Output file: docs/reviews/uf-fix11-deepreview-fix-rereview-mimo-20260817.md

## Verdict

**PASS**。Finding 01 已正确修复；predicate 同源、非法组合 fail-before-mutation、合法路径不回归、无 boundary 扩散。

## 核对维度

### 1. 唯一 skip compatibility predicate 是否为 arbitration/executor 同源 owner

**PASS**。

新增 `_company_decision_allows_canonical_skip` (filing_upload_publication.py:429-451) 是唯一表达 `keep/no-intent | stage/preserve_published intent` 的 private pure predicate。

- `_canonical_skip_requirements_are_met` (line 476) 删除原有内联规则，改为调用该 predicate。
- SKIP executor (line 795) 在任何 repository stage/commit 前调用同一 predicate。

两处消费同一函数引用，不存在复制或漂移空间。

### 2. 非法组合是否在任何 stage/commit 前失败且 outer rollback exactly once

**PASS**。

Executor guard 位于 line 795：

```python
if not _company_decision_allows_canonical_skip(company_decision):
    raise ValueError("canonical SKIP company decision 必须是 ...")
```

此时 `batch_terminal_started` 仍为 `False`（line 695 初始化），guard 失败后直接进入 `finally` 块 (line 846)，通过 `rollback_prepared_upload_batch` 恰好回滚一次。

红测 `test_incompatible_company_decision_fails_before_canonical_skip_mutation` 断言：
- `events == ["rollback"]`：仅 rollback，无 commit
- `company.intents == []`：零 stage 调用
- `company.stage_tokens == []`：零 stage 调用
- `batching.commit_tokens == []`：零 commit 调用
- `batching.rollback_tokens == batching.begin_tokens`：rollback 恰一次
- 文件树仅含原始输入 bytes，无 durable side effect

### 3. 合法 keep 与 stage/preserve 是否不回归

**PASS**。

- `test_canonical_skip_company_compatibility_accepts_keep_and_preserve`：validator 产生的真实 `keep/no-intent` 与 `stage/preserve_published` 均由 predicate 接受。
- `test_canonical_keep_skip_rolls_back_without_stage_or_commit`：keep SKIP 返回 skipped、commit 零调用、rollback 恰一次。
- 既有 `test_metadata_only_skip_transfers_capability_and_projects_exact_outcome`：stage/preserve 路径的 commit outcome 与 warning 投影不变。

三路合法路径均通过。

### 4. 无 public/README/boundary 扩散

**PASS**。

- 新增符号：`_company_decision_allows_canonical_skip`（私有）、`UploadCompanyMetaDecision` import（既有公共类型，非新增）。
- 无公共 enum、schema、warning 文案、LLM-facing 文本、tool schema 或 README 变化。
- `docs/gateflow/uf-fix11-deepreview-fix-20260817.md` 已确认 README 无需更新。

### 5. `object.__setattr__` 测试模式评估

**合理，但有更干净替代。**

当前模式：
```python
object.__setattr__(
    fresh_request,
    "company_meta_decision",
    UploadCompanyMetaDecision(disposition="skip", company_meta_intent=None),
)
```

**合理性**：这是 deliberate impossible-state injection。`ValidatedFinsUploadFilingRequest` 是 frozen dataclass，正常路径不可能产生 `disposition="skip"` 的 company decision（`resolve_upload_company_meta_decision` 只返回 keep/skip/stage，其中 "skip" 只在 `action not in UPLOAD_ACTIONS_REQUIRING_COMPANY_META` 时出现，而 filing validation 已排除该路径）。测试需要绕过 frozen 限制注入该状态。

**不违反项目约束**：约束"禁止使用 `object`"针对的是生产代码类型签名（`def foo(object)` 或 `: object`），不是测试中用 `object.__setattr__` 突破 frozen dataclass 的标准 Python 测试模式。

**更干净替代**：可用 `dataclasses.replace()` 创建新实例：

```python
from dataclasses import replace

def _force_skip_with_incompatible_company_decision(...) -> FilingUploadPublicationDecision:
    del initial_request, prepared_identity, initial_skip_disposition
    # 用 replace 创建新实例，不绕过 frozen 限制
    modified = replace(
        fresh_request,
        company_meta_decision=UploadCompanyMetaDecision(
            disposition="skip",
            company_meta_intent=None,
        ),
    )
    # 但 monkeypatch 函数无法把 modified 传回 executor，因为 executor 用的是原始 fresh_request
    # 所以仍需修改原始对象...
```

问题在于：monkeypatch 替换的是 `arbitrate_filing_upload_publication`，该函数接收 `fresh_request` 参数但不返回它。executor 随后使用的是同一个 `fresh_request` 对象引用。`replace()` 创建新实例不影响原始引用。

**可行替代方案**：不使用 monkeypatch，直接构造包含非法 decision 的 `ValidatedFinsUploadFilingRequest`，然后调用 `execute_prepared_filing_publication`：

```python
def test_incompatible_company_decision_fails_before_canonical_skip_mutation(tmp_path):
    primary = tmp_path / "test.pdf"
    primary.write_bytes(b"test")
    identity = _build_publication_identity()
    # 直接构造包含非法 decision 的 request
    incompatible_request = _build_validated_request(
        _build_request(primary, action="update"),
        status=SourceIntegrityStatus.COMPLETE,
        revision="stable",
        publication_identity=identity,
        company_meta=_fresh_company_meta(),
    )
    # 用 replace 创建新实例（不绕过 frozen）
    from dataclasses import replace
    incompatible_request = replace(
        incompatible_request,
        company_meta_decision=UploadCompanyMetaDecision(
            disposition="skip",
            company_meta_intent=None,
        ),
    )
    # 直接构造 SKIP decision（不经过 arbitration）
    skip_decision = FilingUploadPublicationDecision(
        disposition=FilingUploadPublicationDisposition.SKIP,
        publish_mode=None,
        failure_reason=None,
    )
    # ... 然后直接调用 executor 的 SKIP 分支
```

但这需要重构 executor 以接受 decision 作为参数，或提取 SKIP 分支为独立函数。当前架构下，monkeypatch + `object.__setattr__` 是最简洁的注入方式。

**结论**：当前模式合理，红测有效。若追求更干净，可考虑将 SKIP 分支提取为接受 `(fresh_request, decision)` 的独立函数，测试直接调用该函数而不 monkeypatch。但这属于后续 refactor，不阻塞当前修复。

## Findings

未发现新问题。

## Residual Risk

- `object.__setattr__` 测试模式：合理但非最干净；后续可考虑提取 SKIP 分支为独立可测函数。
- 既有 residual（`file_events` mutable list、`RESOLVER_VERSION` 人工 bump）未扩大。
- 未执行真实 CLI/network/calibration，符合本轮 scope。
