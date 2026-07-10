# WU-SEMANTIC-OWNERSHIP-01 / P3-D Aggregate Deepreview

## Scope

- Mode: current changes (aggregate review after accepted slices S1/S2/S3)
- Branch: `phaseflow/host-issues-control`
- Base: `main` (baseline commit: `c52519f0`)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-aggregate-deepreview-mimo.md`
- Included scope: P3-D production code, tests, docs, and review/control artifacts from commits `c52519f0..47e90f71`
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 3 subagents 覆盖跨 slice 一致性、fatal/non-fatal 全栈贯穿、weak-typing guard 与 LLM-facing 泄漏防护

## Findings

未发现实质性问题。

## Verification Evidence

### 1. Cross-Slice Consistency (S1 / S2 / S3)

| 检查点 | 结论 | 直接证据 |
|---|---|---|
| S1 ChoicePolicyError.error_code (str) → RunnerProtocolErrorData 包装 | 通过 | sse_parser.py `_handle_choice_policy_error` line 487 使用 `runner_protocol_error_code()`；non_stream_parser.py `_emit_choice_policy_error` line 407 同样包装 |
| S2 非致命 diagnostic 不设置 failure_candidate | 通过 | agent.py line 1401-1421 处理 `RunnerProviderDiagnosticData` 仅调用 `_provider_diagnostic_event()`，不触碰 `state.failure_candidate` |
| S3 typed error code 全构造点 | 通过 | agent.py 18 个 `EngineRunErrorCode` 常量 + `RunnerSpecificErrorCode` wrapper pass-through；`RunFailedData.__post_init__` 运行时校验兜底 |
| Host serialize_engine_error_code 覆盖 | 通过 | engine_ingest.py 5 个调用点覆盖 RUN_FAILED terminal、PROVIDER_PROTOCOL_ERROR payload+reason、failure_metadata 全部输出路径 |

### 2. Fatal vs Non-Fatal 全栈贯穿

| 层 | fatal (PROVIDER_PROTOCOL_ERROR) | non-fatal (PROVIDER_DIAGNOSTIC) |
|---|---|---|
| Runner | `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)` | `RunnerProviderDiagnosticData`，无 `RunnerDoneData(ERROR)` |
| Agent | 设置 `failure_candidate`，终态为 `RUN_FAILED` | 不设 `failure_candidate`，终态可为 `FINAL_ANSWER` |
| Host ingest | 写入 `failure_metadata` (含 `failure_kind`) | 无 `failure_metadata`，`terminal_closeout=False` |
| Tool Trace | `provider_error_ref` 有值，产生 `failure_metadata` | `provider_error_ref=None`，无 `failure_metadata` |
| Outbox | 通过 terminal event 间接进入 | 被 `EventClass.CANONICAL_FACT` filter 排除 |

### 3. Provider Wire Normalization at Adapter Boundary

- `_choice_policy.py`：adapter 私有 choice policy helper 在 SSE 和 non-stream 路径先校验 `choices` 和 `finish_reason`，fatal 后才产出 `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)`
- 未知 finish_reason 不再 fallback 到 `FinishReason.STOP`；unknown non-empty string、empty string、non-string 类型均 fatal
- `null`/missing 作为 absent 处理，不默认为 `STOP`
- SSE cross-chunk conflicting terminal finish_reason 已 fatal
- source scan：`rg -n "unknown_finish_reason|FinishReason\.STOP|finish_reason or FinishReason\.STOP"` 在 `dayu/engine/runners/openai/` 仅命中 `_choice_policy.py` 的 `"stop"` → `FinishReason.STOP` 正向映射

### 4. Error-Code Typing at Host Boundary

- `EngineRunErrorCode` (StrEnum) 覆盖 18 个已知 Engine-owned 失败码
- `RunnerSpecificErrorCode(value, source)` wrapper：trim、拒绝空白/空/超长 (128 chars)；闭集 source enum (`RUNNER_PROTOCOL` / `HTTP_PROVIDER` / `ADAPTER`)
- `serialize_engine_error_code()` 是 Host durable/public 边界唯一序列化入口
- `EngineErrorCode` TypeAlias = `EngineRunErrorCode | RunnerSpecificErrorCode`
- dataclass `__post_init__` 运行时类型校验防止测试绕过 pyright

### 5. Weak-Typing Guard

`tests/engine/test_weak_typing_guard.py` 包含 8 个测试函数：

- AST 扫描 `dayu/engine/contracts/` 无 `error_code: str` 字段
- AST 扫描构造点禁止 literal string `error_code=`
- AST 扫描禁止 `.error_code` 与 literal string `==`/`!=` 比较
- 逐行扫描 `engine_ingest.py` 要求 `data.error_code` 访问必须伴随 `serialize_engine_error_code`

### 6. LLM-Facing Leakage

以下路径零匹配 `PROVIDER_DIAGNOSTIC`、`provider_diagnostic`、`message_marker_fallback`、`RunnerSpecificErrorCode`、`EngineRunErrorCode`、`provider_error_code`：

- `dayu/config/` 全目录
- `dayu/host/memory.py`、`dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`、`compact_payload.py`、`compact_pipeline.py`
- `dayu/host/_terminal_answer.py`、`accepted_result_projection.py`、`run_input.py`

`provider_error_code` / `provider_diagnostic` 仅存在于 Host ingest / read_api / tool_trace 等非 LLM-facing 边界文件中。

### 7. Public Exports & Docs Coherence

- `dayu/engine/__init__.py`：导出 `EngineRunErrorCode`、`RunnerSpecificErrorCode`、`RunnerSpecificErrorSource`、`serialize_engine_error_code`、`RunnerProviderDiagnosticData`、`ProviderDiagnosticData` 等
- `dayu/engine/contracts/__init__.py`：导出 `ContextOverflowDetection`、`ContextOverflowDetectionKind`、`RunnerDiagnosticSeverity`、`RunnerDiagnosticSource`
- `docs/engine/design.md`：更新 RunnerEvent/EngineEvent 表、context overflow marker fallback provenance、Engine failure code contract
- `docs/host/design.md`：更新 EventLog taxonomy、PROVIDER_DIAGNOSTIC diagnostic event matrix
- `dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`：均已按 Agent 更新约束更新

## Open Questions

无。

## Residual Risk

- Provider 可能返回多个 choices（尽管 Dayu 未请求）。S1 有意 fail closed，不 fabricate 单一 response。此为已知设计决策，非缺陷。
- `dayu/engine/runners/openai/_choice_policy.py` 内部 `ChoicePolicyError.error_code: str` 保持 adapter 私有语义，进入 `RunnerProtocolErrorData` 前已包装。若未来 choice policy 扩展到多个 adapter 实现，该私有 str 可能需要升级为 typed enum，但当前单一 OpenAI-compatible adapter 下不构成风险。
- Provider-specific protocol code 仍仅以 durable serialized text 对外投影；Host 不掌握 wrapper source。若未来 public API 需暴露 source，应由 Engine/Host public contract 单独设计。
- 全量 `tests/engine tests/host` 包含不相关 Host 失败，不在 P3-D 范围内。P3-D 必跑验证与覆盖率均通过。

## Coverage Summary

| Slice | 关键测试 | pyright | 覆盖率 |
|---|---|---|---|
| S1 | 60 passed | 0 errors | sse_parser 86%, non_stream_parser 89% |
| S2 | 164 passed | 0 errors | 全 touched 文件 ≥ 80% |
| S3 | 514 passed (engine) + 155 passed (host) | 0 errors | 全 touched 文件 ≥ 80% |

---

P3-D aggregate deepreview complete.
