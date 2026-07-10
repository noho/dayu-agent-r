# Code Review - WU-SEMANTIC-OWNERSHIP-01 P3-A S1

## Scope

- Mode: current changes (unstaged S1 implementation diff)
- Branch: `phaseflow/host-issues-control`
- Base: `main` (selected base for diff scope; S1 changes are unstaged)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-mimo.md`
- Included scope:
  - `dayu/host/lifecycle_events.py` (unstaged diff)
  - `dayu/host/durable/state.py` (unstaged diff)
  - `tests/host/test_lifecycle_events.py` (new file)
  - `tests/host/test_state_schema.py` (unstaged diff)
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-controller-validation.md`
  - `docs/host/issues-implementation-control.md` (S1 status)
  - `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- Excluded scope: S2/S3 consumer migration, worker lifecycle closeout, commit/push
- Parallel review coverage: 无

## Findings

### 001-unfixed-medium-Attempt 终态 helper 语义覆盖过宽，S2 迁移者无法从 helper 本身区分 closeout-supported 与 durable-shape-only 终态

- **入口/函数**: `attempt_terminal_event_type_for_status()` in `dayu/host/lifecycle_events.py:169-182`
- **文件(行号)**: `dayu/host/lifecycle_events.py:169-182`, `dayu/host/lifecycle_events.py:50-57`
- **输入场景**: S2 迁移者调用 `attempt_terminal_event_type_for_status(AttemptStatus.SUSPENDED)` 或 `attempt_terminal_event_type_for_status(AttemptStatus.STEERED)` 生成 closeout event type
- **实际分支**: helper 接受所有 6 个 Attempt terminal status 并返回对应 `HostAttemptEventType`
- **预期行为**: 按 P3-A plan，`SUSPENDED`/`STEERED` 是 durable Attempt row 终态（`_row_rules.TERMINAL_ATTEMPT_STATUS_VALUES` 确认），但 Run 终态不包含 `RUN_SUSPENDED`——`SUSPENDED` Attempt 对应 Run 进入 `WAITING`，不是 Run terminal closeout。S2 terminal closeout producer 应只对 closeout-supported Attempt terminal subset 生成 `ATTEMPT_*` canonical facts；对 `SUSPENDED`/`STEERED` 应走 waiting confirmation 或 steer path，不应生成 terminal closeout event。当前 helper 不区分这两个子集
- **实际行为**: `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` 包含全部 6 个枚举成员，`attempt_terminal_event_type_for_status` 不对 `SUSPENDED`/`STEERED` fail-fast
- **直接证据**:
  - `dayu/host/lifecycle_events.py:50-57`: `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` 包含 `ATTEMPT_SUSPENDED` 和 `ATTEMPT_STEERED`
  - `dayu/host/lifecycle_events.py:92-101`: `_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS` 映射 `SUSPENDED`/`STEERED` 到对应 event type
  - `dayu/host/durable/_row_rules.py`: `TERMINAL_ATTEMPT_STATUS_VALUES` 确实包含 `suspended` 和 `steered`
  - P3-A plan section 5 S1: "SUSPENDED/STEERED 是否进入 helper 由 implementation 按当前 closeout support 裁决，但若不支持必须明确 fail-fast"
  - P3-A plan section 2: "RUN_SUSPENDED 是 Engine terminal event，但在 Host 中对应 WAITING，不是 Run terminal event"
- **影响**: S2 迁移者可能误用 `attempt_terminal_event_type_for_status(SUSPENDED)` 在 terminal closeout path 生成 `ATTEMPT_SUSPENDED` canonical fact，而该 Attempt 实际上应让 Run 进入 `WAITING` 而非 terminal closeout。当前 helper 让这种误用在类型检查和运行时都不报错
- **建议改法和验证点**:
  1. 在 `lifecycle_events.py` 新增 `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES: tuple[HostAttemptEventType, ...]`，排除 `ATTEMPT_SUSPENDED` 和 `ATTEMPT_STEERED`（当前 4 个：SUCCEEDED、FAILED、CANCELLED、LOST）
  2. 新增 `closeout_attempt_terminal_event_type_for_status(status: AttemptStatus) -> HostAttemptEventType`，对 `SUSPENDED`/`STEERED` fail-fast
  3. 或者在现有 `attempt_terminal_event_type_for_status` docstring 中明确标注"本 helper 覆盖全部 durable Attempt 终态，但 SUSPENDED/STEERED 不属于 closeout-supported subset；closeout path 应先判断是否 closeout-supported"
  4. 新增测试断言 `SUSPENDED`/`STEERED` 被 helper 接受但不属于 closeout-supported subset
- **修复风险（低/中/高）**: 低。新增一个子集常量和一个 fail-fast helper，不影响现有行为
- **严重程度（中）**: S2 迁移依赖此 helper 的正确语义；当前设计让 closeout path 和 durable shape path 使用同一个不区分语义的 helper

### 002-unfixed-low-is_terminal_run_status 与 is_terminal_attempt_status 缺少独立单元测试覆盖

- **入口/函数**: `is_terminal_run_status()`, `is_terminal_attempt_status()` in `dayu/host/durable/state.py`
- **文件(行号)**: `dayu/host/durable/state.py:557-565`, `dayu/host/durable/state.py:615-623`
- **输入场景**: `is_terminal_run_status(RunStatus.SUCCEEDED)` 等
- **实际分支**: 返回 `status in TERMINAL_RUN_STATUSES` / `status in TERMINAL_ATTEMPT_STATUSES`
- **预期行为**: 每个 `RunStatus` 和 `AttemptStatus` 成员都应有直接断言覆盖 `is_terminal_*` 返回值
- **实际行为**: `test_terminal_run_statuses_derive_from_row_rules` 和 `test_terminal_attempt_statuses_derive_from_row_rules` 中的 `for status in RunStatus/AttemptStatus` 循环隐式覆盖了这两个函数，但测试名称和 docstring 未提及 `is_terminal_*` predicate；如果未来重构移除这些循环，predicate 可能失去覆盖
- **直接证据**:
  - `tests/host/test_state_schema.py:96-103`: `for status in RunStatus: assert is_terminal_run_status(status) is (status in expected)`
  - `tests/host/test_state_schema.py:106-113`: 同理 AttemptStatus
- **影响**: 低。当前隐式覆盖有效，但测试语义与被测函数名不绑定，未来重构可能意外丢失覆盖
- **建议改法和验证点**: 在现有测试函数中增加注释说明 `is_terminal_*` 是被测 predicate；或新增独立测试 `test_is_terminal_run_status_covers_all_members` / `test_is_terminal_attempt_status_covers_all_members` 显式覆盖
- **修复风险（低/中/高）**: 低。仅补充测试
- **严重程度（低）**: 测试可维护性问题，不影响当前正确性

### 003-unfixed-low-serialized_run_status_values 对 frozenset 与 tuple 的排序行为差异缺显式测试

- **入口/函数**: `serialized_run_status_values()` in `dayu/host/durable/state.py:568-583`
- **文件(行号)**: `dayu/host/durable/state.py:568-583`
- **输入场景**: 传入 `TERMINAL_RUN_STATUSES`（frozenset）vs 传入 `(RunStatus.LOST, RunStatus.SUCCEEDED)`（tuple）
- **实际分支**: `isinstance(statuses, frozenset)` 时按 `RunStatus` 定义顺序输出；否则保留调用方顺序
- **预期行为**: docstring 说明了两种行为，但测试只断言了 `serialized_run_status_values(TERMINAL_RUN_STATUSES)` 的输出等于按定义顺序的序列化值；未断言 `serialized_run_status_values((RunStatus.LOST, RunStatus.SUCCEEDED))` 保留 LOST-first 顺序
- **实际行为**: `test_serialized_run_status_values_use_owner_serialization` 断言了 tuple 输入保留顺序（LOST, SUCCEEDED -> "lost", "succeeded"），但未断言 frozenset 输入的排序稳定性（假设 `RunStatus` 定义顺序不变）
- **直接证据**: `tests/host/test_state_schema.py:145-162`
- **影响**: 低。当前行为正确，但 frozenset 排序依赖 `RunStatus` enum 定义顺序，该依赖未被显式测试
- **建议改法和验证点**: 增加一条断言 `serialized_run_status_values(frozenset({RunStatus.LOST, RunStatus.SUCCEEDED}))` 返回按 `RunStatus` 定义顺序的值（SUCCEEDED, LOST），明确记录排序行为
- **修复风险（低/中/高）**: 低。仅补充测试
- **严重程度（低）**: 测试覆盖完整性问题

## Open Questions

- 无。S1 实现正确建立 lifecycle/status owner helper，类型安全，无 import cycle，pyright 通过，focused tests 全通过。主要关注点是 Attempt SUSPENDED/STEERED 的 closeout 语义区分（finding 001），应在 S2 迁移前解决。

## Residual Risk

- S2 迁移必须处理 `SUSPENDED`/`STEERED` Attempt terminal status 的 closeout routing 语义，不能直接使用 `attempt_terminal_event_type_for_status` 作为 closeout producer。当前 `run_transition.py` 和 `engine_ingest.py` 中的 terminal event string 复制尚未迁移，这是 S2 scope。
- `read_active_run_for_session` / `read_non_terminal_runs_for_session` / `read_non_terminal_runs` 的 SQL 仍硬编码 status 列表，未消费 `START_BLOCKING_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES` + `run_status_in_clause` helper。这是 S2 scope。
- `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` 的 docstring 写"Host Attempt terminal canonical fact 事件集合"，但 SUSPENDED/STEERED 在 Host lifecycle 中是否产生 canonical fact（而非 waiting/steer confirmation）取决于 S2/S3 设计。当前 docstring 未区分 durable shape terminal 和 closeout canonical fact terminal。
