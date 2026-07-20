# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2a Code Review — AgentMiMo

**Reviewer**: AgentMiMo
**Date**: 2026-07-11
**Scope**: WU-SEMANTIC-OWNERSHIP-01 / Round2 Batch D2a workspace changes only
**Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-implementation-codex.md`

---

## Findings

### F01 — `tests/cli/test_prompt_command.py` RunSnapshot invariant violation

**Severity**: Medium
**Category**: Test-side semantic repair failure
**File**: `tests/cli/test_prompt_command.py`, line 2243 (`_run_snapshot` helper) and line 1260 (call site)

D2a 在 `RunSnapshot.__post_init__` 新增了终态不变量：terminal status 必须携带一致的 `TerminalResultSummary`，非终态不得携带。`tests/cli/test_prompt_command.py` 的 `_run_snapshot` helper 硬编码 `terminal_result_summary=None`，但在 `test_prompt_command_uses_outbox_fallback_when_watcher_fails`（line 1260）中以 `run_statuses=(RunStatus.SUCCEEDED,)` 调用。`SUCCEEDED` 是终态，构造时将触发 `ValueError("RunSnapshot.terminal_result_summary is required for terminal status")`。

D2a 验证列表未包含 `tests/cli/test_prompt_command.py`，因此该 violation 未被当前 batch 覆盖的测试集发现。

**建议**: 将 `_run_snapshot` helper 改为条件构造 `TerminalResultSummary`，与 `tests/service/test_entrypoint_runtime.py:2042` 的 pattern 一致：

```python
def _run_snapshot(*, run_id: str, status: RunStatus) -> RunSnapshot:
    terminal_summary = None
    if is_terminal_run_status(status):
        terminal_summary = TerminalResultSummary(
            status=status, summary_ref=None, summary_digest=None,
        )
    return RunSnapshot(
        run_id=run_id,
        session_id="session-1",
        status=status,
        current_attempt_id=None,
        terminal_result_summary=terminal_summary,
        ...
    )
