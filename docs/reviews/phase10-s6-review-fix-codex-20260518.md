# Phase 10 Slice 6 Review Fix Codex

## 修改摘要

- 修复 F2：`HostCommandHandleOptions.context_window_size` 与 `reserved_output_tokens` 改为必填 typed input，所有当前构造点显式传入正整数。
- 修复 F2：command composition 的 minimum protection fallback 改为基于当前显式 window / reserved 生成的 policy，不再依赖 command options 的固定默认 window / reserved。
- 修复 F4：`test_dispatch_scheduler.py` 新增 multi-turn aggregate integration，覆盖 accepted Run 经 scheduler gate 多轮 dispatch、follow-up under budget 观察 recent raw turn、小 budget proactive compact、当前 compacted RunInputBuilder 暴露 compact artifact、下一轮 Engine request 观察 compact 后 pinned state / episode summary / recent raw turn 顺序。
- 同步 `dayu/host/README.md`、`tests/README.md` 与原 S6 implementation artifact，使文档反映必填 production budget input 与新增多轮集成覆盖。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q`：81 passed。
- `source .venv/bin/activate && pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py -q`：180 passed。
- `source .venv/bin/activate && pyright`：0 errors。
- `git diff --check`：通过。

## Residual

- F1 保留为 controller-accepted residual：`compose_host_local_execution_options(...)` 是显式 composition helper，不在同步 command handle factory 内隐藏 async scheduler lifecycle。
- F3 保留为 controller-accepted residual：production helper 不默认注入 fake compactor，真实 production compactor adapter 由后续显式 composition owner 提供。
- 新增 multi-turn 测试未串完整业务工具 verified fact public fake-worker 链路；该语义当前由 ToolRuntime accepted fact、memory projection verified fact、RunInputBuilder verified fact message 的分层测试覆盖。
