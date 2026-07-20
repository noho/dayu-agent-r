# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 re-review - AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S1 re-review (fix verification)
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-controller-validation.md`
- Changed files:
  - `dayu/host/lifecycle_events.py`
  - `tests/host/test_lifecycle_events.py`
  - `tests/host/test_state_schema.py`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`

## Re-review Method

逐条走读 S1-F01..S1-F04 的 fix 实现与测试覆盖，沿真实代码路径验证每个 finding 是否被关闭；同时执行 adversarial pass 检查是否引入新 blocker、owner boundary drift、过度设计或类型问题。

## Finding-by-Finding Verification

### S1-F01 [medium] — FIXED

**要求**: Attempt durable terminal 与 closeout-supported subset 必须明确且有测试保护。

**实现验证**:

- `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` (`lifecycle_events.py:69-74`) 正确排除 `ATTEMPT_SUSPENDED` 和 `ATTEMPT_STEERED`，只包含 `SUCCEEDED / FAILED / CANCELLED / LOST`。
- `closeout_attempt_terminal_event_type_for_status` (`lifecycle_events.py:215-232`) 使用 `_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS` 映射表，对 `SUSPENDED` / `STEERED` fail-fast 并给出独立错误消息 `"unsupported closeout Attempt terminal status"`，与 durable helper 的 `"unsupported Attempt terminal status"` 区分。
- `attempt_terminal_event_type_for_status` (`lifecycle_events.py:195-212`) 保留为 durable terminal helper，覆盖全部 6 个终态，docstring 明确指引 closeout path 必须使用 closeout helper。
- `_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS` (`lifecycle_events.py:120-127`) 与 `_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS` (`lifecycle_events.py:109-118`) 各自独立维护，不存在共享可变状态。

**测试覆盖**:

- `test_closeout_attempt_terminal_event_type_for_status_covers_supported_subset` (`test_lifecycle_events.py:88-106`): 验证 closeout helper 只覆盖 4 个 closeout-supported status，且 `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` tuple 与其一致。
- `test_closeout_attempt_terminal_event_type_for_status_rejects_durable_only_terminal` (`test_lifecycle_events.py:109-128`): 参数化测试 `SUSPENDED` / `STEERED`，验证 durable helper 返回正确 event type 且不属于 closeout set，closeout helper 抛出 ValueError。
- `test_attempt_terminal_event_type_for_status_rejects_non_terminal_status` (`test_lifecycle_events.py:131-149`): 验证两个 helper 对非终态 `STARTING` / `RUNNING` 均 fail-fast。

**判决**: 已关闭。durable terminal 与 closeout-supported 的区分明确，正反测试完整，错误消息可区分。

### S1-F02 [low] — FIXED

**要求**: terminal predicate tests 必须显式命名 `is_terminal_run_status` 和 `is_terminal_attempt_status`。

**实现验证**:

- `test_is_terminal_run_status_covers_all_members` (`test_state_schema.py:112-118`): 遍历 `RunStatus` 全部成员，对每个 status 调用 `is_terminal_run_status(status)` 并与 row-rules 派生的 expected set 比较。终态返回 `True`，非终态返回 `False`。
- `test_is_terminal_attempt_status_covers_all_members` (`test_state_schema.py:121-127`): 遍历 `AttemptStatus` 全部成员，对每个 status 调用 `is_terminal_attempt_status(status)` 并与 row-rules 派生的 expected set 比较。

**判决**: 已关闭。两个 predicate 均有显式命名的全覆盖测试，不再依赖间接推导测试。

### S1-F03 [low] — FIXED

**要求**: `serialized_run_status_values` frozenset 输入排序必须显式断言。

**实现验证**:

- `test_serialized_run_status_values_use_owner_serialization` (`test_state_schema.py:177-187`) 新增断言:
  ```python
  assert serialized_run_status_values(
      frozenset({RunStatus.LOST, RunStatus.SUCCEEDED})
  ) == (
      serialize_run_status(RunStatus.SUCCEEDED),
      serialize_run_status(RunStatus.LOST),
  )
  ```
  输入 frozenset 的字面量顺序是 `LOST, SUCCEEDED`，输出是 `SUCCEEDED, LOST`（`RunStatus` 定义顺序），证明排序逻辑由 `RunStatus` 定义顺序驱动，不依赖 frozenset 迭代顺序。
- 实现逻辑 (`state.py:579-580`): `tuple(status for status in RunStatus if status in statuses)` — 正确按定义顺序过滤。

**判决**: 已关闭。frozenset 排序行为有聚焦断言覆盖。

### S1-F04 [low] — FIXED

**要求**: lifecycle module/class docstrings 必须准确反映 Attempt ownership。

**实现验证**:

