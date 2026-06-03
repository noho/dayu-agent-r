# WU-ENG-02 Slice 4 Code Review — AgentDS

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: Slice 4 code review
- reviewer: AgentDS
- artifact path: `docs/reviews/wu-eng-02-slice4-code-review-ds.md`
- review scope: README sync, residual risk 复核, final validation; 不做实现修改

## Verdict

**pass**

0 条 blocking findings。README 变更准确描述当前已实现行为，residual risk 复核建议合理，验证命令全部通过。

---

## 1. 范围确认

审查文件：
- `dayu/engine/README.md` (modified, diff verified)
- `dayu/host/README.md` (modified, diff verified)
- `tests/README.md` (modified, diff verified)
- `docs/reviews/wu-eng-02-slice4-implementation-codex.md` (implementation artifact, untracked)
- `docs/host/issues-implementation-control.md` (Controller gate state only, not modified by this slice)

真源文档：
- `docs/host/wu-eng-02-provider-request-identity-plan.md` (accepted plan)
- `docs/host/design.md` (design reference)

---

## 2. Findings

### 2.1 README 准确性审查

#### F-001 (INFO) `dayu/engine/README.md` — Runner 接口描述准确

**文件**: `dayu/engine/README.md:123`
**证据**: `AsyncRunner.call(messages, options, tools, *, request_identity)` 与代码 `dayu/engine/contracts/runner.py` 中 `AsyncRunner.call` 协议签名一致。`request_identity` 为 keyword-only `RunnerRequestIdentity | None`，保留 `messages/options/tools` 位置参数不变。

**影响**: 无。与 accepted plan Slice 1 要求一致。

#### F-002 (INFO) `dayu/engine/README.md` — RunnerRequestIdentity 描述准确

**文件**: `dayu/engine/README.md:127`
**证据**: README 描述的字段集合（`run_id`、可选成对的 `attempt_id`/`execution_id`、`iteration_id`、`iteration_index`、`runner_call_index`、`client_correlation_id`）与 `dayu/engine/contracts/runner_identity.py:41-44` 完全一致。`client_correlation_id` 的 `dayu-` + 64 位 lowercase SHA-256 hex 格式与 builder 实现 `build_runner_request_identity()` 一致。

**影响**: 无。

#### F-003 (INFO) `dayu/engine/README.md` — ClientCorrelationPolicy 描述准确

**文件**: `dayu/engine/README.md:133-139`
**证据**: 
- 枚举成员 `DISABLED` 和 `OPENAI_X_CLIENT_REQUEST_ID` 与 `dayu/engine/contracts/runner_spec.py:72-87` 一致。
- "policy 关闭或 identity 缺失时不发送" — 与 `dayu/engine/runners/openai/runner.py` 中 `_build_request_headers()` 逻辑一致。
- "静态 `RunnerSpec.headers` 不得包含大小写不敏感的 `X-Client-Request-Id`，否则 Runner fail fast" — 与 `_has_client_request_id_header()` 冲突检测一致。
- "transport retry 复用同一次逻辑 Runner call 的 `client_correlation_id`" — 与 `_call_impl()` retry loop 行为一致。

**影响**: 无。

#### F-004 (INFO) `dayu/engine/README.md` — 公共契约更新准确

**文件**: `dayu/engine/README.md:183,188-189,205`
**证据**:
- Line 183: `AgentRunRequest` 新增 `attempt_id`/`execution_id` — 与 `dayu/engine/contracts/agent_run.py:94-95` 一致，验证了成对约束。
- Lines 188-189: 新增 `RunnerRequestIdentity` 和 `ClientCorrelationPolicy` 条目 — 字段描述与实现一致。
- Line 205: `client_correlation_id` 出现在 `IterationCompletedData`、`ProviderProtocolErrorData`、`ContextCompactionRequestedData`、`RunFailedData` 和 `EngineRunOutcomeFailed` — 全部验证通过：
  - `engine_events.py:332` (`IterationCompletedData`)
  - `engine_events.py:315` (`ProviderProtocolErrorData`)
  - `engine_events.py:273` (`ContextCompactionRequestedData`)
  - `engine_events.py:415` (`RunFailedData`)
  - `agent_run.py:156` (`EngineRunOutcomeFailed`)

