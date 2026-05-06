# Host P2 常规 Code Review

审查对象：当前分支 `codex/host-p2-toolruntime-truncate` 相对 `HEAD` 的未提交 diff 与 untracked files。

审查依据：

- `docs/host/phase2-plan.md`
- `docs/host/migration-plan.md` 的 workflow / P2 gate
- 当前 `git diff HEAD --` 与 untracked files
- `dayu/host/_tool_runtime.py`、`dayu/host/contracts.py`、`dayu/host/_run_harness.py`
- P2 tests、`utils/smoke_host_tool_runtime.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

## Findings

### P1-已修复：未校验 cursor 绑定前先按请求 run 写入 fetch_more 事实，会污染错误 Run 的 EventLog

修复状态：已修复。`fetch_more()` 现在先按 cursor 原文读取可信 record；record 不存在时只返回 typed
failure 且不写任意 run fact。record 存在时先按 owner run 做 terminal guard，再把 binding mismatch 的
`tool_cursor_denied` / `tool_fetch_more_failed` 写入 owner run，不写入请求伪造的 run；通过
`test_cross_run_fetch_more_does_not_pollute_claimed_run` 覆盖。

文件 / 行号：

- `dayu/host/_tool_runtime.py:342`
- `dayu/host/_tool_runtime.py:353`
- `dayu/host/_tool_runtime.py:354`
- `dayu/host/_tool_runtime.py:376`
- `dayu/host/_tool_runtime.py:993`

问题：

`fetch_more()` 先用 `request.run_id` 判断 terminal，再立即调用 `_append_fetch_requested(request)`，之后才读取 cursor record 并校验 session / run / tool_call / scope token。失败路径 `_fetch_failure()` 也继续用 `request.run_id`、`request.session_id`、`request.tool_call_id` 写 canonical failed fact。

这意味着调用方只要拿到某个有效 cursor handle，就可以构造 `ToolFetchMoreRequest(run_id="other_run", ...)`，在 `other_run` 的 EventLog 中写入 `tool_fetch_more_requested` 与 `tool_fetch_more_failed`；若 `other_run` 不存在，也会被创建出 canonical facts。当前 `tests/host/test_phase2_tool_runtime_boundary.py:232` 只断言跨 session / run / tool_call 会失败，没有断言错误 run 的 EventLog 不被污染。

影响：

- 破坏 P2 的 run-scoped cursor 语义：事实被写到请求声称的 run，而不是 cursor record 绑定的 run。
- 破坏 EventLog truth：canonical facts 不再能可靠表达“该 run 自己发生的 ToolRuntime 补读事实”。
- terminal guard 校验的是 `request.run_id`，不是 record 绑定 run；跨 run 请求会绕开真实 run 的 terminal 状态判断，虽然最终被 scope mismatch 拒绝，但拒绝事实仍可能写入错误 run。

建议：

先读取 cursor record，并在可信 record 存在后决定事实归属。对于 scope mismatch，建议将 denied / failed facts 写到 record 绑定的 `run_id` / `session_id` / `tool_call_id`，并在 data 中记录被拒绝原因；对于完全找不到 cursor 的请求，不应无条件创建任意 run 的 canonical facts，至少需要先确认该 run 存在且未 terminal。补充测试：跨 run fetch_more 后，原 run 只出现 denied / failed 审计或按设计不追加；错误 run 不应被污染。

### P2-已修复：handle 读取阶段的 expired / denied 不进入 RunEvent，P2 要求的 cursor 失败事实不完整

修复状态：已修复。`get_tool_fetch_more_handle()` 对可信 record 的 binding mismatch / expired 分别写入
owner run 的 `tool_cursor_denied` / `tool_cursor_expired`；record 不存在时不伪造 run fact；owner run
terminal 后返回 typed failure 且不追加事实。新增 handle denied / expired / terminal 后不追加事实测试。

文件 / 行号：

- `dayu/host/_tool_runtime.py:274`
- `dayu/host/_tool_runtime.py:285`
- `dayu/host/_tool_runtime.py:292`
- `dayu/host/_tool_runtime.py:304`

问题：

`get_tool_fetch_more_handle()` 是 P2 公开补读路径的第一步，但它在 cursor 不存在、绑定不匹配或过期时只返回 `ToolFetchMoreHandleFailedResult`，不会追加 `tool_cursor_denied` / `tool_cursor_expired` canonical RunEvent。

P2 plan 要求 `cursor expired / denied` 进入 `RunEventStore`，而当前只有 `fetch_more()` 阶段的过期 / 拒绝会写事件。若调用方在 handle 阶段就被拒绝或遇到过期 cursor，这些治理事实不可补读、不可审计，测试也没有覆盖 handle 失败路径的 EventLog 行为。

影响：

- EventLog 中的 cursor lifecycle 不完整，P6 observer / audit 后续无法从 canonical facts 派生完整失败轨迹。
- `get_tool_fetch_more_handle(...)` 作为 public Run 级入口，失败行为不符合“截断与补读事实进入 P1.5 RunEventStore”的 P2 验收口径。

建议：

为 handle 读取失败路径明确事实策略：对已找到 record 的过期 / 绑定拒绝，追加 `tool_cursor_expired` / `tool_cursor_denied`；对 record 不存在的 fingerprint，若无法可信归属 run，则不要伪造任意 run fact，或先引入明确的 run 存在性校验。补充测试覆盖 handle 阶段 expired / denied 的 canonical fact 与 terminal 后不追加事实。

### P2-已修复：smoke 绕过 Run 级 public 补读入口，无法验证 README 宣称的 P2 public surface

修复状态：已修复。`utils/smoke_host_tool_runtime.py` 现在通过 `LocalRunHarness.get_tool_fetch_more_handle()`
和 `LocalRunHarness.fetch_more_tool_result()` 展示 Run 级补读路径，日志仍只输出 cursor fingerprint、
事件 cursor、chunk size、错误码等摘要，不输出 `scope_token` 或完整大结果。

文件 / 行号：

- `utils/smoke_host_tool_runtime.py:30`
- `utils/smoke_host_tool_runtime.py:31`
- `utils/smoke_host_tool_runtime.py:214`
- `utils/smoke_host_tool_runtime.py:230`
- `dayu/host/_run_harness.py:490`
- `dayu/host/_run_harness.py:505`

问题：

P2 plan 要求 smoke 展示通过 `get_tool_fetch_more_handle(...)` 获取非 EventLog handle，并通过 `fetch_more_tool_result(...)` 补读。当前 smoke 直接 import `_tool_runtime.InMemoryToolRuntime` / `ToolRuntimeToolExecutor`，并调用 `runtime.get_tool_fetch_more_handle()`、`runtime.fetch_more()`，没有覆盖 `dayu.host` 包根 public 函数，也没有覆盖 `LocalRunHarness.get_tool_fetch_more_handle()` / `LocalRunHarness.fetch_more_tool_result()` 这层 Run 级入口。

影响：

- `dayu/host/README.md` 已把 `await get_tool_fetch_more_handle(request)` 与 `await fetch_more_tool_result(request)` 写成当前 public surface，但 smoke 不能证明这条路径真的可用。
- public wrapper、默认 harness loop 绑定、harness 与 runtime 装配关系即使回归，当前 smoke 仍可能通过。

建议：

调整 smoke 或新增测试，让至少一条路径经由 Run 级入口完成 handle 获取和补读。若默认 harness 暂时无法注入 fake executor / truncate spec，可用内部 `LocalRunHarness` 组装 runtime，但调用 harness 的 `get_tool_fetch_more_handle()` 与 `fetch_more_tool_result()`；同时保留日志不输出 `scope_token`、完整大结果或大块 delta。

## 其它观察

- `scope_token` 未进入 `RunEvent`、Engine projection、README 示例或 smoke 日志；当前测试和 smoke 输出均未发现明文 token 泄漏。
- Engine 生产代码未被修改，边界测试也验证 Engine 不 import `dayu.host`。
- terminal 后 `fetch_more()` 当前会返回 typed failure 且不追加新 RunEvent，符合 P1.5 terminal guard 方向。
- `dayu/contracts/tool_schema.py:21` 与 `dayu/contracts/tool_schema.py:22` 重复 import `Mapping`，不影响行为，可在修复其它问题时顺手清理。
  修复状态：已清理重复 import。

## 验证

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase1_public_boundary.py tests/contracts/test_package_exports.py -q
```

