# Host Phase 6 P6-S5 Fix: Duplicate Governance Review Findings

## 背景

AgentDS 在 `docs/reviews/host-phase6-code-review-s5-ds-20260515.md` 中提出 2 个 medium finding 和 4 个 low finding。Controller 裁决：

- DS-F1 accepted：`require_justification` valid path 与 downgrade-to-hint path 必须在当前 S5 覆盖。
- DS-F2 accepted：duplicate index 不应把 governed error accepted entry 作为后续 reuse 来源。
- DS-F3 accepted：diagnostic emitter validation 应保持一致。
- DS-F4 accepted：普通 policy rejection 不应携带无关 duplicate prior refs。
- DS-F5 deferred：`semantic_duplicate_key` 默认关闭，专用测试不阻塞 S5。
- DS-F6 deferred：defensive validation 可在后续 ToolRuntime hardening 处理。

## 修复

- `dayu/host/tool_runtime.py`
  - `_record_duplicate_accepted` 收紧为仅在 `policy_decision.kind is ALLOW` 且 `duplicate_decision.kind is ALLOW` 的实际工具 outcome accepted 后写入 run-local duplicate index。
  - `_tool_fact_accept_candidate` 新增 `duplicate_governed` 输入，只有 duplicate governance 的非 allow 决策实际触发 governed outcome 时才携带 `reuse_prior_event_refs`。
  - `DeterministicToolTraceDiagnosticEmitter.emit` 补齐 `reason_code` / `message` 非空校验，与 no-op / in-memory emitter 保持一致。
- `tests/host/test_toolruntime_duplicate_governance.py`
  - 新增 valid justification 允许重复调用继续执行的测试。
  - 新增未配置 justification 参数名时降级为 `HINT` 的测试。
  - 新增 governed duplicate accepted 不覆盖 prior successful reuse source 的测试。
  - 新增普通 policy rejection 不携带 duplicate prior refs 的测试。
- `tests/host/test_toolruntime_diagnostics.py`
  - 新增 deterministic emitter 空字段拒绝测试。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q`
  - 24 passed
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q`
  - 46 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean
