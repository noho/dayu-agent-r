# WU-OBS-SIGNALS-01 / OBS-SIG-02 Fix Re-Review — AgentDS

## Gate

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: `fix re-review`
- Slice: `OBS-SIG-02 / P02 Tool Duration Signal`
- Reviewer: AgentDS
- Artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-rereview-ds.md`
- Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-fix-codex.md`

## Scope

Re-review the Codex fix for the single controller-accepted finding MIMO-F1: failed / cancelled / governed-error result facts did not assert `tool_timing`. Verify fix correctness, test-only nature, no scope creep, and validation reproducibility.

---

## Accepted Finding Recheck

### MIMO-F1: Failed / cancelled result facts do not assert `tool_timing`

**Controller instruction**: Add focused assertions for `tool_timing` on failed, cancelled, and governed-error payloads. Expected value should match `_missing_tool_timing()` limited signal shape.

**Fix applied** (in `tests/host/test_toolruntime_accept_barrier.py`):

| 变更 | 行号 | 内容 |
|------|------|------|
| Failed payload assertion | 886 | `assert payloads[0]["tool_timing"] == _missing_tool_timing()` |
| Cancelled payload assertion | 887 | `assert payloads[1]["tool_timing"] == _missing_tool_timing()` |
| Governed-error payload assertion | 888 | `assert payloads[2]["tool_timing"] == _missing_tool_timing()` |
| Helper function | 1538-1551 | `_missing_tool_timing()` — 返回 `schema_version=1, status="missing_tool_result_meta", started_at=None, finished_at=None, duration_ms=None, duration_source=None` |

**Payload 索引验证**:

- `payloads[0]`: `ToolFactKind.FAILED` (tool-call-failed), policy=ALLOW
- `payloads[1]`: `ToolFactKind.CANCELLED` (tool-call-cancelled), policy=ALLOW
- `payloads[2]`: `ToolFactKind.GOVERNED_ERROR` (tool-call-governed-error), policy=GOVERNED_ERROR

索引与 `tool_fact_kind` 断言（line 881-884）一致。

**`_missing_tool_timing()` 与生产代码一致性**:

| 字段 | 测试 helper | 生产 `_tool_timing_from_meta(None)` |
|------|------------|--------------------------------------|
| `schema_version` | `1` | `_TOOL_TIMING_SCHEMA_VERSION` = `1` |
| `status` | `"missing_tool_result_meta"` | `_TOOL_TIMING_STATUS_MISSING_META` = `"missing_tool_result_meta"` |
| `started_at` | `None` | `None` |
| `finished_at` | `None` | `None` |
| `duration_ms` | `None` | `None` |
| `duration_source` | `None` | `None` |

完全一致。✅

**附带必要变更**（非 fix 部分，而是 `tool_timing` 成为 `ToolAcceptResult` 必填字段后的编译一致性变更）:

- `_completed_candidate()` line 1318: 新增 `tool_timing=_missing_tool_timing()`
- `_fact_kind_candidate()` line 1402: 新增 `tool_timing=_missing_tool_timing()`
- `test_tool_accept_result_rejects_payload_ref_digest_mismatch` line 1032: 新增 `tool_timing=_missing_tool_timing()`

这三处变更均为 `ToolAcceptResult` 构造调用，因 `tool_timing` 是必填字段（dataclass 无默认值），不传会导致 `TypeError`。这些变更是必要的编译一致性变更，不影响测试逻辑。

**Verdict**: ✅ MIMO-F1 已正确修复。

---

## New Findings

无新增 finding。Fix 严格限于 controller 接受的 MIMO-F1：

- 仅在 `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 中新增 3 行断言。
- 新增 `_missing_tool_timing()` helper，语义与生产 `_tool_timing_from_meta(None)` 一致。
- 对既有 helper 的 `tool_timing` 参数补充为编译一致性变更，不改变测试逻辑。
- 未修改任何生产代码。
- 未引入新测试文件、新 fixture 或新测试约定。

---

## Residual Risk

与 controller 裁决一致，无新增 residual risk：

| 风险 | Owner |
|------|-------|
| 不填充 `ToolResultMeta` 的工具产生 `status="missing_tool_result_meta"` limited signal | WU-OBS-00 analyzer |
| Analyzer latency aggregation (median/p99/distribution) | WU-OBS-00 |

---

## Validation

独立重新运行受影响的测试与 pyright：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_phase6_toolruntime_integration.py \
  tests/host/test_toolruntime_executor.py -v
```

结果: **80 passed in 0.69s**

```bash
source .venv/bin/activate && pyright
```

结果: **0 errors, 0 warnings, 0 informations**

与 fix artifact 报告一致（80 passed in 0.62s / 0 errors），验证可信。

---

## Verdict

**PASS**

Fix 精确实现了 controller 接受的 MIMO-F1：三个终态 payload（failed / cancelled / governed-error）均断言 `tool_timing == _missing_tool_timing()`，且 `_missing_tool_timing()` 返回值与生产代码 `_tool_timing_from_meta(None)` 完全一致。Fix 为 test-only，未改变生产行为。无 scope creep（未引入 P03/P04/analyzer 行为）。80 个测试全部通过，pyright 零错误。

等待 controller 裁决。
