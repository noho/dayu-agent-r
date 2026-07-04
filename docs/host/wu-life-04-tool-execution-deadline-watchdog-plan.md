# WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout Plan

GitHub owner: Issue #168. Umbrella: Issue #87.

Path note: the task mentions `dayu/engine/design.md` 第 11 节, but this repository currently has `docs/engine/design.md` and no `dayu/engine/design.md`. This plan uses `docs/engine/design.md` 第 11 节 as the Engine design source.

## 1. First-Principles Judgment

当前问题成立。

直接证据：

- `docs/engine/design.md` 第 5 节和第 11 节已经冻结：`AgentPolicy.tool_execution_timeout_seconds` 是 Engine 等待 `ToolExecutor.execute` 返回 outcome 的唯一握手 timeout 真源；`BatchToolExecutionContext.timeout_seconds` 只是同一值的投影；timeout 只表示 Engine 不再等待工具 batch handshake，不证明工具内部线程、子进程、HTTP 请求或远端 job 已停止。
- `docs/host/design.md` Cancel 章节仍写着 `OpenHostOptions.active_cancel_timeout_seconds`：Host 在 `CANCEL_REQUESTED` / `RUN_CANCELLING` 之后按独立 post-cancel timeout 扫描 `CANCELLING` Run，超时后写 `ATTEMPT_CANCELLED` + `RUN_CANCELLED(reason=active_cancel_timeout)`。
- `dayu/host/api.py` 当前把 `active_cancel_timeout_seconds` 暴露在 `OpenHostOptions`，默认值是 300 秒；低层 `HostLocalExecutionOptions` 也有同名字段。
- `dayu/host/open_host.py` 把 public `OpenHostOptions.active_cancel_timeout_seconds` 原样投影给 `HostLocalExecutionOptions`，并用 `local_execution.active_cancel_timeout_seconds is not None` 决定 startup recovery 是否把 accepted cancel 的 `CANCELLING` Run defer 给 watchdog。
- `dayu/host/dispatch.py` 的 `tick_active_cancel_watchdog` 用 `candidate.cancel_requested_at + active_cancel_timeout_seconds` 判定 eligible；这会在用户取消时重新启动一段独立等待预算。
- `dayu/host/durable/run_transition.py` 的 `ActiveCancelTimeoutCloseoutInput` 和 payload 写入 `timeout_seconds`、`cancel_requested_at`、`timed_out_at`、`watchdog_owner`，说明 durable 事实当前表达的是 post-cancel active timeout，而不是工具原始 deadline。
- `dayu/runtime/assembly.py`、`dayu/service/host_assembly.py` 和 `dayu/config/execution_profiles.json` 已经形成 `execution_profiles.json -> agent_policy.tool_execution_timeout_seconds -> AgentPolicy` 的配置链路。该链路没有把工具 timeout 迁移到 `host_runtime.json`。
- `tests/engine/test_agent_phase3_tool_call.py` 已覆盖工具握手 timeout：timeout 后 Engine 产出不可恢复 `run_failed(tool_execution_timeout)`，不产出 `tool_result_accepted`，并确认 `BatchToolExecutionContext.timeout_seconds` 等于 policy 值。
- `tests/host/test_active_cancel_dispatch.py`、`tests/host/test_open_host_runtime.py` 当前直接断言独立 `active_cancel_timeout_seconds` 的 post-cancel closeout 行为；`tests/host/test_run_attempt_transitions.py` 当前通过 closeout helper、payload 字段和 terminal reason 间接依赖 `active_cancel_timeout` 语义。

问题不是 WU-TOOLS-CANCEL-01 的 physical interrupt 范围：本 WU 只裁决 Host durable truth 与 deadline 语义，确保 Host 取消/closeout 不新增或延长工具调用最长运行时间。实际中断工具线程、HTTP 请求、provider stream、子进程、process group、sandbox 或外部长事务仍归 WU-TOOLS-CANCEL-01。

## 2. Goal, Motivation, Success Signal

Goal:

- 固定 `tool_execution_timeout_seconds` 的业务语义：它是单次工具调用最长运行时间，配置真源继续是 `execution_profiles.json -> agent_policy.tool_execution_timeout_seconds`。
- 删除 `active_cancel_timeout_seconds`，避免 Host public API 或 HostLocal execution options 暴露第二套 post-cancel timeout。
- Host cancel / closeout 不得重置、覆盖或延长正在运行 tool call 的原始 deadline。
- 给 Issue #87 umbrella 的 shared supervisor、scan query optimization、clock skew、diagnostics / audit hooks 和 physical interrupt 后续工作明确 owner / destination。

Motivation:

- 当前独立 active-cancel timeout 允许用户取消后重新获得最长 300 秒等待预算；这与“工具调用最长运行时间由 tool execution timeout 控制”冲突。
- 取消是 Host 治理事实，不能伪装成工具物理停止；Host closeout 也不能把 post-cancel 额外等待解释成工具 deadline。

Success signal:

- `OpenHostOptions` 不再暴露 `active_cancel_timeout_seconds`。
- Host active cancel watchdog 不再按 `cancel_requested_at + active_cancel_timeout_seconds` 计算 closeout。
- 取消 active `RUNNING` Attempt 后，Host 最多在 watchdog wakeup / startup tick 的下一个 durable closeout 中写入 `CANCELLED`，不新增 post-cancel 等待预算。
- Engine 工具握手 timeout 测试继续证明 `tool_execution_timeout_seconds` 是唯一工具 handshake timeout 真源。
- Host active cancel tests 改为断言 immediate/no-extra-budget closeout、startup recovery 优先 watchdog closeout、late terminal first-committer-wins 和 queued promotion。

## 3. Non-Goals / Scope Boundary

- 不实现 tool/provider physical interruption、request abort、stream abort、subprocess termination、process-group kill、sandbox kill 或 hard-kill diagnostic closeout；这些归 WU-TOOLS-CANCEL-01。
- 不修改 Engine tool-calling public contract，不新增 Engine 向 Host 上报 per-tool deadline 的 contract。
- 不把 `tool_execution_timeout_seconds` 迁移到 `host_runtime.json`。
- 不保留旧 `active_cancel_timeout_seconds` public API 的兼容读取、兼容 wrapper 或兼容测试。
- 不抽取 generic supervisor runtime abstraction；本 WU 只裁决 #87 umbrella 是否需要后续 owner。
- 不优化全表扫描，除非当前实现修改自然需要触碰同一查询；scan query optimization 默认转交 #87 performance follow-up。

## 4. Design Alignment

Engine 真源已经对齐：

- `docs/engine/design.md` 已说明 `AgentPolicy.tool_execution_timeout_seconds` 是唯一工具 handshake timeout 真源。
- Engine 不托管工具内部任务或外部长事务生命周期，因此 Host 不能从 Engine 当前 contract 精确知道“正在运行的单个工具调用原始 deadline”。

Host 真源需要先修改：

- `docs/host/design.md` Cancel 章节必须删除现有 `OpenHostOptions.active_cancel_timeout_seconds` 段落：不再描述独立 post-cancel timeout、timeout 到期判定或 `reason=active_cancel_timeout`。
- `docs/host/design.md` Startup recovery 章节必须删除 `active_cancel_timeout_seconds=None` opt-out 语义：watchdog 不再可通过 timeout option 关闭。
- Host design 应改为：active `RUNNING` Attempt 收到 cancel 后，Host 写入 `CANCEL_REQUESTED` + `RUN_CANCELLING`，传播 cancellation token，并唤醒 active cancel watchdog；watchdog 是 accepted-cancel closeout supervisor，不提供 post-cancel timeout 预算。若当前 Attempt 仍为 `RUNNING` 且 dispatch 已 worker accepted，watchdog 可在 tick 中写入 `ATTEMPT_CANCELLED` + `RUN_CANCELLED`，释放 active slot 并触发 queued promotion。
- Host design 应明确：该 closeout 不证明 provider/tool 已物理停止；后续旧 worker / tool 事件按 existing identity、state 和 first-committer-wins 被接受或拒绝。
- Startup recovery 描述应改为：startup 先执行 watchdog tick；accepted-cancel `CANCELLING` Run 不因缺少 timeout 配置而进入 `LOST`，而是由 watchdog closeout 或 existing terminal/recovery proof 处理。

`docs/engine/design.md` 可保持不变；只在 implementation agent 发现 Host design 需要引用 Engine 第 11 节时，增加一两句交叉引用，不能改变 Engine contract。

