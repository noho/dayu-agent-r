# P9-S2 Re-Review: Fix Verification

## Scope

- Mode: current changes (fix verification only)
- Branch: feat/host-p9-conversation-memory
- Base: main
- Output file: docs/reviews/p9-s2-code-rereview-mimo-20260517.md
- Initial review: docs/reviews/p9-s2-code-review-mimo-20260517-0905.md
- Included scope: fixes to `dayu/host/memory.py` and `tests/host/test_memory_projection.py`

## Accepted Fixes to Verify

### Fix 1 — ASSISTANT_CONCLUSION items participate in history pool budget

**Finding**: #1 (MEDIUM) — `always_items` bypass history pool budget

**Code verification** (`memory.py:1304-1358`):

`_limit_continuity_items` 重写为以 `primary_pool_items` 替代 `always_items`。所有非 `_is_raw_turn` 且非 `_is_episode` 的 item（包括 `ASSISTANT_CONCLUSION`）现在进入 `primary_pool_items`，参与 history pool size budget 竞争。`budget_used` 从 0 起算，不再从 `always_items` sum 起算。`_event_ordered_items` helper 确保按 `event_sequence` 确定性排序。

**Test verification** (`test_memory_projection.py`):

`test_history_pool_limits_assistant_conclusions_before_episode_summaries` 覆盖：tight budget 下 `ASSISTANT_CONCLUSION` 被降级，episode summary 保留。

**Verdict**: **PASS**

---

### Fix 2 — recent_raw_turns_floor == 0 edge case

**Finding**: #1 子项 — `policy.recent_raw_turns_floor == 0` 时 Python `-0[:]` 返回 full copy

**Code verification** (`memory.py:1323-1326`):

`if policy.recent_raw_turns_floor == _MIN_SEQUENCE: recent_raw = ()` 在 floor 为 0 时跳过 `-0[:]` 切片，直接置空。

**Test verification** (`test_memory_projection.py`):

`test_recent_raw_turns_floor_zero_keeps_no_raw_floor` 覆盖：floor=0 时只有 budget 内的最后一条 raw turn 存活。

**Verdict**: **PASS**

---

### Fix 3 — Missing tool name uses neutral fallback producer name

**Finding**: #1 关联 — `_PRODUCER_NAME_HOST_PROJECTION` 作为 tool 缺失时的 producer_name 语义不当

**Code verification** (`memory.py:72, 1031-1032`):

`_UNKNOWN_TOOL_PRODUCER_NAME = "unknown_tool"` 替代 `_PRODUCER_NAME_HOST_PROJECTION`。当 `tool_name` 缺失时，`VerifiedFactView.provenance.producer_name` 使用 `"unknown_tool"` 而非 host projection 语义。

**Test verification** (`test_memory_projection.py`):

`test_missing_tool_name_uses_unknown_tool_producer` 覆盖：tool_name 为空时 `producer_name == "unknown_tool"`。

**Verdict**: **PASS**

---

### Fix 4 — Invalid source_refs skipped without dropping fact

**Finding**: #2 (LOW) — `HostNeutralRefKind(ref_kind_text)` 无效值抛 ValueError 导致整个投影失败

**Code verification** (`memory.py:1559-1568`):

`HostNeutralRefKind(ref_kind_text)` 外层增加 try/except ValueError，无效值时 `continue` 跳过该 ref。fact 本身仍生成，只丢失 malformed ref。

**Test verification** (`test_memory_projection.py`):

`test_invalid_source_refs_are_skipped_without_dropping_fact` 覆盖：payload 含无效 ref_kind 时 fact 仍生成，good ref 存活。

**Verdict**: **PASS**

---

### Fix 5 — Unknown event type records diagnostic

**Finding**: 新增防御 — `project_conversation_memory_event` 对未识别 event type 的处理

**Code verification** (`memory.py:881-887, 1572-1595`):

`else` 分支调用 `_unsupported_event_type_diagnostic`，生成 `MemoryDiagnostic(reason=SNAPSHOT_DAMAGED, message="UNSUPPORTED_EVENT_TYPE: ...")`。cursor 正常推进，不中断投影。

**Test verification** (`test_memory_projection.py`):

`test_unknown_event_type_records_diagnostic_and_advances_cursor` 覆盖：cursor 推进到 seq 7，无 facts/continuity，diagnostic 含 `UNSUPPORTED_EVENT_TYPE` message。

**Verdict**: **PASS**

---

## New Issues Introduced by Fixes

未发现。

注意事项：
- `_unsupported_event_type_diagnostic` 使用 `SNAPSHOT_DAMAGED` 作为 reason，语义上并非完全匹配。docstring 中已标注 durable schema 尚无独立的 `unsupported_event_type` reason。这是一个已知的临时映射，不构成功能缺陷。

## Verification

### Tests

```
$ source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py -v
35 passed in 0.27s
```

初始 review 30 tests → re-review 35 tests（+5 新测试覆盖 5 个 fix）。

### Pyright

```
$ source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
0 errors, 0 warnings, 0 informations
```

### Git whitespace

```
$ git diff --check HEAD -- dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
(clean)
```

## Verdict

**PASS。0 remaining blocking findings。**

| Fix | Finding | Severity | Verdict |
|-----|---------|----------|---------|
| 1. ASSISTANT_CONCLUSION budget participation | #1 | MEDIUM | PASS |
| 2. recent_raw_turns_floor == 0 edge | #1 子项 | LOW | PASS |
| 3. Missing tool name producer fallback | #1 关联 | LOW | PASS |
| 4. Invalid source_refs skip | #2 | LOW | PASS |
| 5. Unknown event type diagnostic | 新增 | LOW | PASS |

所有初始 review findings 已修复并通过验证。5 个 fix 均未引入新问题。