- Module docstring (`lifecycle_events.py:1-8`): 已包含 "Host Attempt terminal event type" 与 "closeout-supported Attempt terminal subset" 的 ownership 声明。
- `HostAttemptEventType` class docstring (`lifecycle_events.py:33-37`): 明确 "当前 P3-A 只定义 terminal 成员；非终态 Attempt event type 不属于本轮 terminal closeout owner 收敛范围"。
- `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` docstring (`lifecycle_events.py:63-67`): 明确 "``ATTEMPT_SUSPENDED`` 与 ``ATTEMPT_STEERED`` 是 durable Attempt 终态事件，但不属于 Run / Attempt 联合 terminal closeout 支持的子集"。
- `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` docstring (`lifecycle_events.py:75`): 明确这是 "Run / Attempt 联合 terminal closeout 支持的 Attempt terminal 事件子集"。

**判决**: 已关闭。docstrings 准确反映 Attempt terminal event type ownership 和 closeout-supported 子集语义。

## Adversarial Pass

### 新增 blocker 检查

- **无新增 blocker**。变更严格限制在 allowed files 内，未修改 `state.py`、`run_transition.py`、`engine_ingest.py` 或其他 consumer。
- Import cycle 验证通过：`from dayu.host.lifecycle_events import ...` 后 `import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest` 无循环引用。
- Pyright: 0 errors, 0 warnings。
- 59 个 focused tests 全部通过。

### Owner boundary drift 检查

- Closeout-supported Attempt terminal subset 的 owner 是 `dayu.host.lifecycle_events` — 正确的 lifecycle event type owner。
- Durable terminal truth 的 owner 仍是 `dayu.host.durable.state`（`TERMINAL_ATTEMPT_STATUSES` 由 row rules 派生）和 `dayu.host.lifecycle_events`（`HOST_ATTEMPT_TERMINAL_EVENT_TYPES` 包含全部 6 个终态事件类型）。
- 两层 owner 之间无循环依赖：`lifecycle_events.py` import `dayu.host.api`（`AttemptStatus`），不 import `dayu.host.durable.state`。
- 没有下游 consumer 在本 fix 中被修改，因此不存在 downstream fallback / 特例分支掩盖上游语义的风险。

### 过度设计检查

- 新增内容与现有模式一致：一个 tuple 常量 + 一个私有映射表 + 一个 public helper，与 `HOST_RUN_TERMINAL_EVENT_TYPES` / `_TERMINAL_EVENT_TYPE_BY_RUN_STATUS` / `run_terminal_event_type_for_status` 的模式对称。
- 未引入不必要的抽象层、工厂、策略模式或 indirection。
- `closeout_attempt_terminal_event_type_for_status` 的 ValueError 消息与 `attempt_terminal_event_type_for_status` 的消息有区分度，帮助 S2 开发者定位使用了错误的 helper。

### 类型问题检查

- `_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS: dict[AttemptStatus, HostAttemptEventType]` — 类型完整。
- `closeout_attempt_terminal_event_type_for_status(status: AttemptStatus) -> HostAttemptEventType` — 签名完整，docstring 包含参数、返回值、异常说明。
- 测试中所有 fixture 和 parametrize 类型标注完整。

### 边界条件检查

- `closeout_attempt_terminal_event_type_for_status` 对非终态 `STARTING` / `RUNNING` fail-fast（由 `test_attempt_terminal_event_type_for_status_rejects_non_terminal_status` 覆盖）。
- frozenset 为空时 `serialized_run_status_values` 返回空 tuple — 此行为不在本次 fix scope 内，下游 `run_status_in_clause` 有独立的空集合 fail-fast 保护。
- `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` tuple 不为空，且与 `_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS` 的 keys 一致（由测试断言保证）。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **S2 consumer migration**: S2 需要将 `run_transition.py` / `engine_ingest.py` 中的 terminal event consumer 迁移到 lifecycle event owner helpers。S2 必须对 joint terminal closeout path 使用 `closeout_attempt_terminal_event_type_for_status`，并将 `SUSPENDED` / `STEERED` 保留在其 waiting / steer-specific lifecycle route 上。此风险属于 S2 scope，不在 S1 fix 范围内。
- **S2 剩余 SQL/status consumer 迁移**: 同样属于 S2 scope。
- **`closeout_attempt_terminal_event_type_for_status` 无对应 predicate**: 当前 closeout helper 通过 ValueError fail-fast 表达"不支持"，与 durable helper 模式一致。若 S2 需要先判断再调用（而非 try/except），可按需添加 `is_closeout_supported_attempt_terminal_status` predicate — 此项属于 S2 实现细节，不作为 S1 finding。

## Completion Report

- status: completed
- artifact: docs/reviews/wu-semantic-ownership-01-p3-a-s1-rereview-ds.md
- verdict: pass
- blocking findings count: 0
- nonblocking findings count: 0
- blockers: none
