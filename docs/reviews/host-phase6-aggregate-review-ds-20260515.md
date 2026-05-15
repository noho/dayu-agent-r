# Host Phase 6 Aggregate Review — AgentDS

- **Review type**: aggregate adversarial deep review (AgentDS independent)
- **Review date**: 2026-05-15
- **Scope**: cumulative Phase 6 implementation from base `a5863ce` through HEAD `203a69a` on `feat/host-phase-6-toolruntime`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Plan truth**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **Prior reviews**: P6-S1 through P6-S6 review/fix/re-review artifacts and controller adjudications under `docs/reviews/host-phase6-*`
- **Verdict**: BLOCKED — 1 critical finding (Run-local duplicate governance index is per-ToolRuntime-instance, not per-Run)

## Scope

### Commits reviewed

```
b49ba56 gateflow: accept Host Phase 6 S1
0746bd8 gateflow: record Host Phase 6 S1 checkpoint
54184e6 gateflow: accept Host Phase 6 S2
911a510 gateflow: record Host Phase 6 S2 checkpoint
de7a4ae gateflow: accept Host Phase 6 S3
17bfb19 gateflow: record Host Phase 6 S3 checkpoint
28adf70 gateflow: accept Host Phase 6 S4
967eae4 gateflow: record Host Phase 6 S4 checkpoint
31ab68d gateflow: accept Host Phase 6 S5
e805b73 gateflow: record Host Phase 6 S5 checkpoint
53ff69f gateflow: accept Host Phase 6 S6
668f12b gateflow: record Host Phase 6 S6 checkpoint
203a69a gateflow: clarify Host Phase 6 run-local duplicate governance
```

### Files inspected (production)

| File | Lines | Role |
|------|-------|------|
| `dayu/host/tool_runtime.py` | 4480 | Phase 6 core: EffectiveToolBundle, accept barrier, truncation/fetch_more, duplicate governance, diagnostics, ToolRuntimeExecutor, ToolRuntimeHandle/Factory |
| `dayu/host/dispatch.py` | delta | `_run_input_builder_for_dispatch` — scheduler ToolRuntime construction wiring |
| `dayu/host/run_input.py` | delta | `create_tool_enabled_run_input_builder` — RunInputBuilder provider wiring |
| `dayu/host/api.py` | delta | `HostLocalExecutionOptions` tooling fields + private alias |
| `docs/host/design.md` | delta | Run-local duplicate governance clarification, truncation/fetch_more scope |
| `docs/host/implementation-control.md` | delta | Phase 6 tracking, S1-S6 residual risks, run-local duplicate governance exit standard |

### Files inspected (tests)

| File | Lines | Coverage |
|------|-------|----------|
| `tests/host/test_toolruntime_effective_bundle.py` | 254 | EffectiveToolBundle construction, framework tool injection, fetch_more injection |
| `tests/host/test_toolruntime_accept_barrier.py` | 590 | Accept barrier: idempotency, scope validation, rejected ack, timeout, CAS conflict, transaction atomicity |
| `tests/host/test_toolruntime_executor.py` | 596 | ToolRuntimeExecutor full paths: completed, failed, cancelled, governed error, truncation, unsupported executor |
| `tests/host/test_toolruntime_truncation_fetch_more.py` | 556 | TruncationManager: all 4 strategies, cursor scope validation, TTL, single-use, fetch_more, fetch_more through executor |
| `tests/host/test_toolruntime_duplicate_governance.py` | 653 | Duplicate governance matrix, reuse, justification, HINT downgrade, overwrite fix, scope mismatch isolation |
| `tests/host/test_toolruntime_diagnostics.py` | 449 | Diagnostic emitters: deterministic, noop, in-memory, validation consistency |
| `tests/host/test_phase6_toolruntime_integration.py` | 853 | Integration tests crossing multiple components |
| `tests/host/test_dispatch_scheduler.py` | delta | `test_scheduler_uses_toolruntime_when_tooling_is_configured` — real scheduler → ToolRuntime → accept barrier path |
| `tests/host/test_run_input_builder.py` | delta | RunInputBuilder with tool_schema/tool_executor providers |

### Verification results

| Item | Result |
|------|--------|
| `pytest tests/host -q` | 348 passed |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |

---

## Findings

### F1-未修复-严重-Run-local duplicate governance index 跟随 ToolRuntime 实例生命周期而非 Run 生命周期