**影响**: 无。

#### F-005 (INFO) `dayu/engine/README.md` — 执行路径更新准确

**文件**: `dayu/engine/README.md:252-253`
**证据**: 执行路径中新增 "build RunnerRequestIdentity for this logical Runner call" 和 "AsyncRunner.call(messages, request.runner_options, effective_tools, request_identity=identity)" — 与 `dayu/engine/agent.py` 中 `_AsyncAgent` 实际行为一致。

**影响**: 无。

#### F-006 (INFO) `dayu/host/README.md` — RunInputBuilder 投影描述准确

**文件**: `dayu/host/README.md:200`
**证据**: "RunInputBuilder 构造 ordinary Engine `AgentRunRequest` 时，会把当前 `AttemptDispatchSnapshot.attempt_id` 与 `execution_id` 投影到 Engine request" — 与 `dayu/host/run_input.py:1680-1681` 一致。结尾 "Engine 不拥有 Host 状态机" 正确表述了边界。

**影响**: 无。

#### F-007 (INFO) `dayu/host/README.md` — EventLog ingest 诊断字段描述准确

**文件**: `dayu/host/README.md:208`
**证据**: "EngineEvent ingest 在 provider-related payload 中保留 Engine 提供的 `provider_request_id` 与 `client_correlation_id`。当前覆盖 provider protocol diagnostic、reactive context compaction request / recovery closeout、failed terminal closeout 和 iteration completed preview。" — 与 `dayu/host/engine_ingest.py` 中多处 payload 写入一致（lines 850, 1388, 1503, 2420, 3915, 4220, 4259 等）。"不改变 Run / Attempt 状态迁移规则，也不新增 durable hot-table schema column" 准确。

**影响**: 无。

#### F-008 (INFO) `dayu/host/README.md` — Tool Trace 诊断描述准确

**文件**: `dayu/host/README.md:276`
**证据**: "hot row 仍只把 `provider_request_id` 作为查询列；`client_correlation_id` 进入 `trace_summary_json`，cold JSONL 的 `trace_summary` 也保留同名字段" — 与 `dayu/host/tool_trace.py:711,793` 一致。非文本字段 fail closed 的校验在 `_optional_text()` 调用中实现。

**影响**: 无。

#### F-009 (INFO) `tests/README.md` — 测试覆盖描述准确

**文件**: `tests/README.md:128,164-167,174,177`
**证据**:
- Line 128: 新增 "provider request identity / Tool Trace correlation" 条目覆盖 effective config、RunInputBuilder、compactor、ingest payload、Tool Trace projection 测试 — 与实际测试文件覆盖一致。
- Lines 164-165: `runner_spec` 条目新增 `ClientCorrelationPolicy` 枚举值 — `test_runner_spec.py` 已验证。
- Lines 166-167: 新增 `runner_identity` 和 `agent_run` 条目 — `test_runner_identity.py` 和 `test_agent_run.py` 已验证。
- Line 177: 新增 "request identity header" 条目 — `test_request_identity.py` 已验证。

**影响**: 无。

#### F-010 (PASS) 无"未来设计"或过程状态

对三个 README 的 diff 全文扫描：
- 未发现 "未来"、"计划"、"即将"、"后续"、"TODO"、"FIXME" 等过程状态标记。
- 未发现 analyzer 未实现能力被描述为当前能力。
- 未发现旧术语残留。
- 根 `README.md` 未被修改，符合 plan 预期。

**影响**: 无。

### 2.2 Residual Risk 复核

#### F-011 (LOW) S1-R1 — 工具超时 `RunFailedData` 缺少 `client_correlation_id`

**来源**: WU-ENG-02 Slice 1 re-review
**Codex 建议**: 继续 deferred-with-owner
**独立复核**: 同意。

代码证据：`dayu/engine/agent.py:2150-2156`
```python
async def _make_tool_timeout_terminal_with_close(self) -> EngineEvent:
    await self._close_runner_once()
    return self._make_terminal_failed(
        RunFailedData(
            error_code=_ERROR_TOOL_EXECUTION_TIMEOUT,
            message=_TOOL_EXECUTION_TIMEOUT_MESSAGE,
            provider_request_id=None,
            recoverable=False,
        )
    )
```

