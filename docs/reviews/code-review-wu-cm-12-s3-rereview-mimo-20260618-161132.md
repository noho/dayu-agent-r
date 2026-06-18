# Code Review

## Scope

- Mode: current changes
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/code-review-wu-cm-12-s3-rereview-mimo-20260618-161132.md
- Included scope: WU-CM-12 S3 focused re-review after review fixes。只复核 3 个 accepted findings 是否闭环。
- Excluded scope: S3 其余行为（已在前轮 review 中通过）。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

## Verification

### Finding 1: EventLogContextFallbackProvider required readers — PASS

**检查项**: `selected_recent_window_turn_floor`、`selected_raw_turn_count`、`selected_material_view_digest` 是否已 required 读取，缺失/坏类型/负数/空文本是否 HostDurableError fail closed。

**直接证据**:

- `context_fallback.py:373-384` 使用 required reader：
  ```python
  selected_recent_window_turn_floor=_required_non_negative_int(
      window, _FIELD_SELECTED_RECENT_WINDOW_TURN_FLOOR,
  ),
  selected_raw_turn_count=_required_non_negative_int(
      window, _FIELD_SELECTED_RAW_TURN_COUNT,
  ),
  selected_material_view_digest=_required_text(
      window, _FIELD_SELECTED_MATERIAL_VIEW_DIGEST,
  ),
  ```

- `_required_non_negative_int`（行 766-780）：字段缺失、非 int、bool、或负数 → `raise HostDurableError`。
- `_required_text`（行 783-795）：字段缺失、非 str、或空白 → `raise HostDurableError`。

- `_optional_non_negative_int` 和 `_optional_text` 仍存在（行 752、766），但不再用于 always-present provenance 字段。`_optional_text` 仅用于 `window_current_ref`（行 362）和 `_optional_mapping`（行 356），这些是 genuinely optional 的字段。

- `ActiveRecentWindowFallback` dataclass 字段仍为 `int | None` / `str | None` 类型（行 243-245），但 provider 总是传入非 None 值。下游 `_selected_material_render_view`（`run_input.py:2803-2806`）和 `_validate_fallback_protected_groups`（`run_input.py:2890`）的 `is not None` guard 在当前 provider 写入路径下永远不会短路跳过。

### Finding 2: Provider-level EventLog payload path tests — PASS

**检查项**: 测试是否覆盖 missing window、digest mismatch、current_input_ref mismatch、缺失/非法 always-present provenance 字段，且不是只测 `_fallback_context_messages`。

**直接证据**:

`test_eventlog_context_fallback_provider_fail_closes_on_payload_drift`（行 1435-1461）直接测试 `EventLogContextFallbackProvider.load_context_fallback`，通过 `_append_context_fallback_failed_event` 写入 EventLog。覆盖 9 个 parametrized case：

| case_name | 测试的 failure mode | 匹配消息 |
|-----------|-------------------|---------|
| `missing_window` | fallback_input_window 缺失 | "active fallback input window is missing" |
| `digest_mismatch` | fallback_input_digest 不匹配 | "fallback input digest mismatch" |
| `current_ref_mismatch` | current_input_ref 不匹配 | "fallback current_input_ref mismatch" |
| `missing_material_digest` | selected_material_view_digest 字段缺失 | "selected_material_view_digest" |
| `blank_material_digest` | selected_material_view_digest 为空文本 | "selected_material_view_digest" |
| `missing_raw_turn_count` | selected_raw_turn_count 字段缺失 | "selected_raw_turn_count" |
| `negative_raw_turn_count` | selected_raw_turn_count 为 -1 | "selected_raw_turn_count" |
| `missing_turn_floor` | selected_recent_window_turn_floor 字段缺失 | "selected_recent_window_turn_floor" |
| `bad_turn_floor_type` | selected_recent_window_turn_floor 类型非法 | "selected_recent_window_turn_floor" |

测试 helper `_context_fallback_failed_payload`（行 2883-2925）通过删除/篡改 window 字段构造损坏 payload，直接写入 EventLog 后由 provider 读取。不是只测 `_fallback_context_messages`。

### Finding 3: _validate_fallback_protected_groups dead code cleanup — PASS

**检查项**: 依赖 `protected_recent_raw_turn=True` 的 marked-group 死代码及其 synthetic 测试是否已删除；主 protected group consistency guard 是否仍保留。

**直接证据**:

- `_validate_fallback_protected_groups`（`run_input.py:2875-2919`）不再包含 `marked_group_ids` 相关代码。函数现在只做：
  1. `selected_raw_turn_count` 一致性校验（行 2890-2895）
  2. `protected_recent_turn_group_ids_for_material_blocks` 计算 + `expected_protected_ids.issubset(selected_ids)` 校验（行 2896-2919）

- `protected_recent_raw_turn` 在 `run_input.py` 中 grep 结果为空（无引用）。

- `test_fallback_context_messages_fail_closed_on_mixed_protected_turn_group` 已删除（grep 无结果）。

- `test_fallback_context_messages_fail_closed_on_protected_group_mismatch`（行 1565-1604）仍保留，测试 protected floor group 有 block 缺失于 selected ids 时 fail closed。

- 181 tests passed / pyright 0 errors / git diff --check clean。

## Open Questions

- 无。

## Residual Risk

- 无。3 个 accepted findings 均已闭环。

## Conclusion

**PASS** — 3 个 accepted findings 全部闭环：
1. Provider 使用 required reader 读取 always-present provenance 字段，缺失/坏类型/负数/空文本均 HostDurableError fail closed。
2. Provider 级 EventLog payload 路径测试覆盖 9 个 fail-closed case，直接写入 EventLog 后由 provider 读取。
3. `_validate_fallback_protected_groups` 中 marked-group 死代码及 synthetic 测试已删除，主 protected group consistency guard 保留。

181 tests passed / pyright 0 errors / git diff --check clean。
