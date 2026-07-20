# WU-SEMANTIC-OWNERSHIP-01 P3-E S3 Code Review

## Scope

- Mode: current uncommitted diff
- Branch: `phaseflow/host-issues-control`
- Base: `main` + committed S1/S2
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s3-code-review-mimo.md`

### Reviewed files

| File | Role |
|------|------|
| `dayu/fins/direct_events.py` | Shared typed protocol error contract |
| `dayu/fins/ingestion_runtime.py` | Runtime drain-until-sentinel owner |
| `dayu/service/fins_direct.py` | Service boundary guard |
| `dayu/cli/commands/fins.py` | CLI catch/render + local fallback |
| `tests/fins/test_fins_ingestion_runtime.py` | Runtime missing/duplicate/no-hang tests |
| `tests/service/test_fins_direct.py` | Service missing/duplicate/business-failure tests |
| `tests/cli/test_fins_commands.py` | CLI protocol error surface tests |
| `dayu/fins/README.md` | Direct stream contract doc |
| `dayu/service/README.md` | Service direct helper doc |
| `tests/README.md` | Test coverage summary |

### Excluded

- Unrelated untracked `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`
- Committed S1/S2 (no regression detected)

---

## Findings

### 1. [Low] CLI `_consume_fins_direct_events` local MISSING_RESULT fallback duplicates runtime/Service guard

- **入口/函数**: `dayu/cli/commands/fins.py:770` — `_consume_fins_direct_events`
- **文件(行号)**: `dayu/cli/commands/fins.py:770-774`
- **输入场景**: Service stream 正常结束但 CLI 层未收到 RESULT（runtime 和 Service 均已抛 MISSING_RESULT，但如果 Service 被 mock 或 stream 被截断，CLI 层仍会触发此分支）
- **实际行为**: CLI 构造 `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, "Fins direct Service stream ended without RESULT")`
- **预期行为**: 与 runtime/Service 使用同一 typed error，不伪造 business RESULT — 已满足
- **直接证据**: `dayu/cli/commands/fins.py:770-774`
- **影响**: 无功能影响。此分支是 defense-in-depth：正常路径下 runtime/Service 已抛出同一错误，CLI 此处是最后防线。`operation_kind` 通过 `_direct_operation_kind` 正确映射。
- **建议改法和验证点**: 无需修改。可考虑在注释中标注此为 defense-in-depth 而非主路径。
- **修复风险**: 无
- **严重程度**: 低

### 2. [Info] `FinsDirectStreamProtocolError` 继承 `ValueError` 而非自定义基类

- **入口/函数**: `dayu/fins/direct_events.py:88`
- **文件(行号)**: `dayu/fins/direct_events.py:88`
- **输入场景**: 协议错误抛出时
- **实际行为**: 继承 `ValueError`，CLI 通过 `except FinsDirectStreamProtocolError` 精确捕获
- **预期行为**: 协议错误应有明确语义区分 — `ValueError` 是合理选择，因为这是输入/状态非法
- **直接证据**: `dayu/fins/direct_events.py:88`
- **影响**: 无功能影响。`ValueError` 是 Python 标准语义，CLI 精确捕获不会被 `except Exception` 误吞
- **建议改法和验证点**: 无需修改
- **修复风险**: 无
- **严重程度**: 信息

---

## Open Questions

无。

---

## Residual Risk

1. **Producer lifecycle**: Runtime 现在延迟 yield terminal RESULT 直到 sentinel。如果未来 producer emit RESULT 后执行长时间阻塞才 return，会暴露 producer lifecycle bug 而非被下游隐藏。这是正确的 fail-fast 行为，implementation artifact 已记录。

2. **Business failure 与 protocol error 分离**: Producer 执行异常仍由 wrapper 转为 business failure RESULT（`FinsResultStatus.FAILURE`），与 stream protocol violation 分离。测试 `test_failure_result_is_passed_through` 确认 pass-through。

3. **CLI `upload_filings_from` 不经过 `_direct_operation_kind`**: 该命令在 `_run_fins_direct_command_async` 之前被 `_run_upload_filings_from` 拦截，不进入 direct stream path。映射正确。

---

## Verification Summary

| 检查项 | 结果 |
|--------|------|
| `FinsDirectStreamProtocolError` contract 质量 | ✅ typed `reason`/`operation_kind`/`message`，`__init__` 校验，`__all__` 导出 |
| Runtime drain-until-sentinel | ✅ buffer first RESULT → drain to sentinel → yield single RESULT |
| Duplicate RESULT → DUPLICATE_RESULT | ✅ runtime + Service |
| Missing RESULT → MISSING_RESULT | ✅ runtime + Service + CLI fallback |
| No-hang normal stream | ✅ `test_direct_stream_drains_to_done_before_yielding_result` |
| Business failure RESULT pass-through | ✅ `test_failure_result_is_passed_through` |
| CLI catches `FinsDirectStreamProtocolError` | ✅ `run_fins_direct_command` line 286 |
| CLI `_direct_operation_kind` mapping | ✅ 6 commands mapped, `upload_filings_from` excluded |
| `FinsDirectStreamContractViolation` removed | ✅ `grep -rn` 零匹配 |
| `_direct_missing_result_event` / `_missing_result_event` removed | ✅ `grep -rn` 零匹配 |
| README stale synthetic result wording removed | ✅ 3 READMEs updated |
| Tests pass | ✅ 124 passed, 3 warnings |
| pyright | ✅ 0 errors |
| `git diff --check` | ✅ clean |

---

## Conclusion

**PASS**

S3 实现正确满足计划目标。`FinsDirectStreamProtocolError` 作为 shared typed contract 跨 runtime/Service/CLI 统一使用；runtime drain-until-sentinel 行为正确（buffer → drain → yield）；Service mirror 同一协议；CLI 删除 local exception 并 catch shared error；business failure RESULT pass-through 未受影响；READMEs 移除 stale synthetic result 措辞。仅发现一处 defense-in-depth 注释建议（低 severity），无 material defect。
