# Code Review — Phase 11 Slice 3 RECOVERING Dispatch

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: `feat/host-phase-11-recovery`
- Base: Slice 2 accepted commit `2e89558`
- Output file: `docs/reviews/phase11-slice3-code-review-ds-20260519.md`
- Included scope: `dayu/host/recovery.py`, `dayu/host/dispatch.py`, `dayu/host/open_host.py`, `dayu/host/durable/run_transition.py`, `tests/host/test_recovery_dispatch.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_open_host_runtime.py`, `dayu/host/README.md`, `tests/README.md`, `docs/host/implementation-control.md`
- Excluded scope: Engine (`dayu/engine/**`), Fins, Service, UI — no changes.
- Parallel review coverage: 无 — 单一 reviewer 覆盖全部链路。

## Review Method Summary

review 从以下关键真实入口逐行走读：
1. `open_host.__aenter__` → `StartupRecoveryScanner.scan()` 集成链（`dayu/host/open_host.py:461-466`）
2. `StartupRecoveryScanner._classify_run` → `_classify_recovering` / `_classify_active_or_cancelling` 分类与 dispatch 链路（`dayu/host/recovery.py:203-522`）
3. `start_recovery_run_with_starting_attempt_in_transaction` 事务内 CAS 链（`dayu/host/durable/run_transition.py:1452-1531`）
4. `_recovery_run_started_event_request` payload 构造与 compact event ref 可选化（`dayu/host/durable/run_transition.py:3087-3126`）
5. `_validate_start_recovery_input` 对 optional compact event refs 的验证收紧（`dayu/host/durable/run_transition.py:5221-5252`）
6. Slice 2 tracked item `lose_recovering_run_in_transaction` 前置条件审议（`dayu/host/durable/run_transition.py:1391-1449`）
7. `HostDispatchScheduler.host_instance_id` 暴露（`dayu/host/dispatch.py:604-611`）
8. `RunInputBuilder` recovery 路径测试（`tests/host/test_run_input_builder.py:229-251`）
9. old execution rejection 测试（`tests/host/test_recovery_dispatch.py:189-213`）
10. public `open_host` recovery + `watch_session_events` 集成测试（`tests/host/test_open_host_runtime.py:392-429`）

## Findings

### 1-未修复-低-RECOVERING dispatch CAS 失败时 orphan closeout 已部分写入同事务

- **入口/函数**: `_close_positive_orphan` → `_start_recovery_dispatch_or_ready` (同一 write transaction)
- **文件(行号)**: `dayu/host/recovery.py:405-457`
- **输入场景**: orphan closeout（`close_startup_orphan_attempt_in_transaction`）在同一事务内成功将 RUNNING 转为 RECOVERING 后，`start_recovery_run_with_starting_attempt_in_transaction` 的 CAS 因 Session 级 active-run 约束（`start_recovering_run_row` 的 `NOT EXISTS` 子查询）或其他 CAS 条件失败。
- **实际分支**: `start_recovery_run_with_starting_attempt_in_transaction` 返回 `INVALID_STATE` → `_require_run_mutation_updated` 不触发（CAS 失败在 helper 内部直接返回，未经过 `_require_run_mutation_updated`）→ `_action_from_mutation` 将 `INVALID_STATE` 映射为 `StartupRecoveryDecision.INVALID_STATE` decision → 事务正常提交，orphan closeout 生效。
- **预期行为**: 事务提交后 Run 处于 RECOVERING 状态，但 scan action 报告 `INVALID_STATE`，与原义"无法创建 recovery dispatch"不完全匹配（orphan closeout 本身成功）。
- **直接证据**: `dayu/host/recovery.py:435-441` (orphan closeout 事务内已完成)、`dayu/host/recovery.py:504-516` (`_action_from_mutation` 将 `INVALID_STATE` 映射为 `INVALID_STATE` decision，丢失"closeout 已成功"的区分信号)。
- **影响**: 仅可观测性影响。Run 安全留在 RECOVERING 状态，下次 startup scan 会重新分类并尝试 dispatch。没有状态损坏、数据丢失或错误的 LOST 收口。
- **建议改法和验证点**: 可在 `_close_positive_orphan` 返回 action 时，若 orphan closeout 已成功但 dispatch 未成功，优先使用 closeout 的 decision（`RECOVERING_READY` 或类似）而非 dispatch 的 `INVALID_STATE`。当前行为不构成正确性缺陷，可 deferred。
- **修复风险（低）**:
- **严重程度（低）**:

### 2-未修复-低-Slice 2 tracked 项 lose_recovering_run_in_transaction 前置条件充分

- **入口/函数**: `lose_recovering_run_in_transaction`
- **文件(行号)**: `dayu/host/durable/run_transition.py:1391-1449`
- **输入场景**: RECOVERING Run 的 recovery dispatch count 已达上限，scanner 调用 `lose_recovering_run_in_transaction` 将其收口为 LOST。
- **实际分支**: CAS 检查 `run.status == RECOVERING` 且 `run.current_attempt_id == request.source_attempt_id`（行 1415-1419）。
- **预期行为**: 仅当 Run 确为 RECOVERING 且 current_attempt_id 与调用方提供的 source_attempt_id 匹配时，才允许执行 `terminal_recovering_run_lost_row` 转为 LOST。
- **直接证据**: 行 1415-1419 的 CAS 条件。该函数不修改 dispatch record，只将 Run 终态化。因 `source_attempt_id` 来自 `run.current_attempt_id`（在 `_classify_recovering` 行 278-279 传入），CAS 确保 Run 在执行 `terminal_recovering_run_lost_row` 前未被其他事务修改。
- **影响**: 该 CAS 对 `lose_recovering_run_in_transaction` 的语义（将不再可恢复的 RECOVERING Run 终态化）已足够。无需额外检查 dispatch record ownership，因为 dispatch record 在此操作中不被修改，且被 lost 的 Run 的 current_attempt_id 已充分标识旧 source attempt。
- **建议改法和验证点**: 无需修改。当前 CAS 条件与函数契约匹配。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

