# Host Phase 6 Aggregate Review

## Scope

- Mode: current changes (aggregate)
- Branch: feat/host-phase-6-toolruntime
- Base: a5863ce (Host Phase 6 plan checkpoint)
- HEAD: 203a69a (Host Phase 6 run-local duplicate governance clarification)
- Output file: docs/reviews/host-phase6-aggregate-review-mimo-20260515.md
- Included scope: all Phase 6 cumulative changes from a5863ce through HEAD, covering P6-S1 through P6-S6 implementation, reviews, fixes, and controller adjudications
- Excluded scope: Engine code, Remote transport, business tool implementations, Phase 7+ capabilities
- Parallel review coverage: 无

## Commands And Files Inspected

- `git diff a5863ce...HEAD --stat` — 46 files changed, 12166 insertions, 65 deletions
- `git log a5863ce...HEAD --oneline` — 13 commits (S1–S6 accept + checkpoint + governance clarification)
- Production code: `dayu/host/tool_runtime.py` (4480 lines), `dayu/host/dispatch.py`, `dayu/host/run_input.py`, `dayu/host/api.py`
- Test code: 8 new test files under `tests/host/` totaling ~4320 lines
- Design source: `docs/host/design.md` §18 / §18.3 / §19
- Control doc: `docs/host/implementation-control.md` Phase 6
- All existing P6-S1 through P6-S6 review, fix, re-review, and controller adjudication artifacts under `docs/reviews/`
- pyright: `python -m pyright dayu/host tests/host` — 0 errors
- Tests: `pytest tests/host -q` — 348 passed

## Findings

### 1-未修复-严重-Run-local duplicate governance 实例级而非 Run 级

- **入口/函数**: `HostDispatchScheduler._run_input_builder_for_dispatch()` 和 `DefaultToolRuntimeFactory.create_tool_runtime()`
- **文件(行号)**: `dayu/host/dispatch.py:701-728`, `dayu/host/tool_runtime.py:2447-2449`
- **输入场景**: 同一个 Run 内发生多 Attempt（如 steer、recovery、WAITING→resolve_wait→resume），每次 dispatch 创建新 ToolRuntime
- **实际分支**: `_run_input_builder_for_dispatch` 每次调用都创建新的 `DefaultToolRuntimeFactory` 和 `InMemoryRunLocalDuplicateGovernance`
- **预期行为**: 设计 §18.3 (design.md:1911) 明确规定 "run-local 是同一个 Run 的治理语义，不是单个 Attempt 或单个 ToolRuntime 实例的生命周期语义。同进程且未丢失 Host 运行期状态时，同一个 Run 因 `WAITING -> resolve_wait -> resume`、steer 或 recovery 创建的新 Attempt 必须继续复用该 Run 的 duplicate index"
- **实际行为**: `InMemoryRunLocalDuplicateGovernance._entries_by_key` 是实例级 dict (`tool_runtime.py:1490`)，每次 dispatch 创建新实例后 duplicate index 为空；Attempt 1 中 accepted 的工具事实对 Attempt 2 的 duplicate governance 不可见
- **直接证据**:
  - `dispatch.py:701-703`: `tool_runtime = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(...)` — 每次 dispatch 创建新 factory
  - `tool_runtime.py:2447-2449`: `duplicate_governance=InMemoryRunLocalDuplicateGovernance(request.duplicate_governance_policy)` — 每次创建新实例
  - `tool_runtime.py:1490`: `self._entries_by_key: dict[str, _DuplicateAcceptedEntry] = {}` — 空 dict 初始化
  - commit `203a69a` 明确将 Run-local duplicate governance 作为 Phase 6 exit standard
- **影响**: 同 Run 跨 Attempt 的 duplicate governance 失效；模型复读同一工具调用时，新 Attempt 的 duplicate index 为空，会重新执行本应 reuse 的工具调用；违反 design §18.3 核心不变量
- **建议改法和验证点**:
  1. 在 `HostDispatchScheduler` 中维护 `dict[str, InMemoryRunLocalDuplicateGovernance]` 以 `run_id` 为 key
  2. `_run_input_builder_for_dispatch` 按 `record.run_id` 查找或创建 Run 级 duplicate governance 实例
  3. Run terminal 后清理对应 entry
  4. 补充测试：同一 Run 内 Attempt 1 accepted 的工具事实，在 Attempt 2 dispatch 时 duplicate governance 能识别并 reuse
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重 — Phase 6 exit standard violation

