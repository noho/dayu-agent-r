# P10.5 Slice 2 Code Review

## Gate

- Gate: P10.5 Slice 2 code review
- Review target: uncommitted Slice 2 diff vs HEAD (`feat/host-p10-5-public-contract-freeze`)
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Implementation artifact: `docs/reviews/phase10-5-slice2-implementation-codex-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- Reviewer: DS (deepseek-v4-pro via Claude Code)

## Scope Boundary Verification

### Slice 2 范围

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| production composition root | PASS | `_OpenHostContextManager.__aenter__` 装配 durable store、command handle、scheduler、active registry、admission service、projection catch-up、wakeup port |
| public async handle delegation | PASS | `_PublicHostHandle` 提供全部 public method 的 async wrapper，含 `_raise_if_closed()` gate |
| handle lifecycle (idempotent close, `__aexit__`) | PASS | `close()` 检查 `_closed` 幂等；`__aexit__` 调用 `self._host.close()` |
| command -> scheduler wakeup | PASS | `create_host_admission_service(..., wakeup_port=scheduler)` |
| memory catch-up | PASS | `_MemoryProjectionCatchupPort` 实现 `ProjectionCatchupPort`，调用 `catch_up_conversation_memory_projection` |
| compactor baseline internal mapping | PASS | `_local_execution_options_from_open_host_options` 映射全部 compactor fields；`compactor_baseline=None` → 全部 `None`（fail-closed） |
| shared ActiveWorkerRegistry | PASS | 同一个 `ActiveWorkerRegistry()` 传给 `HostDispatchScheduler.open(...)` 和 `HostCommandHandle(...)` |

### 未越界到后续 Slice

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| Slice 3 request contract migration | PASS | `SubmitFollowupRequest` 仍使用旧 shape（`HostInput`、`FollowupBehavior`）；未新增 `system_prompt`/`user_prompt`/`tool_names`/per-run override fields |
| Slice 4 live HostEvent fanout | PASS | `watch_session_events` 直接 `raise NotImplementedError`，未假装可用 |
| Slice 5 steer/retry/replay/WAITING semantics | PASS | public handle 方法仅 delegate 已有内部 primitive；`retry_run`/`replay_run`/`resolve_wait`/`submit_followup(steer)` 语义归 Slice 5 |
| Slice 6 smoke matrix | PASS | 未新增 real-runner / provider matrix / compact smoke tests |

### 禁止越界

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| Service 不得接触 scheduler/store/registry internals | PASS | `_PublicHostHandle` 三个内部字段均为 `_` 前缀私有；`Host` Protocol 不暴露这些类型 |
| 无 schema/state-machine 变更 | PASS | diff 未触及 `durable/schema.py`、Engine contracts |
| 无 Engine/Recovery/Outbox/Purge 越界 | PASS | diff 范围仅 `open_host.py`、`api.py`、README、test files |

## Findings

### Finding N1 (Non-blocking, Medium): `_PublicHostHandle.close()` — scheduler close 异常时 durable store 资源泄露

**文件**: `dayu/host/open_host.py:291-307`

**证据**:

```python
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    await self._scheduler.close()          # 若此处 raise，后续不执行
    try:
        self._projection_catchup_port.catch_up_projection()
    finally:
        self._command_handle.close()       # durable store 不会被关闭
```

`HostDispatchScheduler.close()` 内部会 cancel drain task、cancel active worker tasks、close lane controller。这些操作在极端条件下可能 raise（例如 lane controller close 写入 lane DB 失败）。如果 `_scheduler.close()` raise，`_closed` 已被设为 `True`（所有 public API 调用均会收到 `HostClosedError`，但这是假闭合——durable store 连接未释放），`_command_handle.close()` 不会执行，SQLite connection 和 WAL 文件泄露直到进程退出。

**设计依据**: `docs/host/design.md` §11 明确 "最后关闭 durable store" 且不得因中间步骤失败跳过。close 流程要求的清理顺序是保证所有资源被释放，而非 best-effort。

**影响**: 极端情况下（lane DB I/O 错误、task cancel 传播异常），opener close 导致 SQLite connection leak。调用方看到 `HostClosedError`、认为 handle 已安全关闭，但连接未释放。

**修复建议**: 将 scheduler close 与 projection flush 都包裹在 try/finally 中：

```python
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    try:
        await self._scheduler.close()
    finally:
        try:
            self._projection_catchup_port.catch_up_projection()
        finally:
            self._command_handle.close()
