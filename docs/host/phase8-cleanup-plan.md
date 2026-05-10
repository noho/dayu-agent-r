# Host P8 Legacy Cleanup + Code-Review Fix Plan

## Goal

修复 P8 三轮 code review (`docs/reviews/code-review-20260510-0825.md` / `-0830.md` / `-0831.md`) 中所有 controller-accepted findings，同时删除诱导绕过 durable governance 的 legacy 入口，使 Host 回到「`build_durable_harness()` 是 production-like / durable 唯一装配入口；`LocalRunHarness` 仅是 Host 本地执行内核」的契约边界。

完成后必须保证：

- 不存在任何能在 durable harness 上下文外写入 attempt-scoped canonical fact 的入口；
- 不存在任何在 owner-lost / CAS miss 状态下仍向 EventLog 写入 stale terminal RunEvent 的路径；
- recovery scan 不会创建无人能继续治理的 RUNNING attempt；
- legacy P6 `AttemptStateStore` 兼容路径不再保留 production 用途，仅在显式标记为「非 durable 测试场景」时才允许使用。

## Motivation (直接证据)

- **0830-F1 / 0831-F001**：`_handle_owner_lost` 在 `_finish_attempt_if_durable` 之后通过 `self.event_store.append(host_failure_draft(...))` 直接写 EventLog，不经过 `AttemptScopedRunEventAppender` 的 `verify_owner` CAS。lease 已 lost、recovery 已接管时仍可能写入 stale RUN_FAILED。
- **0825-F01**：上述 append 与 attempt close 是两步独立操作，crash 窗口下会出现「attempt 已 LOST 但无 terminal event」状态。`AttemptSupervisor.append_terminal_and_close` 已提供 `BEGIN IMMEDIATE` 内部原子接口，但 `_handle_owner_lost` 没有走它。
- **0831-F002**：`_process_recovery_candidate` 调 `mark_recovering_and_create_attempt` 创建 `state='running'` 的 recovery attempt，但 `AttemptRecoveryDecision` 不返回 `AttemptOwnerContext`、不注册 `_LeaseSession`、不启动 renew loop；新 attempt 只有 hash，没有任何进程能合法 renew/append/close 它。
- **0831-F003**：`LocalRunHarness.fetch_more_tool_result` 直接委派 `tool_runtime.fetch_more`，而 `InMemoryToolRuntime._resolve_appender` 在 ContextVar 无 `ToolRuntimeOwnerScope` 时降级 `PlainRunEventAppender`，使外部补读入口在 durable harness 中可绕过 fencing。
- **0830-F2**：`list_recovery_candidates` SQL `AND lease_expires_at IS NOT NULL`，把 P6 legacy 路径产生的 `CREATED + lease=NULL` 行永久排除在 recovery 之外。
- **0830-F3**：`_allocate_fencing_token` `FencingToken(value=int(cursor.lastrowid or 0))` —— `lastrowid` 为 None/0 时 `or 0` 触发 `FencingToken.__post_init__` 的 `ValueError`，错误信息含义不清。
- **0830-F4**：`_decode_snapshot` 完全不读取 `schema_version`，回滚部署 + 高版本 snapshot 场景下会静默 decode 出错误数据。
- **0830-F5**：legacy P6 `_finish_attempt_if_durable` 把 `terminal_position` 硬编码为 `None`，supervisor 路径与 legacy 路径行为不一致。

公开 API 层面：`dayu.host.__all__` 暴露 `start_run` / `stream_run_events` / `get_run_result` / `get_tool_fetch_more_handle` / `fetch_more_tool_result`，背后由 `_default_harness_for_running_loop` 用 `:memory:` SQLite + InMemory store 临时拼装一个 non-durable 默认 harness。该路径既绕过 `build_durable_harness` 治理装配，又使外部代码可以在没有 owner scope 的情况下触发补读入口（直接对应 0831-F003）。删除是消除一类入口，而非一次单点修复。

## Non-Goals

- 不实现 P9 lifecycle / admission / observer claim。
- 不为存量旧库做 schema 迁移；按 AGENTS.md / CLAUDE.md 「全新 schema 起库」规则处理（这是 0825-F02 被裁决为 `rejected-with-reason` 的依据）。
- 不引入 production launcher / 真实多进程 launcher。
- 不实现完整 ToolRegistry 或新的 fetch_more 公开入口；framework 工具只能走 `Engine -> ToolRuntimeToolExecutor -> InMemoryToolRuntime.execute_tool_call`。
- 不保留任何兼容 wrapper 或 re-export。
- 不更新 owner_context snapshot stale 字段语义（0825-F03 被裁决为 `rejected/deferred-with-reason`，CAS 真源在 DB）。
- 不更新根 README（用户手册），不把 P9 写成当前事实。

## Scope Boundary

允许触及的代码区域：

