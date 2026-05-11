# P8.5 Slice 2 Code Review

## Gate / Target

- Review gate name: `code review`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 2 — Durable Memory Repair Stabilization
- Approved plan path: `docs/host/phase8.5-plan.md`
- Implementation artifact: `docs/host/phase8.5-s2-implementation-report.md`
- Baseline: accepted Slice 1 commit `20617f6`
- Reviewed diff scope:
  - `dayu/host/_conversation_memory_durable.py`
  - `dayu/host/_durable_event_store.py`
  - `dayu/host/_durable_harness.py`
  - `tests/host/test_phase8_durable_memory_recovery.py`
  - `dayu/host/README.md`
  - `docs/host/phase8.5-s2-implementation-report.md`

## Reviewer Conclusion

fail

Slice 2 的主路径实现与计划大体一致：typed repair report / diagnostic 已加入，缺失 snapshot row 会按 EventLog terminal canonical facts 自动重建，已有坏 row 不会被覆盖，repair 会记录 WARNING 并继续其它 session；`startup_reconcile()` 暴露 report；EventLog helper SQL shape 与索引符合计划；指定 pyright 与测试均通过。未发现本 slice 引入 ToolRuntime Event Model 变更或旧库兼容承诺。

但 corrupt snapshot row 的诊断覆盖范围不完整：当前 repair 只检查 EventLog 中已有 canonical event 的 session，无法诊断 snapshot 表中已存在但没有 canonical EventLog 候选的坏 row。这个场景可由现有 `MemoryResetPatch` / `ScopeClearPatch(SESSION)` 写入空 snapshot row 后被运维或存储损坏触发，且会导致 `get_snapshot()` 继续抛错，但 `startup_reconcile()` 返回空 diagnostics。

## Findings

### 1-未修复-[中]-corrupt snapshot row 诊断只覆盖 EventLog canonical session，漏掉 snapshot-only 坏行

- **入口/函数**: `DurableHarnessBundle.startup_reconcile()` -> `DurableConversationMemoryStore.repair_missing_session_snapshots()` -> `_repair_missing_session_snapshots_locked()`
- **文件(行号)**: `dayu/host/_conversation_memory_durable.py:365`, `dayu/host/_conversation_memory_durable.py:371`, `dayu/host/_conversation_memory_durable.py:440`, `dayu/host/_conversation_memory_durable.py:457`, `dayu/host/_conversation_memory_durable.py:488`, `dayu/host/_conversation_memory_durable.py:500`, `dayu/host/_conversation_memory_durable.py:518`
- **输入场景**: 某 session 已有 snapshot row，但 EventLog 中没有该 session 的 canonical event；例如 `MemoryResetPatch` 先写入 intentional empty snapshot row，随后该 row 的 `snapshot_payload` 被运维误操作或存储损坏改成非法 JSON。
- **实际分支**: `_repair_missing_session_snapshots_locked()` 只遍历 `_collect_repair_candidate_session_ids_after()` 返回的 `session_ids`；该 helper 的 SQL 只从 `host_run_events` 读取 `e.kind = CANONICAL` 的 distinct `session_id`。snapshot-only session 不会进入循环，因此 `_inspect_snapshot_row()` 不会被调用。
- **预期行为**: approved plan Slice 2 要求 “snapshot row 存在但 payload corrupt / schema mismatch / type invalid：不覆盖，返回 typed diagnostic，记录 WARNING，继续其它 session repair”。该要求没有把 corrupt row 限定为 EventLog 中已有 canonical facts 的 session。
- **实际行为**: repair 返回 `MemoryRepairReport(repaired_session_ids=(), diagnostics=())`，没有 WARNING；坏 row 保留，后续 `get_snapshot(session_id)` 仍会抛 `ValueError`。
- **直接证据**:
  - 候选集只来自 EventLog canonical session：`_collect_repair_candidate_session_ids_after()` 在 `dayu/host/_conversation_memory_durable.py:457-486` 执行 `SELECT DISTINCT e.session_id ... FROM host_run_events AS e WHERE e.kind = ? ...`。
  - 坏 row 检查只对候选 session 执行：`dayu/host/_conversation_memory_durable.py:371-376` 调用 `_inspect_snapshot_row()` 并记录 diagnostic。
  - `_inspect_snapshot_row()` 本身能识别坏 payload：`dayu/host/_conversation_memory_durable.py:500-536` 查询 snapshot row，解码失败时构造 `CORRUPT_SNAPSHOT`。
  - 复现命令使用临时 SQLite：先 `MemoryResetPatch(session_id="orphan_session")` 写入 snapshot row，再把 payload 改成 `{bad-json`，随后 `await bundle.startup_reconcile()` 输出 `MemoryRepairReport(repaired_session_ids=(), diagnostics=())`。