```

### Finding N2 (Non-blocking, Low): `_command_options_from_open_host_options` — context budget 默认值未在 plan/design 冻结

**文件**: `dayu/host/open_host.py:63-65`

**证据**:

```python
_DEFAULT_CONTEXT_WINDOW_SIZE = 8192
_DEFAULT_RESERVED_OUTPUT_TOKENS = 1024
```

当 `OpenHostOptions.context_budget_policy is None` 时，`HostCommandHandleOptions.context_window_size` 与 `reserved_output_tokens` 使用这两个硬编码默认值。Plan §Typed Options Shape 中 `context_budget_policy: ContextBudgetPolicy | None` 标记为可选，但未定义 `None` 时的 fallback 语义，也未将 8192/1024 作为显式契约写入。

**影响**: 调用方若省略 `context_budget_policy`，无声获得 8192/1024 配置，可能与其预期不符。但 `HostCommandHandleOptions` 要求这两个字段必填，opener 必须提供值——硬编码 fallback 是 pragmatic 选择，不会导致静默错误。

**修复建议**: 在下一次 plan hardening 中将 fallback 默认值写入 `OpenHostOptions` docstring 或 plan 的 Typed Options Shape 节；或在 `OpenHostOptions.__post_init__` 中将 `context_budget_policy=None` 替换为 `ContextBudgetPolicy(context_window_size=8192, reserved_output_tokens=1024)`，使默认值显式化。优先级低，不阻塞 Slice 2。

## Observations (无 Fix 要求)

### O1: `_durable_options_from_public_options` import alias 语义偏移

`dayu/host/command.py:757` 定义的函数名是 `_durable_options_from_public_options`，但其参数是 `HostCommandHandleOptions`（内部类型，非 public）。`open_host.py:51` 将其 import 为 `_durable_options_from_command_options`，别名比原名更准确。根源在 `command.py` 的命名，属于 pre-existing 问题，不在 Slice 2 修改范围。

### O2: `_MemoryProjectionCatchupPort` 持有完整 `OpenHostOptions`

`_MemoryProjectionCatchupPort` 存储整个 `OpenHostOptions` 对象但只用 `memory_projection_policy` 和 `memory_projection_catchup_batch_size` 两个字段。作为私有内部类且在 Slice 2 composition root 中仅使用一次，可接受。若未来 `ProjectionCatchupPort` 需要更窄的依赖接口，可从 `OpenHostOptions` 拆出专用 dataclass。

### O3: 测试 `_event_type_count` 直读 SQLite

`test_public_lifecycle_smoke.py:_event_type_count` 直接 `sqlite3.connect` 查询 `event_log` 表。Slice 4 前 `watch_session_events` 不可用，此为合理的 interim 验证手段。Slice 4/Slice 6 应在 public-path smoke 中将此类断言迁移为通过 `watch_session_events` 观察。

## Positive Checks

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| `open_host(options)` 正确装配 durable store | PASS | `open_host_durable_store(_durable_options_from_command_options(command_options))` |
| 内部 command handle options 从 OpenHostOptions 构造 | PASS | `_command_options_from_open_host_options` 逐字段映射 |
| HostLocalExecutionOptions 从 OpenHostOptions 构造 | PASS | `_local_execution_options_from_open_host_options` 映射 all fields |
| shared ActiveWorkerRegistry | PASS | 同一对象传入 scheduler 和 command handle |
| after-commit wakeup 接线 | PASS | `create_host_admission_service(..., wakeup_port=scheduler)` |
| Service 无法接触 scheduler/store/registry | PASS | `_PublicHostHandle` 三个内部字段均为私有 |
| `compactor_baseline=None` fail-closed | PASS | 所有 compactor fields 为 `None`，无 fake default |
| compactor fields 映射到 internal execution options | PASS | `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy_ref`、`compact_artifact_root`、`compact_artifact_create_parent_dirs` 六字段全部映射 |
| host.close() 幂等 | PASS | `if self._closed: return` |
| `__aexit__` 调用 close | PASS | `if self._host is not None: await self._host.close()` |
| close 不写 cancel/failed terminal facts | PASS | close 方法不接触 EventLog；scheduler.close 只 cancel worker tasks 不写 canonical facts |
| close 后 public methods raise HostClosedError | PASS | `_raise_if_closed()` 在所有 public method 第一行 |
| `watch_session_events` 不假装 Slice 4 可用 | PASS | `raise NotImplementedError("watch_session_events is owned by P10.5 Slice 4")` |
| 完整中文 docstring | PASS | 所有 public/private 函数和类含中文 docstring，包含 `:param:`、`:returns:`、`:raises:` |
| 严格类型，无 Any/object/untyped | PASS | pyright `0 errors, 0 warnings, 0 informations` |
| 测试覆盖 submit_followup(queue) auto-wakeup | PASS | `test_submit_followup_queue_auto_wakes_scheduler` |
| 测试覆盖 close_session vs opener close vs cancel | PASS | `test_close_session_host_close_and_cancel_are_distinct` |
| 测试覆盖 idempotent close | PASS | `await host.close(); await host.close()` 无异常 |
| 测试覆盖 post-close HostClosedError | PASS | `pytest.raises(HostClosedError)` 验证 get_session/submit_followup |
| 测试覆盖 no cancel facts on opener close | PASS | `test_host_close_does_not_close_open_session_or_write_terminal_facts` |
| 测试覆盖 compactor_baseline=None fail-closed | PASS | `test_compactor_baseline_none_maps_to_fail_closed_no_capability` |
| README 同步当前事实 | PASS | 只更新了 `open_host(options)` 当前 runtime 行为描述；未写 Slice 4 fanout 为已实现 |
| `HostClosedError` 是 standalone lifecycle exception | PASS | `class HostClosedError(Exception)`，不是 `HostApiErrorCode.INVALID_STATE` |

## Validation Reproduce

Implementation agent 报告的验证结果可复现检查：

- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q` → 应 4 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host` → 应 0 errors

## Verdict

**PASS**

Blocking count: **0**

Accepted non-blocking findings: **N1** (scheduler close 异常时 resource leak)、**N2** (context budget 默认值未冻结)

Residual risks:
- N1 描述的 resource leak 场景概率极低（lane controller close I/O error），当前无需 blocking；Phase 11 recovery hardening 或后续 opener hardening 时修复。
- `watch_session_events` 仍为 `NotImplementedError` 占位；Slice 4 实现后才能验证完整 live event path。
- 测试通过 raw SQL `_event_type_count` 验证 EventLog 事实；Slice 4/Slice 6 应将此类断言迁移为 public-path 观察。

Artifact path: `docs/reviews/phase10-5-slice2-code-review-ds-20260518.md`