- `dayu/host/__init__.py`
- `dayu/host/_run_harness.py`
- `dayu/host/_durable_harness.py`（如需调整 `build_durable_harness` 的 fail-fast 行为）
- `dayu/host/_attempt_supervisor.py`
- `dayu/host/_attempt_lease.py`（仅在 `AttemptRecoveryDecision` 语义需要明确「不再创建 running recovery attempt」时调整字段/docstring）
- `dayu/host/_run_state_store.py`
- `dayu/host/_conversation_memory_durable.py`
- `dayu/host/_tool_runtime.py`（仅在删除 `fetch_more` 外部入口时配套收紧 `_resolve_appender` 的 fallback 边界，使其在 durable 路径无 owner scope 时 fail fast）
- `dayu/host/_event_store.py`（仅当需要在 `PlainRunEventAppender` docstring 中明确禁用范围时）
- `tests/host/`（迁移 / 新增）
- `docs/host/README.md` 中的 dayu/host 概览（如分层文字与 P8 治理表述需更新）→ 实际目标是 `dayu/host/README.md`
- `dayu/host/README.md`
- `docs/host/design.md`
- `docs/host/phase8-plan.md`（recovery scan 策略变更时的「契约同步」段落）
- `docs/host/migration-plan.md`（如其中提及已删入口）
- `tests/README.md`
- `docs/reviews/code-review-20260510-0825.md` / `-0830.md` / `-0831.md`（添加 controller decision + fix status）

不允许触及：

- `dayu/engine/*`、`dayu/service/*`、`dayu/ui/*`、`dayu/fins/*`、`dayu/runtime/*`（除非测试 / 文档同步必须）；
- 任何 production 数据库或 workspace 目录；
- 不在本 work unit 范围的其它 P8 测试断言。

## Implementation Decisions

### D1 — `_handle_owner_lost` 走原子接口

- 入口：`AttemptSupervisor.append_terminal_and_close(owner_context, terminal_event_draft, target_state, reason_code, ...)`（已存在）。
- 行为：在同一 `BEGIN IMMEDIATE` 事务内：(a) `verify_owner` CAS；(b) append `host_run_events`；(c) update `host_attempts` 到 `LOST/FAILED`；CAS miss 时直接 ROLLBACK，**不写任何 RunEvent**。
- 调用方：`LocalRunHarness._handle_owner_lost` 在拿到 `active_attempt` 的 owner_context 后调用一次该接口；不再在 catch path 中执行裸 `event_store.append`。
- legacy（无 supervisor）路径同时下线（见 D5）。
- **RunStream stop 信号契约（F07 修复）**：
  - CAS hit（owner 仍有效）：`append_terminal_and_close` 在事务内写入 `RUN_FAILED(error_code=attempt_lease_lost)` terminal RunEvent，订阅方按事件流自然收到 terminal event 后 stream 自然结束（沿用现有 `_run_to_store` `terminal_seen` 退出路径）。
  - CAS miss（owner 已被 recovery 替换）：不写任何 RunEvent；harness 通过现有 `_run_to_store` 异常退出路径让上层 `stream_run_events` 的 async generator 自然 break；记 typed log（`host.run.attempt_lease_lost_cas_miss`）但不抛 user-visible error。
  - 不引入新的 typed close 事件、不引入新公开入口；现有 `RunStream` 关闭机制（async generator close + `_run_to_store` cleanup）足够。
  - 若实施期发现 CAS miss 路径无法让现有 generator 退出，停下问 controller，**禁止**新增公开 close 入口或写 stale RUN_FAILED 退路。

### D2 — Recovery scan = 诊断收口

- `_process_recovery_candidate` 不再调用 `mark_recovering_and_create_attempt`；只对旧 attempt 做 owner-aware diagnostic close（`AttemptSupervisor.close_attempt_with_diagnostic_state` 等价路径，不需要持有原 owner_token —— 因 supervisor 已经持有 lease_store + storage，直接 `update_state_owner_aware` 在 recovery scope 下用「lease 已过期 + state CAS」做 close）。
- `host_attempts` 收口字段：`state = LOST`、`stale_marked_at = now`、`failure_summary = 'recovery_lease_expired'` 或 `'recovery_created_orphan'`（D3 路径）。
- 不写 EventLog 终态（终态由原 owner 的 `append_terminal_and_close` 在收到 owner-lost 时尝试写；若原 owner 已彻底失联则 EventLog 上无 RUN_FAILED，由后续 P9 reconcile 入口覆盖）。
- **契约层级变更（F03 修复）**：
  - `AttemptRecoveryAction` 枚举仅保留 `MARK_LOST`、`NOOP_TERMINAL`；**删除 `MARK_RECOVERING_AND_CREATE_ATTEMPT`** 整套引用（含 enum 值、docstring 引用、tests / utils 引用）。
  - `AttemptRecoveryDecision` 字段：`action`、`source_attempt_id`、`reason`；**删除 `recovery_attempt_id` / `recovery_attempt_index`**；docstring 明确「P8 recovery scan 仅做旧 attempt 诊断收口；新执行 attempt 由上层重启 / 调度逻辑触发」。
  - `_attempt_supervisor.py:765-774` 的 typed log 字段调整为 `source_attempt_id` / `action` / `reason`。