- **影响**: 运维 / 存储导致的 corrupt snapshot row 可能在启动 repair 中静默漏报，违反 Slice 2 “typed diagnostic + WARNING” 的可观测性目标；坏 row 不会被覆盖是正确的，但 caller 无法从 startup report 知道该 session 需要人工处理。
- **建议改法和验证点**:
  - repair 的候选扫描应覆盖 snapshot 表中已有 row 的 corrupt 检查。可选方案是新增一个按 `session_id` 分页扫描 `host_conversation_memory_snapshots` 的 helper，只做 `_inspect_snapshot_row()` 与 diagnostic，不触发重建；缺失 row rebuild 仍使用 EventLog canonical candidate scan。
  - 或构造统一候选流：EventLog canonical session 用于 missing-row rebuild，snapshot table session 用于 corrupt-row diagnostic，二者都分页并去重。
  - 补测试：创建无 canonical EventLog 的 snapshot row（可通过 `MemoryResetPatch`），破坏 `snapshot_payload`，调用 `startup_reconcile()`，断言返回一个 `CORRUPT_SNAPSHOT` diagnostic、记录 WARNING、原 row 不被覆盖。
  - 保持 no old DB compatibility promise：不要写旧 schema 兼容 reader / migration；schema mismatch 仍只作为 corrupt diagnostic。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Plan Compliance Notes

- typed repair report / diagnostic：已实现 `MemoryRepairReport`、`MemoryRepairDiagnostic`、`MemoryRepairDiagnosticKind.CORRUPT_SNAPSHOT`。
- missing snapshot row auto-rebuild：已保留，且事务内二次确认 row 是否仍缺失，避免覆盖并发写入。
- corrupt snapshot row no-overwrite + diagnostic + WARNING + continue：对 EventLog canonical candidate session 成立；见 Finding 1，snapshot-only 坏行漏诊断。
- startup exposure/logging：`DurableHarnessBundle.startup_reconcile()` 返回 `MemoryRepairReport | None`，repair 对 diagnostic 逐条 WARNING。
- paged/batched scan：session 候选按 `session_id` 分页；单 session canonical events 通过 `fetch_events_for_session_by_position()` 分页读取。
- durable event helper SQL shape and index：helper SQL 使用 `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`；新增索引 `idx_host_run_events_session_kind_position` on `(session_id, kind, event_position)`。
- transaction boundaries / race behavior：missing-row rebuild 在写入事务内只做 row-exists 二次确认，不覆盖并发产生的 row；重复投影同一 run 的 raw turn / tool fact 由 turn id / fact id 去重降低后续 drain 重放风险。
- ToolRuntime Event Model：reviewed diff scope 未修改 ToolRuntime event model。
- old DB compatibility：未发现兼容 reader、migration 或旧 schema promise。

## Tests / Docs Alignment

- 新增测试覆盖 corrupt row 不覆盖、WARNING、继续修复其它缺失 session，以及 `startup_reconcile()` report 暴露。
- 测试缺口：未覆盖 Finding 1 的 snapshot-only corrupt row。
- Host README 已同步 repair report 与 corrupt row 行为；但在 Finding 1 修复前，README 中 “snapshot row 已存在但 payload 损坏、schema 不匹配或类型非法时，repair 不覆盖该 row，而是返回 CORRUPT_SNAPSHOT 诊断并记录 WARNING” 的描述比当前实现更宽。

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_durable_memory_recovery.py -q`
  - Result: passed, `16 passed in 0.23s`.
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - Result: passed, `4 passed in 1.72s`.

## Open Questions And Residual Risk

- Finding 1 requires controller decision: `pending-controller-decision`.
- Existing implementation report tracks corrupt row root cause / quarantine / operator command / overwrite policy under issue #41; this review does not expand that scope.
- No additional ToolRuntime / EventLog model residual risk was found in this slice diff.

## Artifact

- Artifact path: `docs/host/phase8.5-s2-code-review.md`
