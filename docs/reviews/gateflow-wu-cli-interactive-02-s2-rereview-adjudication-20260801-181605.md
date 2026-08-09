# Gateflow S2 re-review adjudication — `wu-cli-interactive-02-conformance-fixes`

## Gate

- Gate：S2 `re-review`
- MiMo artifact：`docs/reviews/code-review-20260801-180937.md`
- DS artifact：`docs/reviews/code-review-20260801-181208.md`
- Controller decision：`changes required`
- Next gate：AgentCodex 修复 S2-CR-004，随后双路独立 re-review

## Accepted finding closure

- S2-CR-001：原 unsupported-loop fallback 已建立并通过 startup/active tests，但其 signal-handler 内通知方式仍有下述新缺口，暂不能关闭。
- S2-CR-002：`closed`。真实 PTY readiness、ordinary Enter、exact Shift+Enter、Escape 与 terminal restore 证据成立。
- S2-CR-003：`closed`。真实无 label CLI→Service→Host 路径与 durable Run/Attempt truth成立；没有 fake terminal、SQLite写入或 scope expansion。

## Reviewer low findings

- DS re-review 01（重复 `close()` 显式 early return）：`rejected-with-reason`。现有 `NONE` 路径已经是精确幂等 no-op；增加分支没有行为或维护收益。
- DS re-review 02（integration monitor 的空 install/close）：`rejected-with-reason`。artifact 自己也确认这是测试 seam 且无需修改，不是 finding。
- MiMo re-review：无新增 finding。

## S2-CR-004 — 高 — 同步 Python signal handler 直接操作 asyncio Event

- Status：`accepted`
- Owner：`dayu.cli.agent_entrypoint.CliSigintMonitor` 的同步 fallback 安装/通知边界。
- Direct code evidence：`install()` 当前把 `self.notify` 直接交给 `signal.signal(SIGINT, ...)`；`notify()` 立即执行 `self._event.set()`。`asyncio.Event` 是事件循环同步原语，不提供 signal-handler 重入安全 contract。
- Review evidence issue：`code-review-20260801-181208.md` 声称 `Event.set() -> Future.set_result() -> call_soon_threadsafe`，该描述不是当前实现保证；不能据此判定安全。同步 handler 与 asyncio `add_signal_handler` 的核心区别正是前者直接运行 Python handler，后者由 loop 安排 callback。
- Counterexample：SIGINT 在 event loop 正修改 ready queue / Future callback state 时重入 `Event.set()`；当前代码直接触碰 loop-owned Future/event state，行为依赖 CPython偶然实现。F08 要求 unsupported-loop 平台也使用同一 graceful lifecycle，不能把重入安全留给实现细节。
- Required owner fix：同步 `signal.signal` handler 只做 `loop.call_soon_threadsafe(self.notify)`（不得直接 `Event.set()`）；安装状态必须在新 handler 可被调用前完整可见，安装失败要恢复 `NONE` 状态；`close()` 同源恢复 previous handler并清理 loop引用。不得在 interactive consumer 加 fallback，也不得改变 ASYNCIO模式或 prompt/Fins语义。
- Required tests：同步 harness 直接调用 installed handler 后，在 event loop 获得执行机会前 `count` 不应同步变化；随后 `wait_next` 必须收到一次通知。startup/active三阶段、handler恢复、重复close、prompt/Fins回归继续通过。

## Validation and residual risk

- Controller 已独立重跑 PTY、startup fallback、active fallback、真实 Host queued closeout及三条 Host stage owner tests：`7 passed`。
- S2-CR-004 修复前，Windows真实 console仍是外部平台证据，但同步 fallback 的内部调度安全不是可接受 residual risk。
- S3-S6 未进入；不得提交、push或更新README/registry/oracle。