`RunFailedData` 字段定义（`engine_events.py:415`）已包含 `client_correlation_id: str | None = None`，但该路径未显式传入。当前 `_client_correlation_id_from_state()` helper 已在 force-answer 等路径使用，工具超时路径可以同样使用。但工具超时发生在 Runner 调用之外（等待 `ToolExecutor.execute`），此时上一个 Runner call 的 correlation id 在 state 中可用但语义上不一定对应工具超时本身。

建议保持 deferred-with-owner，由后续工作单元决定是否在该路径补 correlation。

#### F-012 (LOW) S1-R2 — force-answer failure EngineEvent 直接 assertion

**来源**: WU-ENG-02 Slice 1 re-review
**Codex 建议**: 继续 deferred-with-owner，除非 Controller 接受现有间接覆盖
**独立复核**: 同意。

代码证据：`dayu/engine/agent.py:2093-2099`
```python
RunFailedData(
    error_code=_ERROR_FORCE_ANSWER_EMPTY,
    message=_FORCE_ANSWER_EMPTY_MESSAGE,
    provider_request_id=None,
    client_correlation_id=_client_correlation_id_from_state(state),
),
```

代码行为正确：force-answer 路径的 `RunFailedData` 已携带 `client_correlation_id`。gap 仅在于测试没有显式断言 emitted EngineEvent 的 `client_correlation_id` 字段值等于预期。现有测试覆盖：
- `runner_call_index` 在 force-answer 路径递增为 `[1, 2]` — 间接证明第二次 Runner call 使用了不同 identity
- `iteration_id` 正确 — 间接证明 identity 在 force-answer 调用前已构造

建议保持 deferred-with-owner。若需要关闭，应在后续 slice 补 focused Engine test 而非 README 变更。

#### F-013 (PASS) S2-R1 — production assembly 默认 DISABLED

**来源**: WU-ENG-02 Slice 2 code review
**Codex 建议**: 关闭
**独立复核**: 同意关闭。

证据：
- `ClientCorrelationPolicy.DISABLED` 是显式枚举值（`runner_spec.py:72`）
- RunnerSpec 测试锁定枚举值（`test_runner_spec.py`）
- OpenAI Runner 测试确认 disabled 即使有 identity 也不发送 header（`test_request_identity.py`）
- Host effective execution config 测试确认 enabled policy 可 freeze/restore（`test_effective_execution_config.py`）
- production assembly 默认 `DISABLED` 符合本 WU "显式 policy 才发送" 的验收信号

关闭依据充分。

#### F-014 (LOW) S2-R2 — 静态 header 冲突上层收口

**来源**: WU-ENG-02 Slice 2 code review
**Codex 建议**: Engine adapter 部分关闭；Service/config assembly 继续 deferred-with-owner
**独立复核**: 同意。

OpenAI Runner 已在 policy enabled 且静态 header 冲突时抛 `ValueError`（`dayu/engine/runners/openai/runner.py`），测试确认不会发 HTTP 请求。Engine adapter 层面已正确处理。Service/config assembly 的结构化错误收口不在 Slice 4 scope，也不在本 WU 的最小验收范围内。

Engine adapter 部分：建议关闭。
Service 收口部分：建议 deferred-with-owner（Service assembly）。

#### F-015 (PASS) S3-R1 — usage observation 与 client correlation

**来源**: WU-ENG-02 Slice 3 code review
**Codex 建议**: 继续 deferred-with-owner（WU-OBS-00 analyzer）
**独立复核**: 同意。

`UsageReportedData`（`engine_events.py`）当前只携带 token usage 与 iteration id，不含 `client_correlation_id`。usage observation 是 post-call projection signal，不是 provider debugging correlation 主链路信号。是否扩展 `UsageReportedData` 属于 analyzer/observation 设计决策，不应在本 WU 强行扩展。

#### F-016 (LOW) S3-R2 — ContextRecoveryCloseInput 专用测试

**来源**: WU-ENG-02 Slice 3 code review
**Codex 建议**: 不作为当前 blocker；可保留为专用测试 residual
**独立复核**: 同意。