## 5. Affected Files / Modules

Allowed implementation files/modules for later implementation gate:

- `docs/host/design.md`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py` if import/helper construction still passes `active_cancel_timeout_seconds`
- `tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization
- `dayu/host/README.md`
- `tests/README.md` only if test layering or command list meaningfully changes

Files to inspect but not expected to change:

- `docs/engine/design.md`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `dayu/config/execution_profiles.json`
- `tests/engine/test_agent_phase3_tool_call.py`
- `dayu/engine/README.md`
- `dayu/config/README.md`

## 6. Public Contract / Schema / State-Machine Changes

Recommended decision: delete the public field and remove the independent timeout semantics.

- Delete `OpenHostOptions.active_cancel_timeout_seconds` from `dayu/host/api.py`.
- Delete `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS`.
- Delete validation for `OpenHostOptions.active_cancel_timeout_seconds`.
- Do not add a replacement public option.
- Delete `HostLocalExecutionOptions.active_cancel_timeout_seconds`.
- Do not add an internal disable flag or any scheduler opt-out that can turn off the accepted-cancel watchdog. After deleting the timeout option, the watchdog is unconditionally enabled.
- Rename durable input/function/helper names that contain `ActiveCancelTimeout` / `active_cancel_timeout` to accepted-cancel watchdog closeout terminology. The desired semantic is accepted-cancel watchdog closeout, not timeout. Payload should stop carrying `timeout_seconds` and `timed_out_at`; keep diagnostic fields that remain true, such as `cancel_requested_at`, `closed_out_at` or `occurred_at`, `watchdog_owner`, `worker_lifecycle_signal`, `last_observed_worker_event_index`, and `last_accepted_event_id`.
- Rename terminal reason and worker lifecycle signal from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value. No compatibility mapping is required.

Schema compatibility:

- EventLog payload shape changes are allowed as new-schema behavior under this project’s schema policy. Do not add old payload compatibility readers/tests unless explicitly requested.

State-machine change:

- `RUNNING + active cancel -> CANCELLING` remains unchanged.
- After commit, Host still propagates cancel to active worker.
- Watchdog closeout no longer waits for `cancel_requested_at + timeout_seconds`; it closes eligible `CANCELLING` / `RUNNING Attempt` / worker-accepted dispatch rows on tick.
- Terminal first-committer-wins remains unchanged: if cooperative `run_cancelled`, success, failure, waiting, or lost terminal already committed, watchdog closeout must no-op.

## 7. Implementation Decisions

### Host Must Not Extend Tool Original Deadline

Current Host cannot reliably know a per-tool original deadline.

Evidence:

- `dayu/host/dispatch.py` active-cancel candidate only contains `run_id`, `session_id`, `attempt_id`, and `cancel_requested_at`.
- `USER_INPUT_ACCEPTED.effective_execution_config` can reconstruct effective `AgentPolicy`, including `tool_execution_timeout_seconds`, and per-run override tests prove it is frozen. This gives the timeout duration, not the start time of the currently running tool call.
- ToolRuntime computes a monotonic batch deadline from `BatchToolExecutionContext.timeout_seconds`, but this deadline is runtime-local and not durable.
- Host durable watchdog has no direct current tool-call start/deadline fact.

Minimal correct方案:

- Do not try to derive `cancel_requested_at + tool_execution_timeout_seconds`; that still resets budget on cancel and can extend a tool already near timeout.
- Do not derive from Attempt start or worker accepted time; that can close a non-tool Runner phase too early and still does not represent a later tool call’s own deadline.
- Use no post-cancel time budget: cancel commit wakes watchdog, and watchdog closes eligible accepted-cancel active workers immediately on tick. This can shorten running work after user cancel, but cannot extend the original tool deadline.
- This no-extra-budget choice is intentional: if a tool outcome was already durably accepted before cancel reached Engine, existing Engine/Host commit ordering preserves it; if it was not accepted yet, user cancel may close the Run before a later tool result appears. That is the correct tradeoff for an explicit cancel and does not require a separate waiting budget.

Residual owner:

- Precise per-tool original deadline observability, if later required for diagnostics or physical interrupt escalation, belongs to WU-TOOLS-CANCEL-01 or a child issue under #87 because it requires a new Host-visible tool execution phase/deadline signal.