### 2-未确认-中-Phase 7 await 语义是否意外引入

- **入口/函数**: `ToolRuntimeExecutor._normalize_runtime_outcome()`
- **文件(行号)**: `dayu/host/tool_runtime.py:2269-2294`
- **输入场景**: 工具 callable 返回 `ToolAwaitingOutcome`
- **实际分支**: 检测到 `ToolAwaitingOutcome` 后转为 governed error 并发出诊断
- **预期行为**: Phase 6 不实现 wait/resolve_wait；awaiting 必须被拒绝或转为 governed error
- **实际行为**: 正确转为 governed error，不创建 wait record、不推进 Run WAITING、不关闭 Attempt
- **直接证据**: `tool_runtime.py:2281-2293` — `ToolAwaitingOutcome` 被 `_normalize_runtime_outcome` 归一为 `_governed_failure_outcome`，诊断码为 `unsupported_awaiting`
- **影响**: 无 — Phase 6 正确拒绝 awaiting，Phase 7 将在此路径扩展 wait record 创建
- **结论**: 确认 P6 未意外引入 Phase 7 语义

## Review Lens Verification

### ToolRuntime / truncation / fetch_more / duplicate governance / diagnostics / scheduler wiring

| Goal | Status | Evidence |
|------|--------|----------|
| Host-owned ToolRuntime | PASS | `ToolRuntimeExecutor` (`tool_runtime.py:2001`) is the sole Engine↔Host tool execution bridge; all tool calls go through accept barrier |
| Effective ToolBundle | PASS | `EffectiveToolBundleBuilder` (`tool_runtime.py:1830`) merges business + framework tools; `ToolRuntimeHandle` enforces schema/executor same-source (`tool_runtime.py:2361-2371`) |
| Host accept barrier | PASS | `DefaultHostToolFactAcceptPort` (`tool_runtime.py:1634`) writes TOOL_CALL_REQUESTED + TOOL_CALL_GOVERNED + TOOL_RESULT_ACCEPTED within single transaction with idempotency |
| TruncationManager | PASS | `TruncationManager` (`tool_runtime.py:1194`) stores run-local cursors with session/run/attempt scope validation, TTL, single-use, scope_token digest check |
| fetch_more | PASS | `FetchMoreToolCallable` (`tool_runtime.py:1431`) injected as framework tool; cursor validation checks run scope, token, TTL, single-use, remainder digest |
| Duplicate governance | BLOCKED | `InMemoryRunLocalDuplicateGovernance` is instance-local, not Run-local (Finding 1) |
| Diagnostics | PASS | `DeterministicToolTraceDiagnosticEmitter` / `NoopToolTraceDiagnosticEmitter` / `InMemoryToolTraceDiagnosticEmitter` all implement `ToolTraceDiagnosticEmitter` protocol |
| Scheduler wiring | PASS | `HostDispatchScheduler._run_input_builder_for_dispatch` (`dispatch.py:682-733`) creates tool-enabled RunInputBuilder when tooling present and policy allows; no-tool fallback when absent/disabled |
| No-tool mode | PASS | `ToolRuntimeUnsupportedExecutor` (`tool_runtime.py:1964`) returns failure for each call; `DefaultToolRuntimePolicyPort.decide_tool_call` blocks when `allow_tool_calls=False` |
| Side-effect/paid policy | PASS | `DefaultToolRuntimePolicyPort.decide_tool_call` (`tool_runtime.py:1141-1168`) requires idempotency key for SIDE_EFFECT/PAID tools |
| Awaiting guard | PASS | `_normalize_runtime_outcome` (`tool_runtime.py:2269-2294`) converts `ToolAwaitingOutcome` to governed error |
| Phase 7 not introduced | PASS | No wait record creation, no Run→WAITING transition, no Attempt SUSPENDED in P6 code |

### Truncation / fetch_more Run-local scope