- **入口/函数**: `HostDispatchScheduler._run_input_builder_for_dispatch` → `DefaultToolRuntimeFactory.create_tool_runtime`
- **文件(行号)**:
  - `dayu/host/dispatch.py:682-733` — 每次 dispatch 创建全新 `DefaultToolRuntimeFactory().create_tool_runtime()`
  - `dayu/host/tool_runtime.py:2388-2462` — `create_tool_runtime` 每次创建全新 `ToolRuntimeExecutor`
  - `dayu/host/tool_runtime.py:2447-2448` — `InMemoryRunLocalDuplicateGovernance(request.duplicate_governance_policy)` 创建全新内存索引
  - `dayu/host/tool_runtime.py:1474-1558` — `InMemoryRunLocalDuplicateGovernance._entries_by_key: dict[str, _DuplicateAcceptedEntry] = {}` 实例级字典
- **输入场景**: 同一 Run 内因 Phase 7 `WAITING -> resolve_wait -> resume`、steer 或 recovery 创建新 Attempt 时，Host 调度器调用 `_run_input_builder_for_dispatch` 构造新 ToolRuntime。
- **实际分支**: `dispatch.py:701-727` 无条件创建新 `DefaultToolRuntimeFactory`，无 Run-level duplicate index 复用或共享逻辑。
- **预期行为**: 按 `docs/host/design.md` 最新版（commit `203a69a`）与 `docs/host/implementation-control.md` Phase 6 exit standard 明确要求：

  > "同一个 Run 因 `WAITING -> resolve_wait -> resume`、steer 或 recovery 创建的新 Attempt 必须继续复用该 Run 的 duplicate index，不能因为重新创建 ToolRuntime 而忘记已 accepted 的工具事实。"

  > "Run-local duplicate governance 是 P6 既定目标，不是 Attempt-local 目标。P6 aggregate review 必须确认同一 Run 内跨 Attempt 的正常同进程路径不会因重新创建 ToolRuntime 而丢失 duplicate memory；若当前实现只跟随单个 ToolRuntime 实例生命周期，则作为 Phase 6 退出 blocker 进入 fix，不得推迟到 Phase 7 重新裁决。"

- **实际行为**: 每次创建新 `ToolRuntimeHandle` 时，`create_tool_runtime` 构造全新的 `ToolRuntimeExecutor`，其持有的 `InMemoryRunLocalDuplicateGovernance` 以空字典 `{}` 开始。上一个 Attempt 中已 accepted 的工具事实被遗忘。若 resume/steer/recovery 路径下模型再次发出相同语义的工具调用，duplicate governance 无法命中既有记录，必然返回 `ALLOW` 并无防护地再次执行 callable。
- **直接证据**:
  1. `dispatch.py:701` — `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())` 每次构造全新 factory 实例。
  2. `dispatch.py:703-704` — `ToolRuntimeBuildRequest(...)` 无任何 Run-level index 共享标识。
  3. `tool_runtime.py:2447-2448` — `duplicate_governance=InMemoryRunLocalDuplicateGovernance(...)` 创建全新实例，`_entries_by_key` 为空 dict。
  4. 整个 `_run_input_builder_for_dispatch` 方法中搜索 "duplicate"、"index"、"governance"、"shared"、"run_level" 等关键词，无任何跨 ToolRuntime 实例的 index 共享机制。
  5. HEAD commit `203a69a` 对 `docs/host/design.md` 和 `docs/host/implementation-control.md` 的变更，明确将 Run-local（非 Attempt-local）语义写入 Phase 6 退出条件。
- **影响**: 当前架构无法满足 Phase 6 exit standard。同一个 Run 的多个 Attempt 会因为 ToolRuntime 重建而丢失 duplicate memory，导致：
  - Resume 路径下模型重复调用相同工具时无 duplicate 防护（duplicate index 为空）
  - 已 accepted 的 tool fact 无法被 reuse/hint/hard_stop
  - 可能重复执行 side-effect 或 paid tool
  - 与 design doc "duplicate governance 不放在 Engine，完全由 Host/ToolRuntime 打理"的架构宗旨冲突
- **建议改法和验证点**:
  1. 引入 Run-level in-memory duplicate registry，以 `run_id` 为 key，由 Host 调度器在 Run 生命周期内持有，跨 ToolRuntime 实例复用。
  2. 建议在 `HostDispatchScheduler` 或更高层引入 `_run_duplicate_indexes: dict[str, InMemoryRunLocalDuplicateGovernance]`，在构造 ToolRuntime 时传入已有索引而非创建空实例。
  3. 或者将 `InMemoryRunLocalDuplicateGovernance` 从 `ToolRuntimeExecutor` 中分离，提升为独立 Run-scoped 对象，通过 `ToolRuntimeBuildRequest` 传入。
  4. 新增测试：同一 Run 的两个 Attempt 创建独立 ToolRuntime，第二个 Attempt 的 duplicate index 命中第一个 Attempt 的 accepted record。
  5. 新增测试：Run 终态后清理对应 Run-level index（防止内存泄漏）。