结果：`24 passed in 0.15s`

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`

已运行：

```bash
source .venv/bin/activate && python utils/smoke_host_tool_runtime.py --log-level DEBUG
```

结果：smoke 通过；日志仅输出 cursor fingerprint、事件 cursor、chunk size、error code 等摘要，未输出明文 `scope_token` 或完整大结果。

## Review 结论

常规 code review 修复项已落地。`fetch_more()` 事实归属、handle 阶段 cursor lifecycle facts、Run 级 smoke
补读路径与重复 import 均已修复；最终通过情况以本轮实施后的验证命令为准。

## 复审结论

常规 code review 复审通过。当前 diff 已修复初审 findings，未发现新的阻塞问题。

复审重点确认：

- `fetch_more()` 先按 cursor 原文读取可信 record；record 不存在时只返回 typed failure，不创建任意 run
  事实；跨 run / session / tool_call 拒绝事实写入 cursor owner run，不污染请求伪造的 run。
- `get_tool_fetch_more_handle()` 对可信 record 的 denied / expired 写入 owner run；record 不存在时不伪造
  EventLog；owner run terminal 后返回 typed failure 且不追加新事实。
- `utils/smoke_host_tool_runtime.py` 的补读阶段经由 `LocalRunHarness.get_tool_fetch_more_handle()` 与
  `LocalRunHarness.fetch_more_tool_result()`，不直接绕过 Run 级补读入口。
- `scope_token` 仍只存在于受控 handle / fetch request，不进入 `RunEvent`、Engine projection、README 示例或
  smoke 日志。
- 测试已覆盖语义差异：跨 run 不污染错误 run、handle denied / expired owner fact、terminal 后不追加事实、
  scope token 非 EventLog 交付与 Engine projection 不恢复 OLD `fetch_more_args`。

## 复审状态

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase1_public_boundary.py tests/contracts/test_package_exports.py -q
```

结果：`29 passed in 0.15s`

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`

已运行：

```bash
source .venv/bin/activate && python utils/smoke_host_tool_runtime.py --log-level DEBUG
```

结果：smoke 通过；日志仅输出 cursor fingerprint、事件 cursor、chunk size、error code 等摘要，未输出明文
`scope_token` 或完整大结果。
