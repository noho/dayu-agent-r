# Host Phase 6 P6-S5 Code Review — Duplicate Governance And Diagnostic Emitter

- **reviewer**: AgentMiMo
- **date**: 2026-05-15
- **scope**: `dayu/host/tool_runtime.py`、`tests/host/test_toolruntime_duplicate_governance.py`、`tests/host/test_toolruntime_diagnostics.py`、`dayu/host/README.md`、`tests/README.md`
- **plan source**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` §P6-S5
- **design source**: `docs/host/design.md` §18.2–18.3
- **implementation artifact**: `docs/reviews/host-phase6-implementation-s5-duplicate-governance-20260515.md`

## Verdict

**PASS — 无 blocking finding。** 实现严格符合 P6-S5 计划与设计真源，duplicate governance 为 run-local、ToolRuntime 实例内，diagnostic emitter 覆盖 candidate / ack / reject / timeout governed paths，未越界修改 Engine / Remote / P7 wait / P6-S6 scheduler。

## Findings

### F1 — REUSE rejection 不产生 reject-specific diagnostic ref（Low）

- **文件**: `dayu/host/tool_runtime.py:2306–2313`
- **描述**: `_accept_with_retry` 在收到 `ToolFactRejectedAck` 且 `diagnostic_refs` 为空时才补充 reject diagnostic ref。REUSE candidate 经 `_accept_reuse` 路径进入 accept barrier 时已携带 duplicate governance diagnostic ref，因此若 REUSE 被 accept barrier reject，不会补充 reject-specific diagnostic。
- **影响**: 轻微。duplicate diagnostic ref 已解释治理意图，reject 原因码仍通过 `ToolFactRejectedAck.reason_code` 携带。不影响正确性或安全边界。
- **建议**: 可在后续 slice 或 P13 durable trace 中为 REUSE rejection 追加独立 reject diagnostic ref；当前不阻塞。

### F2 — `_event_payload.py` / `event_log.py` 未修改（Info）

- **描述**: P6-S5 计划列出 `dayu/host/_event_payload.py` 与 `dayu/host/durable/event_log.py` 为允许修改文件（governance event payload support）。实现选择让 REUSE 通过既有 accept barrier 路径写入 `TOOL_CALL_REQUESTED` + `TOOL_CALL_GOVERNED`，不写 `TOOL_RESULT_ACCEPTED`，因此不需要新增 payload codec。
- **影响**: 无。实现路径更简洁，复用既有 barrier 语义，未引入新 EventLog 事件类型。REUSE 的 `tool_result_event_ref` 正确为 `None`。

### F3 — `_tool_fact_kind` 条件从 `GOVERNED_ERROR` 扩展为 `not ALLOW`（Info）

- **文件**: `dayu/host/tool_runtime.py:4108`
- **描述**: 原条件 `policy_decision.kind is ToolPolicyDecisionKind.GOVERNED_ERROR` 改为 `policy_decision.kind is not ToolPolicyDecisionKind.ALLOW`。此变更使 HINT / REQUIRE_JUSTIFICATION / HARD_STOP duplicate 决策正确映射为 `ToolFactKind.GOVERNED_ERROR`。REUSE 走独立 `_accept_reuse` 路径，不经过此函数。
- **影响**: 正确。符合 plan §3.5 `ToolFactKind` 语义表。

## Validation

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q` | 19 passed |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q` | 41 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Checklist Detail

### 1. Duplicate governance 是否严格 run-local、ToolRuntime 实例内

**PASS.** `InMemoryRunLocalDuplicateGovernance` 在 `DefaultToolRuntimeFactory.create_tool_runtime` 中构造（`tool_runtime.py:2431–2434`），索引存储在 `self._entries_by_key: dict[str, _DuplicateAcceptedEntry]`（`tool_runtime.py:1490`）。无 durable table、无 Memory retrieval、无跨 Run / Session 继承。`test_new_runtime_does_not_inherit_duplicate_index` 直接验证新实例不继承旧索引。

### 2. Duplicate key 是否基于 tool identity 与 normalized arguments digest，排除 index_in_iteration

**PASS.** `_duplicate_key`（`tool_runtime.py:4407–4417`）计算 sha256(`{tool_name, tool_identity_digest, normalized_arguments_digest, semantic_duplicate_key}`)。`index_in_iteration` 不参与。`test_duplicate_key_excludes_index_in_iteration` 验证同 iteration 不同 index 仍命中同一 key。`test_duplicate_key_normalizes_arguments_deterministically` 验证参数顺序无关。

### 3. Allow / reuse / hint / require_justification / hard_stop matrix

**PASS.**

- `allow`: 执行 callable，accept 结果，记录到 duplicate index（`_execute_one:2142–2147`）。测试 `test_allow_duplicate_decision_executes_and_accepts_each_call`。
- `reuse`: 不调用 callable（`_accept_reuse:2158–2205`），构造 `ToolFactKind.REUSE` candidate 通过 accept barrier，引用 prior accepted refs，`tool_result_event_ref` 为 `None`，返回 prior outcome 给 Engine。测试 `test_reuse_references_prior_refs_without_second_result_fact`。
- `hint` / `require_justification` / `hard_stop`: 映射为 `ToolPolicyDecision`（`_policy_decision_from_duplicate`），产生 `ToolFactKind.GOVERNED_ERROR` candidate，携带 diagnostic refs 与 prior event refs。`require_justification` 无 justification 参数时降级为 `hint`（`_decision_for_request:1552–1553`）。测试 `test_duplicate_governed_matrix_produces_diagnostics` 参数化覆盖三者。

### 4. Diagnostic emitter 与 diagnostic refs 是否进入所有 governed paths

**PASS.**

- Duplicate governed: `_diagnostic_refs_for_duplicate`（`tool_runtime.py:2207–2226`）为非 allow 决策发出 ref。
- Accept rejected: `_accept_with_retry`（`tool_runtime.py:2306–2313`）在 `diagnostic_refs` 为空时补充 reject ref。
- Accept timeout: `_accept_with_retry`（`tool_runtime.py:2322–2332`）在 retry 耗尽后追加 timeout ref。
- 所有 diagnostic refs 通过 candidate → ack 链传递，不伪装为 durable trace projection。

### 5. 是否改动 Engine、业务工具、Remote、P7 wait 或 P6-S6 scheduler composition 边界

**PASS.** 变更文件仅 `dayu/host/tool_runtime.py`（production）+ 2 个新测试 + 2 个 README。未触碰 `dayu/engine/`、`dayu/contracts/`、`dayu/host/durable/`、`dayu/host/dispatch.py`、`dayu/host/local_proxy.py`、`dayu/host/command.py`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`。