## 8. Implementation Slices

Slice count: 2. This is a small cross-module contract cleanup, so it stays within the control doc’s 1-3 slice budget.

### Slice 1: Design And Public Contract Cleanup

Objective:

- Make Host design and public construction contract remove the independent active-cancel timeout.

Allowed files/modules:

- `docs/host/design.md`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/README.md`
- Host tests only for constructor/import fallout if needed.

Exact changes:

- Update `docs/host/design.md` Cancel and startup recovery text before code changes.
- Remove `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS`.
- Remove `OpenHostOptions.active_cancel_timeout_seconds` field, docstring entry, and validation.
- Remove projection from `_local_execution_options_from_open_host_options`.
- Remove `HostLocalExecutionOptions.active_cancel_timeout_seconds`.
- Do not add an internal watchdog disable flag; the accepted-cancel watchdog must be unconditionally enabled after the timeout field is removed.
- Update `docs/host/design.md` concretely:
  - Delete the existing `OpenHostOptions.active_cancel_timeout_seconds` paragraph and any `reason=active_cancel_timeout` wording.
  - Delete the `active_cancel_timeout_seconds=None` opt-out paragraph.
  - Rewrite Cancel / startup recovery text around an accepted-cancel watchdog closeout supervisor that does not grant post-cancel budget.
  - State explicitly that this closeout does not prove provider/tool physical stop.
- Update `dayu/host/README.md` because `dayu/host/` public contract changed.

Tests:

- Update constructor/helper tests that still pass `active_cancel_timeout_seconds`.
- Add or update a public opener test proving `OpenHostOptions` no longer accepts/exposes `active_cancel_timeout_seconds`.

Docs:

- `docs/host/design.md` required.
- `dayu/host/README.md` required because Host public construction contract changes.

Stop condition:

- No production code path or test helper references `OpenHostOptions.active_cancel_timeout_seconds`.
- No production code path or test helper references `HostLocalExecutionOptions.active_cancel_timeout_seconds`.
- No internal disable flag or timeout-option opt-out exists for the accepted-cancel watchdog.
- `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md` returns no live usage except archived historical artifacts under `docs/reviews/` or old WU plans.

### Slice 2: Watchdog No-Extra-Budget Closeout

Objective:

- Convert active cancel watchdog from timeout scanner to accepted-cancel closeout supervisor with no post-cancel budget.

Allowed files/modules:

- `dayu/host/dispatch.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py` if needed.
- `tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization.
- `tests/README.md` only if test documentation materially changes.

Exact changes:

- `wake_active_cancel_watchdog` should no longer return because a timeout option is `None`.
- `_start_active_cancel_watchdog_loop` should no longer be gated by timeout seconds.
- `tick_active_cancel_watchdog(now)` should still validate `now` for deterministic event timestamps, but eligibility must no longer compare elapsed time to a timeout.
- `_read_active_cancel_watchdog_candidates` preconditions stay strict: only `CANCELLING` Run, current Attempt `RUNNING`, worker-accepted dispatch, linked accepted cancel fact.
- Replace `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_*` helpers with names matching accepted-cancel watchdog closeout, for example `ActiveCancelWatchdogCloseoutInput` and `active_cancel_watchdog_closeout_*`.
- Rename the terminal reason and worker lifecycle signal value from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value.
- Payload should no longer include `timeout_seconds` / `timed_out_at`; include `cancel_requested_at` and `closed_out_at` or use `occurred_at` consistently.
- Startup recovery should always let accepted-cancel `CANCELLING` Run be handled by watchdog tick before orphan/lost recovery. Remove the `defer_accepted_cancel_to_watchdog=local_execution.active_cancel_timeout_seconds is not None` dependency.
- Tests that need to cover orphan `CANCELLING -> LOST` must use a fixture with no accepted cancel fact, so `_has_accepted_cancel_fact` is false; do not cover that path by disabling the watchdog.
- Existing late terminal and replay protections must remain first-committer-wins.

Tests:

