# WU-CLI-01 / CLI-01-S2 Implementation Review (AgentDS)

## Scope

- Mode: current changes (未提交 workspace changes)
- Branch: `phase/host-ui-implementation`
- Base: `HEAD` (working tree diff)
- Output file: `docs/reviews/wu-cli-01-s2-implementation-review-ds.md`
- Included scope:
  - `dayu/runtime/location.py` — explicit config overlay
  - `dayu/service/host_assembly.py` — ServiceRunOverrides / compose_submit_followup_request_with_overrides
  - `dayu/service/entrypoint_runtime.py` — entrypoint runtime Service boundary
  - `tests/runtime/test_runtime_location.py` / `tests/service/test_host_assembly.py` / `tests/service/test_entrypoint_runtime.py`
  - `dayu/README.md` / `dayu/service/README.md` / `tests/README.md` / `docs/host/ui-implementation-control.md`
- Excluded scope: S3-S7 (CLI command / Fins direct / init), non-diff files
- Parallel review coverage: 无

## Findings

### 1-未修复-中-cancel_entrypoint_run_and_wait 在 get_run 与 watcher attach 之间存在 race window

- **入口/函数**: `cancel_entrypoint_run_and_wait`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:436-442`
- **输入场景**: Run 在 `get_run` 返回 `RUNNING` 之后、`_attach_watcher` 完成之前变为终态。此时 terminal event 可能已在 watcher attach cursor 之前发出，`cancel_run` 发送到已终态 Run
- **实际分支**: line 436 `get_run` → line 437 `_attach_watcher` → line 442 `cancel_run`。Run 在 line 436 和 line 437 之间终态化时，watcher cursor（由 `_session_live_event_start_cursor` 在 attach 时获取）可能已在 terminal event 之后
- **预期行为**: 若 Run 已是终态，不应调用 `cancel_run`（可能被 Host 拒绝为 HostApiError），应直接进入 `_wait_for_terminal` 通过 outbox fallback 返回终态结果；若 Run 非终态，应在 cancel 前有 watcher 覆盖 cancel 引发的 terminal event
- **实际行为**: watcher 可能遗漏 terminal event；`cancel_run` 在 Run 已终态时可能被 Host 拒绝（Host 可合理拒绝取消已终态 Run），异常向上传播给调用方；实际上完全依赖 outbox fallback 获取 terminal 结果
- **直接证据**: `cancel_entrypoint_run_and_wait` 先 `get_run`（line 436）再用其 `session_id` 去 `_attach_watcher`（line 437），然后才 `cancel_run`（line 442）。plan CLI-01-S2 明确要求 "必须在 Host.cancel_run(...) 前 attach watcher"（line 513），但未要求在 get_run 后检查是否已是终态。`get_run` 的返回值未被检查是否终态即进入 cancel 流程
- **影响**: 极端时序下 `cancel_run` 可能抛出 HostApiError（Host 拒绝取消已终态 Run），调用方（CLI adapter）需处理此异常；如果 Host 静默吸收（idempotent），则 watcher 可能错过 terminal 需完全依赖 outbox fallback，增加了不必要的延迟
- **建议改法和验证点**: 在 line 436 `get_run` 之后、line 437 `_attach_watcher` 之前，检查 `run_snapshot.status` 是否已是终态（通过 `_is_terminal_run_status`）。若是终态，直接进入 `_wait_for_terminal`（跳过 cancel_run），通过 outbox 获取 terminal 结果；若非终态，继续现有 watcher + cancel + wait 流程。测试需覆盖：Run 在 `get_run` 时已是终态 → 跳过 cancel_run 且 outbox fallback 成功
- **修复风险**: 低 — 仅增加一个提前返回分支，不改变现有 cancel 流程的控制流
- **严重程度**: 中

### 2-未修复-低-_drain_available_watcher_items 静默忽略 _WatcherFailure 且该路径无测试覆盖

- **入口/函数**: `_drain_available_watcher_items` / `_drain_host_events`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:493-494`（failure 注入）、`dayu/service/entrypoint_runtime.py:578-579`（静默 continue）
- **输入场景**: Host watcher iterator 在 drain 过程中抛出非 `CancelledError` 异常（如 Host 内部 event bus 断开、durable store 读取失败）
- **实际分支**: `_drain_host_events` 的 `except Exception as exc` 分支（line 493）将异常包装为 `_WatcherFailure` 放入 queue；`_drain_available_watcher_items` 的 `isinstance(item, _WatcherFailure)` 分支（line 578）执行 `continue` 静默跳过
- **预期行为**: watcher failure 后系统回退到 outbox fallback 获取 terminal，行为正确
- **实际行为**: `_WatcherFailure` 被静默忽略，没有任何日志、诊断或计数器，操作者无法知道 watcher 已失败、当前正完全依赖 outbox；drain task 在注入 `_WatcherFailure` 后退出（async for 循环终止），后续迭代不会再有新 live event
- **直接证据**: line 578-579 的 `if isinstance(item, _WatcherFailure): continue` 静默跳过且不更新任何状态；line 493-494 的 `except Exception as exc: await queue.put(_WatcherFailure(error=exc))` 捕获所有异常但不记录。与此同时，coverage 报告显示 line 493-494 未被任何测试覆盖（`Missing: 493-494`），line 579（`QueueEmpty` 异常）也未直接测试命中
- **影响**: observability gap — watcher 失败只通过 outbox fallback 频率增加间接体现，无直接信号。在 outbox 也 LAGGED 或 FAILED 时，排查 watcher 是否已死需要额外诊断手段
- **建议改法和验证点**: `_WatcherFailure` 消费时记录 warning-level 日志（使用 `dayu.runtime.log`），包含 `error` 详情。测试需注入 watcher 异常并断言 outbox fallback 仍正常工作（当前缺少 watcher failure → outbox 的集成路径测试）
- **修复风险**: 低 — 增加日志不影响控制流
- **严重程度**: 低

