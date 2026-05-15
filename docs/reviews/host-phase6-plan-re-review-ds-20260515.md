# Host Phase 6 Plan Re-Review - AgentDS - 2026-05-15

- **reviewer**: AgentDS (role-scoped plan re-review)
- **re-reviewed target**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` (after plan fix)
- **original review**: `docs/reviews/host-phase6-plan-review-ds-20260515.md`
- **controller adjudication**: `docs/reviews/host-phase6-plan-review-controller-adjudication-20260515.md`
- **current gate**: Phase 6 plan re-review
- **verdict**: PASS

## 复核范围

仅复核 controller accepted findings（DS-F1 至 DS-F4、MIMO-F1 至 F3、DS-F5 至 DS-F10）的修复状态。MIMO-F4 无需修复，不在复核范围。

复核亦检查是否引入新的 blocking finding。

## Accepted Blocking Findings 修复状态

### DS-F1 — fixed

- **修复位置**: §3.3.1, §6 P6-S1 exact changes, §7 Testing Matrix
- **证据**:
  - §3.3.1 明确 `PolicySnapshot.__post_init__` "must only validate policy reference consistency and typed field coherence; it must not unconditionally reject `allow_tool_calls=True`"。
  - §3.3.1 明确 `_validate_no_tool_snapshot` 拆分为条件校验：no-tool 校验仅对 `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED` 执行，tool-enabled 校验仅对 `TOOL_ENABLED` 执行。
  - §6 P6-S1 exact changes 显式列出 "Split `PolicySnapshot.__post_init__` from no-tool enforcement" 和 "Split or conditionalize `_validate_no_tool_snapshot`"。
  - §7 Unit tests 覆盖 `PolicySnapshot(allow_tool_calls=True)` 对 `TOOL_ENABLED` 构造成功、no-tool 校验对 replay/no-tool scope 仍拒绝 tool-enabled snapshot。
  - §6 P6-S1 tests 覆盖 `PolicySnapshot(allow_tool_calls=True)` constructs successfully。

### DS-F2 — fixed

- **修复位置**: §3.3.1, §6 P6-S1 exact changes, §7 Testing Matrix
- **证据**:
  - §3.3.1 明确 `DefaultSceneParameterProvider` "must derive system-message tool status from `ToolExecutionMode` plus policy / tool snapshot. It must not output `tools=disabled` for `TOOL_ENABLED`"。
  - §6 P6-S1 exact changes 显式列出 "Update `DefaultSceneParameterProvider` so system messages reflect mode/policy"。
  - §7 Unit tests 覆盖 "tool-enabled scene/system messages do not contain `tools=disabled`"。
  - §6 P6-S1 tests 覆盖 "Tool-enabled scene/system messages do not contain `tools=disabled`"。

### DS-F3 — fixed

- **修复位置**: §3.3.1 (新增 Tool Execution Mode / RunInputBuilder Boundary), §6 P6-S1 exact changes
- **证据**:
  - 新增 §3.3.1 定义 `ToolExecutionMode` typed enum 含 `TOOL_ENABLED`、`NO_TOOL_REPLAY`、`NO_TOOL_DISABLED`。
  - 明确决策机制：在 Host dispatch / RunInputBuilder construction 边界显式传入。
  - 覆盖 `AttemptDispatchSnapshot` 是否携带 mode 的两种实现路径，均明确为 approved contract change 或 dispatch-local 参数。
  - §6 P6-S1 exact changes 显式列出 "Add `ToolExecutionMode` or equivalent typed enum" 和 dispatch 路径要求。

### DS-F4 — fixed

- **修复位置**: §4.3.1 (新增 EngineEvent Tool Events Are Preview / Diagnostic), §6 P6-S2 exact changes, §7 Testing Matrix
- **证据**:
  - 新增 §4.3.1 显式列举 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE`、`TOOL_CALL_DELTA` 等 EngineEvent 工具事件必须保持 preview/diagnostic。
  - 明确 "EngineEvent ingest must not become a canonical tool fact writer in Phase 6"。
  - 明确 "The only canonical owner for `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED` and `TOOL_RESULT_ACCEPTED` is `ToolRuntime -> HostToolFactAcceptPort`"。
  - §6 P6-S2 exact changes 显式列出 "Keep EngineEvent tool mappings diagnostic / preview only" 和降级要求。
  - §7 Unit tests 覆盖 "EngineEvent tool mappings remain preview / diagnostic and cannot append canonical tool facts"。
  - §6 P6-S2 tests 覆盖 EngineEvent ingest 不能 bypass accept path。

