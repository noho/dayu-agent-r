# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 Code Review — AgentDS

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted workspace changes, S1 implementation)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-ds.md`
- Included scope:
  - `dayu/host/lifecycle_events.py` — new `HostAttemptEventType`, `HOST_ATTEMPT_TERMINAL_EVENT_TYPES`, `run_terminal_event_type_for_status`, `attempt_terminal_event_type_for_status`, `attempt_event_type_values`
  - `dayu/host/durable/state.py` — promoted `TERMINAL_ATTEMPT_STATUSES`, new `START_BLOCKING_RUN_STATUSES`, `is_terminal_run_status`, `is_terminal_attempt_status`, `serialized_run_status_values`, `run_status_in_clause`; internal callers migrated to public predicates
  - `tests/host/test_lifecycle_events.py` — new owner tests for Run/Attempt terminal event type helpers
  - `tests/host/test_state_schema.py` — new owner tests for status predicates, SQL helper, derivation chains, exact start-blocking membership
  - `docs/host/issues-implementation-control.md` — S1 status update (next gate → code review)
- Excluded scope: S2/S3 consumer migration, worker lifecycle closeout — not yet implemented
- Parallel review coverage: 无（single-agent review）

## Independent Verification

所有验证命令在本地重新执行，结果与 AgentCodex implementation artifact 和 controller validation artifact 一致：

```text
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py -q
  → 54 passed in 0.54s

source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
  → import-ok

source .venv/bin/activate && pyright
  → 0 errors, 0 warnings, 0 informations

git diff --check
  → passed (confirmed no whitespace issues)
