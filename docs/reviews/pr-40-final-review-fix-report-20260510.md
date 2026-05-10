# PR #40 Final Review Fix Report

## Scope

- PR: #40 — Host P8 durable attempt governance
- Branch: `migration/host-p8-attempt-lease-recovery`
- Fix date: 2026-05-10
- Review sources:
  - `docs/reviews/pr-40-review-20260510-2044.md` (6 findings)
  - `docs/reviews/pr-40-review-20260510-2051.md` (5 findings + 4 test findings)

## Summary

13 accepted findings fixed (11 code fixes + 3 coverage tests). All findings marked as 已修复 in review artifacts.

## Fixes

### Correctness Bugs (F1-F6 from 2044 review)

| ID | Severity | Description | Files Changed |
|----|----------|-------------|---------------|
| F1 | 高 | `_append_worker_failure_if_needed` scope 调用问题 | `_run_harness.py`, `test_phase8_attempt_supervisor.py` |
| F2 | 中 | `RECOVERING` 死状态删除 | `_internal_contracts.py`, `_run_state_store.py`, `README.md`, `design.md` |
| F3 | 中 | `_handle_owner_lost` 非 fencing 异常时未关闭 lease_exit_stack | `_run_harness.py`, `test_phase8_attempt_supervisor.py` |
| F4 | 中 | `_fetch_more` cursor 内存变更先于 EventLog fact（root-cause: pure build + deferred commit） | `_tool_runtime.py`, `test_phase8_tool_runtime_fencing.py` |
| F5 | 低 | terminal state set 混用 | `_run_state_store.py`, `test_phase8_attempt_fencing.py` |
| F6 | 低 | diagnostic close 返回值日志 | `_run_harness.py` |

### Low-risk Fixes (F1-F5 from 2051 review)

| ID | Severity | Description | Files Changed |
|----|----------|-------------|---------------|
| F1 | 低 | lease_context session 注册泄漏 | `_attempt_supervisor.py`, `test_phase8_attempt_supervisor.py` |
| F2 | 低 | `_verify_run_id_matches` 硬编码 current_state | `_attempt_supervisor.py` |
| F3 | 低 | 零事件 observer IDLE -> CAUGHT_UP | `_event_observer.py`, `test_phase6_projection_checkpoint.py` |
| F4 | 低 | lastrowid or 0 掩盖异常 | `_durable_event_store.py` |
| F5 | 信息 | RECOVERING 死状态 (同 2044-F2) | (covered above) |

### Coverage Tests (T2-T4 from 2051 review)

| ID | Description | Test File |
|----|-------------|-----------|
| T2 | `recover_stale_attempts(run_id=None)` 全库扫描 | `test_phase8_attempt_recovery.py` |
| T3 | truncation strategy/value 类型不匹配 | `test_phase2_tool_runtime_truncation.py` |
| T4 | `terminal_state_override` 参数覆盖 | `test_phase8_attempt_fencing.py` |

### F4 Root-Cause Fix Detail: `_fetch_more` cursor memory mutation

**根因**: 原实现 `_store_cursor_from_record` → `_create_cursor` 在 EventLog append 之前立即写入 `_records_by_cursor` / `_cursor_by_fingerprint` 内存 maps。"先写 map、except 里 remove" 不是 root-cause fix。

**修复**: 拆为纯构建 + 延迟提交：
- `_build_cursor_creation(...)`: 纯函数，生成 cursor token / fingerprint / scope / record / issued_event，不写 maps
- `_commit_cursor_creation(creation)`: 仅将 `_CursorCreation` 写入两个 maps
- `_fetch_more` 新流程: pure build → append COMPLETED → append ISSUED → remove old + commit new

**fencing 时状态**:
- `_append_fetch_completed` 失败: old cursor 仍可 fetch，next cursor 不存在，EventLog 无 completed/issued 事实
- `_append_cursor_issued` 失败: old cursor 仍可 fetch，next cursor 不存在，EventLog 有 COMPLETED 但无 ISSUED（partial fact，EventLog 架构限制）
- 全部成功: old cursor 移除，next cursor 注册，EventLog 有 COMPLETED + ISSUED

**Residual risk**: EventLog multi-fact append 非原子，COMPLETED 成功 + ISSUED 失败时存在 partial fact。此为 EventLog 架构层面限制。

**Tests**: `test_fetch_more_completed_fencing_preserves_old_cursor`, `test_fetch_more_issued_fencing_preserves_old_cursor`, `test_fetch_more_success_path_old_removed_next_registered`

### ToolRuntime Naming Cleanup: `InMemoryToolRuntime` → `HostToolRuntime`

**依据**: `docs/reviews/pr-40-tool-runtime-durability-investigation-20260510.md` 调查结论 + Controller decision 采纳方案 A。

**改动范围**:
- `dayu/host/_tool_runtime.py`: 类名 + docstring（显式说明 cursor registry 是 transient state）
- `dayu/host/_durable_harness.py`: import + usage
- `dayu/host/_run_harness.py`: import + type hint + docstring
- `dayu/host/README.md`: 术语刷新
- `tests/README.md`: 术语刷新
- `docs/host/design.md`: 执行路径图
- 8 个测试文件 + 2 个 utils smoke 脚本

**未保留兼容 alias / wrapper / re-export**。行为不变。

## Verification

- `pytest tests/host -q`: all pass (343 passed)
- `pyright`: 0 errors on all modified files
- `python utils/smoke_host_p8_attempt_lease.py`: all steps pass
- `git diff --check`: clean
- Review artifacts updated: all 13 findings marked 已修复