| Check | Status | Evidence |
|-------|--------|----------|
| Cursor stores session/run/attempt | PASS | `ToolTruncationCursor` (`tool_runtime.py:706-736`) has `session_id`, `run_id`, `attempt_id` fields |
| fetch_more validates run scope | PASS | `_validate_cursor` (`tool_runtime.py:1383-1428`) checks `cursor.session_id != self._session_id or cursor.run_id != self._run_id` |
| scope_token cannot cross runs | PASS | `_scope_token_digest` (`tool_runtime.py:3645`) is sha256 of token; cursor stores digest, fetch_more compares |
| Cursor cannot cross tool result | PASS | Each cursor is bound to a specific `tool_call_id` and `tool_name` |
| No durable cursor | PASS | Cursors stored in `self._cursors: dict[str, ToolTruncationCursor]` (instance memory); docstring states "不落 durable cursor 表" (`tool_runtime.py:1196-1199`) |
| Same Run continuation model | PASS | TruncationManager scoped to Run; new Attempt gets new TruncationManager (by design — no durable cursor recovery) |

### Tool schema and callable same-source wiring

- `ToolRuntimeHandle.__post_init__` (`tool_runtime.py:2361-2371`) enforces `tool_schemas == effective_bundle.tool_schemas`
- `EffectiveToolBundleBuilder.build` (`tool_runtime.py:1868-1869`) generates `tool_schemas` from same `definitions` list
- `DefaultToolDispatcher.dispatch_tool_call` (`tool_runtime.py:1091-1115`) looks up callable from `effective_bundle.definitions_by_name`
- Real scheduler path: `dispatch.py:701-733` creates `ToolRuntimeHandle` and passes to `create_tool_enabled_run_input_builder`

### Tests covering real paths

| Test file | Coverage |
|-----------|----------|
| `test_phase6_toolruntime_integration.py` (853 lines) | End-to-end: fake Engine tool call → ToolRuntimeExecutor → accept barrier → EventLog canonical facts |
| `test_toolruntime_executor.py` (596 lines) | Policy rejection, side-effect idempotency, governed error, awaiting guard, reuse path |
| `test_toolruntime_accept_barrier.py` (590 lines) | Accept idempotency, stale execution rejection, schema mismatch, CAS conflict |
| `test_toolruntime_truncation_fetch_more.py` (556 lines) | Truncation strategies, cursor scope validation, TTL expiry, single-use, digest mismatch |
| `test_toolruntime_duplicate_governance.py` (653 lines) | Duplicate policy actions, justification, governed error not recorded as reuse source |
| `test_toolruntime_diagnostics.py` (449 lines) | Diagnostic emitter types, validation |
| `test_toolruntime_effective_bundle.py` (254 lines) | Bundle validation, reserved name conflicts, framework injection |
| `test_dispatch_scheduler.py` (217+ lines modified) | Real scheduler dispatch with ToolRuntime wiring |

## Open Questions

- 无。Finding 1 的 root cause 和 fix 方向已明确。

## Residual Risk

- Finding 1 是唯一 blocking issue；修复后 Phase 6 可达到 exit standard。
- P6-S6 controller adjudication 已记录的 deferred items（multi profile, policy_snapshot_digest 非 durable, semantic_duplicate_key 默认关闭）均为 non-blocking，不影响 Phase 6 exit。
- Phase 7 wait/resolve_wait 引入时需要复核 `_normalize_runtime_outcome` 的 awaiting guard 是否需要扩展为 wait record 创建路径。
- crash recovery 后 duplicate index 丢失属于设计 §18.3 明确的已知边界，不要求 Phase 6 解决。

## Conclusion

**BLOCKED.**

Phase 6 cumulative implementation satisfies all stated goals except Run-local duplicate governance。Finding 1 是 blocking：`InMemoryRunLocalDuplicateGovernance` 的生命周期绑定到 `ToolRuntimeExecutor` 实例，而 design §18.3 要求 duplicate index 的生命周期绑定到 Run。`HostDispatchScheduler._run_input_builder_for_dispatch` 每次 dispatch 创建新实例，导致同 Run 跨 Attempt 的 duplicate memory 丢失。

其余所有 review lens（ToolRuntime、truncation、fetch_more、diagnostics、scheduler wiring、no-tool mode、side-effect policy、Phase 7 边界、same-source schema wiring、test coverage）均 PASS。

修复风险低：在 `HostDispatchScheduler` 中按 `run_id` 缓存 `InMemoryRunLocalDuplicateGovernance` 实例即可；Run terminal 后清理。
