# Code Review — WU-CM-12 S3 Fix Re-Review

## Scope

- Mode: current changes (focused re-review after review fixes)
- Branch: `wu-cm-12-conversation-memory-drift`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cm-12-s3-rereview-ds-20260618-161031.md`
- Included scope: 仅复核 accepted findings 的三个修复点。Working tree unstaged changes in `dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`tests/host/test_run_input_builder.py`。
- Excluded scope: committed S1/S2 changes；S3 其余已通过 review 的变更（accepted compact semantic renderer、`selected_material_view_digest`、fallback renderer 重构等）；S4 tier fallback。
- Source artifact: `docs/reviews/code-review-wu-cm-12-s3-ds-20260618-160229.md`（DS review，提出 3 个 accepted findings）
- Parallel review coverage: 无。单一 reviewer 逐项复核。

## Findings

未发现实质性问题。

三个 accepted finding 的修复均已正确闭环。

### Fix 1 复核：provenance 字段从 optional 改为 required 读取

- **修复前状态**（来自 DS review Open Question 1）：
  - `_load_context_fallback_tx` 使用 `_optional_non_negative_int`、`_optional_text` 读取 `selected_recent_window_turn_floor`、`selected_raw_turn_count`、`selected_material_view_digest`。
  - 缺失或非法值时静默返回 `None`，rendering 阶段的 `_validate_fallback_protected_groups` 内 `is not None` guard 会跳过相应校验。

- **修复后状态**（直接证据）：

  `_load_context_fallback_tx`（`context_fallback.py:368-386`）：
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

  - `_required_non_negative_int`（`context_fallback.py:766-780`）：缺失 → `HostDurableError`；非 int → `HostDurableError`；bool → `HostDurableError`（`not isinstance(value, bool)` 显式拒绝）；负数 → `HostDurableError`。
  - `_required_text`（`context_fallback.py:783-796`）：缺失 → `HostDurableError`；非 str → `HostDurableError`；空白字符串 → `HostDurableError`（`value.strip() == ""`）。
  - 旧的 `_optional_non_negative_int` payload reader 已完全删除（grep 确认仅存在 `_required_non_negative_int` 和 `_require_optional_non_negative_int` 两个函数，前者是 required payload reader，后者是 `ActiveRecentWindowFallback.__post_init__` validator）。

  **不再有 optional reader 让这些 always-present provenance guard 被静默跳过。** 三个字段在 Provider 读取时必须存在、类型正确、值合法，否则 `HostDurableError` fail closed。

- **`_require_optional_non_negative_int` 附加修复**（`context_fallback.py:896-912`）：新增 `isinstance(value, bool)` 显式拒绝，防止 Python `bool` 是 `int` 子类导致 `True`/`False` 被误接受。

- **结论**：**PASS**。

### Fix 2 复核：Provider 级 EventLog payload 路径测试

- **修复前状态**（来自 DS review Open Question 2）：
  - 所有 fail-closed 测试仅覆盖 `_fallback_context_messages`（rendering 层），无测试走 `EventLogContextFallbackProvider.load_context_fallback()` 完整 Provider 路径。

- **修复后状态**（直接证据）：

  新增 `test_eventlog_context_fallback_provider_fail_closes_on_payload_drift`（`test_run_input_builder.py:1435`），9 个 parametrized case：

  | case_name | 构造方式 | 断言 `HostDurableError` match | 覆盖层 |
  |-----------|---------|------------------------------|--------|
  | `missing_window` | `del payload["fallback_input_window"]` | `"active fallback input window is missing"` | `_load_context_fallback_tx:358-359` |
  | `digest_mismatch` | `payload["fallback_input_digest"] = _DIGEST_B` | `"fallback input digest mismatch"` | `_load_context_fallback_tx:360-361` |
  | `current_ref_mismatch` | `window["current_input_ref"] = "event-other-input"` | `"fallback current_input_ref mismatch"` | `_load_context_fallback_tx:363-364` |
  | `missing_material_digest` | `del window["selected_material_view_digest"]` | `"selected_material_view_digest"` | `_required_text:793-795` |
  | `blank_material_digest` | `window["selected_material_view_digest"] = ""` | `"selected_material_view_digest"` | `_required_text:793-795` |
  | `missing_raw_turn_count` | `del window["selected_raw_turn_count"]` | `"selected_raw_turn_count"` | `_required_non_negative_int:778-779` |
  | `negative_raw_turn_count` | `window["selected_raw_turn_count"] = -1` | `"selected_raw_turn_count"` | `_required_non_negative_int:776-779` |
  | `missing_turn_floor` | `del window["selected_recent_window_turn_floor"]` | `"selected_recent_window_turn_floor"` | `_required_non_negative_int:778-779` |
  | `bad_turn_floor_type` | `window["selected_recent_window_turn_floor"] = "zero"` | `"selected_recent_window_turn_floor"` | `_required_non_negative_int:776-779` |

  测试路径：`_context_fallback_failed_payload(case_name)` → `_append_context_fallback_failed_event`（通过 `EventLogStore().append_event()` 写入真实 EventLog）→ `EventLogContextFallbackProvider.load_context_fallback()` 读取 → 断言 `pytest.raises(HostDurableError)`。

  这是完整的 **Provider → EventLog → 读回 → fail closed** 路径，不是仅测 `_fallback_context_messages`。

- **结论**：**PASS**。

### Fix 3 复核：marked-group 死代码及 synthetic 测试删除

