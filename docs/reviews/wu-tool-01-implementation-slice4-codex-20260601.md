# WU-TOOL-01 Slice 4 Implementation Report

## Motivation Check

Slice 4 动机成立。Slice 1-3 已把 duplicate governance 实现收敛到 attempt-local in-memory，但回归矩阵与 README 若继续保留 run-scoped duplicate registry 文字，会把旧边界重新固化。worker / Host restart 行为也需要明确测试：当前 duplicate index 不 durable，重启后不复用旧 accepted refs；这只是内存治理边界，不是 correctness 前提。

## Changed Files

- `tests/host/test_toolruntime_duplicate_governance.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-tool-01-implementation-slice4-codex-20260601.md`

未修改未授权生产文件，未 commit / push / PR。

## Implemented Items

- 强化 cross-Attempt regression：`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` 覆盖相同 `run_id`、旧 Attempt 已 accepted 后，新 Attempt 相同 tool / args 仍作为 fresh request 执行；断言不复用旧 Attempt refs、`duplicate_decision` 为 `ALLOW`、`reuse_prior_event_refs` 为空、duplicate key 因 Attempt scope 不同而不同。
- 新增 worker / Host restart in-memory 行为测试：`test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior` 构造新的 ToolRuntime handle，保持同 `attempt_id` / tool / args；因 fresh `InMemoryAttemptDuplicateGovernance` 不继承旧内存索引，真实工具再次执行，不复用 prior refs。测试名和 docstring 明确这是 in-memory non-durable restart behavior，不作为 correctness 前提。
- 保留并依赖 `tests/host/test_dispatch_scheduler.py::test_reactive_recovery_uses_fresh_duplicate_governance_attempt` 覆盖 reactive recovery 创建新 Attempt 后 fresh duplicate governance 的生产 dispatch wiring。
- 未保留 run-scope sharing 测试。

## README Updates

- `dayu/host/README.md`：删除 “run-scoped duplicate governance registry” 旧说法；改为 attempt-local duplicate governance state。补充 duplicate governance 是 attempt-local in-memory、不会跨新 Attempt / worker restart / Host restart 继承，也不会从 EventLog 重建 durable ledger。
- `dayu/host/README.md`：补充 `HostToolingOptions.duplicate_governance_policy` 是 construction-time typed `DuplicateGovernancePolicy` 配置入口，承载默认动作、按工具覆盖动作、模型可见治理文案和 justification 参数名。
- `tests/README.md`：把旧 “Run-scoped duplicate registry 的同 Run 共享 / 跨 Run 隔离 / scheduler 生命周期清理” 改为 attempt-scoped duplicate key、in-flight owner / waiter、cross-Attempt fresh request、worker restart in-memory non-durable behavior、trace scope projection 覆盖。
- `tests/README.md`：相关命令入口补充 `test_tool_trace_projection.py`、`test_dispatch_scheduler.py`、`test_tooling_options.py`。

## Validation

已运行：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tooling_options.py
```

结果：123 passed。

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

## Terminology Grep

已运行：

```bash
rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md
```

结果仍有匹配，但不属于 duplicate governance run-scope wording：

- `dayu/host/README.md` 和 `tests/README.md` 的 `run-scoped truncation cursor / scope token`：允许保留，属于 truncation cursor 语义。
- `dayu/host/tool_runtime.py` 与 `dayu/host/api.py` 的 run-scoped truncation manager / cursor / remaining ref：允许保留，属于 truncation / fetch_more。
- `dayu/host/README.md` 的 `run-local token`：属于 reactive compaction cancellation token wording，不是 duplicate governance。
- `tests/host/test_local_proxy_engine_ingest.py` 的 `run_id="run-local"`：测试数据 id，不是 duplicate governance wording。

duplicate governance 生产、测试和 README 文字未残留 run-scoped registry / run-local duplicate registry 说法。

## Residual Risks

- 未发现当前 Slice 4 范围内未关闭的 correctness 风险。
- 当前行为仍按设计不提供 durable duplicate ledger；worker / Host restart 后同 Attempt 相同 tool / args 会重新真实执行。该行为已由测试和 README 明确为 in-memory non-durable 边界。

## Stop Conditions

未触发 stop condition：

- 未修改 schema / public command / EventLog 表结构。
- 未引入兼容 re-export、wrapper 或 facade。
- 未越过授权文件范围修改生产代码。
- 未发现需要回到 design gate 的新架构问题。
