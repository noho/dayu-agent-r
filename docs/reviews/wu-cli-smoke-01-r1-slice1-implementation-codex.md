# WU-CLI-SMOKE-01-R1 Slice 1 Implementation Artifact（AgentCodex）

## 1. Gate 结论

- status: completed
- branch: `phaseflow/wu-cli-smoke-01-r1`
- accepted plan commit / current HEAD: `929691eaeb541a1cb754a0e8a1cae167980962e8`
- scope: 仅实施 Plan §7 Slice 1，并在同一未提交 worktree 内依次完成 S1-A / S1-B / S1-C。
- 未执行：commit、push、PR、code review、aggregate deepreview、Slice 2 stress / deterministic wakeup barrier / 真实 Host→Service→CLI slow-consumer E2E、全域测试与 README 收口。

## 2. 第一性原理 root cause 与 semantic owner

### 2.1 Root cause

问题真实存在且严重性评估成立。原实现把三种同属 Engine 流式传输过程的 delta 做成不对称语义：`CONTENT_DELTA` 与 `TOOL_CALL_DELTA` 不落 EventLog，`REASONING_DELTA` 却被写成 durable `PREVIEW` row，并经 `HostEvent.thinking` 投影给 Service。随后 Service/CLI 又用 durable `event_sequence` 排序、去重本应只在当前 Host runtime 有意义的 thinking。

这不是 renderer 局部缺字段，而是语义 owner 错位：瞬态 delivery identity 被 durable EventLog envelope 和下游消费者共同推导，造成 reasoning 独有的 durable 副本、三类 delta 语义不一致，以及未来 replay/memory/audit 消费者误把 thinking 当 durable fact 的风险。修复必须同时删除旧 durable owner 并建立 Host runtime owner；在 CLI 做 fallback、保留旧 DTO 或双路发布都只会固化双 owner。

### 2.2 Owner 判定

- Engine typed event：只拥有原始 `ContentDeltaData` / `ReasoningDeltaData` / `ToolCallDeltaData`。
- Host ingest：唯一拥有 durable identity、Attempt/execution、worker index、duplicate/late-state validation，以及三类 delta 的 zero-row accepted decision。
- 当前 `open_host` 的 transient hub：唯一拥有 `runtime_id`、全局 `runtime_sequence`、dedupe key、Session fanout、bounded subscription、overflow/detach/close 与 watcher-local terminal fence。
- EventLog / durable `HostEvent`：只拥有 durable facts、durable cursor 与 terminal/activity projection，不再拥有 thinking。
- Service：只从 public `HostSessionEvent` union 投影 entrypoint 语义；只有 `HostReasoningDelta` 可成为 `EntrypointThinking`。
- CLI：只拥有 stderr rendering 和当前 renderer 内的 runtime sequence/dedupe 状态，不反推 Host 或 Engine 事实。

## 3. §12.4 stop confirmation

六项 stop condition 均未命中：

1. `HostTransactionRunner.run_write` 在 operation 成功后先 commit、成功返回后才进入 `_finish_ingest` publish；rollback 测试证明 transaction 未返回时 publisher 为 0。
2. 现有 EventLog polling 与无后台 fanout task 的 bounded subscription 可合流；terminal 交付前先 drain transient 并建立同 Run fence。
3. 实现没有引入跨进程/restart replay，也没有创建 durable/transient 统一 cursor。
4. Service/CLI 只依赖 `dayu.host` public union；静态 import-boundary grep 为零。
5. memory/audit/recovery/outbox 的真实生产依赖不读取 durable thinking；删除项只要求迁移旧 fixture/helper。
6. 未新增旧 reasoning row、旧 DTO、旧 import path 的 compatibility shim/default/re-export/fallback。

因此无需 blocked 或回到 design/goal gate。

## 4. 实现说明

### 4.1 S1-A：Host public contract 与 runtime owner

- 在 `dayu.host.api` 建立闭合的 `HostTransientDeltaType`、三种 typed payload、只读 discriminator/data mapping、严格 `HostTransientDelta` envelope 与 `HostSessionEvent` union；空 delta 原文保留，identity、正整数 sequence/index、UTC 时间与 payload discriminator 严格校验。
- 新增 `dayu.host.transient_delta`：每次 `open_host` 一个 hub/runtime UUID；每个 accepted candidate 只构造一个 immutable envelope；全局 sequence 即使当前无 watcher 仍推进；按 Session 对已 attach watcher snapshot non-blocking fanout。
- 每个 subscription 使用容量 256 的 bounded queue；第 257 个未消费 item 触发 watcher-local `UNAVAILABLE` / `slow_consumer`，detach 慢 watcher并保留连续前缀，不阻塞 publisher 或其它 watcher。
- Host ingest 在 durable identity/late-state validation transaction 成功返回后才 publish；三类 delta 共享一个 typed mapping/zero-row path。stale、late、wrong data、rollback 均不发布；publisher 意外只记录不含 delta/异常正文的 sanitized operator diagnostic，不改变 accepted 结果。
- public watch 在方法返回前同步注册 subscription 并提交 durable cursor attach；返回显式 closable iterator。merge 保持 durable 与 transient 各自内序，在同 Run terminal 前 drain accepted transient，再设置 terminal fence；consumer detach、overflow 与 Host close 都走 owner cleanup。
- scheduler/open composition 显式传递 publisher，无 optional/default/extra payload。

