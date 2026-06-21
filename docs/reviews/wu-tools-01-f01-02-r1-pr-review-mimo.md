# PR Review — WU-TOOLS-01-F01-02-R1

## Scope

- Mode: PR
- PR: [#162](https://github.com/noho/dayu-agent-r/pull/162)
- Title: WU-TOOLS-01-F01-02-R1 two-phase Fins activation
- Author: noho
- Head branch: phase/wu-tools-01-f01-02-r1
- Base branch: main
- Review date: 2026-06-21
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-pr-review-mimo.md`
- Included scope: PR 相对 main 的完整 diff（8002 行），涉及 13 个生产文件和 4 个测试文件，以及大量过程性 review/control/plan artifacts。
- Excluded scope: 无。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

以下是按检查维度整理的审查结论，均未构成 blocker：

### 1. PR 完整性与 Issue #129 目标对齐

PR 完整实现了 Issue #129 / WU 目标：

- **Host accepted-wait activation hook**：`dayu/host/wait_adapter.py` 新增 `WaitActivationRequest`、`WaitActivationAdapter` protocol、`WaitActivationRegistry`，与现有 `WaitAdapterRegistry` 模式平行。
- **Host ToolRuntime integration**：`dayu/host/tool_runtime.py:2776-2847` 在 `_accept_awaiting` 返回 `ToolAwaitingAcceptedAck` 后、`is_cancelled()` 检查通过后调用 `_activate_accepted_wait_best_effort`，best-effort 且不传播异常。
- **Fins prepare/activate 两阶段**：`dayu/fins/ingestion_runtime.py` 新增 `prepare_observed_download/preprocess/upload` 和 `activate_observation`；`start_observed_*` 委托给 prepare + activate，保持向后兼容。
- **Tool callable 迁移**：`download_tools.py`、`preprocess_tools.py`、`upload_tools.py` 均改为调用 `prepare_observed_*`。
- **Fins activation adapter**：`dayu/fins/ingestion/wait_adapter.py` 新增 `FinsIngestionWaitActivationAdapter`，解析 resume token 并调用 `runtime.activate_observation(handle)`。
- **Service assembly wiring**：`dayu/service/host_assembly.py` 使用同一 `fins_awaiting_runtime` 同时构造 tool callable 和 activation registry。
- **Engine contract / LLM-facing schema 未变更**：确认无改动。

### 2. PR 级别问题

- **PR body**：正确使用 `Refs #129`，无 `close`/`fix`/`resolve` 自动关闭关键词。
- **Premature final closeout artifact**：`docs/reviews/wu-tools-01-f01-02-r1-final-closeout.md` 已存在，但 control doc (`docs/host/issues-implementation-control.md:159`) 正确标记为 premature，明确说明 "不得视为 final-closeout-pass 依据"。
- **文件覆盖**：plan 列出的所有 affected files 均在 PR diff 中出现，无遗漏。
- **Process gate artifacts**：大量 slice review/rereview/fix/adjudication artifacts 随 PR 一起进入 diff，属于 gate 流程产物，不影响生产代码。

### 3. 分层边界

- **Host/Engine 边界**：Engine public contract（`ToolAwaitingOutcome`、`ToolExecutor.execute`）未变更。activation 是 Host 内部 construction-time wiring。
- **Host/Fins 边界**：`WaitActivationAdapter` protocol 定义在 `dayu/host/wait_adapter.py`（Host 层），Fins 实现在 `dayu/fins/ingestion/wait_adapter.py`（Fins 层），通过 `WaitAdapterKey` 关联，无反向依赖。
- **Service/Host 边界**：`HostToolingOptions.wait_activation_registry` 是 Host 公开的 typed option，Service assembly 构造后传入，不穿透 Host 内部。
- **FinsObservationRuntime protocol**：`observation_handle.py` 新增 `prepare_observed_*` 和 `activate_observation` 到 protocol，这是正确的——protocol 应反映 runtime 能力。

### 4. Runtime 一致性

- **共享 runtime**：`build_fins_wait_activation_registry(runtime=...)` 显式接收 shared `FinsObservationRuntime`。Service assembly (`host_assembly.py:1786-1789`) 使用 `fins_awaiting_runtime` 传入，与 tool callable 使用同一实例。AGG-F01 修复已确认。
- **无 dead helper**：`FinsIngestionWaitActivationAdapter.from_workspace_root` 已删除。`_start_observed_stream` 已重命名为 `_prepare_observed_stream`，不再调用 `executor.submit`。`start_observed_*` 方法保留但委托给 prepare + activate。
- **无 compat wrapper**：无兼容性 re-export 或 facade。

### 5. Activation 状态机正确性

- **prepare 不 submit**：`_prepare_observed_stream` 只注册 observation record，不调用 `executor.submit`。
- **activate 幂等**：`activate_observation` 在 `_observation_lock` 内检查 `submitted`、`cancelled`、`terminal` 状态，标记 `submitted=True` 后才 submit。重复调用不会 double-submit。
- **cancel/activate 共享锁**：`cancel_observation` 和 `activate_observation` 都使用 `self._observation_lock`，确保 cancel-vs-activate ordering 确定性。
- **activation 失败收口**：`activate_observation` 的 `except` 块在 re-raise 前将 observation 标记为 terminal `FAILED`（通过 `_mark_observation_failed`），不会留 PENDING 孤儿。
- **Host best-effort**：`_activate_accepted_wait_best_effort` 捕获所有异常，只记日志和发 diagnostic，不向 Engine 传播。Host wait truth 已 durable 成立。

### 6. Tests / README / Design 同步

- **Tests**：103 passed（Fins tools + Service assembly）、159 passed（Host executor + Phase 7 + Fins tools + Fins runtime）。覆盖了 prepare 不 submit、activate 幂等、cancel-before-activate、cancel/activate 共享锁、activation submit failure、unexpected activation exception、Host cancel-after-accept-skip-activation、Host activation failure keeps accepted outcome 等关键路径。
- **README**：`dayu/host/README.md`、`dayu/fins/README.md`、`tests/README.md` 均有更新，反映 activation hook 和 prepare/activate API。
- **Design**：`docs/host/design.md` 更新了 accepted-wait activation hook 和 Engine non-ownership 的说明。
- **无过程性 gate 文本泄漏**：README 和 design 中无 slice review artifacts 或 gate 状态文本。

### 7. 验证命令可信性

- `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q` → **103 passed, 3 warnings** ✓ 已复现
- `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` → **159 passed, 3 warnings** ✓ 已复现
- `pyright` → **0 errors** ✓ 已复现（提示 pyright 版本可升级，非阻塞）
- `git diff --check` → **clean** ✓ 已复现

## Open Questions

无。

## Residual Risk

- **Concurrent cancel-after-accept-before-activation 测试缺口**：`tool_runtime.py:2776` 的 `if not context.cancellation_token.is_cancelled()` 门禁在 accept ack 之后、activation 之前被取消的并发路径没有直接测试覆盖。生产代码行为正确（guard 简单直白），但若未来重构误删此检查，测试不会发现。低风险，可作为后续补充。
- **`exc_info=True` 在 diagnostic failure 路径**：`tool_runtime.py:2874` 的 `_emit_wait_activation_diagnostic_best_effort` 失败时使用 `exc_info=True` 记录完整 traceback。这不是 activation 主路径（主路径 L2836 只记 `exc.__class__.__name__`），且日志非 LLM-facing 通道。低风险。
- **Production poller / callback / physical cancel**：均不属于本 WU scope，分别由 #90 / #89 / #92 拥有。

## Verdict

**PASS**。PR 完整实现了 Issue #129 / WU-TOOLS-01-F01-02-R1 的 Host accepted-wait two-phase activation 目标，不过度设计，分层边界正确，runtime 一致性已验证，测试覆盖充分，验证命令均已复现通过。无 blocker。