- **`mark_recovering_and_create_attempt` 删除（F06 收敛）**：grep 已确认仅 supervisor + 自身专项测试 (`tests/host/test_phase8_attempt_recovery.py:365,510`) + `tests/host/test_phase8_multiprocess_stress.py:782-785` + `utils/smoke_host_p8_attempt_lease.py:283-340` 使用。
  - 在 `dayu/host/_run_state_store.py` 删除 `mark_recovering_and_create_attempt`、对应 docstring 引用、`AttemptStaleConflictError` 等仅服务该方法的 helper（保留 `close_attempt_with_diagnostic_state` 与 `update_state_owner_aware`）。
  - 在 `dayu/host/_attempt_supervisor.py:846` 删除调用点，整段 `_process_recovery_candidate` 改为按 candidate 状态分派 diagnostic close。
  - **`AttemptRecoveryDecision` 所有构造点**（grep `recovery_attempt_id=` 命中：`dayu/host/_run_state_store.py:1133/1145`、`dayu/host/_attempt_supervisor.py:905`）按新字段集（`source_attempt_id` / `action` / `reason`）重写（N03 修复）。
  - **同步删除** supervisor / lease store 中提及该 enum/方法的 docstring 段落与状态机叙述（grep 命中行：`dayu/host/_attempt_supervisor.py:735, 785, 796, 876`、`dayu/host/_run_state_store.py:822, 1064`），避免完成信号 grep 触发 stop condition（N04 修复）。
  - `tests/host/test_phase8_attempt_recovery.py` 中 6 处直接调用与 4 处 `recovery_attempt_id*` 断言全部改写为 diagnostic close 断言（详见 S5 测试矩阵）。
  - `tests/host/test_phase8_multiprocess_stress.py:686-786` 的 worker 协议改为只交换 `action` / `source_attempt_id` / `reason`，不再 expect 新 attempt id。
  - `utils/smoke_host_p8_attempt_lease.py:283-340` 删除 recovery 创建后续段，改为 `assert decision.action is MARK_LOST`。
- `docs/host/phase8-plan.md` 的 §recovery 段落同步更新（S10）。

### D3 — `list_recovery_candidates` 包含 CREATED orphan

SQL 修正为：

```sql
WHERE
  (state = 'running'  AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
  OR
  (state = 'created'  AND (lease_expires_at IS NULL OR lease_expires_at <= ?))
```

`_process_recovery_candidate` 收到 `CREATED` 行时走 D2 的 diagnostic close 分支（`reason_code = 'recovery_created_orphan'`）。

### D4 — `_allocate_fencing_token` fail-fast

```python
cursor = await conn.execute(...)
new_id = cursor.lastrowid
if new_id is None or new_id < 1:
    raise RuntimeError("fencing token allocation returned invalid lastrowid")
return FencingToken(value=int(new_id))
```

错误消息包含上下文（attempt_id / run_id），便于诊断。

### D5 — `_finish_attempt_if_durable` 删除 legacy fallback

- 该函数当前在没有 supervisor 时仍走 `attempt_state_store.update_state(...)` 路径并把 `terminal_event_position=None`。
- 用户裁决：production / durable 不允许 no-supervisor fallback。
- **改造**：
  - `LocalRunHarness.__init__` 新增显式 `is_durable: bool` 构造参数（见 D7）；
  - `_finish_attempt_if_durable` 收窄为 supervisor-only 单一分支，删除 `if self.attempt_state_store is None or self.storage is None: return` 与硬编码 `terminal_position = None` 的整段 legacy 逻辑（line 1807-1817）；
  - 当 `is_durable=True` 但 `attempt_supervisor is None` 或 `active_attempt.owner_context is None` 时 `raise RuntimeError("durable harness requires AttemptSupervisor + AttemptOwnerContext for finish_attempt")`；
  - 0830-F5 自动消除（已无 legacy 分支需要补 terminal_event_position）。
- 测试：依赖 legacy fallback 的测试（grep 显示 phase1 / phase2 / phase5 等 `start_run` 路径）改为显式构造 `LocalRunHarness(is_durable=False, attempt_state_store=...)` 或 `build_durable_harness()`（见 S9）。

### D6 — Public API surface 收窄

`dayu/host/__init__.py` 中删除：

- `start_run`、`stream_run_events`、`get_run_result`、`get_tool_fetch_more_handle`、`fetch_more_tool_result` 模块级转发。
- `__all__` 仅保留：`LocalRunHarness`、`build_durable_harness`、相关 contracts 与已审定的公开类型。

`dayu/host/_run_harness.py` 中删除：

- `LocalRunHarness.fetch_more_tool_result`（method）；
- `LocalRunHarness.get_tool_fetch_more_handle`（method，仅服务于 fetch_more 入口）；
- 模块级 `start_run` / `stream_run_events` / `get_run_result` / `get_tool_fetch_more_handle` / `fetch_more_tool_result`；
- `_default_harness_for_running_loop` / `_build_default_harness`（删除整个非 durable 默认装配链）；
- 模块 `__all__` 中相应项。

**InMemoryToolRuntime fetch_more 入口裁决（F02 修复）**：用户原话「framework fetch_more 仅作普通 tool call 经 ToolRuntimeToolExecutor → InMemoryToolRuntime.execute_tool_call」=> `InMemoryToolRuntime.get_tool_fetch_more_handle` 与 `fetch_more` 公开方法**全部删除**，仅保留内部 `execute_tool_call` 路径下经 ToolRuntimeToolExecutor 转译的 fetch_more 处理（`_append_fetch_requested` / `_append_fetch_completed` 等内部 helper 仍由 `execute_tool_call` 调用，保持 fenced append 不变）。

涉及调整的 ToolRuntime 入口：
- `dayu/host/_tool_runtime.py:695` `get_tool_fetch_more_handle`、`dayu/host/_tool_runtime.py:823+` 的 `async def fetch_more` 公开方法 —— 删除。
- 内部 `_append_fetch_requested` / `_append_fetch_completed` / `_append_cursor_issued` / `_append_cursor_denied` / `_append_cursor_expired` 仅作为 `execute_tool_call` 内部子例程保留，签名不外暴。

