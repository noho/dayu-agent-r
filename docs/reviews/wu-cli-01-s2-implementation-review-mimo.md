# WU-CLI-01 / CLI-01-S2 Implementation Review

## Scope

- Mode: current changes (unstaged + untracked, relative to main)
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`
- Included scope: `dayu/runtime/location.py`、`dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`（untracked）、`tests/runtime/test_runtime_location.py`、`tests/service/test_host_assembly.py`、`tests/service/test_entrypoint_runtime.py`（untracked）、`dayu/README.md`、`dayu/service/README.md`、`tests/README.md`、`docs/host/ui-implementation-control.md`
- Excluded scope: S3–S7 CLI commands、Fins direct、init、Engine internals
- Parallel review coverage: 无

## Findings

### 1-未修复-中-watcher failure 被静默忽略继续 fallback

- **入口/函数**: `dayu/service/entrypoint_runtime.py:573-586`，`_drain_available_watcher_items`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:578-579`
- **输入场景**: watcher drain task 捕获到非 `CancelledError` 异常（如 Host 内部 stream 错误），将 `_WatcherFailure` 放入 queue
- **实际分支**: `_drain_available_watcher_items` 遇到 `_WatcherFailure` 时执行 `continue`，静默跳过
- **预期行为**: plan 未明确指定 watcher failure 的 fallback 合约。按保守策略，watcher failure 意味着 live event 观测不可靠，应至少记录到 observation state 或返回值中，让调用方知道 terminal 来源的可靠性已降级
- **实际行为**: watcher failure 被静默丢弃，Service 继续走 `get_run` + outbox fallback 路径，返回 `OUTBOX_READ` 终态。调用方无法区分"watcher 从未收到事件"和"watcher 出错后 fallback"
- **直接证据**: `entrypoint_runtime.py:578`: `if isinstance(item, _WatcherFailure): continue`
- **影响**: 不会丢失 terminal（outbox 兜底），但 watcher 健康状况不可观测。如果 watcher 持续失败且 outbox 投影也出问题，错误链路会更难诊断
- **建议改法和验证点**: 在 `_TerminalObservationState` 中增加 `watcher_failure: Exception | None` 字段；`_drain_available_watcher_items` 遇到 `_WatcherFailure` 时记录首个错误而非跳过；`EntrypointRunTerminalResult` 可选增加 `watcher_degraded: bool` 字段。或者，如果合约明确 watcher failure 应被忽略，应在 docstring 和测试中显式覆盖
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-watcher failure + outbox fallback 路径无测试覆盖

- **入口/函数**: `tests/service/test_entrypoint_runtime.py`
- **文件(行号)**: 无对应测试
- **输入场景**: `_FakeHost` watcher drain 捕获异常、queue 收到 `_WatcherFailure`、后续 `get_run` 终态 + outbox read 命中
- **实际分支**: 测试套件未覆盖此路径
- **预期行为**: plan S2 tests 要求 "watcher fallback test：fake watcher 不产出 terminal，但 `get_run(...)` 返回 terminal 且 `read_outbox_terminal_items(...)` 返回同 run item"。当前已有 `test_submit_entrypoint_turn_uses_outbox_when_live_terminal_missing`，但它测试的是 watcher 不产出任何事件（queue 为空），而非 watcher 出错
- **实际行为**: watcher 出错后 fallback 路径未被测试
- **直接证据**: 测试文件无 `_WatcherFailure` 相关 fixture 或断言
- **影响**: 如果未来重构 `_drain_available_watcher_items` 时误删 `continue` 分支或改变 `_WatcherFailure` 处理逻辑，无测试拦截
- **建议改法和验证点**: 新增测试：构造 `_FakeHost` 的 watcher 在 drain 过程中抛异常（通过注入一个 push 后抛异常的 event），验证 Service 仍通过 outbox 返回终态
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-低-_attach_watcher 使用 cast 而非 Protocol 结构匹配

