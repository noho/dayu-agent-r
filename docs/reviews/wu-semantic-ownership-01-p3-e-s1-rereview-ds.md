# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Fix Re-Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace diff vs HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted staged changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-rereview-ds.md`
- Reviewed fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-controller-validation.md`
- Re-reviewed findings: P3-E-S1-CR-F01 through P3-E-S1-CR-F04
- Files in scope:
  - `dayu/host/tool_runtime.py` (F02: dead parameter/constant removal)
  - `tests/host/test_toolruntime_truncation_fetch_more.py` (F03: strengthened assertions)
  - `tests/host/test_toolruntime_executor.py` (F04: accept rejection reason proof)
  - `tests/tools/test_doc_tools_provider.py` (F01: stale cancellation hints)
  - `tests/tools/web/test_web_tools_provider.py` (F01: stale cancellation hints)
  - Previously changed files (S1 original scope, already re-reviewed in initial DS review):
    - `dayu/contracts/tool_result.py`
    - `tests/contracts/test_tool_result_envelope.py`
    - `tests/host/test_toolruntime_duplicate_governance.py`
    - `tests/fins/test_fins_storage_provider.py`
    - `docs/host/issues-implementation-control.md` (gate bookkeeping only)

## Closure Verdict Per Finding

### P3-E-S1-CR-F01 — CLOSED ✅

**要求**: `tests/tools/` 中三处 `hint == "tool_runtime_cancelled"` 改为 `hint is None`，同时保留 `policy_decision.reason_code == "tool_runtime_cancelled"`。

**验证**:

- `tests/tools/test_doc_tools_provider.py:1210`: `assert governed_outcome.result.hint is None` ✅
- `tests/tools/test_doc_tools_provider.py:1212-1213`: `assert accept_port.candidates[0].governance.policy_decision.reason_code == "tool_runtime_cancelled"` ✅
- `tests/tools/test_doc_tools_provider.py:1263`: `assert governed_outcome.result.hint is None` ✅
- `tests/tools/test_doc_tools_provider.py:1265-1266`: `policy_decision.reason_code` 断言保留 ✅
- `tests/tools/web/test_web_tools_provider.py:714`: `assert governed_outcome.result.hint is None` ✅
- `tests/tools/web/test_web_tools_provider.py:716-717`: `policy_decision.reason_code` 断言保留 ✅

**直接证据**: 三处 `governed_outcome.result.hint` 均改为 `is None`；三处 `policy_decision.reason_code == "tool_runtime_cancelled"` 均保留。ToolRuntime 治理原因仍在 ToolRuntime-owned policy diagnostic path 中，不再进入 LLM-facing hint。

**闭合结论**: 通过。

### P3-E-S1-CR-F02 — CLOSED ✅

**要求**: 删除 `_truncation_failure` 的死 `reason_code` 形参、所有 `_TRUNCATION_*_REASON` 常量，更新全部调用点。

**验证**:

- `dayu/host/tool_runtime.py:7443`: 函数签名 `def _truncation_failure(message: str) -> ToolFailedOutcome:` — 单参数，`reason_code` 已删除 ✅
- 11 个调用点全部改为仅传入 message 字符串（`dayu/host/tool_runtime.py:2038,2079,2091,2186,2190,2194,2198,2202,2241,5995,6001,6012`）✅
- `_TRUNCATION_*_REASON` 全量 source scan 无命中（覆盖 `_TRUNCATION_UNSUPPORTED_REASON`、`_TRUNCATION_CURSOR_MISSING_REASON`、`_TRUNCATION_SCOPE_MISMATCH_REASON`、`_TRUNCATION_TOKEN_MISMATCH_REASON`、`_TRUNCATION_CURSOR_EXPIRED_REASON`、`_TRUNCATION_CURSOR_USED_REASON`、`_TRUNCATION_REMAINDER_DIGEST_REASON`、`_TRUNCATION_INVALID_REQUEST_REASON`）✅
- 保留 `_TRUNCATION_ERROR_CODE = "truncation_error"` — 这是结构化 `error` 字段的固定值，非死代码 ✅
- Hidden hint protocol 全量 scan 无命中（`_hint_with_diagnostic_refs`、`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`、`_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`、`accept_rejected:`）✅

**直接证据**: `_truncation_failure` 不再接收也不丢弃任何结构化 reason code；场景差异仅通过 owner-authored `message` 保留，无假真源残留。

**闭合结论**: 通过。

### P3-E-S1-CR-F03 — CLOSED ✅

**要求**: 截断测试统一使用 `_assert_truncation_failure` 断言 `error == "truncation_error"` + 场景特定 `message` + `hint is None`。

**验证**:

- `tests/host/test_toolruntime_truncation_fetch_more.py:674-686`: `_assert_truncation_failure(outcome, expected_message)` 定义正确 ✅
- 断言三元组: `outcome.result.error == "truncation_error"` + `outcome.result.message == expected_message` + `outcome.result.hint is None` ✅
- 场景覆盖（行号 → 场景 → 预期 message）:
  - L287: cursor first-use then missing → `"truncation cursor is missing or no longer available"` ✅
  - L436: cursor never existed → `"truncation cursor is missing or no longer available"` ✅
  - L455: scope token mismatch → `"truncation scope token does not match cursor"` ✅
  - L477: cursor already used → `"truncation cursor has already been used"` ✅
  - L496: limit ≤ 0 → `"limit must be positive when provided"` ✅
  - L515: TTL expiry → `"truncation cursor expired"` ✅
  - L557: scope mismatch → `"truncation cursor does not belong to this run scope"` ✅
  - L586: digest mismatch → `"truncation remainder digest mismatch"` ✅
  - L626: unreplaceable target → `"tool result target cannot be replaced safely"` ✅

**直接证据**: 所有 9 处截断失败测试均通过 `_assert_truncation_failure` 锁定三个断言维度。若任何截断场景的 message 坍缩为空或 error 偏离 `"truncation_error"`，测试会失败。

**闭合结论**: 通过。

### P3-E-S1-CR-F04 — CLOSED ✅

**要求**: `test_accept_rejected_does_not_expose_raw_fake_result` 证明 accept rejection reason 通过 owner-authored `message` 或 diagnostics 保留，且 `hint is None`。

**验证**:

- `tests/host/test_toolruntime_executor.py:1426`: `assert record.outcome.result.error == "tool_accept_rejected"` ✅
- L1427: `assert record.outcome.result.hint is None` ✅
- L1428: `assert "idempotency_conflict" in record.outcome.result.message` — rejection reason 保留在 owner-authored message ✅
- L1429: `assert "must-not-leak" not in record.outcome.result.message` — raw fake result 不泄漏 ✅
- L1412-1413: accept port 返回 `ToolFactRejectedAck(reason_code=IDEMPOTENCY_CONFLICT, message="idempotency_conflict: reject fake result")` — 这是 accept barrier owner-authored message ✅

**直接证据**: 移除 `accept_rejected:*` hidden hint protocol 后，`idempotency_conflict` reason 在 `message` 中仍然可见；raw fake result `must-not-leak` 未进入 message；hint 为 None。

**闭合结论**: 通过。

## New Material Findings

无。

经逐路走读全部 fix 变更、source scan 确认无死代码/假真源残留、验证 business-authored hint（`dayu/host/tool_runtime.py:6566` `hint=parsed.hint`）未被误删后，未发现新的 correctness、stability、maintainability 或 semantic ownership 缺陷。

## Blocking Questions

无。

## Residual Risk

1. **`_truncation_failure(str(exc))` 路径消息稳定性**: 当 `FetchMoreRequest.__post_init__` 抛出 `ValueError` 时，`_fetch_more_request_from_call` 通过 `str(exc)` 将其 message 直接作为截断失败 message。测试（`test_fetch_more_rejects_invalid_limit`）已验证 `"limit must be positive when provided"` 的端到端一致性。若未来 `FetchMoreRequest` 的校验 message 被修改，对应测试 message 断言需同步更新。风险级别：低（message 变更会被该场景测试捕获）。

2. **`fetch_more limit must be a positive integer` 路径无直接测试覆盖**: 当 `limit_value` 为 bool 或非 int 类型时，`_fetch_more_request_from_call` 返回 message `"fetch_more limit must be a positive integer"`。该路径无对应测试断言其 message 内容。风险级别：低（该路径的 hint=None 行为已通过其他截断测试间接覆盖，message 内容变化不影响正确性）。

3. **S2/S3 未实施**: P3-E S2（wait callback typed provider ref + accepted status projection）和 S3（Fins direct RESULT protocol error）仍未开始。S1 独立可 ship。

## Conclusion

**PASS**

S1 的四个 code review finding 修复均已完成并通过独立验证：

- **F01**: `tests/tools/` 取消 hint 断言对齐为 `hint is None`，policy reason 保留在 ToolRuntime-owned diagnostic path
- **F02**: 死 `reason_code` 形参和 7 个 `_TRUNCATION_*_REASON` 常量已真实删除，无假真源残留
- **F03**: 截断测试通过 `_assert_truncation_failure` 锁定 `error == "truncation_error"` + 场景 message + `hint is None`，覆盖 9 个场景
- **F04**: accept rejection reason 保留在 owner-authored message（`idempotency_conflict`），`hint is None`，raw fake result 不泄漏

Hidden hint protocol 全量 source scan 确认无残留；business-authored process-backed hint 路径（`hint=parsed.hint`）未被误删。所有变更均落在 ToolRuntime / accept barrier / truncation manager 的 owner boundary 内，无下游特例、无语义漂移。