保留：`LocalRunHarness.start_run` / `stream_run_events` / `get_run_result`（实例方法），用作 Host kernel 接口；上层应通过 `build_durable_harness().harness` 使用。

### D7 — `_resolve_attempt_appender` fail-fast + `is_durable` invariant

**`LocalRunHarness` 显式 invariant（F04 修复）**：

- `LocalRunHarness.__init__` 新增 `is_durable: bool` **keyword-only 必填参数（无默认值）**。所有现有 `LocalRunHarness(...)` 构造点必须显式传值，否则 `TypeError` —— 这是装配方显式声明意图的强约束（N01 修复）。
- `is_durable=True` 时构造期断言：
  - `attempt_supervisor is not None`；
  - `event_store` 是 `DurableRunEventStore`（用 `isinstance` 检查 invariant —— **invariant 装配契约校验非类型逃避**，必须在该检查处加中文注释「invariant 校验：`isinstance` 用于装配契约校验，非类型分支判断；与 CLAUDE.md 禁止 `isinstance` 当类型逃避不冲突。」N05 修复）；
  - `attempt_state_store is None`（durable 路径不使用 P6 legacy store）；
  - `storage is not None`。
  违反 invariant raise `RuntimeError(f"durable harness invariant violated: ...")`。
- `is_durable=False` 时是 test-only 装配：禁止 `attempt_supervisor`；event_store 可以是 `InMemoryRunEventStore`；`PlainRunEventAppender` 仅服务该路径。
- `build_durable_harness` 装配时显式传 `is_durable=True`。

**`_resolve_attempt_appender` 行为**：

- `is_durable=True` 路径：必须能解析出 `AttemptOwnerContext`（来自当前 active_attempt 或 ContextVar），否则 raise `RuntimeError("durable harness requires AttemptOwnerContext for attempt-scoped append")`。**永不返回 PlainRunEventAppender**。
- `is_durable=False` 路径：返回 `PlainRunEventAppender`（test-only）。
- `PlainRunEventAppender` 类 docstring 加：`"test-only fallback; never used in durable harness; durable path always uses AttemptScopedRunEventAppender via AttemptSupervisor.scoped_appender"`。

**`InMemoryToolRuntime._resolve_appender` 行为（F08 双源优先级修复）**：

- `InMemoryToolRuntime.__init__` 新增 `is_durable: bool` 构造参数（与 harness 同源 —— `build_durable_harness` 传 `True`，test-only 装配传 `False`）。
- 解析顺序：
  1. `is_durable=True` 时，**必须**从 ContextVar 读到 `ToolRuntimeOwnerScope`，缺失 → `RuntimeError("durable runtime requires ToolRuntimeOwnerScope for attempt-scoped append")`；
  2. `is_durable=False` 时，ContextVar 存在且包含 owner scope → 返回 scoped appender（test-only owner-aware 模拟仍允许）；ContextVar 缺失 → 返回 `PlainRunEventAppender`。
- 这样 ContextVar 与 `is_durable` 的双源优先级明确：`is_durable=True` 是上限，ContextVar 是严格充要条件；`is_durable=False` 时 ContextVar 是 best-effort。

### D8 — Durable memory `_decode_snapshot` 校验 schema

```python
schema_version = payload.get("schema_version")
if schema_version is None:
    raise ValueError("snapshot_decode_failed:missing schema_version")
if int(schema_version) != _SCHEMA_VERSION:
    raise ValueError(
        f"snapshot_decode_failed:schema version mismatch: expected={_SCHEMA_VERSION} actual={schema_version}"
    )
```

不实现向后兼容读取（违反 schema 起库规则）；明确异常即可。

## Implementation Slices

每个 slice 完成后回报 controller，controller 才决定是否进入下一 slice 的 implementation/review 循环。

**Slice 顺序（F05 修复）**：先收紧边界（durable invariant + appender fail-fast），再删入口，再做原子化 owner-lost。理由：S1 把 invariant 立住后，S2 删入口期间任何残留的 plain-fallback 路径在 durable 测试上立即抛 RuntimeError，可阻止「测试通过但漏洞仍在」。

### Slice S1 — `LocalRunHarness` durable invariant + appender fail-fast

- **目标**：建立 `is_durable` 显式真源；durable 路径 plain fallback fail-fast；后续 slice 的契约前提。
- **允许文件**：`dayu/host/_run_harness.py`、`dayu/host/_event_store.py`、`dayu/host/_tool_runtime.py`、`dayu/host/_durable_harness.py`。
- **允许改动**（按 D7）：
  - `LocalRunHarness.__init__` 加 `is_durable: bool` **keyword-only 必填参数（无默认值）**；S1 同步把所有现有 `LocalRunHarness(...)` 构造点（包括 `build_durable_harness` 装配点 + S1 直接引用的 fixture：phase1 公开边界测试、phase8 supervisor / fencing / recovery / durable_memory_recovery 测试、`utils/smoke_host_p8_attempt_lease.py`）补全显式 `is_durable=...`；其余测试在 S2/S9 内补全（N01 修复）；
  - 构造期 invariant 校验（supervisor / event_store 类型 / attempt_state_store / storage 组合）；
  - `_resolve_attempt_appender` durable 路径无 owner_context 时 fail fast；
  - `PlainRunEventAppender` docstring 加禁用说明；
  - `InMemoryToolRuntime.__init__` 加 `is_durable: bool` 参数；`_resolve_appender` 按 D7 优先级；
  - `build_durable_harness` 装配时显式传 `is_durable=True`。
