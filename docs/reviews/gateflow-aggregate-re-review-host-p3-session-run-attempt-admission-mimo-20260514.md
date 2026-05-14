# Aggregate Re-Review: Host Phase 3 Session / Run / Attempt Admission (AgentMiMo)

- **Reviewer**: AgentMiMo (mimo-v2.5-pro)
- **Date**: 2026-05-14
- **Type**: Aggregate re-review (fix verification)
- **Base accepted slice HEAD**: `49fc1d5`
- **Branch**: `feat/host-phase3-admission-state-machine`

## Controller Accepted Fixes

| ID | Description | File |
|----|-------------|------|
| N-1 | `_require_event_sequence` SQL 改用 `TABLE_EVENT_LOG` 常量 | `dayu/host/admission.py` |
| N-2 | `terminal_run_row` docstring 说明 `WAITING` 是后续 phase 预留 | `dayu/host/durable/state.py` |

## Fix Verification

### N-1: `_require_event_sequence` 使用 `TABLE_EVENT_LOG` 常量

- **Status**: FIXED
- **Evidence**: `admission.py:52` 导入 `from dayu.host.durable.schema import TABLE_EVENT_LOG`；`admission.py:1660` SQL 改为 `f"SELECT event_sequence FROM {TABLE_EVENT_LOG} WHERE event_id = ?"`。
- **Behavior impact**: 无。当前 `TABLE_EVENT_LOG` 值仍为 `"event_log"`，运行时行为不变。
- **Import boundary**: `dayu.host.durable.schema` 是 durable schema convention 真源，只依赖 durable error，不引入反向依赖或循环依赖。
- **Scope**: 未改变状态机行为、schema、CAS 条件或 EventLog 语义。

### N-2: `terminal_run_row` docstring 补充 Phase 3 边界说明

- **Status**: FIXED
- **Evidence**: `state.py:1483-1484` docstring 新增："``WAITING`` 源状态是为后续 phase 的 wait resolve 路径预留；Phase 3 调用方通过前置检查保证只会传入 ``RUNNING`` Run。"
- **Behavior impact**: 无逻辑变化，仅文档补充。
- **Scope**: 未改变状态机行为、schema、CAS 条件或 EventLog 语义。

## Fix Scope Control Check

| Check | Result |
|-------|--------|
| 状态机行为变更 | 无 |
| Schema / DDL 变更 | 无 |
| CAS 条件变更 | 无 |
| EventLog 语义变更 | 无 |
| Phase 3 scope 扩大 | 无 |
| 新增 import boundary 问题 | 无 |
| 新增循环依赖 | 无 |
| 新增弱类型 | 无 |
| README 触发未同步 | 无（fix 未触及 README 职责范围内的变更） |

## Verification (post-fix)

| Check | Result |
|-------|--------|
| `pytest tests/host -q` | 157 passed in 2.18s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean (exit 0) |

## New Blocking Findings

**无新 blocking finding。**

## Conclusion

Controller accepted 的两个 non-blocking findings 均已完全修复：

- **N-1**: FIXED — `_require_event_sequence` 改用 `TABLE_EVENT_LOG` 常量，import 边界正确，无行为变化。
- **N-2**: FIXED — `terminal_run_row` docstring 明确 `WAITING` 是 forward-looking 预留，无逻辑变化。

Fix 未引入新的状态机行为变更、schema 变更、CAS 条件变更、EventLog 语义变更或 Phase 3 scope 扩大。无新 import boundary、循环依赖、弱类型或文档同步问题。

**Accepted. No blocking findings.**
