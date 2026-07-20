# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Code Review Re-Review

## Artifact Metadata

- Review type: adversarial code re-review (post code-review fix verification)
- Target slice: `S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-rereview-ds.md`
- Timestamp: 2026-07-13T00:52:58+08:00
- Status: pass

## Review Scope

验证 controller adjudication 接受的唯一 finding `S2-F01` 是否已修复，确认无 regression、scope drift 或工具安全实现。

### Sources consulted

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-fix-codex.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-ds.md`
- Current working tree diff

---

## Finding Verification

### S2-F01 — CN commit failure test should assert storage absence

**Controller required fix**: 在 `test_cn_commit_failure_does_not_trigger_caller_rollback_or_success` 中添加 `pytest.raises(FileNotFoundError)` 断言 source absence。

**Fix location** (`tests/fins/test_cn_download_workflow.py:979-980`):

```python
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("600519", "fil2024", SourceKind.FILING)
```

逐项验证：

1. **断言存在**: `pytest.raises(FileNotFoundError)` 在行 979 ✅
2. **语义正确**: commit failure 后 storage owner 消费 token 并回滚，source 不应存在 ✅
3. **原有断言保留**: `summary["failed"] == 1`, `commit_calls == 1`, `rollback_calls == 0`, 无 `FILING_COMPLETED` 全部未变（行 972-978）✅
4. **无 production code 变更**: fix 仅修改测试文件 ✅
5. **测试通过**: fix artifact 报告 `1 passed`，完整 S2 suite `194 passed`，全量 `tests/fins` `519 passed` ✅

**Verdict**: ✅ **已修复** — CN commit failure 测试现与 upload/generic download 的 commit failure 测试对称，三种 caller 均断言 source absence。

---

## Regression / Scope Drift / Tool-Security Check

### Regression

fix 仅在已有测试的末尾增加 2 行 `FileNotFoundError` 断言。无 production code 变更。完整 test suite 194 passed, 519 passed。✅

### Scope drift

- 未修改任何 production file ✅
- 未新增 S3/Host/Service/Engine/README 文件 ✅
- `git diff HEAD --stat` 的 production file 列表与原始 S2 implementation 一致（8 production files）✅

### Tool-security

fix 不涉及任何 production code。测试仅新增 `FileNotFoundError` 断言，不引入 allowlist、file authority、URL/TLS/SSRF、byte budget、prompt 或 tool schema 相关内容。✅

---

## Open Questions

无。

---

## Residual Risk

无新增。既有 residual risk 分类不变。

---

## Re-Review Conclusion

**Status: pass**

**Findings count: 0**

**Completion report:**

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-rereview-ds.md`
- **fixed findings count**: 1
- **remaining findings count**: 0
- **new findings count**: 0
- **blocking questions count**: 0
