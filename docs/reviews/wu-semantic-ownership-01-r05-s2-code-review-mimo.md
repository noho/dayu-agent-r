# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Review（AgentMiMo）

## Scope

- Mode: current changes（R05-S2 implementation slice）
- Branch: `phaseflow/host-issues-control`
- Base: transition HEAD `e077c708`（R05-S1 accepted commit `c5af5613`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-mimo.md`
- Included scope: 5 tracked changed paths + 1 untracked implementation artifact
  1. `tests/engine/test_agent_phase3_tool_call.py` (+136 lines)
  2. `utils/smoke_host_public_awaiting_entrypoint.py` (+1094/-97 lines)
  3. `dayu/host/README.md` (+2 lines)
  4. `tests/README.md` (+5/-3 lines)
  5. `docs/host/issues-implementation-control.md` (+5/-3 lines)
  6. `docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md` (untracked)
- Excluded scope: `dayu/engine/agent.py`（verified no diff）、S1 七条 protected paths、scheduler owners、根 README、`dayu/README.md`、Engine README
- Parallel review coverage: 无（单 reviewer 全量走读）

## Findings

### 001-未修复-中-`_durable_options` 重复 durable options 投影

- **入口/函数**: `utils/smoke_host_public_awaiting_entrypoint.py::_durable_options()`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:1413-1436`
- **输入场景**: smoke 需要独立读取 durable WaitRecord 以验证 timeout release 状态
- **实际分支**: smoke 手动构造 `HostDurableStoreOptions`，逐字段从 `OpenHostOptions` 投影
- **预期行为**: 复用已有的 `_durable_options_from_public_options()`（`dayu/host/command.py:1295`）或等价公共 helper
- **实际行为**: smoke 独立实现了相同的投影逻辑，包括 `PayloadStoragePolicy` 和 `HostSQLiteStoragePolicy` 嵌套构造
- **直接证据**: `utils/smoke_host_public_awaiting_entrypoint.py:1413-1436` 与 `dayu/host/command.py:1295-1319` 结构相同
- **影响**: 若 production 投影逻辑变更（如新增字段、修改嵌套映射），smoke 会静默偏离，读取配置不一致的 store
- **建议改法和验证点**: 将 `_durable_options_from_public_options` 提升为 `dayu/host/durable/options.py` 或 `dayu/host/command.py` 的公共 helper，smoke 直接调用；或在 smoke 中 import 并适配 `OpenHostOptions` → `HostCommandHandleOptions` 的字段映射
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-`_WaitPollerDiagnosticsHost` Protocol 访问私有 `_wait_poller`

- **入口/函数**: `utils/smoke_host_public_awaiting_entrypoint.py::_capture_smoke_state()`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:230-233, 1381-1384`
- **输入场景**: smoke 需要读取 runner dropped count 以验证 late publication fencing
- **实际分支**: 通过 `cast(_WaitPollerDiagnosticsHost, host)._wait_poller` 访问 `WaitPollerSupervisor.observation_diagnostics_snapshot().dropped_count`
- **预期行为**: 通过公共 API 或显式 diagnostics 接口读取
- **实际行为**: 通过 Protocol cast 绕过类型系统访问 Host 私有属性 `_wait_poller`
- **直接证据**: `_WaitPollerDiagnosticsHost` 在 smoke 中定义（行 230），`cast(...)` 在行 1381
- **影响**: 若 Host 内部 `_wait_poller` 属性重命名或重构，smoke 编译期不会报错，运行时 `AttributeError`
- **建议改法和验证点**: 在 Host 公共 API 上暴露只读 diagnostics accessor（如 `observation_dropped_count` property），smoke 通过公共接口读取；或显式记录此为 smoke-only 内部访问约定
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-smoke 规模约 2200 行，辅助类/函数分散但未过度集中

- **入口/函数**: `utils/smoke_host_public_awaiting_entrypoint.py` 全文
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:0-2200+`
- **输入场景**: R05-S2 plan 十项 contract 全部在单一 smoke 中验证
- **实际分支**: 新增 `_ExternalOperationController`（~90 行）、`_SmokePhaseContext`（~30 行）、`_TimedLateReadyPollAdapter`（~70 行）、`_ReadWaitRecordOperation`（~20 行）、7 个 assertion helper（~200 行）、5 个 wait helper（~100 行）、`_phase_failure`（~50 行）
- **预期行为**: plan 要求的最小可维护实现
- **实际行为**: 每个 helper 职责单一，无 God function；但 smoke 整体体量较大，后续维护者需理解多个协作类
- **直接证据**: 文件从 ~1300 行增至 ~2200 行（+1094/-97）
- **影响**: 维护成本中等；新增 contract 维度时可能继续膨胀
- **建议改法和验证点**: 当前可接受；若后续 R06+ 继续扩展 smoke contract，考虑拆分为 `smoke_support.py` 公共 helper 模块
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 004-未修复-低-`backoff_max_delay_seconds` 在 test-effective policy 中与 initial 相同