- **不允许**：删除任何 public API；改 supervisor / lease / state store 内部逻辑；改 owner-lost / recovery 路径。
- **测试**：
  - 新增 `tests/host/test_phase8_durable_invariant.py`：
    - `LocalRunHarness(is_durable=True, attempt_supervisor=None)` → `RuntimeError`；
    - `LocalRunHarness(is_durable=True, attempt_state_store=non_none)` → `RuntimeError`；
    - `LocalRunHarness(is_durable=True, event_store=InMemoryRunEventStore())` → `RuntimeError`；
    - `LocalRunHarness(is_durable=False, attempt_supervisor=non_none)` → `RuntimeError`；
  - `tests/host/test_phase8_tool_runtime_fencing.py` 增加：durable runtime ContextVar 缺 owner scope 调 `execute_tool_call` → `RuntimeError`；
  - 单元测试 `_resolve_attempt_appender(is_durable=True, owner=None)` 抛 RuntimeError；
  - `grep -n "PlainRunEventAppender" dayu/host/` 命中处必须只在 test-only 路径。
- **完成信号**：phase8 fencing/tool_runtime 测试通过；新 invariant 测试通过；pyright 干净。
- **stop**：发现 `build_durable_harness` 装配缺某 invariant 字段且无法直接补齐 → 停下问 controller。

### Slice S2 — Public API surface 收窄

- **目标**：删除所有诱导绕过 durable harness 的入口（含 ToolRuntime 公开 fetch_more 入口）。
- **允许文件**：`dayu/host/__init__.py`、`dayu/host/_run_harness.py`、`dayu/host/_tool_runtime.py`。
- **允许改动**（按 D6）：
  - `dayu/host/__init__.py` `__all__` 删除 5 个 legacy 名 + 删除 import；
  - `dayu/host/_run_harness.py` 删除 `LocalRunHarness.fetch_more_tool_result`、`LocalRunHarness.get_tool_fetch_more_handle`、模块级 5 个 helper、`_default_harness_for_running_loop` / `_build_default_harness`、模块 `__all__` 中相应项；
  - `dayu/host/_tool_runtime.py` 删除 `InMemoryToolRuntime.get_tool_fetch_more_handle` / `fetch_more` 公开方法；保留 `_append_fetch_*` / `_append_cursor_*` 内部 helper（仍由 `execute_tool_call` 调用）。
- **测试迁移（具体到文件）**：
  - `tests/host/test_phase1_public_boundary.py:57-59`：从 expected `__all__` 移除 `fetch_more_tool_result` / `get_tool_fetch_more_handle`；新增反向断言 `not in __all__`。
  - `tests/host/test_phase1_run_harness.py`、`tests/host/test_phase5_multiturn_no_governance_smoke.py`、`tests/host/test_phase2_tool_runtime_eventlog.py`、`tests/host/test_phase2_tool_runtime_truncation.py`、`tests/host/test_phase2_tool_runtime_boundary.py`：
    - 凡是 `from dayu.host import start_run / stream_run_events / get_run_result / get_tool_fetch_more_handle / fetch_more_tool_result` 改为 `from dayu.host import LocalRunHarness` 后构造 `LocalRunHarness(is_durable=False, ...)`；
    - 凡是 `runtime.get_tool_fetch_more_handle(...)` 改为通过 `runtime.execute_tool_call(...)` 走标准 fetch_more 工具调用路径；
    - `test_phase5_multiturn_no_governance_smoke.py:524,539` 走 `harness.execute_tool_call`。
  - `utils/smoke_host_tool_runtime.py:246,263,285` 改为 `execute_tool_call` 路径或在与 P8 装配契约不兼容时删除。
  - `utils/smoke_host_multiturn_no_governance.py`、`utils/smoke_engine_worker.py` 检查并迁移 import。
- **新增测试**：`tests/host/test_host_public_api_surface.py`：
  - 断言 `dayu.host.__all__` 不含 5 个 legacy 名；
  - 断言 `getattr(dayu.host, name, None) is None`；
  - 断言 `getattr(LocalRunHarness, "fetch_more_tool_result", None) is None` 且 `getattr(LocalRunHarness, "get_tool_fetch_more_handle", None) is None`；
  - 断言 `getattr(InMemoryToolRuntime, "get_tool_fetch_more_handle", None) is None` 且 `getattr(InMemoryToolRuntime, "fetch_more", None) is None`。
- **完成信号**：
  - `pytest tests/host -q` 通过；
  - `grep -RIn "fetch_more_tool_result\|get_tool_fetch_more_handle\|_default_harness_for_running_loop" dayu tests utils` 仅出现在 `test_host_public_api_surface.py` 反向断言；
  - pyright 干净。
- **stop**：grep 命中 `dayu/cli/`、`dayu/service/`、`dayu/ui/`、`dayu/fins/`、`dayu/runtime/` 内任何调用 → 停下问 controller。

### Slice S3 — `_handle_owner_lost` 走 `append_terminal_and_close`