## Accepted Non-Blocking Findings 修复状态

### MIMO-F1 — fixed

- **修复位置**: §4.2, §10
- **证据**: §4.2 明确 "Current EventLog `append_event` does not perform global closed-set validation for `event_type`; P6 normally does not need a schema version bump"。§10 working assumption 同步确认。

### MIMO-F2 / DS-F9 — fixed

- **修复位置**: §7 Testing Matrix unit + integration, §6 P6-S3 tests
- **证据**: §7 Unit tests 覆盖 "batch execution with one accept failure does not roll back other already accepted calls in the same batch"。Integration tests 覆盖 "mixed batch accept outcomes return accepted call results and governed errors for failed accepts without EventLog rollback"。§6 P6-S3 tests 覆盖对应场景。

### MIMO-F3 — fixed

- **修复位置**: §3.4 step 5, §3.5, §3.9, §6 P6-S3 exact changes, §7 Testing Matrix
- **证据**: §3.4 step 5 明确映射为 `ToolFailedOutcome` + `governed_error` policy decision + `unsupported_awaiting` reason。§3.5 明确 `awaiting` 只能进入 canonical `governed_error`。§3.9 同步。§6 P6-S3 exact changes 显式列出。

### DS-F5 — fixed

- **修复位置**: §5.2 P6-S3 test files
- **证据**: 明确 "Prefer no change to `tests/host/test_phase5_local_execution_integration.py`; only touch it if an assertion explicitly names Phase 5 no-tool internals that P6 removes. Add new Phase 6 integration tests instead of migrating broad Phase 5 coverage."

### DS-F6 — fixed

- **修复位置**: §3.6, §6 P6-S4 exact changes, §7 Testing Matrix
- **证据**: §3.6 明确 `TruncationManager` construction must receive `truncate_specs_by_name` from `EffectiveToolBundle.truncate_specs_by_name`。§6 P6-S4 exact changes 显式列出 "Initialize `TruncationManager` from `EffectiveToolBundle.truncate_specs_by_name`"。§7 Unit tests 覆盖。

### DS-F7 — fixed

- **修复位置**: §6 P6-S3 exact changes
- **证据**: 显式列出 "Inject `PassThroughDuplicateGovernance` always-allow stub for P6-S3; P6-S5 replaces it with the full duplicate matrix."

### DS-F8 — fixed

- **修复位置**: §3.5, §7 Testing Matrix
- **证据**: 新增按 `ToolFactKind` 的必填字段/受限字段表（覆盖 `completed`、`failed`、`cancelled`、`reuse`、`governed_error` 五种 kind）。明确 `__post_init__` 必须校验必填字段。§7 Unit tests 覆盖。

### DS-F10 — fixed

- **修复位置**: §3.7, §6 P6-S5 exact changes, §7 Testing Matrix
- **证据**: §3.7 明确 "`index_in_iteration` is explicitly excluded from the duplicate key"。§6 P6-S5 exact changes 显式列出 "Compute duplicate key without `index_in_iteration`"。§7 Unit tests 覆盖。

## 新增 Finding 检查

未发现新的 blocking finding。plan fix 引入的新内容（§3.3.1 `ToolExecutionMode`、§4.3.1 EngineEvent preview/diagnostic、§3.5 candidate 校验表）均为 controller 要求的修复，范围受控，未引入新矛盾或缺口。

## Conclusion

- **verdict**: PASS
- **finding count**: 0（所有 accepted findings 已修复，无新增 finding）
- **blocking count**: 0
- **artifact path**: `docs/reviews/host-phase6-plan-re-review-ds-20260515.md`

## Verification

```bash
git diff --check docs/host/phase6-toolruntime-truncation-fetch-more-plan.md
```
结果: 无 whitespace 错误。