### 3-未修复-低-ensure_or_create_entrypoint_session 参数校验错误路径未测试

- **入口/函数**: `ensure_or_create_entrypoint_session`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:344-347`（create 缺 context/id）、`dayu/service/entrypoint_runtime.py:358-359`（ensure 缺 scope/slot_key）
- **输入场景**: 调用方错误传入 `create_new=True` 但未提供 `create_context` 或 `create_client_request_id`，或 `create_new=False` 但未提供 `scope` / `slot_key`
- **实际分支**: 四个 `if` 分支分别抛出 `ValueError`
- **预期行为**: 正确抛出 `ValueError` 并带清晰消息
- **实际行为**: 行为正确（raise 路径代码本身无误）
- **直接证据**: coverage 报告显示 line 345、347、359 未被测试覆盖。这些是 Service helper 的防御性校验，调用方（CLI adapter）应在构造参数时确保字段非空，但 Service 层独自暴露时缺少测试保证错误消息稳定
- **影响**: 低 — 不影响正确使用的调用方；但如果未来 UI adapter（WeChat/GUI）错误调用，错误消息的稳定性未被测试锁定
- **建议改法和验证点**: 补充四个错误路径的参数化测试，验证每个缺少必填字段的场景抛出 `ValueError` 且消息包含对应字段名
- **修复风险**: 低
- **严重程度**: 低

### 4-未修复-低-ClosableHostEventIterator Protocol 通过 cast 绕过类型安全

- **入口/函数**: `_attach_watcher`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:473`
- **输入场景**: `host.watch_session_events(session_id)` 返回的 runtime 对象不实现 `aclose()`
- **实际分支**: `cast(ClosableHostEventIterator, host.watch_session_events(session_id))` 强制将 `AsyncIterator[HostEvent]` 转型为 `ClosableHostEventIterator`
- **预期行为**: 当前 Host 实现（`open_host.py:544`）返回 async generator，Python async generator 确实有 `aclose()`，所以运行时安全
- **实际行为**: 运行时行为正确。但 `cast` 绕过了类型检查器——如果未来 Host 实现变更为不提供 `aclose()` 的 iterator（如返回一个手动实现的 `AsyncIterator` 类），类型检查器不会报告错误，运行时才会在 `_close_watcher`（line 506）的 `await watcher.aclose()` 处抛出 `AttributeError`
- **直接证据**: `Host.watch_session_events` 的 Protocol 签名返回 `AsyncIterator[HostEvent]`（api.py:544），`AsyncIterator` 不保证 `aclose()`。`cast(ClosableHostEventIterator, ...)` 在 line 473 绕过此限制
- **影响**: 低 — 当前 Host 实现安全，但 `cast` 使类型系统无法在未来 Host API 变更时发出警告。如果 Host 实现变为返回不带 `aclose()` 的对象，错误只在运行时出现
- **建议改法和验证点**: 两个可选方向：(a) 直接在 `_close_watcher` 中用 `hasattr` + `getattr` 检查 `aclose` 可用性并优雅降级（但 AGENTS.md 禁止无充分理由使用 hasattr/getattr）；(b) 在 Host public API Protocol 中将 `watch_session_events` 的返回类型从 `AsyncIterator[HostEvent]` 改为明确包含 `aclose()` 的 Protocol（但这是 Host API 变更，不在 S2 scope）。当前阶段可接受 `cast`，但建议在 residual risk 中登记
- **修复风险**: 低（若选 a）或中（若选 b，涉及 Host API 变更）
- **严重程度**: 低