- **入口/函数**: `utils/smoke_host_public_awaiting_entrypoint.py::_deterministic_public_poll_options()`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:1076`
- **输入场景**: smoke 构造 test-effective timing policy
- **实际分支**: `backoff_max_delay_seconds=_TEST_INITIAL_BACKOFF_SECONDS`（0.6s），与 `backoff_initial_delay_seconds` 相同
- **预期行为**: 测试 policy 应保留 max > initial 的关系以验证 cap 逻辑
- **实际行为**: max = initial = 0.6s，消除了退避封顶逻辑的测试覆盖
- **直接证据**: 行 1076 `backoff_max_delay_seconds=_TEST_INITIAL_BACKOFF_SECONDS` vs production packaged 值 300.0
- **影响**: 若退避封顶逻辑有 bug，smoke 不会发现；当前只覆盖单次 timeout retry（attempt=1），cap 不生效
- **建议改法和验证点**: 可将 max 设为 `2 * _TEST_INITIAL_BACKOFF_SECONDS`（1.2s），保留 cap 语义但不显著延长测试时间；当前因只验证首轮 retry，风险有限
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Reviewed Evidence

### Engine no-diff 验证

- `git diff HEAD -- dayu/engine/agent.py`：0 lines（确认 no diff）
- Engine regression test `test_accepted_awaiting_external_operation_outlives_handshake_timeout`：独立运行 `1 passed in 0.38s`
- Engine 整文件 `test_agent_phase3_tool_call.py`：`48 passed in 0.45s`
- Regression 证明：executor 在 0.1s 握手预算内返回 `ToolAwaitingOutcome`，独立 operation 0.25s 越过预算、未被取消、终态 `RUN_SUSPENDED`、事件序列为 `TOOL_AWAITING → RUN_SUSPENDED`、无 `RUN_FAILED`

### Engine 78% branch-aware / 80.458% statement 解释

- `agent.py` 在 fixed base / S1 accepted / transition HEAD 三重 no diff
- statement coverage `597/742 = 80.458%`，branch-aware combined `77.626%`（显示 78%）
- `agent.py` 不是 changed production file，不存在新增 coverage debt
- 计划所述 "agent.py=80%" 对应 statement coverage；78% 是 branch-aware display
- 两项如实保留，没有把 78% 伪装成 80%

### Public smoke 独立验证

独立运行 smoke：

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-s2-mimo-review-smoke
```

exit 0。关键证据：

```text
SMOKE TYPED_PROVIDER_MODES poll=poll manual=manual callback=callback
SMOKE PACKAGED_RUNTIME_POLICY enabled=True poll=1.0 claim_ttl=60.0 ... max_outstanding=8
SMOKE TEST_EFFECTIVE_RUNTIME_POLICY enabled=True poll=0.01 ... backoff_max=0.6
SMOKE HANDSHAKE_ACCEPTED elapsed=0.001004 budget=0.05
SMOKE OBSERVED_WAITING true
SMOKE FIRST_OBSERVATION_TIMEOUT run=WAITING wait=WAITING claim_released=true
  diagnostic=ADAPTER_ERROR/wait_observation_timeout terminal_outbox=0
SMOKE OPERATION_DURATION measured=0.301077 handshake_budget=0.05
SMOKE TIMING_INEQUALITIES ...=true（四项全部 true）
SMOKE LATE_READY_DROPPED runner_dropped_count=1 run=WAITING terminal_outbox=0
SMOKE TERMINAL_STATUS SUCCEEDED
SMOKE OUTBOX_TERMINAL_MATCH true
SMOKE WORKER_ACCEPT_COUNT 2
SMOKE POLL_OBSERVATION_COUNT 2
SMOKE PHASES_COMPLETED run_accepted,operation_started,handshake_accepted,
  durable_waiting,first_observation_entered,first_observation_timeout_released,
  operation_finished,late_result_released,late_publication_dropped,
  second_observation_entered,public_terminal_outbox
SMOKE PASS Host public awaiting entrypoint
```