- **入口/函数**: `dayu/service/entrypoint_runtime.py:473`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:473`
- **输入场景**: `host.watch_session_events(session_id)` 返回 `AsyncIterator[HostEvent]`（Host Protocol 声明）
- **实际分支**: `cast(ClosableHostEventIterator, ...)` 强制转换
- **预期行为**: Host Protocol 声明 `watch_session_events` 返回 `AsyncIterator[HostEvent]`，不含 `aclose()` 方法。`ClosableHostEventIterator` Protocol 额外要求 `aclose()`。类型安全的做法是让 Host Protocol 直接声明返回带 `aclose()` 的类型
- **实际行为**: `cast` 绕过了 pyright 的 Protocol 结构检查，依赖运行时实际实现具有 `aclose()` 方法
- **直接证据**: `entrypoint_runtime.py:473`: `return cast(ClosableHostEventIterator, host.watch_session_events(session_id))`
- **影响**: 如果 Host 实现返回不支持 `aclose()` 的 iterator，`_close_watcher` 会在运行时抛 `AttributeError`。当前 `open_host.py` 实现支持 `aclose()`，所以不会出问题，但类型安全有缺口
- **建议改法和验证点**: 优先方案：在 `dayu.host.api.Host` Protocol 中将 `watch_session_events` 返回类型改为 `ClosableHostEventIterator`（或等价 Protocol）。若不想改 Host Protocol，至少在 `ClosableHostEventIterator` docstring 中说明它只用于 Service 内部 cast，不作为 Host public contract
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 4-未修复-低-cancel_entrypoint_run_and_wait 先 get_run 再 attach watcher 存在理论 race

- **入口/函数**: `dayu/service/entrypoint_runtime.py:436-437`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:436-437`
- **输入场景**: `cancel_entrypoint_run_and_wait` 被调用时，Run 可能已在 `get_run` 返回后、`cancel_run` 调用前进入终态
- **实际分支**: `get_run` → attach watcher → `cancel_run`；如果 Run 已终态，`cancel_run` 可能抛 `HostApiError`
- **预期行为**: plan 要求 "cancel 前有 watcher"，实现满足。但 plan 也要求 cancel 后 "继续观察到 terminal"，如果 `cancel_run` 因 Run 已终态而失败，watcher 仍然能看到终态事件
- **实际行为**: `cancel_run` 的 `HostApiError` 会向上传播，`_close_watcher` 在 `finally` 中正确清理。调用方收到异常，但 cancel 前已 attach 的 watcher 已被丢弃
- **直接证据**: `entrypoint_runtime.py:441-461`: `cancel_run` 在 try 块内，异常会跳过 `_wait_for_terminal`
- **影响**: 在 cancel 与 terminal 竞争时，调用方收到 `HostApiError` 而非 terminal result。UI adapter 需要把此异常映射为"Run 可能已自行结束"，而非"cancel 失败"。这是 race 的固有行为，但 Service helper 可以更明确地处理
- **建议改法和验证点**: 在 `cancel_entrypoint_run_and_wait` 中 catch `HostApiError`，如果 `cancel_run` 失败但 watcher 已 attach，继续 `_wait_for_terminal` 观察终态。或者在 docstring 中说明此 race 行为，让 UI adapter 决定如何处理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 5-未修复-低-_wait_for_terminal 无超时或最大迭代保护

- **入口/函数**: `dayu/service/entrypoint_runtime.py:537`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:537`
- **输入场景**: watcher 不产出事件、`get_run` 持续返回非终态、outbox 投影 LAGGED
- **实际分支**: `while True` 无限循环，只在找到 terminal 时返回
- **预期行为**: Service helper 作为 reusable 边界，应有防御性超时或让调用方通过外部机制（如 `asyncio.wait_for`）控制超时
- **实际行为**: 循环无内置超时。调用方必须自行用 `asyncio.wait_for` 包装或通过 cancel 中断
- **直接证据**: `entrypoint_runtime.py:537`: `while True:`
- **影响**: 如果 Host 出现异常状态（如 Run 永不终态、outbox 投影永久 LAGGED），`_wait_for_terminal` 会永久阻塞。CLI adapter 可以通过 SIGINT cancel 中断，但非 CLI 调用方（如 WeChat）需要额外的超时机制
- **建议改法和验证点**: 接受当前设计（Service 不持有超时），但在 docstring 中明确说明调用方需自行控制超时。或增加可选 `timeout_seconds` 参数
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- **watcher failure 合约未明确**: plan 未定义 watcher drain 异常时 Service 的行为。当前实现选择静默忽略并 fallback，这是合理的保守策略，但应在测试或 docstring 中显式声明此合约。
- **`_FakeHost.watch_session_events` 返回类型**: 测试中 `_FakeHost.watch_session_events` 返回 `_FakeHostEventIterator`，但类型注解写 `AsyncIterator[HostEvent]`。pyright 当前通过是因为 `_FakeHostEventIterator` 实现了 `__aiter__`/`__anext__`，但 `cast(ClosableHostEventIterator, ...)` 在测试路径中依赖运行时 duck typing。
- **`HostEvent.run_id` 类型为 `str | None`**: `_terminal_result_from_live_event` 直接使用 `event.run_id` 构造 `EntrypointRunTerminalResult.run_id: str`。Host API 合约保证 terminal event 的 `run_id` 非 None，但代码中无显式 assert。pyright 可能报 narrowing error。
- **未覆盖并发场景**: 无测试覆盖同一 Session 中多个 Run 同时终态、或 watcher queue 中交替出现多个 Run 事件的边界场景。
- **`_read_outbox_terminal` 内循环无上限**: `has_more=True` 时循环继续读取下一页，理论上如果 outbox 持续有新 item 且目标 run 不在其中，循环可能过长。实际风险低（outbox 页会耗尽），但可考虑增加 max pages 保护。
- **`_close_watcher` 中 `aclose` 在 `cancel` 之前**: 如果 `aclose()` 阻塞，`drain_task.cancel()` 会延迟执行。当前 `open_host.py` 的 `aclose` 实现应该是非阻塞的，但值得在 Host watcher contract 中确认。

## Conclusion

**pass-with-risks**

实现严格限于 S2 scope（runtime location + reusable Agent entrypoint Service boundary），未实现 S3–S7 / CLI command / Fins direct / init。Service boundary 清晰：不解析 CLI args、不 stdout/stderr、不安装 signal handler。只使用 Host public API / Protocol，未读取 Host durable internals 或导入 Engine 内部。

核心逻辑（submit 前 watcher attach、accepted_run_id 过滤、fast terminal race、outbox fallback with CAUGHT_UP/LAGGED/FAILED、CancelRunRequest 完整构造）均正确实现。`ServiceRunOverrides` 通过 `host_assembly` 真源合并，未在 `entrypoint_runtime` 中重写 merge 逻辑。

主要风险是 watcher failure 静默忽略（Finding 1）和对应测试缺失（Finding 2），以及 `cast` 类型安全缺口（Finding 3）。这些不影响正确性（outbox 兜底保证 terminal 不丢失），但影响可诊断性和类型安全。