## Open Questions

1. `_terminal_result_from_live_event` 在 line 611 将 `event.event_id` 加入 `seen_terminal_event_ids` 的时机早于 duplicate 判断（line 612-613）。对于重复 terminal event，`seen_terminal_event_ids` 会包含该 event_id（重复加入但 set 去重），而 `seen_dedupe_keys` 不会重复加入。这个不对称在当前逻辑下正确——`seen_terminal_event_ids` 用于 outbox 排除列表，应包含所有见过的 terminal 事件包括重复项。但代码意图不够明显，建议加一行注释说明意图。

2. `cancel_entrypoint_run_and_wait` 的 `cancel_run` 返回值（`RunSnapshot`）在 line 442 被丢弃。如果 Host 在 cancel_run 返回时已确认 Run 终态，此信息被浪费，后续 `_wait_for_terminal` 仍需再次 `get_run`。这不是 bug 但值得在后续优化时考虑。

## Residual Risk

1. **watcher failure → outbox fallback 集成路径无测试**（对应 Finding 2）：当前测试覆盖了 watcher 正常产出 terminal、watcher 无 terminal → get_run + outbox、outbox LAGGED/FAILED/CAUGHT_UP 等场景，但未测试 watcher 异常后 outbox fallback 的完整链路。风险：若 `_drain_host_events` 的异常处理（line 493-494）或 `_WatcherFailure` 的 queue 注入有 bug，测试不会捕获。

2. **`ensure_or_create_entrypoint_session` 的 `EnsureSessionRequest` 缺少 `context` 字段**：当前 Host public `EnsureSessionRequest` contract（对照 api.py）只接受 `scope`、`slot_key`、`metadata`，不接收 `context`。Service helper 在 ensure 路径（line 360）直接传 `EnsureSessionRequest(scope=..., slot_key=..., metadata=...)`，而 create 路径（line 348-356）传 `CreateSessionRequest` 带 context/client_request_id。这是正确的（ensure session 不需要调用上下文），但确保未来 Host API 变更时不会意外地在 ensure_session 增加 context 要求。

3. **`_runner_options_with_run_overrides` 仅覆盖 `temperature`**：当前只支持 temperature override，其它 `RunnerCallOptions` 字段（如 `top_p`、`stream`）不可 per-run override。这是 plan 明确的设计决策（plan line 262: "temperature 只覆盖完整 RunnerCallOptions.temperature"），但未来若需要支持更多 per-run runner options，需扩展此 helper。

4. **`_agent_policy_with_run_overrides` 中 `continuation_max_attempts`、`allow_tool_calls`、`continuation_prompt` 不可 per-run override**：与 plan 一致（plan line 262 只列出 5 个可覆盖字段），但需注意这些字段在 config 层面有值但不暴露给 per-run override。

5. **`ClosableHostEventIterator` cast 安全依赖 Host 实现细节**（对应 Finding 4）：若未来 Host `watch_session_events` 返回不带 `aclose()` 的实现，运行时会在 `_close_watcher` 处失败。当前 Host 使用 async generator（有 `aclose()`），安全。

## Conclusion

**pass-with-risks**

理由：S2 scope 严格限定，所有 10 项审查重点均通过基本检查。核心路径（submit 前 watcher attach、outbox fallback、cancel request 构造、override merge）逻辑正确。Finding 1（cancel race）是唯一的真实 correctness 风险但极端时序下发生概率极低且有 outbox 兜底；Finding 2-4 为 observability / 测试覆盖 / 类型安全 gap，不影响当前正确性。64 tests 全通过、pyright 零报错、覆盖率 95%。建议在进入 CLI-01-S3 前修复 Finding 1（增加终态检查），并在 S3 实现时补充 Finding 2-3 的测试路径。
