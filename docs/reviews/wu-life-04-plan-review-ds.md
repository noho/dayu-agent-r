# WU-LIFE-04 Plan Review — AgentDS Adversarial Review

Review target: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
Reviewer: AgentDS
Date: 2026-07-04
Verdict: **pass-with-findings** (0 blocking, 5 non-blocking findings)

## 1. 动机验证

Plan §1 的动机成立，直接代码证据充分：

- `dayu/host/api.py:57`: `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS = 300.0`
- `dayu/host/api.py:1080`: `OpenHostOptions.active_cancel_timeout_seconds` 默认 300s，暴露为 public API
- `dayu/host/dispatch.py:1083`: `tick_active_cancel_watchdog` 从 `local_execution.active_cancel_timeout_seconds` 读 timeout
- `dayu/host/dispatch.py:1102`: 用 `(now - cancel_requested_at).total_seconds() < timeout_seconds` 判定 closeout 资格——这确实是 post-cancel 独立预算
- `dayu/host/open_host.py:898-899`: `defer_accepted_cancel_to_watchdog=local_execution.active_cancel_timeout_seconds is not None`——用 timeout 存在性决定 startup recovery defer
- `dayu/host/dispatch.py:2554`: watchdog loop 启动被 `active_cancel_timeout_seconds is None` 门控

`cancel_requested_at` 是用户取消时间，不是工具调用开始时间。用 `cancel_requested_at + timeout_seconds` 确实是在用户取消后额外授予一段独立等待预算，这与 `tool_execution_timeout_seconds` 是唯一工具调用最长运行时间真源的语义冲突。

**边界正确**：Plan §3 明确把 WU-TOOLS-CANCEL-01 的 physical interrupt 排除在 scope 外，与 Engine design §11 一致（"该 timeout 只表示 Engine 不再等待 execute() 的 handshake outcome。它不证明工具内部线程、子进程、HTTP 请求或远端 job 已停止"）。本 WU 只裁决 Host durable truth 与 deadline 语义，不越界。

## 2. 架构边界审查

### 2.1 Engine contract 不变

Plan §4 正确识别：Engine design §5 和 §11 已冻结 `AgentPolicy.tool_execution_timeout_seconds` 是唯一工具 handshake timeout 真源。本 WU 不需要修改 Engine code 或 Engine design。

### 2.2 Host 不能知道 per-tool original deadline — 验证通过

Plan §7 的核心论断正确。直接证据：

- `_ActiveCancelWatchdogCandidate` (`dispatch.py:413-425`) 只有 `run_id`, `session_id`, `attempt_id`, `cancel_requested_at` 四个字段
- `cancel_requested_at` 来自 `CANCEL_REQUESTED` event 的 `occurred_at`，与工具调用时刻无关
- 没有 durable fact 记录单个工具调用的开始时间或 deadline
- `USER_INPUT_ACCEPTED.effective_execution_config` 可重建 `AgentPolicy`（含 `tool_execution_timeout_seconds`），但这是 duration，不是 start time
- `ToolRuntime` 的 batch deadline 是 runtime-local，不 durable

因此 plan 的 "no-extra-budget closeout" 方案是**最小正确方案**：不尝试推导 per-tool deadline（会引入错误），而是取消 commit 后在 watchdog 下一次 tick 中立即 closeout。这**可以**缩短正在运行中的工具（如果工具调用恰好在 cancel 之前刚开始），但**不能**延长原始 deadline——正确性优先。

### 2.3 状态机影响 — 无破坏性

Plan §6 的状态机变更检查：
- `RUNNING + active cancel -> CANCELLING` 不变 ✓
- Cancel commit 后传播 cancel 到 active worker 不变 ✓
- Terminal first-committer-wins 不变 ✓
- Watchdog closeout 从 "等待 `cancel_requested_at + timeout_seconds`" 变为 "tick 上立即关闭 eligible CANCELLING/RUNNING Attempt" ——这是**加速** closeout，不是延迟或覆盖 ✓
- 迟到 terminal（cooperative `run_cancelled`、success、failure、waiting、lost）仍然 first-committer-wins ✓

无状态机破坏。唯一的语义变化是 watchdog closeout 可能比旧行为**更早**发生（因为不再等待 300s），这对于用户取消体验是改善。

## 3. Slice 切分审查

Plan §8 提出 2 个 implementation slices。对照 control doc Slice 切分原则逐项检查：