- **修复风险（中）**: 需要决定 Run-level index 的生命周期管理（何时创建、何时清理）。Phase 7 的 `WAITING`/resume 路径尚不存在，测试需要用 mock attempt transition 模拟。但这是架构级修复，风险可控。
- **严重程度（严重）**: Phase 6 退出 blocker。Control doc 和 design doc 均明确要求 Run-local 语义，当前实现仅满足 Attempt-local。不满足 P6 exit standard 则 Phase 6 不应被标记为完成。

---

### F2-未修复-中-同源 ToolRuntimeHandle 通过每次新建 factory 实例实现同名提供者，增加运行时 TypeProvider 不必要的重新实例化

- **入口/函数**: `HostDispatchScheduler._run_input_builder_for_dispatch` → `create_tool_enabled_run_input_builder`
- **文件(行号)**:
  - `dayu/host/dispatch.py:701-703` — 每次调用都创建 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())`
  - `dayu/host/run_input.py:883-912` — `create_tool_enabled_run_input_builder` 接收已构造的 `tool_runtime_handle` 并创建新的 `StaticToolRuntimeHandleProvider`
- **输入场景**: 正常 dispatch 循环，每次有 pending dispatch 记录时调用 `_run_input_builder_for_dispatch`。
- **实际分支**: `dispatch.py:701` 每次创建新的 `EffectiveToolBundleBuilder` 实例（当前为轻量无状态对象），然后用它构造 `DefaultToolRuntimeFactory`。
- **预期行为**: `EffectiveToolBundleBuilder` 本身是无状态的纯函数构建器，重复实例化无害。
- **实际行为**: 每次 dispatch 都构造新的 `EffectiveToolBundleBuilder()` 和 `DefaultToolRuntimeFactory(...)`。当前两个类均为轻量级（无持久化、无锁、无连接池），实际无性能影响。
- **直接证据**: `dispatch.py:701-702` — `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())`；`tool_runtime.py:1830-1832` — `EffectiveToolBundleBuilder` 类体无实例状态。
- **影响**: 当前无实际影响。但如果未来 `EffectiveToolBundleBuilder` 引入缓存、连接或初始化成本，这段代码会成为不必要的重初始化热点。
- **建议改法和验证点**: 可在 P6 fix 中顺带将 factory 提升为 scheduler 实例级字段（例如在 `open()` 时创建），减少重复构造。非阻塞。
- **修复风险（低）**: 只需将 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())` 移到 `open()` 中作为 `self._tool_runtime_factory`。
- **严重程度（中）**: 当前无行为影响，但如果将此报告为低严重度会使 deferred cleanup 可能在后续 phase 中变成隐式依赖问题。中严重度可接受——不需要立即修复，但应在 fix 时顺带处理。

---

### 未发现实质性问题（以下目标均已满足）

#### ToolRuntime truncation / fetch_more scope 正确

- `TruncationManager` (`tool_runtime.py:1194`) 只持有内存 `_cursors: dict[str, ToolTruncationCursor]`，不写 durable table。
- `_validate_cursor` (`tool_runtime.py:1383-1428`) 校验 `session_id`、`run_id`、`attempt_id` 三字段与当前 manager scope 完全匹配，scope mismatch 返回 `_TRUNCATION_SCOPE_MISMATCH_REASON`。
- Cursor 为 `single_use=True` (`tool_runtime.py:1377`)，`_store_cursor` 每次生成随机 `scope_token` (`secrets.token_urlsafe(32)`)，`cursor_id` 随机不可猜测。
- `scope_token` 通过 `sha256_digest_json` hash 后存入 cursor，明文仅返回给 truncated result 中的 `fetch_more` meta，不暴露内部状态。
- 所有 cursor 校验失败均返回 `ToolFailedOutcome`（非 completed），不泄露内部状态。
- Cursor/scope_token 不能跨 tool result 边界：每个截断产生的 cursor 只能通过同一个 `fetch_more` 调用使用一次（`single_use`）。
- Cursor 不能跨 Run 边界：`_validate_cursor` 的 `session_id != self._session_id or run_id != self._run_id` 检查阻止跨 Run 访问。
- Truncation 只支持 same-Run continuation model：cursor `expires_at` 默认为 `_DEFAULT_TRUNCATION_TTL_SECONDS=600` 秒，过期后自动失效。