```

Durable truth 核对：

- `_row_rules.py:21-28` 定义 `TERMINAL_ATTEMPT_STATUS_VALUES = (SUCCEEDED, FAILED, CANCELLED, SUSPENDED, STEERED, LOST)` — 包含 SUSPENDED 和 STEERED。
- `api.py:304-311` 定义 `AttemptStatus` 包含 `STARTING, RUNNING, SUCCEEDED, FAILED, CANCELLED, SUSPENDED, STEERED, LOST` — 非终态只有 STARTING 和 RUNNING。
- S1 实现中 `TERMINAL_ATTEMPT_STATUSES = frozenset(AttemptStatus(value) for value in TERMINAL_ATTEMPT_STATUS_VALUES)` 正确从 row rules 真源派生，包含全部 6 个终态。✓

## Findings

### 1-未修复-中- Attempt SUSPENDED/STEERED 终端事件类型无对应 Run 终态 closeout 路径

- **入口/函数**: `attempt_terminal_event_type_for_status(AttemptStatus.SUSPENDED)` / `attempt_terminal_event_type_for_status(AttemptStatus.STEERED)` 在 `dayu/host/lifecycle_events.py`
- **文件(行号)**: `lifecycle_events.py:169-182`（helper 定义）, `lifecycle_events.py:92-101`（映射表）, `state.py:88`（`TERMINAL_ATTEMPT_STATUSES` 包含 SUSPENDED/STEERED）
- **输入场景**: 任何调用方对 `AttemptStatus.SUSPENDED` 或 `AttemptStatus.STEERED` 调用 `attempt_terminal_event_type_for_status` 或 `is_terminal_attempt_status`
- **实际分支**: helper 返回有效 `HostAttemptEventType.ATTEMPT_SUSPENDED` / `HostAttemptEventType.ATTEMPT_STEERED`；predicate 返回 `True`
- **预期行为**: 按 plan Section 5 S2 约束，`_TERMINAL_STATUS_PAIRS` 只允许 `(SUCCEEDED, SUCCEEDED)`、`(FAILED, FAILED)`、`(CANCELLED, CANCELLED)`、`(LOST, LOST)` 进入 terminal closeout transaction。SUSPENDED/STEERED 没有对应 Run 终态配对，无法进入 Run/Attempt 联合 closeout。
- **实际行为**: S1 helper 将 SUSPENDED/STEERED 按完整终端事件类型处理，返回有效 `HostAttemptEventType`。这是 durable truth 的正确投影——row rules 确实宣告它们为终态。但 plan 的 closeout 设计不支持它们进入联合 closeout。S2/S3 消费者可能误以为所有 terminal Attempt event type 都可以进入 closeout transaction。
- **直接证据**:
  - plan Section 5 S2（`docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md:261`）明确 `_TERMINAL_STATUS_PAIRS` 只覆盖 SUCCEEDED/FAILED/CANCELLED/LOST
  - plan Section 2 AgentMiMo SM-2 裁决："RUN_SUSPENDED 在 Engine 是 terminal，但 Host 只做 waiting confirmation"
  - controller validation（`docs/reviews/wu-semantic-ownership-01-p3-a-s1-controller-validation.md:33`）显式标记："Code review should pay special attention to whether Attempt terminal helper coverage for SUSPENDED and STEERED matches durable Attempt terminal truth and later closeout-supported subsets"
  - 当前实现中 `attempt_terminal_event_type_for_status` 对 SUSPENDED/STEERED 返回有效值（非 fail-fast），`is_terminal_attempt_status` 返回 `True`
- **影响**: 如果 S2/S3 实现中直接对所有 terminal Attempt event type 调用 terminal closeout，SUSPENDED/STEERED 路径会因为缺少 Run 终态配对而失败或产生错误事实。SUSPENDED（Attempt 暂停等待外部结果）和 STEERED（同 Run steer 收口旧 Attempt）的正确处理路径是各自独立的 lifecycle 分支，不走 Run/Attempt 联合 closeout。
- **建议改法和验证点**:
  - S2/S3 实现前，在 `attempt_terminal_event_type_for_status` 的 docstring 中增加说明：SUSPENDED/STEERED 是终端 Attempt 事件类型，但不进入 Run/Attempt 联合 terminal closeout transaction
  - 或在 `_TERMINAL_STATUS_PAIRS` 派生处增加注释，显式列举 closeout-supported 子集
  - 或在 S2 的 `_TERMINAL_STATUS_PAIRS` derived invariant 中增加 fail-fast：对不在 closeout-supported 子集中的 terminal Attempt status 拒绝生成 pair
  - S3 的 active-cancel decision table 已在 plan 中覆盖 CANCELLING + SUSPENDED/STEERED 的 routing，但需要验证 `is_terminal_attempt_status` predicate 在这些场景下不会错误地将 late event 接受为 terminal closeout
- **修复风险（低）**: 只需文档/注释澄清或 S2 derived invariant 的 fail-fast；不改变 S1 helper 的行为语义
- **严重程度（中）**: 不是当前 S1 的 correctness bug——helper 正确反映 durable truth——但在 S2/S3 中可能被误用。S1 将其无条件纳入 terminal helper 的决策需要在 S2/S3 的 consumer 路径上得到 follow-through 验证

### 2-未修复-低- `lifecycle_events.py` 模块 docstring 未反映 Attempt event type 所有权扩展

- **入口/函数**: 模块级 docstring `dayu/host/lifecycle_events.py:1-7`
- **文件(行号)**: `lifecycle_events.py:1-7`
- **输入场景**: 开发者阅读模块 docstring 了解本模块职责范围
- **实际分支**: 当前 docstring 写 "本模块是 Host Run lifecycle event type、terminal event set 与 public outbox terminal item set 的代码真源"
- **预期行为**: docstring 应反映本模块现在也是 Host Attempt terminal event type 的代码真源
- **实际行为**: docstring 只提到 Run，未提及 Attempt
- **直接证据**: 模块现在导出 `HostAttemptEventType`、`HOST_ATTEMPT_TERMINAL_EVENT_TYPES`、`attempt_terminal_event_type_for_status`、`attempt_event_type_values`，这些是模块级 public API
- **影响**: 开发者可能误以为 Attempt event type 所有权在别处，导致在错误位置新增 Attempt event type 映射
- **建议改法和验证点**: 将 docstring 更新为 "本模块是 Host Run lifecycle event type、Attempt terminal event type、terminal event set 与 public outbox terminal item set 的代码真源。" 或在 docstring 中补充说明 Attempt terminal event type 同样由本模块拥有
- **修复风险（低）**: 纯文档修改
- **严重程度（低）**: 不影响代码正确性；但 CLUADE.md 要求 "函数必须提供完整中文 docstring"，模块级 docstring 的准确性同样重要

### 3-未修复-低- `HostAttemptEventType` 与 `HostRunEventType` 的 docstring 语义不对称

- **入口/函数**: class docstring `HostAttemptEventType` 和 `HostRunEventType`
- **文件(行号)**: `lifecycle_events.py:16`（`HostRunEventType`）, `lifecycle_events.py:31`（`HostAttemptEventType`）
- **输入场景**: 未来 P3-J 或其他 WU 需要为 Attempt 添加非终态 event type（如 `ATTEMPT_STARTING`、`ATTEMPT_RUNNING`）
- **实际分支**: 当前设计有意只在 S1 添加 terminal Attempt event type（plan 明确 non-goal "不处理非 terminal Host EventLog 常量的全局 owner 化"）
- **预期行为**: docstring 应说明当前只有 terminal 成员的原因，避免未来开发者困惑为什么 Run event type 是 "lifecycle"（含非终态）而 Attempt event type 是 "terminal only"
- **实际行为**: `HostRunEventType` docstring: "Host Run lifecycle EventLog 事件类型。"（含 ACCEPTED/QUEUED/STARTED 等非终态）；`HostAttemptEventType` docstring: "Host Attempt terminal EventLog 事件类型。"（只有终态）。两个同层 enum 的 docstring 遵循不同模式
- **直接证据**: `lifecycle_events.py:31-32` 的 docstring 与 `lifecycle_events.py:16-17` 的 docstring 语义粒度不一致
- **影响**: 低。当前代码行为正确，但未来扩展时可能产生困惑。例如开发者可能直接往 `HostAttemptEventType` 加非终态成员而不意识到命名/docstring 暗示它是 terminal-only
- **建议改法和验证点**: 在 `HostAttemptEventType` docstring 中补充："当前 P3-A 只定义 terminal 成员；非终态 Attempt event type 归后续 EventLog schema hardening 处理。" 或在 P3-J 实施时重命名/拆分
- **修复风险（低）**: 纯文档修改
- **严重程度（低）**: 不影响当前代码正确性

## Open Questions

1. **S2/S3 closeout 会如何处理 ATTEMPT_SUSPENDED/ATTEMPT_STEERED？** 当前 plan 的 `_TERMINAL_STATUS_PAIRS` 只覆盖 SUCCEEDED/FAILED/CANCELLED/LOST。SUSPENDED/STEERED 作为 Attempt terminal event type 的消费路径需要在 S2/S3 中显式处理。建议在 S2 实现前确认 routing：这些 event type 是否进入 `_TERMINAL_STATUS_PAIRS` 的 fail-fast？还是作为独立 Attempt terminal fact 写入 EventLog 但跳过 Run 联合 closeout？

2. **F-1 是否需要在 S1 修复？** Finding 1 的 root cause 不在 S1——S1 正确投影了 durable truth。风险在 S2/S3 的 consumer 实现。建议 S1 保持现状，将 F-1 作为 S2/S3 的 implementation constraint 传递。

## Residual Risk

- **S1 scope 内无未覆盖风险。** 所有 planned S1 helpers 已实现并通过 owner-level 测试。54 个测试覆盖了 terminal event type 映射、non-terminal fail-fast、status 集合派生、SQL helper 生成和内部消费者迁移。pyright 零错误零警告，import cycle 验证通过。
- **S2 scope handoff risk：** `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` 的 source scan 正则只覆盖这四类 terminal constant；S2 实现时必须验证 `ATTEMPT_SUSPENDED` / `ATTEMPT_STEERED` 在 `run_transition.py` / `engine_ingest.py` 中的使用方式，确认它们不会被错误地迁移到联合 closeout path。
- **README 决策已确认：** `dayu/host/README.md` 和 `tests/README.md` 均不需要因为 S1 的内部 owner helper 新增而更新。S1 未改变 public Host behavior、durable schema、EventLog 语义或 documented execution path。`tests/host/test_lifecycle_events.py` 属于已有 `tests/host/` 分层内的 owner-level 测试。

## Completion Report

- status: completed
- artifact: docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-ds.md
- verdict: pass-with-findings
- blocking findings count: 0
- nonblocking findings count: 3
- blockers: none