| 原则 | Slice 1 (Design + Contract) | Slice 2 (Watchdog Behavior) |
|---|---|---|
| 语义闭环 | ✓ 从 public API 删除到 README 同步，可独立验证 | ✓ 从 watchdog 逻辑到 durable payload 到测试，可独立验证 |
| 沿依赖边界 | ✓ 先删 public contract，Slice 2 消费新 contract | ✓ 依赖 Slice 1 的 contract 结论 |
| 可独立验证 | ✓ grep + 构造测试 + pyright | ✓ 所有 watchdog 测试 + pyright |
| 非机械拆分 | ✓ 不是按模块切——合并了 design/api/open_host/README | ✓ 合并了 dispatch/run_transition/所有测试 |

**Slice 预算**：2 slices，在小型 cross-module cleanup 默认 1-3 个 slices 范围内。正确。

**未漏项**：对照 `rg "active_cancel_timeout_seconds"` 的完整 hit list：
- `dayu/host/api.py` (6 hits including field, default, validation, docstring) → Slice 1
- `dayu/host/open_host.py` (2 hits: projection + defer check) → Slice 1
- `dayu/host/dispatch.py` (3 hits: wake guard, tick guard, loop startup guard) → Slice 2
- `dayu/host/README.md` (1 hit) → Slice 1
- `docs/host/design.md` (2 hits: L2493, L2502) → Slice 1
- `tests/host/test_active_cancel_dispatch.py` (8 hits) → Slice 2
- `tests/host/test_open_host_runtime.py` (3 hits) → Slice 2
- `tests/host/test_dispatch_scheduler.py` (1 hit) → Slice 2
- `dayu/service/` — 0 hits, 无需修改 ✓

## 4. Findings

### DS-F01 [LOW] — Watchdog 无条件启用后的边界行为未充分定义

**Evidence**: Plan §6 说 "Prefer deleting `HostLocalExecutionOptions.active_cancel_timeout_seconds` too. If a direct implementation blocker appears, it may be replaced by an internal non-public scheduler behavior flag." 同时 Plan §8 Slice 2 说 "`wake_active_cancel_watchdog` should no longer return because a timeout option is `None`" 和 "`_start_active_cancel_watchdog_loop` should no longer be gated by timeout seconds."

**问题**: 如果 `active_cancel_timeout_seconds` 完全删除（包括 `HostLocalExecutionOptions` 上的字段），watchdog 将无条件启用——`HostDispatchScheduler.open()` 在 line 999 无条件调用 `_start_active_cancel_watchdog_loop()`，而 loop 内部目前通过 `tick_active_cancel_watchdog` 的 `timeout_seconds is None` 检查做 no-op 短路。删除后，watchdog loop **始终运行**，`tick_active_cancel_watchdog` 不再需要 timeout guard。

但 plan 同时保留了 "可能需要内部 non-public flag" 的后路。这个后路如果实现为一个简单的 `bool` 标志，会导致 widget 可以 disable。当前 `active_cancel_timeout_seconds=None` 在 design.md L2502 被描述为 "特殊装配 opt-out"，用于测试和特殊场景。Plan 需要裁决：完全删除该 opt-out 后，测试场景中原来依赖 `None` 来验证 orphan recovery CANCELLING→LOST 路径的用例如何处理。

**建议**: 在 plan §6 或 §8 中明确：删除 `active_cancel_timeout_seconds` 后，watchdog **无条件启用**；不接受内部 disable flag。需要测试 orphan CANCELLING→LOST 路径的场景应通过构造"CANCELLING Run 没有 accepted cancel fact"（即 `_has_accepted_cancel_fact` 返回 False）来触发 recovery 路径，而非通过 disable watchdog。

**候选裁决**: accepted / deferred-with-owner (implementation agent 可在 Slice 2 实现时细化)

### DS-F02 [LOW] — `tests/host/test_run_attempt_transitions.py` 列为 affected 但无直接 `active_cancel_timeout_seconds` 引用

**Evidence**: Plan §5 和 §8 均将 `tests/host/test_run_attempt_transitions.py` 列为 affected file。但 `rg "active_cancel_timeout_seconds" tests/host/test_run_attempt_transitions.py` 返回零结果。

**问题**: 该测试文件可能通过 `ActiveCancelTimeoutCloseoutInput` 的构造间接依赖 `timeout_seconds` 字段。如果 Slice 2 重命名/重构了 `ActiveCancelTimeoutCloseoutInput`，该测试文件确实需要更新。但 plan 没有明确说明为什么这个文件被列入 affected list。