无。

## Residual Risk

1. **RECOVERING cancel 尚未实现（Slice 4）**：当前 RECOVERING Run 在 scan 中只能 dispatch（under limit）或 lose（at/over limit），无法通过 public `cancel_run` / `cancel_session_runs` 取消。这符合 Slice 3 scope，但完整 recovery 语义需 Slice 4 补齐。
2. **多进程并发 scan 测试覆盖**：当前 Slice 3 测试为单进程，两个 opener 同时扫描同一 DB 的并发场景由 Slice 5 覆盖。当前 CAS 设计理论上安全（SQLite write transaction 串行化），但缺乏多进程直接证据。
3. **Recovery dispatch 失败后的 LOST 收口**：若某 RECOVERING Run 已创建 recovery dispatch 但该 dispatch 执行失败（如 worker crash），下次 startup scan 会计入一个已 committed recovery dispatch，导致 count >= limit 从而转换为 LOST。这符合"每个 Run 最多一次 automatic startup recovery dispatch"的设计，但如果希望 retry 语义，需要后续 phase 处理。
4. **WorkerKind 硬编码为 LOCAL**：`_start_recovery_dispatch_or_ready` 行 504 硬编码 `worker_kind=WorkerKind.LOCAL`。若原始 Run 使用 remote worker，recovery 仍以 LOCAL 派发。这符合 Phase 11 不支持 remote recovery 的 non-goal 声明（plan line 29-31），但需注意 remote worker 场景下 recovery 行为可能不完整。

## Verification Against Plan Requirements

| 计划要求 | 验证结果 |
|---------|---------|
| RECOVERING dispatch 创建新 Attempt/execution/dispatch 在同一事务 | 通过 — `start_recovery_run_with_starting_attempt_in_transaction` 在一个 write transaction 内完成 EventLog append + Run CAS + Attempt insert + dispatch insert |
| commit 后唤醒 scheduler | 通过 — `scan()` 行 197-200 在 `run_write` 返回后调用 `wake_dispatch` |
| Recovery 不调用 WorkerProxy | 通过 — scanner 只创建 PENDING dispatch record，由 scheduler 正常 dispatch 路径处理 |
| `open_host` ready 前执行 scan | 通过 — `open_host.py` 行 461-466，scan 在 `host.open.ready` 日志前执行 |
| RunInputBuilder 使用 canonical EventLog/payload descriptors | 通过 — `test_recovery_attempt_rebuilds_current_prompt_from_same_run_eventlog_descriptor` 验证了 payload mutation 后仍从 durable descriptor 重建 |
| old execution late event 被拒绝 | 通过 — `test_late_old_execution_event_after_recovery_dispatch_is_rejected` 验证旧 execution_id 的 terminal event 被 EngineEventIngestor 拒绝 |
| 无 RECOVERING cancel | 通过 — 代码中未实现 RECOVERING cancel 路径 |
| 无 Engine 修改 | 通过 — 无 `dayu/engine/**` 变更 |
| 无 public API 变更 | 通过 — `open_host` 签名与 P10.5 一致，无新增 public methods |
| 无 schema 变更 | 通过 — recovery dispatch count 基于 EventLog 计数，未新增表或列 |
| docs 更新 | 通过 — `dayu/host/README.md` 更新 recovery 语义与 startup scan，`tests/README.md` 更新测试覆盖描述 |
| pyright 0 errors | 通过 — implementation artifact 报告 `0 errors, 0 warnings, 0 informations`；Controller 复跑确认 |
| tests 通过 | 通过 — implementation artifact 报告 39 passed；Controller 复跑确认 |

## Conclusion

**PASS — blocking count = 0**

Phase 11 Slice 3 实现正确完成了 RECOVERING dispatch 的核心语义：startup recovery scan 在 positive orphan proof 成立的 RUNNING Run 上收口旧 Attempt 后，在同一事务内创建新的 recovery Attempt / execution / dispatch record，事务提交后唤醒 scheduler。无 Engine 修改、无 public API 变更、无 schema 变更。RunInputBuilder 从同一 Run 的 canonical EventLog payload descriptor 重建 messages（非旧 Attempt snapshot、非 projection/memory）。old execution_id 的 late terminal event 正确被 EngineEventIngestor 拒绝。Slice 2 tracked 项 `lose_recovering_run_in_transition` 的 CAS 前置条件对终态化 RECOVERING Run 已充分。测试覆盖了 recovery dispatch 创建、late event 拒绝、descriptor 重建与 public watch 集成路径。剩余风险为 RECOVERING cancel（Slice 4）和多进程并发（Slice 5），均在 scope 外且已 deferred 到对应 slice。