#### Phase 7 WAITING / resolve_wait 未泄露到 Phase 6

- `ToolRuntimeExecutor` 的 `_normalize_runtime_outcome` (`tool_runtime.py:2274-2291`) 明确拦截 `ToolAwaitingOutcome`，转为 `governed_error` 带有 `reason_code=_TOOL_RUNTIME_UNSUPPORTED_AWAITING_REASON`。
- `_tool_fact_accept_candidate` (`tool_runtime.py:4121-4133`) 在入口处 `raise TypeError("ToolAwaitingOutcome must be normalized before accept")`。
- `_tool_outcome_digest` (`tool_runtime.py:4277-4309`) 同样在入口处拦截 awaiting outcome。
- `dayu/host/tool_runtime.py` 和 `dayu/host/dispatch.py` 中无 `WAITING` run status 推进、无 `resolve_wait` 实现、无 wait record 创建。
- Phase 7 语义完全保持 deferred。

#### Tool schema 与 callable 同源

- `ToolRuntimeHandle.__post_init__` (`tool_runtime.py:2361-2371`) 校验 `tool_schemas == effective_bundle.tool_schemas`。
- `create_tool_enabled_run_input_builder` (`run_input.py:883-912`) 使用同一个 `StaticToolRuntimeHandleProvider` 实例分别构造 `ToolRuntimeSchemaSnapshotProvider` 与 `ToolRuntimeExecutorProvider`。
- `_validate_tool_enabled_snapshot` (`run_input.py:1182-1209`) 额外做 identity 检查 (`tool_snapshot.tool_runtime_handle.tool_schemas == tool_snapshot.tool_schemas`, `tool_snapshot.tool_runtime_handle.tool_executor is tool_executor`)。
- 三层防护，无绕过可能。

#### 同源保卫在 no-tool 模式下也保持

- `NoopToolSchemaSnapshotProvider` (`run_input.py:499-521`) 返回空 schemas。
- `NoopToolExecutorProvider` (`run_input.py:524-550`) 返回 `DisableToolsExecutor`。
- Scheduler 的 `_run_input_builder_for_dispatch` 在 `tooling_options is None or not allow_tool_calls` 时走 `create_no_tool_run_input_builder`，不创建 ToolRuntime。
- 既有测试（`test_pending_waiting_dispatching_worker_accept_marks_running`）确认 no-tool 模式下 `disable_tools is True`。

#### Side-effect 与 paid-tool policy 未被静默绕过

- `DefaultToolRuntimePolicyPort.decide_tool_call` (`tool_runtime.py:1141-1168`) 检查：
  1. `allow_tool_calls` 为 False → `GOVERNED_ERROR`
  2. 对于 `SIDE_EFFECT` 或 `PAID` 工具，`tool_idempotency_key` 为空 → `GOVERNED_ERROR`
  3. 通过上述检查 → `ALLOW`
- `_tool_idempotency_key` (`tool_runtime.py:3831-3847`) 从工具参数中按 `rule.idempotency_key_argument_name` 提取 key，key 为非空字符串；未配置或值为非字符串时返回 `None`。
- 侧效应/付费工具缺幂等 key 时，callable 不会被调用，outcome 直接变为 governed error。
- 测试验证：`test_toolruntime_executor.py` 中的相关用例确认 `SIDE_EFFECT` 工具缺幂等 key 时 `GOVERNED_ERROR` 结果。

#### 测试验证真实 scheduler/tool 执行路径

- `test_scheduler_uses_toolruntime_when_tooling_is_configured` (`test_dispatch_scheduler.py:523-575`) 完整执行路径：
  1. `HostDispatchScheduler.open()` → 真实 durable store + lane controller
  2. `_seed_current_run()` → 真实 Run/Attempt/dispatch_record 写入 SQLite
  3. `scheduler.wake_dispatch()` + `scheduler.drain_once()` → 完整 dispatch 闭环
  4. `factory.accepted_requests[0]` → worker 收到的 `AgentRunRequest` 含 tool_schemas 与 tool_executor
  5. `request.tool_executor.execute(...)` → 真实 `ToolRuntimeExecutor.execute()`，走 dispatcher → policy → truncation → accept barrier 全链路
  6. `tool.call_count == 1` → 业务 callable 被真实调用
  7. `_read_event_by_type(..., "TOOL_CALL_REQUESTED")` → EventLog 有 canonical 工具调用请求事实
  8. `_read_event_by_type(..., "TOOL_RESULT_ACCEPTED")` → EventLog 有 canonical 工具结果接受事实