- **目标**：消除 0830-F1 / 0831-F001 / 0825-F01。
- **允许文件**：`dayu/host/_run_harness.py`、`dayu/host/_attempt_supervisor.py`（仅在 `append_terminal_and_close` API 需要小调整时）。
- **允许改动**（按 D1）：
  - `_handle_owner_lost` 用 `supervisor.append_terminal_and_close` 替代 `_finish_attempt_if_durable` + 裸 `event_store.append`；
  - CAS miss 时不写任何 fact，只记 typed log；
  - 不引入新公开 close 入口（详见 D1 RunStream 契约）。
- **测试矩阵（F01 修复）**：
  - **Case A — owner CAS hit**：
    - EventLog 出现恰 1 条 `RUN_FAILED(error_code=attempt_lease_lost)` terminal RunEvent；
    - `host_attempts.state == LOST`、`terminal_event_position is not None`、`failure_summary` 以 `attempt_lease_lost:` 开头；
    - RunStream 订阅方收到 terminal event 后 generator 自然结束。
    - **改写位置**：`tests/host/test_phase8_attempt_supervisor.py:1151-1342` 现有 `_handle_owner_lost` case 改为 Case A 形态，保持 `host_data.error_code == "attempt_lease_lost"` / `summary.startswith("attempt_lease_lost:")` 断言。
  - **Case B — owner CAS miss**：
    - 构造：先用 supervisor 内部 helper 模拟 recovery 把旧 attempt 推到 `LOST`，再触发旧 owner 的 `_handle_owner_lost`；
    - EventLog **不**新增 `RUN_FAILED`；
    - `host_attempts.state` 保持 recovery 推进后的值；
    - RunStream generator break 但不抛 user-visible 异常；
    - typed log 出现 `host.run.attempt_lease_lost_cas_miss`。
  - 新增测试位置：`tests/host/test_phase8_attempt_supervisor.py::test_handle_owner_lost_cas_miss_no_stale_terminal`。
- **完成信号**：phase8 supervisor / fencing 测试全绿；`grep -n "self.event_store.append(host_failure_draft" dayu/host/_run_harness.py` 命中数为 0。

### Slice S4 — `_finish_attempt_if_durable` legacy 分支移除

- **目标**：消除 0830-F5 与 D5。
- **允许文件**：`dayu/host/_run_harness.py`；测试。
- **允许改动**：
  - 删除 line 1807-1817 legacy 分支；
  - `_finish_attempt_if_durable` 收窄为「supervisor + owner_context 均有时执行 owner-aware diagnostic close」；
  - `is_durable=True` 但 supervisor / owner_context 缺失 → raise；`is_durable=False` 路径下 noop。
- **测试**：
  - phase8 fencing / supervisor 现有 case；
  - 新增：`is_durable=True` + `attempt_supervisor=None` 的 finish 路径触达时 raise。
- **完成信号**：pyright 干净；相关测试通过；`grep -n "terminal_position: GlobalEventPosition | None = None" dayu/host/_run_harness.py` 命中数为 0。

### Slice S5 — Recovery scan 诊断收口语义

- **目标**：消除 0831-F002。
- **允许文件**：`dayu/host/_attempt_supervisor.py`、`dayu/host/_attempt_lease.py`、`dayu/host/_run_state_store.py`、recovery 测试 / smoke。
- **允许改动**（按 D2）：
  - `AttemptRecoveryAction` 删除 `MARK_RECOVERING_AND_CREATE_ATTEMPT`，仅保留 `MARK_LOST` / `NOOP_TERMINAL`；
  - `AttemptRecoveryDecision` 删除 `recovery_attempt_id` / `recovery_attempt_index`，新增 `source_attempt_id`；
  - `_process_recovery_candidate` 改为按 candidate state 分派 diagnostic close（`RUNNING + lease 过期` → `MARK_LOST` + `recovery_lease_expired`；`CREATED + lease NULL` → `MARK_LOST` + `recovery_created_orphan`；run terminal → `NOOP_TERMINAL`）；
  - 删除 `AttemptLeaseStore.mark_recovering_and_create_attempt` 与仅服务它的 helper（`AttemptStaleConflictError` 等）；
  - 同步更新 `_attempt_supervisor.py:765-774` typed log 字段。
- **测试矩阵（F03 修复）**：
  - 改写 `tests/host/test_phase8_attempt_recovery.py:167,190-194,213,259,313,370-379,450,510-515,609-610`：
    - 删除所有 `recovery_attempt_id` / `recovery_attempt_index` 断言；
    - 改为断言 `decision.action is AttemptRecoveryAction.MARK_LOST`、`decision.source_attempt_id == old_attempt_id`、`decision.reason in {"recovery_lease_expired", "recovery_created_orphan"}`；
    - 新增「scan 后 host_attempts 不出现新行」「scan 幂等」「CREATED orphan → MARK_LOST」三个 case。
  - 改写 `tests/host/test_phase8_multiprocess_stress.py:686-786`：worker 协议字段调整为 `source_attempt_id` / `action` / `reason`；改为多进程 race 下旧 attempt 最终 `LOST` 且无新 RUNNING 行。
  - 改写 `utils/smoke_host_p8_attempt_lease.py:283-340`：删除 recovery 后续段，改为 `assert decision.action is MARK_LOST` 后退出。
