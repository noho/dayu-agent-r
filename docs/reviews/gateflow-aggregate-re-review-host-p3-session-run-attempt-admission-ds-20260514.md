# Aggregate Re-review: Host Phase 3 Session / Run / Attempt Admission (AgentDS)

- **Reviewer**: AgentDS (deepseek-v4-pro)
- **Date**: 2026-05-14
- **Scope**: Aggregate fix re-review — 验证 fix artifact 中 N-1 / N-2 的修复完整性、无副作用、无新增 finding
- **Base accepted slice HEAD**: `49fc1d5`
- **Fix HEAD**: working tree (uncommitted)
- **Input artifacts**:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-ds-20260514.md` (AgentDS original review, 2 non-blocking findings)
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-mimo-20260514.md` (AgentMiMo review, 0 non-blocking findings)
  - `docs/reviews/gateflow-aggregate-fix-host-p3-session-run-attempt-admission-20260514.md` (Controller accepted fixes)

## Verification

| Check | Result |
|-------|--------|
| `pytest tests/host -q` | 157 passed in 1.91s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean (exit 0) |

## Fix Completeness

### N-1. `_require_event_sequence` 使用 `TABLE_EVENT_LOG` 常量

- **Status**: FIXED
- **Change**: `admission.py:52` 新增 `from dayu.host.durable.schema import TABLE_EVENT_LOG`；`admission.py:1660` 将 `"SELECT event_sequence FROM event_log WHERE event_id = ?"` 替换为 `f"SELECT event_sequence FROM {TABLE_EVENT_LOG} WHERE event_id = ?"`。
- **Verification**:
  - `TABLE_EVENT_LOG` 定义在 `dayu/host/durable/schema.py:17`，值为 `"event_log"`——与硬编码字符串相同，无行为变化。
  - 导入位置在 idempotency 导入块与 run_transition 导入块之间，与现有 `dayu.host.durable.*` 导入逻辑一致。
  - f-string 参数 `TABLE_EVENT_LOG` 是模块级常量，非用户输入，无 SQL 注入风险。
  - `schema.py` 仅依赖 stdlib，无循环依赖风险。
- **Coverage**: 完全覆盖 accepted finding。不再有硬编码 `"event_log"` 字符串。

### N-2. `terminal_run_row` docstring 补充 Phase 3 边界说明

- **Status**: FIXED
- **Change**: `state.py:1483-1484` 在 `terminal_run_row` docstring 中新增两行中文说明：``WAITING`` 源状态是为后续 phase 的 wait resolve 路径预留；Phase 3 调用方通过前置检查保证只会传入 ``RUNNING`` Run。
- **Verification**:
  - docstring 描述与代码事实一致：`run_transition.py:1470` 的 `_invalid_terminal_precondition` 要求 `run.status == RunStatus.RUNNING`，因此 Phase 3 中 `WAITING` 源状态不可达。
  - CAS WHERE clause 未修改——`status IN ('running','waiting')` 保持不变，`WAITING` 路径仍为 Phase 7 forward-looking 预留。
  - docstring 使用中文，与项目约定一致，与模块内其他 docstring 风格一致。
- **Coverage**: 完全覆盖 accepted finding。不再有"未说明 forward-looking 意图"的文档不足。

## No-Regression Checks

### 状态机行为

- `terminal_run_row` 的 CAS WHERE clause 未修改：`status IN (?, ?)` 参数仍为 `RUNNING` 和 `WAITING`。
- `_invalid_terminal_precondition` 未修改：仍拒绝非 `RUNNING` Run。
- 所有 transition helper 逻辑未修改。
- **结论**: 状态机行为零变化。

### Schema

- 无 DDL 修改。
- 无 CHECK constraint 修改。
- 无 index 修改。
- **结论**: Schema 零变化。

### CAS 条件

- 无 CAS WHERE clause 修改。
- 无 `rowcount=0` 检测逻辑修改。
- **结论**: CAS 语义零变化。

### EventLog 语义

- `TABLE_EVENT_LOG` 常量值仍为 `"event_log"`——SQL 查询的表名不变。
- EventLog append 逻辑未修改。
- `event_sequence AUTOINCREMENT` 语义未修改。
- **结论**: EventLog 语义零变化。

### Phase 3 Scope

- 未新增 Session/Run/Attempt 状态。
- 未新增 transition 路径。
- 未新增 public API。
- 未实现任何 Phase 3 non-goal（dispatch, scheduler, WorkerProxy, EngineEvent ingest, wait, steer, recovery）。
- **结论**: Phase 3 scope 未扩大。

### Import Boundary

- `admission.py` 新增导入：`from dayu.host.durable.schema import TABLE_EVENT_LOG`
- 导入方向：`dayu.host.admission` → `dayu.host.durable.schema`（同一 Host 包内，同层 durable 子模块间导入）
- `schema.py` 依赖链：仅 stdlib（`dataclasses`, `logging`, `sqlite3`, `textwrap`）
- 未引入 `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui` / `dayu.runtime` 导入
- **结论**: 无循环依赖，无反向依赖，层合规。

### 弱类型

- `TABLE_EVENT_LOG` 类型为 `str`（模块级常量赋值），类型明确。
- f-string 使用字符串常量，类型安全。
- 无新增 `Any`、`object`、无类型参数。
- **结论**: 无新增类型问题。

### 文档/README 触发

- 修改内容：
  - `admission.py`: 表名引用方式从硬编码变为常量——内部实现细节，不影响接口。
  - `state.py`: docstring 补充——内部文档完善。
- 不命中 CLAUDE.md 定义的 README 触发条件（无接口变化、无 schema 变化、无行为变化、无架构边界变化、无新能力）。
- **结论**: 无需更新 README。

## New Findings

**无新增 blocking finding。**

**无新增 non-blocking finding。**

修复范围精确——admission.py 两处（新增 1 行 import + 替换 1 行 SQL 字符串）、state.py 一处（新增 2 行 docstring）。无副作用扩散，无附带修改。

## Acceptance

**Accepted. No blocking findings.**

N-1 和 N-2 两个 accepted non-blocking findings 均已完全修复。修复不改变状态机行为、schema、CAS 条件、EventLog 语义或 Phase 3 scope。未新增 import boundary 违规、循环依赖、弱类型或 README 同步问题。157 测试通过，0 pyright 错误。

可以进入 PR 创建阶段。