- Replace `test_active_cancel_watchdog_noops_before_timeout` with a test proving there is no post-cancel grace budget: after cancel, the first tick closes eligible Run.
- Update timeout payload assertions to assert no `timeout_seconds` and no `timed_out_at`.
- Update `tests/host/test_run_attempt_transitions.py` only for closeout helper, payload field, and terminal reason rename fallout; it is not affected by a direct `active_cancel_timeout_seconds` field reference.
- Update `tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization.
- Keep tests for:
  - non-cooperative worker closes to `CANCELLED`;
  - zero candidates no-op;
  - multiple eligible runs close;
  - queued promotion after closeout;
  - command replay after closeout does not append duplicate facts or re-propagate cancel;
  - scheduler close does not write terminal facts;
  - cooperative terminal first-committer-wins;
  - success terminal before watchdog no-ops;
  - open_host public watch observes cancelled closeout;
  - reopen/startup path closes accepted-cancel `CANCELLING` via watchdog and does not route to `LOST`.

Docs:

- Update `tests/README.md` only if new/changed test category needs mention.

Stop condition:

- No active production/test code computes active cancel closeout eligibility from `cancel_requested_at + timeout_seconds`.
- Active cancel closeout payload no longer describes a post-cancel timeout.
- `rg "active_cancel_timeout" dayu/host tests/host docs/host/design.md dayu/host/README.md` leaves no live timeout semantic in reason strings, worker lifecycle signals, helper names, payload assertions, or design text.
- All affected Host tests and pyright pass.

## 9. Required Tests / Validation Commands

Implementation agent must run:

```bash
source .venv/bin/activate
pytest tests/engine/test_agent_phase3_tool_call.py -q
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_run_attempt_transitions.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_effective_execution_config.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Recommended targeted grep before final report:

```bash
rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md
rg "active_cancel_timeout|timeout_seconds.*active" dayu/host tests/host docs/host/design.md dayu/host/README.md
```

For this plan-only gate, required validation is only:

```bash
git diff --check
```

## 10. README / Docs Decision

Later implementation must update/check:

- `docs/host/design.md`: required because Host cancel design and public contract semantics change.
- `dayu/host/README.md`: required by AGENTS trigger because `dayu/host/` public construction contract and cancel mechanism change.
- `tests/README.md`: check after test edits; update only if the documented test layering or command list changes materially.
- `dayu/engine/README.md`: check only if Engine code or Engine contract docs are modified. Current plan expects no Engine code change.
- `dayu/config/README.md`: check only if config schema changes. Current plan expects no config change because `tool_execution_timeout_seconds` remains in `execution_profiles.json`.
- Root `README.md` and `dayu/README.md`: not expected, because no user-visible CLI/Web/WeChat workflow or layer boundary changes are planned.

## 11. Residual Risks / Owners

- Per-tool original deadline is not Host-visible today. Owner/destination: WU-TOOLS-CANCEL-01 or Issue #87 child follow-up if precise deadline diagnostics become required. Current WU handles correctness by not adding post-cancel budget.
- Physical interruption after Host closeout is not solved. Owner/destination: WU-TOOLS-CANCEL-01.
- Active watchdog scan query optimization remains unimplemented if this plan keeps the current `read_non_terminal_runs` scan. Owner/destination: Issue #87 performance follow-up.
- Clock skew risk is reduced because no elapsed timeout comparison remains, but event timestamps still depend on Host clock. Owner/destination: Issue #87 diagnostics/audit follow-up if multi-host timestamp ordering needs stronger guarantees.
- Shared supervisor abstraction is not introduced. Owner/destination: Issue #87 umbrella; defer until multiple target-specific supervisors show real duplication or operational need.
- Diagnostic/audit hooks beyond current EventLog payload are not expanded. Owner/destination: Issue #87 diagnostics/audit hooks follow-up, with #70 Tool Trace diagnostics lane as consumer if tool-level trace analysis needs it.

## 12. Completion Report Format

Implementation agent final report must include:

- Changed files.
- Public contract decision: confirm `active_cancel_timeout_seconds` removed from public API and `HostLocalExecutionOptions`, with no internal disable flag.
- Host deadline behavior: confirm no post-cancel budget and no `cancel_requested_at + timeout` closeout.
- Tests run, including exact pytest commands, pyright, and `git diff --check`.
- README/docs updated or checked.
- Residual risks with owner/destination, especially WU-TOOLS-CANCEL-01 and Issue #87 follow-ups.