证据：
- `ContextRecoveryCloseInput` 有 `client_correlation_id: str | None = None` 字段（`run_transition.py:425`）
- 通过 `_require_optional_non_empty_text()` 校验（`run_transition.py:5672`）
- payload 写入 `client_correlation_id`（`run_transition.py:3191`）
- engine ingest reactive compaction 测试间接覆盖 request payload 包含该字段

缺少直接针对 `ContextRecoveryCloseInput` validation/payload 的专用单元测试，但现有间接覆盖和对称校验足以通过 Slice 4。建议保持 deferred-with-owner，后续可选补 focused test。

### 2.3 Plan 验证命令覆盖

#### F-017 (PASS) 验证命令全部通过

Plan 要求的 Engine 测试：
```
tests/engine/contracts/test_runner_identity.py
tests/engine/contracts/test_agent_run.py
tests/engine/contracts/test_runner_spec.py
tests/engine/test_agent_phase2.py
tests/engine/test_agent_phase3_tool_call.py
tests/engine/runners/openai/test_request_identity.py
tests/engine/runners/openai/test_streaming_capability_and_content_type.py
tests/engine/runners/openai/test_http_error_event.py
```
结果：**174 passed** in 0.25s

Plan 要求的 Host 测试：
```
tests/host/test_effective_execution_config.py
tests/host/test_run_input_builder.py
tests/host/test_engine_ingest_mapping.py
tests/host/test_tool_trace_projection.py
tests/host/test_tool_trace_queries.py
tests/host/test_local_proxy_engine_ingest.py
tests/host/test_run_attempt_transitions.py
tests/host/test_llm_compaction.py
```
结果：**198 passed** in 1.48s

pyright：
结果：**0 errors, 0 warnings, 0 informations**

后两个 Host 测试文件（`test_run_attempt_transitions.py`、`test_llm_compaction.py`）不在 plan 的显式命令列表中，但属于 affected Host tests，且全部通过。

### 2.4 其他观察

#### F-018 (INFO) implementation artifact 中验证结果可复现

Codex artifact 报告 174 Engine passed + 198 Host passed + pyright 0 errors。独立验证全部复现，无差异。

#### F-019 (INFO) 未发现 README 描述与代码不一致

对三个 README 的全部变更做了逐条代码验证，未发现描述不准确、过时或夸大。所有变更均为对当前已实现行为的稳定描述。

---

## 3. 验证命令与结果

```bash
# Engine tests
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py -q
# => 174 passed in 0.25s

# Host tests
source .venv/bin/activate && pytest tests/host/test_effective_execution_config.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_local_proxy_engine_ingest.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_llm_compaction.py -q
# => 198 passed in 1.48s

# pyright
source .venv/bin/activate && python -m pyright
# => 0 errors, 0 warnings, 0 informations
```

所有 plan 要求的验证命令覆盖完整，结果通过。

---

## 4. Open Questions

none

---

## 5. Residual Risks / Deferred Items

| ID | 当前状态 | 本 review 建议 |
|---|---|---|
| WU-ENG-02-S1-R1 | deferred-with-owner | 保持。工具超时路径 `RunFailedData` 缺 `client_correlation_id`；已在 agent.py:2150 确认。 |
| WU-ENG-02-S1-R2 | deferred-with-owner | 保持。代码行为正确，缺 EngineEvent 级直接断言。 |
| WU-ENG-02-S2-R1 | deferred → **close** | 建议关闭。policy 枚举/disabled 行为/effective config 均有充分测试证据。 |
| WU-ENG-02-S2-R2 | deferred → **partial close** | Engine adapter 部分建议关闭；Service 结构化收口保持 deferred。 |
| WU-ENG-02-S3-R1 | deferred-with-owner | 保持。analyzer concern，不属本 WU scope。 |
| WU-ENG-02-S3-R2 | deferred-with-owner | 保持。间接覆盖充分，可选补 focused test。 |

---

## 6. Final Recommendation

Slice 4 文档同步和最终验证通过。README 变更准确描述当前已实现行为，无未来设计、过程状态或未实现能力。validation 命令全部通过，plan 覆盖完整。0 条 blocking findings。建议进入下一 gate。
