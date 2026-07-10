# Code Review Re-review

## Scope

- Mode: current changes (fix re-review)
- Branch: `phaseflow/host-issues-control`
- Base: unstaged workspace diff
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-rereview-mimo.md`
- Reviewed fixes:
  - `P3-E-S1-CR-F01`: stale `tests/tools/` cancellation hint assertions
  - `P3-E-S1-CR-F02`: dead truncation `reason_code` / `_TRUNCATION_*_REASON` removal
  - `P3-E-S1-CR-F03`: strengthened truncation failure tests
  - `P3-E-S1-CR-F04`: accept rejection reason proof
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-controller-validation.md`
- Excluded scope: S2/S3, unrelated untracked docs

## Closure Verdict Per Finding

### P3-E-S1-CR-F01 - CLOSED

**要求**: 更新 `tests/tools/` 中 stale cancellation hint 断言为 `hint is None`，保留 policy reason。

**验证**:

- `tests/tools/test_doc_tools_provider.py:1207`: `hint == "tool_runtime_cancelled"` → `hint is None` ✅
- `tests/tools/test_doc_tools_provider.py:1260`: 同上 ✅
- `tests/tools/web/test_web_tools_provider.py:711`: 同上 ✅
- 三处均保留 `accept_port.candidates[0].governance.policy_decision.reason_code == "tool_runtime_cancelled"` ✅

**结论**: 修复正确。ToolRuntime cancellation 治理 reason 仍通过 policy diagnostic path 可见，不再泄漏到 LLM-facing hint。

### P3-E-S1-CR-F02 - CLOSED

**要求**: 删除 `_truncation_failure` 死 `reason_code` 参数和 `_TRUNCATION_*_REASON` 常量。

**验证**:

- `_truncation_failure` 签名从 `(reason_code: str, message: str)` 改为 `(message: str)` ✅ (`tool_runtime.py:7443`)
- 全部 12 处调用点已更新，只传入 owner-authored `message` ✅ (diff 行 66-146)
- 8 个 `_TRUNCATION_*_REASON` 常量已删除 ✅ (diff 行 55-62)
- source scan `grep -rn '_TRUNCATION_.*REASON' dayu/host/tool_runtime.py` 返回零命中 ✅
- `_TRUNCATION_ERROR_CODE = "truncation_error"` 保留作为结构化 error code ✅

**结论**: 修复正确。无假真源残留，截断失败语义仅通过 owner-authored `message` 保留。

### P3-E-S1-CR-F03 - CLOSED

**要求**: 截断测试证明 `error == "truncation_error"`、场景 message、`hint is None`，覆盖 accepted 场景。

**验证**:

- 新增 `_assert_truncation_failure(outcome, expected_message)` 统一断言 helper ✅ (`test_toolruntime_truncation_fetch_more.py:674-686`)
  - `assert outcome.result.error == "truncation_error"` ✅
  - `assert outcome.result.message == expected_message` ✅
  - `assert outcome.result.hint is None` ✅
- 8 个场景全部使用该 helper：
  - cursor missing: `"truncation cursor is missing or no longer available"` ✅ (line 433)
  - token mismatch: `"truncation scope token does not match cursor"` ✅ (line 452)
  - cursor already used: `"truncation cursor has already been used"` ✅ (line 474)
  - invalid request: `"limit must be positive when provided"` ✅ (line 493)
  - TTL expiry: `"truncation cursor expired"` ✅ (line 512)
  - scope mismatch: `"truncation cursor does not belong to this run scope"` ✅ (line 554)
  - digest mismatch: `"truncation remainder digest mismatch"` ✅ (line 583)
  - unreplaceable target: `"tool result target cannot be replaced safely"` ✅ (line 626)
- 新增 `test_truncation_rejects_unreplaceable_target` 覆盖 `_VanishingPathMapping` 防御分支 ✅ (line 592-629)
- `_VanishingPathMapping` 实现正确：首次 `__getitem__` 返回值，后续抛 `KeyError`，覆盖截断 target 已选择但替换失败的分支 ✅

**结论**: 修复正确。测试现在锁定每个截断场景的完整三字段语义（error/message/hint），若未来 message 坍缩测试会失败。

### P3-E-S1-CR-F04 - CLOSED

**要求**: accept rejection reason 通过 owner-authored message 或 diagnostics 保留，raw fake result 不泄漏。

**验证**:

- `test_accept_rejected_does_not_expose_raw_fake_result` 变更：
  - fixture message 改为 `"idempotency_conflict: reject fake result"` ✅ (diff 行 343)
  - 新增 `assert record.outcome.result.hint is None` ✅ (diff 行 351)
  - 新增 `assert "idempotency_conflict" in record.outcome.result.message` ✅ (diff 行 352)
  - 保留 `assert "must-not-leak" not in record.outcome.result.message` ✅ (diff 行 353)
- `_accept_failure_outcome` 使用 `message=result.message`（owner-authored），不再构造 `accept_rejected:*` hint ✅ (diff 行 199-204)

**结论**: 修复正确。accept rejection reason 通过 accept barrier owner-authored message 可见，raw fake result 不泄漏，hint 不承载治理码。

## New Material Findings

**0**。四个 finding 修复均正确闭合，未发现新的实质问题。

## Blocking Questions

**0**。

## Residual Risk

- Source scan 确认 `_TRUNCATION_*_REASON`、`_hint_with_diagnostic_refs`、三枚 hidden-hint protocol 常量、`accept_rejected:`、`hidden-hint` 在 `dayu/host/tool_runtime.py`、`tests/host`、`tests/tools` 中均零命中。
- `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON` 和 `_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON` 仍在生产代码中用于 `ToolTraceDiagnosticRecord(reason_code=...)`，这是正确的 owner diagnostic 用途，不是 LLM-facing hint。
- process-backed spawn 测试的 pytest-cov 限制仍存在（`tool_runtime.py` coverage 85%，排除 process-backed cases），controller validation 已接受此限制。
- S2/S3 未实施，不在本 re-review 范围。

## Final Conclusion

**PASS**

四个 accepted findings 全部正确闭合，无新 material findings，无 blocking questions。