```

---

### F02 — `tests/cli/test_interactive_command.py` `_run_snapshot` helper 脆弱

**Severity**: Low
**Category**: Test-side fragility
**File**: `tests/cli/test_interactive_command.py`, line 2323 (`_run_snapshot` helper)

与 F01 同一 pattern：`_run_snapshot` helper 硬编码 `terminal_result_summary=None`。当前仅被 non-terminal status 调用（`RunStatus.RUNNING` at line 334, `RunStatus.CANCELLING` at line 389），不会触发 invariant violation。但 helper 本身不防御 terminal status 调用，若后续测试扩展调用范围将静默违反不变量。

**建议**: 同 F01，改为条件构造 `TerminalResultSummary`。

---

### F03 — `_row_rules.py` 独立定义 terminal status 值集合

**Severity**: Low
**Category**: 语义所有权残留重复
**File**: `dayu/host/durable/_row_rules.py`, lines 13-18

`TERMINAL_RUN_STATUS_VALUES` 硬编码了 4 个终态 `RunStatus.value` 字符串，未从 `dayu/host/api.py` 的 `TERMINAL_RUN_STATUSES` 派生。`state.py:75` 已将 durable 层的 `TERMINAL_RUN_STATUSES` 改为 `PUBLIC_TERMINAL_RUN_STATUSES` 的 clean alias，但 `_row_rules.py` 仍独立维护值集合。

存在 drift-guard test（`test_state_schema.py:196` `test_terminal_run_statuses_derive_from_row_rules`）确保两处一致，但这是检测而非预防。

**Import chain 约束**: `_row_rules.py` 导入 `RunStatus` from `dayu.host.api`（line 10），技术上可以导入 `TERMINAL_RUN_STATUSES` 并派生 `tuple(s.value for s in TERMINAL_RUN_STATUSES)`。但 `_row_rules.py` 定位是 low-level SQL CHECK 表达式 helper，依赖 public API 常量会改变其层级语义。当前 drift-guard test 是可接受的防御策略。

**建议**: 无需在 D2a 修复。若后续 batch 要求严格单源，可在 `_row_rules.py` 中改用 `tuple(s.value for s in TERMINAL_RUN_STATUSES)` 导入，但需评估层级依赖影响。

---

### F04 — Write-side `RunStartReason` 使用 `.value` 而非 `serialize_run_start_reason()`

**Severity**: Informational
**Category**: 风格一致性
**Files**: `dayu/host/durable/run_transition.py`, `dayu/host/admission.py`

D2a 新增了 `serialize_run_start_reason()` codec，但所有生产代码写入 `start_reason` 时直接使用 `RunStartReason.X.value` 或 `request.start_reason.value`，未调用 `serialize_run_start_reason()`。`serialize_run_start_reason` 仅在测试 fixture 中使用。

功能上无差异（`StrEnum.value` 产出相同字符串），但写入端未走 codec 意味着 codec 不是 single write-side chokepoint。

**建议**: 无需在 D2a 修复。若后续 batch 要求 write-side 一致性，可在 `run_transition.py` 和 `admission.py` 的写入点统一使用 `serialize_run_start_reason()`。

---

## Positive Verification

### V01 — `RunSnapshot` 终态不变量覆盖所有生产构造路径

`dayu/host/durable/state.py:5149` 的 `run_snapshot_from_row()` 是唯一生产构造 factory，委托 `_terminal_result_summary_from_status(status)` 条件构造 `TerminalResultSummary`。所有 `command.py` 和 `read_api.py` 的读取路径均经过此 factory。**正确**。

### V02 — `TERMINAL_RUN_STATUSES` / `is_terminal_run_status` 公共导出正确

- `dayu/host/api.py`: `TERMINAL_RUN_STATUSES: Final[frozenset[RunStatus]]` + `is_terminal_run_status(status) -> bool`
- `dayu/host/__init__.py`: 正确 re-export 两者到 `__all__`
- `dayu/host/durable/state.py:75`: `TERMINAL_RUN_STATUSES = PUBLIC_TERMINAL_RUN_STATUSES`（clean alias）
- `dayu/service/entrypoint_runtime.py`: 消费 `is_terminal_run_status`，删除了本地 `_TERMINAL_RUN_STATUSES` 和 `_is_terminal_run_status`

导出粒度合适：`TERMINAL_RUN_STATUSES` 是 `Final[frozenset]`，不可变；`is_terminal_run_status` 是带 `TypeError` 防御的 predicate。两者语义一致，未过度暴露内部细节。

### V03 — `decode_run_started_payload` 正确 fail closed

`dayu/host/durable/state.py:758-773`：
- `start_reason` 缺失 → `HostDurableError("RUN_STARTED.start_reason is required")`
- `start_reason` 非 `str` → same error
- `start_reason` 为空字符串 → same error
- `start_reason` 未知枚举值 → `deserialize_run_start_reason` → `_deserialize_str_enum` → `HostDurableError`

所有消费端（`run_input.py:3467`, `run_input.py:4757`, `event_log.py:891`）均通过此 decoder 读取，无残留 raw string 读取。测试覆盖了缺失、空字符串、未知值三种 negative case。**正确**。

### V04 — `count_recovery_dispatches_for_run` 保持 canonical fact 计数语义

`dayu/host/durable/event_log.py:856-894`：
- SQL 过滤条件不变：`run_id + event_type="RUN_STARTED" + event_class=CANONICAL_FACT`
- payload 解码从 `EventPayloadTextEqualsFilter` 改为 `decode_run_started_payload` typed decoder
- 非法 payload 现在 fail closed（`HostDurableError`），旧实现在 payload filter 层会跳过不匹配行

这是正确的语义升级：canonical fact 不满足 Host lifecycle contract 时应 fail closed，不应静默跳过。

### V05 — `HostToolingOptions` / `OpenHostOptions` Protocol 校验正确

**`HostToolingOptions`** (`dayu/host/tooling.py:255-274`):
- `wait_adapter_registry` → `isinstance(..., WaitAdapterRegistry)`
- `wait_activation_registry` → `isinstance(..., WaitActivationRegistry)`
- `wait_poll_adapter_registry` → `isinstance(..., WaitPollAdapterRegistry)`

**`OpenHostOptions`** (`dayu/host/api.py:1278-1280`):
- `wait_poller_policy` → `_validate_wait_poller_policy()` → `isinstance(..., WaitPollerRuntimePolicy)` + 逐字段数值校验

Protocol 使用 `TYPE_CHECKING` guard + runtime `@runtime_checkable` 定义，避免 import cycle 同时保持 runtime `isinstance` 校验。`open_host.py` 移除了重复的 `isinstance` 检查（原 line 1061-1062, 1076-1080），改为依赖 construction-time validation。**正确**。

### V06 — `TerminalResultSummary` 新增 terminal status 校验

`dayu/host/api.py:2238-2250`：
- `__post_init__` 新增 `is_terminal_run_status(self.status)` 校验
- 非 terminal status 构造 `TerminalResultSummary` → `ValueError("TerminalResultSummary.status must be terminal")`

这与 `RunSnapshot` 不变量配合：`RunSnapshot` 终态要求 `TerminalResultSummary`，而 `TerminalResultSummary` 自身拒绝非终态 status，形成双向约束。**正确**。

### V07 — README 更新在职责边界内

`dayu/host/README.md` 更新仅扩展了 `get_run(run_id)` 的描述，说明终态判断以 Host public `is_terminal_run_status(status)` 为准，以及 `RunSnapshot` 终态不变量。属于 Host developer-facing public contract 文档，符合 `dayu/host/README.md` 职责边界。**正确**。

---

## Conclusion

D2a 变更在生产代码层面正确实现了三个 accepted findings 的修复：Run terminal predicate 单源化、`RUN_STARTED.start_reason` typed codec fail-closed、Host construction options Protocol validation。生产构造路径全部覆盖，无残留 fallback 或下游语义补偿。

发现 1 个 Medium 问题（F01：`test_prompt_command.py` 的 `_run_snapshot` helper 违反新 invariant）和 1 个 Low 问题（F02：`test_interactive_command.py` 同 pattern 脆弱），均属于 D2a 变更引入 invariant 后未扫描全量测试 helper 的遗漏。`_row_rules.py` 独立 terminal set（F03）属于 pre-existing 结构，有 drift-guard test 防护，非 D2a 引入。Write-side `.value` 风格（F04）无功能影响。

F01 需要在 D2a 或后续 batch 中修复，否则 `test_prompt_command.py` 相关测试将在新 invariant 下失败。

---

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2a-code-review-mimo.md`