### 4.2 S1-B：Service public union 与 bounded relay owner

- `EntrypointThinking` 改为 `run_id + runtime_id + runtime_sequence + dedupe_key + text_delta`。
- `_WatchAndWaitRuntime` factory 成为三个 live watcher 路径唯一构造点，统一绑定 closable watcher、容量 256 relay queue 与 drain task；terminal-only/no-watcher queue 保持 unbounded 且不伪装为 live relay。
- relay 使用 `await queue.put`，不丢弃/替换 item；`_WatcherFailure.error` 保存原异常实例，Host typed slow-consumer error 不被改写为 generic error。
- 对 `HostSessionEvent` 做穷举分支：durable `HostEvent` 继续拥有 terminal/activity；content/tool-call transient 明确忽略；只有 reasoning transient 投影 thinking；未覆盖 union/payload 分支使用 `assert_never`。
- 所有直接受 public watch union 影响的测试 helper、既有 stress helper type annotation 与 `utils/` smoke helper 均改为接受 union，并显式跳过 transient 后再读取 durable terminal；没有运行或新增 Slice 2 stress 语义。

### 4.3 S1-C：CLI identity 迁移与旧 durable owner 删除

- CLI thinking renderer 改用 `(runtime_id, runtime_sequence)` 检查同 runtime 单调性，并用 `dedupe_key` 等值去重；runtime 切换时 sequence baseline 重置。
- 删除 reasoning durable `PREVIEW` append、`HostThinkingView`、`HostEvent.thinking`、read projection、reasoning preview enum/export/fixtures，以及所有 production consumer。
- content/reasoning/tool-call 三类 delta 全部 EventLog zero-row；未保留兼容 wrapper、默认值、re-export 或下游 fallback。

## 5. Changed files

### 5.1 Production

- `dayu/cli/thinking.py`
- `dayu/host/__init__.py`
- `dayu/host/api.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/lifecycle_events.py`
- `dayu/host/open_host.py`
- `dayu/host/read_api.py`
- `dayu/host/transient_delta.py`（新增）
- `dayu/service/entrypoint_runtime.py`

### 5.2 Tests / test support

- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_thinking_renderer.py`
- `tests/host/public_smoke_support.py`
- `tests/host/recovery_support.py`
- `tests/host/stress_support.py`（仅 public union 强类型迁移）
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_host_production_stress.py`（仅 public union 强类型迁移，未新增/运行 Slice 2 stress）
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_transient_delta.py`（新增）
- `tests/host/test_watch_session_events.py`
- `tests/host/transient_delta_support.py`（新增）
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`