- **修复前状态**（来自 DS review Finding 1）：
  - `_validate_fallback_protected_groups` 包含 marked-group 校验循环（旧 lines 2920-2935），依赖 `protected_recent_raw_turn=True`，但生产代码无任何路径设置该标记。
  - `test_fallback_context_messages_fail_closed_on_mixed_protected_turn_group` 通过手动设置 `protected_recent_raw_turn=True` 测试了一条生产不可达路径。

- **修复后状态**（直接证据）：

  1. **marked-group 死代码已删除**：`_validate_fallback_protected_groups`（`run_input.py:2875-2919`）不再包含 marked-group 循环。函数在 `expected_protected_ids.issubset(selected_ids)` guard（line 2918）之后直接结束，下一条语句是 `_fallback_message_from_material_block`（line 2922）。

  2. **`protected_recent_raw_turn` 引用已从 `run_input.py` 清除**：`grep -n "protected_recent_raw_turn" dayu/host/run_input.py` 返回空结果。

  3. **synthetic 测试已删除**：`grep -n "mixed_protected_turn_group\|protected_recent_raw_turn=True" tests/host/test_run_input_builder.py` 返回 exit code 1（无匹配）。`test_fallback_context_messages_fail_closed_on_mixed_protected_turn_group` 已完全删除。

  4. **主 guard 保留**：`expected_protected_ids.issubset(selected_ids)`（line 2918）仍有效。对应的测试 `test_fallback_context_messages_fail_closed_on_protected_group_mismatch`（line 1565）保留，测试 `protected_user` 在 selected_ids 中但 `protected_answer`（同 group）缺失 → `HostDurableError("protected group consistency mismatch")`。

  5. **其余 fail-closed 测试保留**：
     - `test_fallback_context_messages_fail_closed_on_selected_view_drift`（6 个 parametrized case，line 1475）
     - `test_fallback_context_messages_fail_closed_on_selected_raw_turn_count_mismatch`（line 1532）
     - `test_fallback_context_messages_fail_closed_on_protected_group_mismatch`（line 1565）

- **结论**：**PASS**。

### 冗余检查：`_validate_fallback_protected_groups` 中 `is not None` guard 的安全性

`_validate_fallback_protected_groups` 中两处 `is not None` guard（lines 2890, 2896）在 after-fix 状态下仍然存在：

```python
if fallback.selected_raw_turn_count is not None:  # line 2890
    ...
if fallback.selected_recent_window_turn_floor is None:  # line 2896
    return
```

由于 Provider 现在使用 `_required_non_negative_int` / `_required_text` 读取，这些字段在 production 路径中 **always present**。`is not None` guard 等效于 always-true/always-false，但不构成漏洞——Provider 级别的 fail-closed 保证字段不会为 None（缺失时已在 Provider 层 `HostDurableError`）。

guard 保留是防御性编程，覆盖了 `ActiveRecentWindowFallback` 被测试代码直接构造（不走 Provider）的场景。**不构成 finding。**

## 验证结果

| 验证项 | 命令 | 结果 |
|--------|------|------|
| S3 affected tests | `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` | **181 passed in 1.89s** |
| Pyright | `pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | | **无 whitespace 错误** |
| `_optional_non_negative_int` dead reader | `grep "def _optional_non_negative_int" dayu/host/context_fallback.py` | **已删除，仅剩 `_required_non_negative_int` + `_require_optional_non_negative_int`** |
| `protected_recent_raw_turn` in run_input.py | `grep "protected_recent_raw_turn" dayu/host/run_input.py` | **0 matches** |
| `mixed_protected_turn_group` test | `grep "mixed_protected_turn_group\|protected_recent_raw_turn=True" tests/host/test_run_input_builder.py` | **exit code 1（已删除）** |
| Main guard preserved | `grep "expected_protected_ids.issubset" dayu/host/run_input.py` | **line 2918，保留** |
| Provider-level test | `grep "test_eventlog_context_fallback_provider" tests/host/test_run_input_builder.py` | **line 1435，9 parametrized cases** |

## Open Questions

无。

## Residual Risk

- `_validate_fallback_protected_groups` 中 `selected_raw_turn_count is not None` guard（line 2890）在 production 路径上恒为 True（Provider 已 required），但作为防御性编程保留。不构成风险，但若未来有人将 Provider 读回改为 optional，此 guard 会导致 raw turn count 检查被静默跳过。建议：若确认 `selected_raw_turn_count` 应为 always-present 字段，可移除 `is not None` guard 使校验无条件执行。

## Conclusion

**PASS** — 三个 accepted finding 的修复均已正确闭环：

1. **provenance 字段 required 读取**：`_load_context_fallback_tx` 使用 `_required_non_negative_int` / `_required_text` 读取三个 provenance 字段，旧 `_optional_non_negative_int` payload reader 已删除。缺失/坏类型/负数/空文本均 `HostDurableError` fail closed。

2. **Provider 级 EventLog 测试**：新增 `test_eventlog_context_fallback_provider_fail_closes_on_payload_drift`（9 parametrized cases），走完整 `EventLogContextFallbackProvider.load_context_fallback()` → EventLog 读写 → fail closed 路径。

3. **marked-group 死代码删除**：`_validate_fallback_protected_groups` 中 marked-group 循环已删除，`protected_recent_raw_turn` 引用从 `run_input.py` 清除，synthetic 测试 `test_fallback_context_messages_fail_closed_on_mixed_protected_turn_group` 已删除。主 guard `expected_protected_ids.issubset(selected_ids)` 保留且测试覆盖。
