# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-cm-15`
- Base: `0439cd80`
- Output file: `docs/reviews/deepreview-wu-cm-15-aggregate-mimo-20260620.md`
- Included scope:
  - Plan artifact: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`
  - Implementation artifacts: `docs/reviews/wu-cm-15-implementation-codex-20260620.md`, `docs/reviews/wu-cm-15-plan-fix-codex-20260620.md`, `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md`
  - Review artifacts: `docs/reviews/code-review-20260620-112127.md`, `docs/reviews/code-review-20260620-112301.md`, `docs/reviews/code-review-20260620-115326.md`, `docs/reviews/code-review-rereview-ds-20260620.md`, plan reviews, adjudications
  - Control doc: `docs/host/issues-implementation-control.md` (committed + uncommitted)
  - Smoke script: `utils/smoke_host_public_conversation_memory_scenarios.py`
  - Assembly tests: `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - Tests README: `tests/README.md`
- Excluded scope: No `dayu/host/`, `dayu/engine/`, `dayu/runtime/`, `dayu/service/`, `dayu/config/`, `dayu/fins/`, or `dayu/contracts/` production code was modified.
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项审查结论如下：

### 1. 正确性：WU-CM-15 范围是否严格限定为 public smoke coverage

**验证结果：PASS。**

`git diff 0439cd80...HEAD --stat` 确认 19 个文件变更，其中：
- 生产代码（`dayu/`）：0 文件。
- Smoke 脚本（`utils/`）：1 文件（`smoke_host_public_conversation_memory_scenarios.py`）。
- 测试（`tests/`）：2 文件（assembly test + `tests/README.md`）。
- 文档（`docs/`）：16 文件（plan、review artifacts、control doc）。

计划明确声明 "No production `dayu/host`, `dayu/engine`, `dayu/runtime`, `dayu/service`, prompt, schema, or config file is planned for modification"，实现严格遵守。

### 2. 正确性：memory-compact strict proactive accepted semantics 是否保持

**验证结果：PASS。**

`_assert_compact_acceptance(...)` 仅在 `SuiteMode.MEMORY_COMPACT` 时执行，仍要求：
- `requested_proactive >= 1`
- `compacted_proactive >= 1`
- `failed_total == 0`（含 proactive + reactive）
- `artifact_count >= 1`

`CONTEXT_COMPACTION_FAILED` 仍是 `memory-compact` 的硬失败。Assembly test `test_compact_acceptance_requires_event_log_audit_summary` 明确覆盖了 `failed_proactive=1` 导致 `RuntimeError("CONTEXT_COMPACTION_FAILED")` 的路径。新增的 `MEMORY_REACTIVE_COMPACT` 和 `MEMORY_COMPACT_FALLBACK` 使用独立的验收 helper，未修改、未弱化、未绕过现有 `memory-compact` 验收逻辑。

### 3. 正确性：Host/Engine production contract/schema 是否未修改

**验证结果：PASS。**

`git diff 0439cd80...HEAD -- dayu/` 返回空。无任何 `dayu/host/`、`dayu/engine/`、`dayu/runtime/`、`dayu/service/`、`dayu/config/`、`dayu/contracts/` 文件被修改。

### 4. 正确性：old marker oracle 非空转

**验证结果：PASS。**

Reactive suite 流程：
1. `reactive-r1-old-seed` 种植 `_SMOKE_REACTIVE_OLD_MARKER`。
2. `reactive-r2/r3/r4-history-gap` 三轮历史间隔把旧种子推出 recent floor。
3. `reactive-r5-protected-recent` 种植 `_SMOKE_REACTIVE_RECENT_MARKER`。
4. `reactive-r6-overflow-target` 触发 deterministic worker 的 `CONTEXT_COMPACTION_REQUESTED`。

验收断言：
- `recovery.joined_messages` 必须包含 `current_input_marker` 和 `protected_recent_marker`。
- `recovery.joined_messages` 必须不包含 `dropped_old_marker`。

Assembly test `test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals` 覆盖了三个失败路径：缺失 reactive request、缺失 dropped marker 期望、old marker 泄漏到 recovery。Oracle 有真实的 assert 逻辑，不是空转。

Fallback suite 流程：
1. `fallback-f1..f5-old-dropped` 种植旧种子。
2. `fallback-f6-selected-recent` 种植近期种子。
3. `fallback-f7-pressure-target` 注入 bounded 压力触发 proactive compact。

验收断言：
- `CONTEXT_COMPACTION_FAILED` + `fallback_action=dispatch`。
- `selected_block_ids` 非空、`dropped_block_ids` 非空、`current_input_ref` 非空。
- Final dispatch 包含 `current_input_marker` 和 `protected_recent_marker`。
- Final dispatch 不包含 `dropped_old_marker`。
- Final dispatch 不包含 compact semantic sections（`Conversation Summary` 等）。

Assembly test `test_fallback_acceptance_helper_requires_proactive_request_and_window` 覆盖了 proactive request 缺失和 pressure 低于 soft threshold 两个失败路径。

### 5. 正确性：suite-local memory policy 是否过度耦合

**验证结果：PASS，无过度耦合。**

`_reactive_compact_smoke_memory_policy(...)` 仅在 `SuiteMode.MEMORY_REACTIVE_COMPACT` 时通过 `dataclasses.replace` 创建本地 policy 副本，收紧 `selected_recent_window_item_cap` 和 `fallback_selected_recent_window_item_cap`。代码有显式边界检查：若 `policy.selected_recent_window_turn_floor` 超过 `_SMOKE_REACTIVE_HISTORY_GAP_ROUNDS + 1`，抛出 `ValueError`。该 policy 不影响其他 suite、不影响生产 Host options，且 assembly test `test_reactive_runtime_assembly_bounds_selected_recent_window` 验证了收紧后的 cap 与 floor 的关系。