**建议**: Implementation agent 应在 Slice 2 开始前验证 `tests/host/test_run_attempt_transitions.py` 是否有对 `ActiveCancelTimeoutCloseoutInput` 或 `active_cancel_timeout_closeout_in_transaction` 的引用；如无，从 affected files 中移除；如有，在 Slice 2 exact changes 中具体说明。

**候选裁决**: accepted (implementation 时验证即可，不阻塞 plan)

### DS-F03 [LOW] — `_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL` 常量值仍为 `"active_cancel_timeout"`

**Evidence**: `dayu/host/dispatch.py:228`: `_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL = "active_cancel_timeout"`。该常量被传入 `ActiveCancelTimeoutCloseoutInput.worker_lifecycle_signal` 并最终写入 durable EventLog payload。

**问题**: Plan §6 说 "Rename durable input/function names only if needed for clarity... Payload should stop carrying `timeout_seconds` and `timed_out_at`"。但 plan 没有明确提到这个 diagnostic signal 常量。如果 watchdog 不再是 "timeout" 语义而是 "accepted-cancel closeout supervisor"，这个常量值 `"active_cancel_timeout"` 会 misdescribe EventLog 中的事实。这不是 correctness 问题（只是 diagnostic label），但会影响后期 audit/trace 可读性。

**建议**: Slice 2 实现时考虑将此常量值改为 `"active_cancel_watchdog_closeout"` 或等价 self-explanatory 值。Plan 可在 §8 Slice 2 exact changes 中加一条 optional rename note。

**候选裁决**: accepted (non-blocking，实现时自行裁决)

### DS-F04 [MEDIUM] — `docs/host/design.md` 变更描述不够具体

**Evidence**: Plan §4 描述 design.md 需要的变更为高层次方向（"Host design 应改为..."），但没有给出 precision 级别足够让 implementation agent 直接执行的具体文本替换指导。对照 design.md L2493 和 L2502 的当前文本：
- L2493: 包含 `OpenHostOptions.active_cancel_timeout_seconds` 语义、timeout 到期判定、`reason=active_cancel_timeout`
- L2502: 包含 `active_cancel_timeout_seconds=None` opt-out 语义

**问题**: `docs/host/design.md` 是 Host 架构真源（control doc §真源层级）。Plan 对设计文档的变更只给了方向性描述，没有具体到"哪些句子删、哪些句子改、替换文本是什么"的粒度。对于 design.md 这种关键真源文档，implementation agent 有较大自由裁量空间，可能导致设计文本与代码实现不一致。

**建议**: 在 plan §4 或 §8 Slice 1 中增加 design.md 的具体变更指引：
- L2493: 删除 `OpenHostOptions.active_cancel_timeout_seconds` 相关整段，替换为 watchdog 作为 accepted-cancel closeout supervisor（无 post-cancel 预算、next tick 即 closeout）
- L2502: 删除 `active_cancel_timeout_seconds=None` opt-out 描述，改为 watchdog 始终启用；accepted-cancel CANCELLING Run 由 watchdog 收口，不再走 orphan LOST
- 新增一句：watchdog closeout 不表示 provider/tool 已物理停止

**候选裁决**: accepted (implementation agent 在 Slice 1 design.md 修改时需额外注意，但不阻塞 plan gate)

### DS-F05 [INFO] — Plan 的 "no-extra-budget" 方案存在一个合理的设计权衡

**Evidence**: Plan §7 正确论证 Host 不能知道 per-tool original deadline，因此采用 no-extra-budget 方案。

**确认**: 该方案可能导致以下场景：用户在工具调用刚开始 1 秒后取消，watchdog 下一个 tick 就 closeout 为 CANCELLED，而工具调用实际上可能只需要再 2 秒就能返回 `ToolAwaitingOutcome`（awaiting 路径）或完成结果。从用户体验角度看，这个工具结果丢失了——但这是**正确**的行为，因为用户明确要求取消。如果工具在 cancel 之前已经返回了 outcome（completed/failed/awaiting），Engine cancellation commit boundary（Engine design §13）保证已接受事实优先。

额外考虑：如果工具是 awaiting 类型（例如 fins download），用户在工具 submit 后很快就 cancel，工具可能还没来得及返回 `ToolAwaitingOutcome`。此时 Engine 的 handshake timeout 还在跑（由 `tool_execution_timeout_seconds` 控制），但 Host 的 cancel 已经通过 cancellation token 传播给 Engine。如果 Engine 在 handshake timeout 前收到取消，会以 `run_cancelled` 收口（Engine design §13: "若 execute 抛出 asyncio.CancelledError 且本次 run 的 cancellation_token 已取消，Agent 以 run_cancelled 收口"）。如果 Engine 在取消前已经拿到 `ToolAwaitingOutcome`，则 awaiting 事实优先（Engine design §13: "ToolExecutor 返回 awaiting outcome 后，Agent 先产出 tool_awaiting，再产出 run_suspended；迟到取消不能吞掉 await_spec 或 snapshot"）。