- 这不是 mock/unit-only 测试——它通过真实 accept barrier 的 transaction runner 写入同一个 SQLite durable store。
- 全部 348 个 Host 测试通过，pyright clean。

#### Phase 6 设计文档合规

- `docs/host/design.md` 新增的 Run-local duplicate governance 要求 (commit `203a69a`) 已明确定义。
- `docs/host/implementation-control.md` 已更新 Phase 6 exit standard。
- Host 内部模块边界未破坏：ToolRuntime 不 import dispatch.py，不直接写 Run/Attempt 状态，不绕过 accept barrier。
- 无 `dayu.fins` / `dayu.service` / `dayu.ui` / `dayu.engine` 反向 import。
- 无 `Any` / `object` / 无类型签名新增。
- 无 God object 扩散。

---

## Open Questions

1. **Run-level duplicate index 的生命周期管理策略**：如果引入 Run-level index registry，Run 终态后何时清理？是通过 Run terminal closeout 事件触发，还是在 scheduler 中基于 Run status 做惰性清理？这影响内存管理和测试设计。
2. **`_run_input_builder_for_dispatch` 中 `EffectiveToolBundleBuilder` 和 `DefaultToolRuntimeFactory` 是否需要提升为 scheduler 实例级字段**（F2）：当前无行为影响，是否在 F1 fix 中顺带处理？

---

## Residual Risks

### F1 fix 引入的级联风险

- Run-level index 需要决定 ownership：若放在 `HostDispatchScheduler`，scheduler 的 `close()` 需要清理所有 Run-level index。若放在独立的 registry，需要决定其与 scheduler 的生命周期关系。
- Phase 7 `WAITING`/`resolve_wait`/resume 路径当前无实现代码，无法测试跨 Attempt 的 duplicate index 行为——F1 fix 的测试需要用模拟的 attempt transition 验证。
- Run 终态清理 index 的时机需要与 Run terminal closeout（Phase 5 已有）对齐。

### 已有残余风险（来自 P6-S5/S6 controller adjudication）

| Risk | Original Owner | Status in Phase 6 |
|------|----------------|-------------------|
| `semantic_duplicate_key_argument_name` 默认关闭、无测试 | P12 或后续 policy provider | Deferred，不阻塞 P6 |
| `ToolFactAcceptCandidate` GOVERNED_ERROR defensive validation 可更严格 | ToolRuntime hardening | Deferred，不阻塞 P6 |
| `ToolTraceDiagnosticEmitter` typed refs 不是 durable trace | Phase 13 | Deferred |
| `tooling_options` 为 single bundle，多 profile 未实现 | Phase 12 | Deferred |
| `policy_snapshot_digest` 是诊断 digest，不是 durable snapshot | ToolRuntime hardening | Deferred |
| `enable_truncation_manager=True` 默认值 | ToolRuntime performance hardening | Deferred |

### 未覆盖测试区域

- 跨 Attempt 的 Run-local duplicate index 行为（无测试，且当前实现不支持）
- `WAITING -> resume` 场景下 ToolRuntime 重建的完整集成行为（Phase 7 才能测试）
- steer 路径下同 Run 多 Attempt 的 duplicate governance（steer 未实现）
- Production policy provider 驱动下的 duplicate matrix 配置（P12）

---

## Final Verdict

**BLOCKED**

Phase 6 的 ToolRuntime / truncation / fetch_more / diagnostics / scheduler wiring 核心实现质量高，目标对齐良好。348 个测试通过，pyright clean。Phase 7 的 WAITING/resolve_wait 语义完全未泄露。Truncation/fetch_more Run-local scope 正确。Side-effect/paid-tool policy 未被绕过。工具 schema 与 callable 同源保卫有三层防护。

但是，Phase 6 exit standard 要求 Run-local duplicate governance 能在同一 Run 的正常同进程跨 Attempt 路径中保持 duplicate memory。当前 `InMemoryRunLocalDuplicateGovernance` 绑定在 `ToolRuntimeExecutor` 实例生命周期内，每次 dispatch 创建新 `ToolRuntimeHandle` 时索引从空字典开始。这不能满足 design doc 和 implementation-control doc 的 Run-local（非 Attempt-local）语义要求。

F1 为严重级阻塞发现，必须在 Phase 6 内修复，不得推迟到 Phase 7。