### 5.3 Existing smoke type consumers

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`

### 5.4 Docs / preserved external state

- `docs/reviews/wu-cli-smoke-01-r1-slice1-implementation-codex.md`（本 artifact，唯一新增文档）
- `docs/host/issues-implementation-control.md` 在 gate 开始前已为 controller 未提交修改；AgentCodex 未编辑、未恢复该文件。

## 6. Validation

所有 pytest / pyright 命令均先执行 `source .venv/bin/activate`。

### 6.1 Final required commands

1. `pytest -q tests/host/test_transient_delta.py --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80`
   - 结果：`6 passed in 0.43s`
   - coverage：`dayu/host/transient_delta.py` 188 statements，20 miss，`89%`（精确 total `89.36%`），通过 80% hard gate。
2. `pytest -q tests/host/test_engine_ingest_mapping.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_host_activity_event_projection.py tests/host/test_public_event_stream.py tests/host/test_lifecycle_events.py tests/host/test_audit_sink.py tests/host/test_public_host_event.py tests/host/test_package_exports.py tests/host/test_dispatch_scheduler.py`
   - 结果：`290 passed in 4.56s`
3. `pytest -q tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py`
   - 结果：`51 passed, 3 warnings in 2.25s`
4. `pytest -q tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_runtime_display.py`
   - 结果：`107 passed, 3 warnings in 4.31s`
5. `pytest -q tests/host/test_active_cancel_dispatch.py tests/host/test_phase5_local_execution_integration.py tests/host/test_phase7_waiting_integration.py tests/host/test_recovery_dispatch.py`
   - 结果：`38 passed in 1.09s`
6. `pytest -q tests/host/test_public_cancel_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_real_runner_matrix_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_recovery_multiprocess.py`
   - 结果：`45 passed, 1 skipped in 22.80s`；skip 为既有 real-provider 条件用例。
7. `pyright`
   - 结果：`0 errors, 0 warnings, 0 informations`。

Service/CLI warning 均来自已安装 `edgar` 包的 deprecated module 提示，不是本实现新增失败。

### 6.2 Repair-loop evidence

- 首次新模块 coverage 命令：`5 passed, 1 failed`，失败仅为测试 regex 与 owner 既有 `timezone.utc aware` 文案不一致；改正断言后最终通过，coverage 当时亦为 89%。
- 首次 Host focused 命令：`286 passed, 3 failed`；一项测试错误地把首个 durable progress 当作应为 transient，另两项 monkeypatch 强类型签名未接收新增显式 publisher/hub。测试改为跳过 durable progress、断言 transient 必须先于 terminal，并更新显式签名；最终 290 passed。
- 首次全仓 `pyright`：65 errors，全部是 public watch 返回值从 `AsyncIterator[HostEvent]` 收紧为 `AsyncIterator[HostSessionEvent]` 后，仓库旧 helper 仍声明 durable-only iterator。所有直接强类型消费者迁移到 public union、显式 `isinstance(HostEvent)` 后，最终全仓为 0。
- 定向回归：`pytest -q tests/host/test_transient_delta.py tests/host/test_engine_ingest_mapping.py` → `100 passed in 1.46s`；相关定向 pyright → 0 errors。

### 6.3 Static checks

- `rg -n --glob '*.py' 'HostPreviewEventType\.REASONING_DELTA|_EVENT_TYPE_REASONING_DELTA|HostThinkingView|thinking=_thinking_from_row' dayu/host tests/host` → exit 1，零命中。
- `rg -n 'EngineEventType\.(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA)' dayu/host/engine_ingest.py` → 仅命中统一 transient classification 与 typed payload projection（module closed set、`_is_transient_delta_event`、`_validated_transient_delta_candidate`）。
- `rg -n 'event_sequence.*thinking|EntrypointThinking.*event_sequence|thinking\.event_sequence' dayu/service dayu/cli tests/service tests/cli` → exit 1，零命中。
- `rg -n 'EngineEvent|dayu\.engine' dayu/service/entrypoint_runtime.py dayu/cli/thinking.py` → exit 1，零命中。
- `rg -n 'append.*(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA)|(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA).*append' dayu/host` → exit 1，零命中。
- `git diff --check` → exit 0，零输出。
- branch/HEAD 复核：目标 branch 与 accepted commit 均匹配。

## 7. README 判断

本变更按仓库触发规则会涉及 `dayu/host/README.md`、`tests/README.md` 及可能的用户可见入口说明；但本 implementation gate 的显式边界要求 README 只在 Slice 2 收口同步，并禁止本 gate 修改。故没有修改任何 README。

静态全文检查仍在 `dayu/host/README.md:247` 与 `:562` 发现旧 `HostThinkingView` 描述；这是已确认的 Slice 2 待同步项，不是 production Python 兼容符号。Python 范围旧 symbol grep 已为零。

## 8. Residual risks / 未覆盖项

- transient delivery 在 overflow、detach、断线、Host close、进程崩溃或重启后不可 replay；这是 live-only contract。
- 容量 256 尚无真实负载调优数据，且本 slice 不暴露 public knob。
- durable 与 transient 只有各自内序，没有统一 cursor/总序；同 Run 只承诺 accepted transient 在 terminal 前交付并在 terminal 后 fence。
- hub 只覆盖同一进程、同一 `open_host` runtime；不支持跨 Host instance watcher。
- 按 gate 边界未运行/实现 Slice 2 的 3×1000 stress、deterministic wakeup barrier、真实 Host→Service→CLI slow-consumer E2E、`tests/cli/test_transient_slow_consumer_path.py`、全量 `tests/host tests/service tests/cli` 或 stress marker suite；这些仍由 Slice 2 收口。
- 既有 real-provider 条件测试有 1 项 skip；未将外部 provider 可用性误报为本地 contract 通过证据。

## 9. Boundary confirmation

- 未修改 `docs/host/design.md`、`docs/engine/design.md`、accepted plan、既有 review artifacts 或任何 README。
- 未修改 controller-owned `docs/host/issues-implementation-control.md` 的既有未提交状态。
- 未创建 compatibility code、feature flag、后台 fanout task、broker、数据库表、replay/cursor 或 Slice 2 测试文件。
- worktree 保持未提交；未 commit、push、开 PR 或执行 code review/deepreview。