### 6. 正确性：fallback pressure 分离

**验证结果：PASS。**

Fallback suite 使用 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS = 160_000`，而 `memory-compact` 使用 `_COMPACT_PRESSURE_RESERVE_TOKENS = 575_000`。两套 pressure padding 函数独立：`_compact_pressure_padding` 用于 `memory-compact`，`_fallback_compact_pressure_padding` 用于 `memory-compact-fallback`。Fallback suite 的压力计算（`_fallback_pressure_observation`）与实际 prompt 生成使用相同的 `_fallback_compact_pressure_padding` 函数，保证观测值与实际值一致。

Assembly test `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 验证了 `memory-compact` pressure 落在 soft 与 hard 之间。Assembly test `test_fallback_acceptance_helper_requires_proactive_request_and_window` 验证了 fallback pressure 低于 soft threshold 时硬失败。

### 7. 正确性：stdout bounded

**验证结果：PASS。**

所有 smoke stdout 输出均以 `SMOKE` 前缀开头：
- `SMOKE ROUND_START`、`SMOKE ROUND_DONE`、`SMOKE FINAL_PREVIEW`：轮次摘要。
- `SMOKE COMPACT_AUDIT`、`SMOKE COMPACT_OPERATION`、`SMOKE COMPACT_REJECT_HISTOGRAM`：compact 审计。
- `SMOKE COMPACT_ACCEPTANCE`：验收信号。
- `SMOKE DETERMINISTIC_DISPATCH`：deterministic dispatch 摘要。
- `SMOKE SOFT_OBSERVE`、`SMOKE SESSION_OBSERVE`：软观测。

不输出完整 pressure blob、不输出 compactor prompt、不输出 provider payload、不输出 per-delta stream 噪声。Assembly test `test_compact_audit_report_prints_operation_histograms_and_manifest_stage` 验证了所有输出行以 `SMOKE ` 开头。

### 8. 正确性：real-provider memory-compact residual 是否合理

**验证结果：PASS。**

Control doc 记录："Real-provider `memory-compact` smoke still depends on a valid compactor provider key and remains a validation residual, not a blocker for deterministic reactive/fallback smoke coverage." 这是已知约束，不阻塞 deterministic suite。新 suite 使用 `DEEPSEEK_API_KEY=test-provider-key`，不需要真实 provider。

### 9. 正确性：README/control doc 是否同步

**验证结果：PASS。**

- `tests/README.md`：更新反映了新增的 `memory-reactive-compact` / `memory-compact-fallback` assembly coverage 和 oracles。
- `docs/host/issues-implementation-control.md`：
  - 表头状态从 `accepted-slice` 更新为 `aggregate-review`。
  - Implementation status 更新为记录 `572a88df` commit 和 aggregate deepreview gate。
  - Next entry point 更新为 aggregate deepreview。
  - WU-CM-15 状态段更新为 `aggregate-review`。
  - Artifacts 列表新增 accepted implementation slice commit。
  - Controller validation 记录完整。

### 10. 架构合规：分层约束

**验证结果：PASS。**

Smoke 脚本通过 Service assembly helper（`compose_open_host_options`、`discover_service_tools`）完成装配，只使用 public Host handle（`open_host`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session`）。Deterministic worker 通过 `dataclasses.replace(options, worker_factory=...)` 注入，未修改 Host public API。Compactor runner 通过 `llm_compaction._run_agent_request` patch 注入，与 `tests/host/test_public_compact_smoke.py` 使用的模式一致。

### 11. 测试覆盖

**验证结果：PASS。**

Assembly tests 20 passed。覆盖：
- SuiteMode 解析边界（`test_cli_bounds_for_suite_and_long_rounds`）。
- Round spec 选择（`test_pure_spec_selection_tool_fact_requirements_and_long20_final_label`）。
- Reactive compact acceptance helper 正面与三个失败路径（`test_reactive_compact_acceptance_helper_requires_reactive_recovery_signals`）。
- Fallback acceptance helper 正面与两个失败路径（`test_fallback_acceptance_helper_requires_proactive_request_and_window`）。
- Compact audit summary、report、histogram、manifest stage（`test_compact_audit_summary_maps_operation_id_to_request_trigger_source`、`test_compact_audit_report_prints_operation_histograms_and_manifest_stage`、`test_compact_audit_report_handles_empty_missing_and_malformed_payloads`）。
- Deterministic proposal marker sanitization（`test_fake_compactor_proposal_does_not_echo_material_markers`）。
- Runtime assembly、tool selection、pressure bounds、session slot（多个 test）。

Pyright 0 errors。

## Open Questions

无。

## Residual Risk

1. **Reactive suite memory policy 依赖 `selected_recent_window_turn_floor`**：若生产 memory policy 的 `selected_recent_window_turn_floor` 增大超过 `_SMOKE_REACTIVE_HISTORY_GAP_ROUNDS + 1`，reactive suite 会在 assembly 阶段抛出 `ValueError` 而非静默失败。这是 fail-closed 设计，非风险。
2. **Deterministic compactor patch 依赖 `llm_compaction._run_agent_request` 内部符号**：若 `dayu.host.llm_compaction` 重构该符号名，smoke 脚本会 fail closed。该依赖与 `tests/host/test_public_compact_smoke.py` 一致，属于 smoke/test 基础设施的已知边界。
3. **Fallback suite pressure 敏感于 configured memory policy caps**：若 context budget policy 的 soft/hard ratio 变化，fallback pressure 可能需要调整 `_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS`。代码有显式 bounds 检查，不会静默跳过覆盖。