11 named phases 全部完成。smoke 保持 packaged `ConfigLoader → provider discovery → Service composition → open_host → durable poller → public terminal/outbox` 主链。

### Timing 关系与 CI 鲁棒性

- 四条 inequality 全部在运行时断言，margin = 0.03s ≥ 5 × 0.005s quantum
- overall deadline 15s、CI cap 20s；实际 smoke 耗时约 2s
- 即使 CI 环境 10× 调度开销，smoke 仍在 5s 内完成，远低于 15s deadline
- `asyncio.sleep(0.30)` 只用于被测独立 operation；state loop 的 0.005s quantum 每次重新读取 owner state

### Tests 验证

| 矩阵 | 结果 |
|---|---|
| Engine exact 7 nodes | `7 passed` |
| Engine 整文件 | `48 passed` |
| R04 config/Fins/Service owner nodes | `35 passed, 3 warnings` |
| ten-file R05 aggregate | `360 passed, 3 warnings` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Changed-file Ruff | `All checks passed!` |
| `git diff --check` | PASS |

### Source / owner / 安全确认

- `agent.py` no diff；Engine handshake budget 只在 `ToolExecutor.execute` 返回前读取
- S1 timeout-only terminal primitive 零定义、零调用
- token/generation publication fence、claim CAS、release/backoff、typed LOST 均保持原 owner
- smoke 无 `hasattr/getattr`、monkeypatch、`.resolve_wait(...)` shortcut、无参 `WaitPollerRuntimePolicy()`
- production added-lines 对 `authorization|permission|callback transport|process isolation|Issue 175` 零命中
- scheduler deterministic probe 仍可复现（未修、未隐藏、未 waive）

### README 确认

- `dayu/host/README.md`：+2 行，只补充 Waiting 章节当前 contract：poll timeout 是 poll-local diagnostic + claim release/backoff、Run 保持 WAITING、late publication 无发布权、cancelled abandon 保持可重试且不写 `poll_abandoned_at`
- `tests/README.md`：纠正旧 stuck-poll/abandon-marker 描述，登记 Engine regression 与 public smoke 覆盖边界
- `dayu/engine/README.md`：已有 handshake timeout 边界说明，`agent.py` no diff，保持 no diff
- 根 README / `dayu/README.md`：无入口/工作流/分层/装配变化，no diff

### Deferred / retained 确认

- scheduler close / terminal promotion coordination：未修、未隐藏、未归 Issue 175
- cancelled wait 长期 retry：R05 只保证 claim CAS、bounded capacity、finite timeout、late-pub fencing、backoff cap
- Issue 175 process isolation：不进入 R05
- callback transport / unified authorization：延期
- R06+ semantic ownership remediation：延期

## Residual Risk

1. **smoke `_durable_options` 投影逻辑**：与 production `_durable_options_from_public_options` 结构相同但独立实现。若 production 新增 durable options 字段，smoke 会静默偏离。风险低，因为当前投影的字段集稳定且有限。
2. **smoke `_WaitPollerDiagnosticsHost` 私有访问**：`_wait_poller` 属性是 Host 内部实现细节。若 Host 重构 poller 持有方式，smoke 运行时失败。风险低，因为该属性自 R04 以来稳定。
3. **timing 常量对慢 CI 的敏感性**：四条 inequality 使用 0.03s margin；在极端慢 CI（>10× 调度开销）下可能 false fail。当前实际运行约 2s，距 15s deadline 有大量余量。
4. **`backoff_max_delay_seconds = initial`**：消除了退避封顶逻辑的测试覆盖。因 smoke 只验证首轮 retry（attempt=1），cap 不生效，风险有限。
5. **scheduler close / terminal promotion coordination**：独立 Host lifecycle owner 缺口，确定性 probe 可复现，不属于 R05。当前 umbrella 不修、不创建 issue。