### 6. AGENTS 合规：类型、中文 docstring、Any/object、extra payload、README 同步、测试覆盖

**PASS.**

- 所有新增类 / 函数 / 模块有完整中文 docstring，含参数 / 返回值 / 异常。
- 签名无 `Any`、`object`、无类型参数或无类型返回值。
- 无 `extra payload` 使用。
- `dayu/host/README.md` 同步 P6-S5 当前事实，更新 ToolRuntime boundary 段、non-goals 列表与测试覆盖描述。
- `tests/README.md` 新增 P6-S5 测试命令行与覆盖描述。
- 新增测试覆盖 duplicate key 规范化、index 排除、allow / reuse / hint / require_justification / hard_stop matrix、ToolRuntime 实例生命周期边界、no-op / in-memory emitter、diagnostic refs 在 candidate / ack / reject / timeout 路径的传递。

## Residual Risks

1. **默认 duplicate policy 仍为 `allow`**：未显式配置策略时不会改变既有执行行为。生产策略 provider resolution 仍未实现（归 P6-S6 或后续 phase）。
2. **`ToolTraceDiagnosticEmitter` 只提供 typed refs**：不落 durable trace projection。durable trace 归 P13。
3. **`semantic_duplicate_key_argument_name` 是 Host 内部 policy 字段**：默认关闭。后续 policy provider 启用时必须明确其与 normalized arguments digest 的关系。
4. **REUSE rejection 无 reject-specific diagnostic**（F1）：duplicate diagnostic 已解释治理意图，不影响正确性。