- **完成信号**：`pytest tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_multiprocess_stress.py -q` 全绿；smoke 通过；`grep -RIn "MARK_RECOVERING_AND_CREATE_ATTEMPT\|mark_recovering_and_create_attempt\|recovery_attempt_id\|recovery_attempt_index" --include='*.py'` 结果为空；`grep -RIn "recovery_attempt_id=" dayu` 结果为空（N03 验证）。

### Slice S6 — `list_recovery_candidates` 包含 CREATED orphan

- **目标**：消除 0830-F2。
- **允许文件**：`dayu/host/_run_state_store.py`、recovery 测试。
- **允许改动**：D3 SQL 调整。
- **测试**：构造 `state='created' AND lease_expires_at IS NULL` 行 + 调 `recover_stale_attempts` → 行被关到 `LOST`，decision.reason = `recovery_created_orphan`。
- **完成信号**：phase8 recovery 测试通过。

### Slice S7 — `_allocate_fencing_token` fail-fast

- **目标**：消除 0830-F3。
- **允许文件**：`dayu/host/_run_state_store.py`、对应测试。
- **允许改动**：D4 实现。
- **测试矩阵（F10 修复）**：
  - fake cursor 模拟 `lastrowid=None` / `0` → 抛 `RuntimeError`，错误信息含 attempt_id / run_id；
  - `acquire_new_attempt` 触发 fail-fast 时：`host_attempts` 行未插入；`host_fencing_tokens` 行未插入；调用方观测到 `RuntimeError`；
  - `FencingToken.__post_init__` 不再被触达。
- **完成信号**：fencing 测试通过；pyright 干净。

### Slice S8 — Durable memory schema_version 校验

- **目标**：消除 0830-F4。
- **允许文件**：`dayu/host/_conversation_memory_durable.py`、对应测试。
- **允许改动**：D8 实现；同步 `_encode_snapshot` / `_decode_snapshot` docstring。
- **测试**：schema_version=2 → `ValueError("...expected=1 actual=2")`；缺失字段 → `ValueError("...:missing schema_version")`；schema_version=1 round-trip 通过。
- **完成信号**：memory recovery 测试通过。

### Slice S9 — 测试整体迁移与新增

- **目标**：把 S1-S8 实施期未触达的剩余测试迁移完整；补齐 `_memory_store_fake` 等基础设施覆盖率。
- **允许文件**：`tests/host/`、`utils/smoke_host_p8_attempt_lease.py`。
- **允许改动**：
  - 替换剩余 `from dayu.host import start_run` 等 import 为 `LocalRunHarness(is_durable=False, ...)` 或 `build_durable_harness`；
  - `tests/host/_memory_store_fake` 增加最小行为一致性断言（snapshot round-trip 与 durable store 等价）—— 实施成本高时记入 residual risk follow-up（owner: P9）。
- **完成信号**：`pytest tests/host -q` 全绿；`python utils/smoke_host_p8_attempt_lease.py` 通过。

### Slice S10 — 文档与 review artifact 同步

- **目标**：按 AGENTS.md README 触发规则同步；为每个 review artifact 添加 controller decision 与 fix status。
- **允许文件**：
  - `dayu/host/README.md`、`docs/host/design.md`、`docs/host/phase8-plan.md`、`docs/host/migration-plan.md`、`tests/README.md`；
  - `docs/reviews/code-review-20260510-0825.md` / `-0830.md` / `-0831.md`。
  - 注：`dayu/README.md` 在当前仓库不存在（已实地核验，N02 修复），不在 grep / 同步范围内；CLAUDE.md README 触发规则也未把 host 包修改映射到该文件。
- **改动**：
  - 删除 README / design.md / phase8-plan.md 中提及 5 个 legacy 名的段落；改写为「通过 `build_durable_harness()` 装配」；
  - phase8-plan.md recovery 段落改为「诊断收口」；
  - migration-plan.md 删除 legacy 入口章节；
  - 在每个 review finding 末尾追加：
    - `**Controller Decision**: accepted | rejected-with-reason | deferred-with-reason`；
    - `**Fix Status**: fixed in S<n> (commit hash) | rejected (cite AGENTS schema policy) | deferred (cite CAS-truth-in-DB)`；
  - rejected/deferred rationale 块（预先草拟）：
    - **0825-F02 schema-migration rejected**：「按 AGENTS.md 与 CLAUDE.md `## schema 变更` 章节规则：『一律按全新 schema 起库处理；禁止旧库兼容读取、兼容测试』。本 work unit 未明确要求兼容升级，因此不实现 ALTER TABLE 迁移逻辑。升级路径由 dayu-cli init 流程负责（见 migration-plan.md）。」
    - **0825-F03 scoped-appender stale-snapshot deferred**：「`AttemptOwnerContext.lease_expires_at` 为 acquire 时快照；`verify_owner` CAS 真源是 DB 当前 `lease_expires_at` 字段（详见 `_run_state_store.py:verify_owner` SQL）。该字段不影响 CAS 正确性，仅诊断字段语义；不在本 work unit 范围内修复。S10 同步在 `AttemptOwnerContext` docstring 中加入说明。」
  - 三份 review artifact 的 residual risk 必须有 owner（指向具体 slice / P9 / 已存在的 issue）。
- **完成信号**：`grep -RIn "start_run\|stream_run_events\|fetch_more_tool_result\|get_run_result\|get_tool_fetch_more_handle" docs/host/ dayu/host/README.md` 不出现 legacy 入口；review artifact 状态完整。

## Tests & Validation

### Per-slice tests

每个 slice 在「Implementation Slices」中已列出。

### 全量验证

```
source .venv/bin/activate
pytest tests/host/test_phase8_attempt_fencing.py \
       tests/host/test_phase8_attempt_supervisor.py \
       tests/host/test_phase8_attempt_recovery.py \
       tests/host/test_phase8_tool_runtime_fencing.py \
       tests/host/test_phase8_durable_memory_recovery.py -q
pytest tests/host -q
python utils/smoke_host_p8_attempt_lease.py
python -m pyright dayu/host tests/host utils
git diff --check
```

所有命令必须通过；任何失败都需在当前 slice 修复或回报 controller。

## Documentation Update Decision

按 AGENTS.md 触发规则，本 work unit 仅同步：

- `dayu/host/README.md`（host 包修改）
- `docs/host/design.md`（Host 架构边界 / 治理边界变化）
- `docs/host/phase8-plan.md`（recovery 策略变更）
- `docs/host/migration-plan.md`（删除 legacy 入口章节）
- `tests/README.md`（如测试分层 / 公开 API surface 测试新增需说明）
- 三份 review artifact

不更新：根 `README.md`（用户手册，本次不涉及 CLI/render 入口变化）；`dayu/README.md`（分层未变）；`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`（未触及）。

## Review Gates

- 本 plan 完成后进入 plan review（`$planreview` 优先；若不可用，由 controller 直接按 plan-review criteria 走）。
- 每个 implementation slice 后进入 code review → fix → re-review；通过且用户确认后 controller 自动创建 accepted slice commit。
- 全部 slice 完成后进入 user additional code review → PR review → final closeout。

## Open Questions

无 blocking open questions（用户已对所有架构裁决预先决定）。

Non-blocking working assumption：

- A1：`mark_recovering_and_create_attempt` 是否完全删除依据 `grep` 结果决定。如果除 supervisor 外没有合法使用方，S5 一并删除；否则保留 store 方法但 supervisor 不再调用。低风险（实现期可微调），不阻塞 plan。
- A2：`_finish_attempt_if_durable` 的「test-only 非 durable supervisor 桩分支」是否保留依据 grep 实际测试使用判断；若所有测试都能改为 `LocalRunHarness(durable=True, supervisor=fake_supervisor)`，则该方法收窄为 supervisor-only 单一分支。低风险。

## Risks & Residual

- **R1**：删除 `_default_harness_for_running_loop` 后，若 `dayu/cli/`、`dayu/service/`、`dayu/ui/` 或 `utils/` 中有依赖 package-level convenience 的代码，会编译失败。**Owner**：S1，grep 后明确迁移点；若发现非测试调用方，停下问 controller。
- **R2**：`_handle_owner_lost` 改为 atomic close 后，已订阅 RunStream 的客户端在旧 owner 失活时不再收到 RUN_FAILED；需确认 RunStream 在 owner-lost 时的 close/timeout 信号。**Owner**：S3 测试覆盖；如果发现需要新增 stream close 信号，纳入 S3 实施而非新增公开入口。
- **R3**：recovery scan 不再创建 RUNNING recovery attempt，意味着 P8 不能自愈到「新 attempt 继续执行」；上层调度 / 重启逻辑需要在 P9 或外部装配显式触发。**Owner**：S10 phase8-plan.md 段落明确说明，并在 review artifact residual risk 中指向 P9。
- **R4**：`_decode_snapshot` 严格校验 schema_version 后，回滚部署立即报错；这是 AGENTS schema 起库政策的直接后果。**Owner**：S8 文档说明；不留后门。
- **R5**：`tests/host/_memory_store_fake` 与 `_multiprocess_platform` 的覆盖率仍未单独断言。**Owner**：S9 中决定是否补 round-trip 等价测试；若实施成本高，定 issue 推到 P9。

## Stop Conditions

任何 slice 触发以下情况必须停下回报 controller，不得自行扩大 scope：

- grep 显示 production 层（非测试 / 非 utils）依赖被删 public API；
- review artifact 中存在与裁决冲突的新发现；
- 删除 `_default_harness_for_running_loop` 后 `build_durable_harness` 装配链需要新增非平凡接口；
- 测试发现 `_handle_owner_lost` 原子化路径与现有 `append_terminal_and_close` API 形态不兼容；
- pyright 出现新增报错且无法在当前 slice 内闭环。

## Completion Report Format

每个 slice 完成后回报 controller 时必须包含：

1. slice id 与 root cause 定位；
2. 实际修改文件列表；
3. 与 plan 偏差及理由（若无偏差注明 "无偏差"）；
4. 当前 slice 通过的验证命令与结果；
5. residual risk 分类（修复 / 转交后续 slice / 转交后续 phase / issue / 用户决定）；
6. 是否可启动下一 slice；
7. 是否需要 controller 介入。

最终 work-unit closeout 报告必须额外包含：

- 每个 review finding 的 controller decision 状态与 fix slice 编号；
- public export 变化清单（删除 / 新增）；
- 文档同步清单；
- 三份 review artifact 的最终 status；
- 完整验证结果（pytest / smoke / pyright / git diff --check）；
- residual risks 清单与 owner；
- 下一 work unit 入口（若有，例如 P9 lifecycle/admission）。