因此在 no-extra-budget 方案下，工具结果只有两种正确命运：
1. 在 cancel 到达 Engine 前已完成/ awaiting → accepted，不被取消覆盖
2. 在 cancel 到达 Engine 时尚未完成 → Engine run_cancelled，Host 随后 watchdog closeout

这与 Engine cancellation commit boundary 一致，不需要 post-cancel 预算来"等待工具完成"。

**结论**: 无问题。记录此分析作为 plan 决策的补充理由。

## 5. 测试矩阵审查

Plan §8 和 §9 的测试覆盖：

| 测试场景 | Slice | 覆盖状态 |
|---|---|---|
| `OpenHostOptions` 不再接受 `active_cancel_timeout_seconds` | Slice 1 | ✓ 明确要求 |
| Watchdog 无 post-cancel grace budget: cancel 后 first tick 即 closeout | Slice 2 | ✓ |
| Payload 不含 `timeout_seconds` / `timed_out_at` | Slice 2 | ✓ |
| Non-cooperative worker closes to CANCELLED | Slice 2 | ✓ |
| Zero candidates no-op | Slice 2 | ✓ |
| Multiple eligible runs close | Slice 2 | ✓ |
| Queued promotion after closeout | Slice 2 | ✓ |
| Command replay no duplicate | Slice 2 | ✓ |
| Scheduler close no terminal facts | Slice 2 | ✓ |
| Cooperative terminal first-committer-wins | Slice 2 | ✓ |
| Success terminal before watchdog no-ops | Slice 2 | ✓ |
| Open_host public watch observes cancelled closeout | Slice 2 | ✓ |
| Reopen/startup path closes accepted-cancel CANCELLING via watchdog | Slice 2 | ✓ |
| Engine tool handshake timeout unchanged | §9 pytest | ✓ |
| pyright 0 errors | §9 | ✓ |
| `git diff --check` | §9 | ✓ |

测试矩阵完整。Plan 同时保留了现有测试的正确性场景（first-committer-wins、replay、cooperative cancel），只是把 timeout-asserting 测试改为 no-extra-budget 断言。

## 6. README / Docs 触发审查

Plan §10 的 README 更新触发判断：
- `docs/host/design.md`: required → 正确，public contract + watchdog 语义变更
- `dayu/host/README.md`: required → 正确，`dayu/host/` public construction contract 变更触发
- `tests/README.md`: check → 正确，只有测试分类变更时才更新
- `dayu/engine/README.md`: check only if Engine code changes → 正确，plan 预期无 Engine 变更
- `dayu/config/README.md`: check only if config schema changes → 正确，`tool_execution_timeout_seconds` 保持在 `execution_profiles.json`
- Root `README.md` / `dayu/README.md`: not expected → 正确，无用户可见入口或分层边界变化

## 7. Residual Risk 审查

Plan §11 列出的 residual risks 均有明确的 owner/destination：
- Per-tool deadline observability → WU-TOOLS-CANCEL-01 or #87 child ✓
- Physical interrupt → WU-TOOLS-CANCEL-01 ✓
- Scan query optimization → #87 performance follow-up ✓
- Clock skew → #87 diagnostics/audit follow-up ✓
- Shared supervisor → #87 umbrella ✓
- Diagnostic/audit hooks → #87 diagnostics/audit + #70 Tool Trace ✓

所有 residual risk 归属到已有 issue owner，无 orphan risk。

## 8. 总评

**Verdict: pass-with-findings**

- 0 blocking findings
- 5 non-blocking findings (DS-F01 through DS-F05)
- DS-F01 (watchdog 无条件启用边界) 和 DS-F04 (design.md 变更不够具体) 推荐 accepted，implementation agent 实现时注意即可
- Plan 动机由直接代码证据支撑，scope 与 WU-TOOLS-CANCEL-01 边界正确
- Slice 切分（2 slices）符合小型 cleanup 的 1-3 slice budget，语义闭环，非机械拆分
- 测试矩阵完整，README 触发判断正确
- Residual risks 全部归属到已有 issue

**Plan 是 code-generation-ready**。所有 findings 均为 non-blocking，可在 implementation 阶段自然解决。
