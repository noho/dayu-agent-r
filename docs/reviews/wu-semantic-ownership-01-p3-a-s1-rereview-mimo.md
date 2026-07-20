# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 re-review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S1 fix re-review
- Agent: AgentMiMo
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-controller-validation.md`
- Changed files: `dayu/host/lifecycle_events.py`, `tests/host/test_lifecycle_events.py`, `tests/host/test_state_schema.py`

## Re-review Scope

只复审 S1 fix 是否关闭 controller 接受的 S1-F01..S1-F04，不检查其他问题。

## S1-F01 Re-review: Attempt durable terminal vs closeout-supported clarity

**Verdict: closed**

Fix 实现了 controller 要求的所有修复点：

1. **closeout-supported subset 明确化**：`CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES`（`lifecycle_events.py:69-75`）只包含 `SUCCEEDED / FAILED / CANCELLED / LOST`，排除 `SUSPENDED / STEERED`。
2. **durable terminal helper 保留**：`attempt_terminal_event_type_for_status`（`lifecycle_events.py:195-212`）覆盖所有 6 个 durable Attempt terminal status，docstring 明确说明 `SUSPENDED / STEERED` 是 durable terminal 但不属于 closeout-supported subset。
3. **closeout helper fail-fast**：`closeout_attempt_terminal_event_type_for_status`（`lifecycle_events.py:215-232`）对 `SUSPENDED / STEERED` 抛出 `ValueError`。
4. **测试保护**：
   - `test_closeout_attempt_terminal_event_type_for_status_covers_supported_subset`（`test_lifecycle_events.py:88-106`）验证 closeout subset 只包含 4 个成员。
   - `test_closeout_attempt_terminal_event_type_for_status_rejects_durable_only_terminal`（`test_lifecycle_events.py:109-128`）验证 `SUSPENDED / STEERED` 通过 durable helper 但 fail through closeout helper。

**传播审计**：closeout-supported subset 的真源是 `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` 和 `_CLOSEOUT_TERMINAL_EVENT_TYPE_BY_ATTEMPT_STATUS`，两者内容一致。S2 consumer 必须使用 `closeout_attempt_terminal_event_type_for_status`，不能直接用 `attempt_terminal_event_type_for_status` 进入 closeout path。

## S1-F02 Re-review: Terminal predicate tests explicitness

**Verdict: closed**

Fix 添加了两个显式命名的 predicate 测试：

1. `test_is_terminal_run_status_covers_all_members`（`test_state_schema.py:428-434`）遍历所有 `RunStatus` 成员，验证 `is_terminal_run_status` predicate 与 `TERMINAL_RUN_STATUS_VALUES` 一致。
2. `test_is_terminal_attempt_status_covers_all_members`（`test_state_schema.py:437-443`）遍历所有 `AttemptStatus` 成员，验证 `is_terminal_attempt_status` predicate 与 `TERMINAL_ATTEMPT_STATUS_VALUES` 一致。

测试名称直接对应 predicate 函数名，不再依赖 row-rule derivation 测试的隐式覆盖。

## S1-F03 Re-review: frozenset ordering coverage

**Verdict: closed**

Fix 在 `test_serialized_run_status_values_use_owner_serialization`（`test_state_schema.py:475-503`）中添加了三个断言：

1. tuple 输入保留调用方顺序：`(RunStatus.LOST, RunStatus.SUCCEEDED)` → `(LOST, SUCCEEDED)`。
2. `TERMINAL_RUN_STATUSES`（frozenset）按 `RunStatus` 定义顺序输出：`(SUCCEEDED, FAILED, CANCELLED, LOST)`。
3. **关键断言**：`frozenset({RunStatus.LOST, RunStatus.SUCCEEDED})` 按定义顺序输出为 `(SUCCEEDED, LOST)`。

第三个断言直接验证了 controller 要求的 unordered frozenset input → definition order output 行为。

## S1-F04 Re-review: Lifecycle module/class docstrings

**Verdict: closed**

Fix 更新了以下 docstrings：

1. **模块 docstring**（`lifecycle_events.py:1-8`）：新增 `Host Attempt terminal event type`、`closeout-supported Attempt terminal subset` 的 ownership 声明。
2. **`HostAttemptEventType` class docstring**（`lifecycle_events.py:33-37`）：明确 P3-A 只定义 terminal 成员，非终态 Attempt event type 不在本轮范围内。
3. **`HOST_ATTEMPT_TERMINAL_EVENT_TYPES` docstring**（`lifecycle_events.py:63-67`）：说明包含 `ATTEMPT_SUSPENDED` 与 `ATTEMPT_STEERED`，它们是 durable terminal 但不属于 closeout-supported subset。

## New Blocker / Owner Boundary Drift / Over-design / Type Issues

**未发现新 blocker。**

- **Owner boundary**：closeout-supported subset 的真源落在 `dayu.host.lifecycle_events`，与 durable terminal 真源 `dayu.host.durable.state.TERMINAL_ATTEMPT_STATUSES` 分离但协调。`TERMINAL_ATTEMPT_STATUSES` 从 private `_TERMINAL_ATTEMPT_STATUSES` 改为 public，允许测试直接验证 durable terminal shape 一致性，这是合理的。
- **过度设计**：fix 只添加了必要的 closeout subset 和 helper，未引入多余抽象。
- **类型问题**：`pyright` 通过，无新增类型错误。

## Verdict

pass - S1-F01..S1-F04 均已正确关闭，无新 blocker。

## Completion Report

- status: completed
- artifact: docs/reviews/wu-semantic-ownership-01-p3-a-s1-rereview-mimo.md
- verdict: pass
- blocking findings count: 0
- nonblocking findings count: 0
- blockers: none
