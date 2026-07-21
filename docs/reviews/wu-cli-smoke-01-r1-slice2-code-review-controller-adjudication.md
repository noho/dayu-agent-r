# WU-CLI-SMOKE-01-R1 Slice 2 Code Review Controller Adjudication

## Scope

- Gate: Slice 2 code review。
- Base: accepted Slice 1 commit `70ccda60`。
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-r1-slice2-implementation-codex.md`。
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-r1-slice2-code-review-mimo.md`（AgentMiMo，PASS）。
  - `docs/reviews/wu-cli-smoke-01-r1-slice2-code-review-ds.md`（AgentDS，PASS）。
- Controller validation:
  - 新增闭环测试 `21 passed, 3 warnings`。
  - 相关文件 pyright `0 errors, 0 warnings, 0 informations`。
  - 独立 3×1000 stress `1 passed`。
  - `git diff --check` pass。

## Motivation / Owner Check

Slice 2 的问题性质是生产级证据缺口，而不是已证明的生产实现缺陷。测试必须从 Host transient owner、Host public merge、Service bounded relay 与 CLI renderer 的真实路径证明 zero-row、单 watcher 隔离、terminal durable truth、typed failure 传播与资源回收；不能用 fake-only 断言替代。

两路 review 独立追踪了上述路径，均确认测试没有绕过 Host ingest、Host subscription、Service relay、Outbox 或 CLI renderer。可控 `LocalEngineWorker` 只替代外部 LLM provider，是确定性测试输入 owner；生产 Python 零修改的结论成立。

## Decisions

### MiMo 1-F1：替换 subscription private `_ready` 的 barrier coupling

- `rejected-with-reason`，不形成 current fix 或 residual risk。
- `HostTransientDeltaSubscription` 使用 `__slots__` 且显式包含 `_ready`。如果 production 删除或重命名该字段，测试赋值会直接失败；如果字段仍存在但 production readiness 不再使用它，`wait_entered` barrier 不会到达并以 timeout 失败。因此该测试不会在 readiness primitive 漂移后静默通过。
- 这些测试验证的正是 owner 内部 lost-wakeup 线性化点，白盒替换 `asyncio.Event` 是必要且范围准确的 owner-level test seam。额外注释不是 correctness、可维护性或 contract 修复的必要条件。

### MiMo 2-F2 / DS F-2：E2E 的 bounded polling 与 50ms 稳定性检查

- `rejected-with-reason`，不形成 current fix 或 residual risk。
- `_wait_for_yielded_count()` 只把单调计数等待到 `block_start + 256 + 1`；第 257 个 item 已从真实 Host iterator 取出并阻塞在 Service `await queue.put(event)`。此时 Service 主循环仍被测试 Event 挡在首次 `get_run()`，不会消费 relay，故计数无法继续前进。
- `asyncio.sleep(0.05)` 是在上述 owner state 已确定后的附加稳定性检查，不参与到达条件，也不存在 reviewer 所述“drain-cycle 恰好继续”的可达路径。把它替换为第二次立即返回的 `_wait_for_yielded_count()` 反而不验证稳定性；引入 Service queue-full public signal则会为测试扩张生产 contract，违反最小化原则。

### MiMo 3-F3 / DS F-1：`cast(Host, probe)` 的局部 Host probe

- `rejected-with-reason`，不形成 current fix 或 residual risk。
- 当前测试需要在 Service 的首次 `get_run()` 处设置 barrier，同时让 `watch_session_events`、`submit_followup` 与 `read_outbox_terminal_items` 透明进入真实 Host。四个方法是该执行路径的直接证据闭集；运行时返回值和异常均未重算或 fallback。
- 若未来 Service 扩大 Host 调用面，测试以 `AttributeError` 明确失败是期望的 contract-change signal。为约十五个未使用方法添加 `NotImplementedError` 桩会制造测试 God facade；以 `__getattr__` 泛化转发则直接违反本仓库禁止用动态属性逃避类型与边界设计的约束。当前显式 `cast` 比两种建议都更小、更严格。

### MiMo 4-F4：stress 默认排除

- `accepted-as-designed`，不形成 current fix 或 residual risk。
- 独立 stress marker、默认快速 suite 排除、README 显式命令与本 WU plan 完全一致，也遵循仓库已有 production stress convention。是否增加定时 CI stress job 属于 CI pipeline owner，不是当前 transient owner 的代码缺陷；当前没有证据要求转成新的 residual item。

### 两路 PASS 结论与九项 adversarial verification

- `accepted`。
- 3×1000 三类 delta 真实进入 `open_host` / ingest / transient hub，EventLog 三类 row 严格为 0；Run、Attempt、terminal、final answer 与 Outbox identity 同源。
- 慢 watcher 精确容量 256 overflow；快 watcher继续接收完整 mixed stream 和成功 terminal，Run 不取消、不伪造 terminal。
- 四类 readiness barrier、attach/no replay/first delta、cancel/aclose/missing/corrupt durable read/Host close cleanup 均有 owner-state 证据。
- DS-F02 已由真实 Host→Service→CLI mixed stream、typed watcher failure、Outbox fallback、thinking/final 单次显示闭环关闭。
- 572 行 test support 按 worker、event constructor、typed count、durable snapshot 与 SQLite strict reader 分责；没有 God function/dataclass、`Any`、`object`、`hasattr/getattr` 或生产反向依赖。
- 四份 README 只同步当前已实现边界，根 README 与 Engine README/design 不命中更新触发。

## Residual Risk

- transient delta 在 overflow、detach、断线、Host close、崩溃或进程重启后不可恢复；这是已接受的 live-only contract。
- 容量 256 是内部安全值，当前无生产负载调优数据；不提升为 public knob。
- durable event 与 transient delta 不承诺跨域总序，只承诺各自内序与同 Run terminal fence。
- E2E 不访问真实外部 LLM provider；可控 worker 是测试输入边界，其后的 Host、Service、SQLite/Outbox 与 CLI 路径均为生产实现。

以上均为 accepted plan 已记录边界，无新增未归属 residual risk。

## Decision

`accepted-slice2-review`。两路均 PASS，0 个 blocking finding，0 个 accepted current-fix finding；无需进入 fix / code re-review，也无需为本 gate 新增 supplemental finding-fix batch。下一 gate 为 accepted Slice 2 commit，随后进入 aggregate deepreview。
