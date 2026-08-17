# UF-FIX11 Deepreview Fix Final Re-Review

## Scope

- Mode: targeted final re-review of DS finding 02 test seam fix
- Branch: codex/upload-filing-oracle
- Inputs:
  - Updated `docs/gateflow/uf-fix11-deepreview-fix-20260817.md` (finding 01 + 02)
  - Working tree test diff (production diff SHA unchanged)
- Output file: docs/reviews/uf-fix11-deepreview-fix-rereview-final-mimo-20260817.md

## Verdict

**PASS**。DS finding 02 测试 seam 修复正确；红测能力未弱化，断言完整，无类型问题。

## 核对维度

### 1. Validator wrapper 调用真实 validator 后 replace typed decision

**PASS**。

`_validate_with_incompatible_company_decision` (test line 92-118):
- 调用 `validate_fins_upload_filing_request(request, published_state=published_state)` — 真实 validator，非 mock
- 返回 `replace(fresh_request, company_meta_decision=UploadCompanyMetaDecision("skip", None))` — `dataclasses.replace` 创建新 frozen 实例，不绕过 owner `__post_init__`
- `UploadCompanyMetaDecision("skip", None)` 匹配 dataclass 构造器签名 `(disposition, company_meta_intent)`
- `replace` 已在文件头导入 (line 5: `from dataclasses import fields, replace`)

### 2. Arbitration helper 只返回 SKIP

**PASS**。

`_force_skip_publication_decision` (test line 121-149):
- `del initial_request, fresh_request, prepared_identity, initial_skip_disposition` — 抑制未使用参数警告
- 返回 `FilingUploadPublicationDecision(disposition=SKIP, publish_mode=None, failure_reason=None)`
- 无 `object.__setattr__`，无 request mutation，无 nested function

### 3. 红测能力、零 stage/commit、exact rollback/durable 断言未弱化

**PASS**。

`test_incompatible_company_decision_fails_before_canonical_skip_mutation` (test line 2170-2228):

- Monkeypatch 两个 seam：`validate_fins_upload_filing_request` → `_validate_with_incompatible_company_decision`，`arbitrate_filing_upload_publication` → `_force_skip_publication_decision`
- `pytest.raises(ValueError, match="canonical SKIP company decision")` — 精确异常类型与消息匹配
- `events == ["rollback"]` — 仅 rollback，无 commit
- `company.intents == []` — 零 company meta stage
- `company.stage_tokens == []` — 零 stage 调用
- `batching.commit_tokens == []` — 零 commit 调用
- `len(batching.begin_tokens) == 1` — begin 恰一次
- `batching.rollback_tokens == batching.begin_tokens` — rollback 恰一次
- 文件树断言：仅含原始输入 `"metadata-skip.pdf"`，bytes 不变

所有断言与 finding 01 版本完全一致，红测能力未弱化。

### 4. 无 nested/glue/类型问题

**PASS**。

- 两个 helper 均为模块级函数，非 nested
- 签名类型完整：`request: FinsUploadFilingRequest`, `published_state: FilingUploadPublishedState`, 返回类型显式
- `replace()` 是标准库 frozen dataclass 替换，不绕过类型检查
- 无新增 import（`replace` 已在文件头存在）
- 无 glue code 或 compatibility shim

### 5. Production diff SHA 不变

**PASS**。

`git diff HEAD -- dayu/fins/pipelines/filing_upload_publication.py` 输出与 finding 01 版本逐字相同。Finding 02 仅调整测试 seam，production diff 零变化。

## Findings

未发现新问题。

## Residual Risk

- 既有 residual（`file_events` mutable list、`RESOLVER_VERSION` 人工 bump）未扩大。
- 未执行真实 CLI/network/calibration，符合本轮 scope。
