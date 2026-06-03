# WU-ENG-02 Slice 1 Code Review — AgentDS

## Gate / Work Unit / Slice

- gate: deepreview (code review)
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 — Engine Contract And Agent Identity
- reviewer: AgentDS
- review basis: git diff of uncommitted workspace changes
- implementation artifact: `docs/reviews/wu-eng-02-slice1-implementation-codex.md`

## Review Target

Current uncommitted workspace changes (git diff vs HEAD). Changed files:

| File | Nature |
|---|---|
| `dayu/engine/contracts/runner_identity.py` | new: RunnerRequestIdentity + builder + encoding |
| `dayu/engine/contracts/runner.py` | changed: AsyncRunner.call keyword-only request_identity |
| `dayu/engine/contracts/agent_run.py` | changed: AgentRunRequest attempt_id/execution_id; EngineRunOutcomeFailed.client_correlation_id |
| `dayu/engine/contracts/engine_events.py` | changed: client_correlation_id in 4 data classes |
| `dayu/engine/contracts/__init__.py` | changed: re-export RunnerRequestIdentity, build_runner_request_identity |
| `dayu/engine/agent.py` | changed: _runner_call_index, _next_runner_request_identity, _IterationState.request_identity, _client_correlation_id_from_state, all emission sites |
| `dayu/engine/runners/openai/runner.py` | changed: signature sync only (accepts + ignores request_identity) |
| `tests/engine/contracts/test_runner_identity.py` | new: 8 contract tests |
| `tests/engine/contracts/test_agent_run.py` | changed: 2 new pair-validation tests |
| `tests/engine/test_agent_phase2.py` | changed: fake runner captures request_identities; success test verifies identity fields |
| `tests/engine/test_agent_phase3_tool_call.py` | changed: fake runners capture request_identities; 3 verification tests |
| `tests/engine/test_metadata_boundary.py` | changed: runner signature sync; field name assertion; attempt_id in request constructor |
| `tests/host/public_smoke_support.py` | changed: 2 fake runners signature sync only |
| `tests/host/test_phase6_toolruntime_integration.py` | changed: fake runner signature sync only |
| `docs/host/issues-implementation-control.md` | changed: gate status update (pre-existing change, not part of Slice 1) |

## Validation Evidence

### Tests
```
source .venv/bin/activate
pytest tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/test_metadata_boundary.py
```
Result: **127 passed, 0 failed** in 0.21s.

### Type Check
```
source .venv/bin/activate && pyright
```
Result: **0 errors, 0 warnings, 0 informations**.

### Extra verification (run independently)
```
pytest tests/host/public_smoke_support.py tests/host/test_phase6_toolruntime_integration.py -q
```
Confirmed: host smoke/integration fake runners are signature-compatible; no test breaks.

## Findings

### Finding 1 (LOW) — EngineEvent client_correlation_id 值未在 Agent 测试中断言

**Evidence:**
- `tests/engine/test_agent_phase2.py:527-539` — `test_success_run_lifts_runner_events_and_agent_final` 验证了 fake runner 捕获的 `request_identity` 字段正确，但**未**遍历 emitted `EngineEvent` 验证 `IterationCompletedData.client_correlation_id` 等字段的值。
- `tests/engine/test_agent_phase3_tool_call.py:970-983` — `test_completed_tool_call_injects_messages_and_reaches_final` 验证了 `runner.request_identities_seen` 的 `runner_call_index` 顺序为 `[1, 2]`，但**未**验证 emitted events 中的 `client_correlation_id`。
- `tests/engine/test_agent_phase3_tool_call.py:1040-1049` — force-answer 测试**未**验证 emitted `RunFailedData.client_correlation_id`。
- `tests/engine/test_agent_phase3_tool_call.py:1964-1973` — length continuation 测试**未**验证 emitted events 的 `client_correlation_id`。

**Impact:** 代码通过单一 helper `_client_correlation_id_from_state` 在所有 emission site 一致使用，行为正确性依赖于该 helper 的调用一致性。当前测试覆盖的是「Agent → Runner」的 id 传递路径，但未覆盖「Agent → EngineEvent」的 correlation id 发射路径。如果未来某处遗漏调用 helper，现有测试不会捕获。

**建议修法:** 在已有的 `test_completed_tool_call_injects_messages_and_reaches_final` 中添加对 `IterationCompletedData` 事件 data 的 `client_correlation_id` 字段断言；在 force-answer / length continuation 测试中同样补齐。这可以 3-5 行断言完成，无需新增测试函数。

**裁决:** deferred-with-owner — 建议在 Slice 4（final validation）或 Slice 3 的 Host ingest 测试中补齐；当前不阻塞 Slice 1 pass。

---

### Finding 2 (LOW) — `_validate_batch_bijection` RunFailedData 缺少 client_correlation_id，与同函数内的 duplicate 检查不一致

**Evidence:**
- `dayu/engine/agent.py:1596-1603` — `_execute_tool_batch` 中 duplicate `tool_call_id` 检测的 `RunFailedData` **包含** `client_correlation_id=decision.client_correlation_id`。
- `dayu/engine/agent.py:1831-1843` — 同一函数调用的 `_validate_batch_bijection` 方法中两次构造 `RunFailedData` **均未**包含 `client_correlation_id`。

**Impact:** 两个检查都是同一 tool batch 执行路径上的 validation，一个携带 correlation id，一个不携带。bijection 失败表示 ToolExecutor 返回了与输入不一致的 records，属于内部一致性错误而非 provider 错误。按 plan 语义（"when tied to a provider call"），bijection 错误不直接关联到 provider 调用，因此缺失不是 bug。但**一致性**上存在轻微差异，可能在诊断时造成困惑。

**建议修法:** 将 `decision`（或 `decision.client_correlation_id`）传入 `_validate_batch_bijection`，在构造 `RunFailedData` 时传递 `client_correlation_id`。这是一个 3 行改动。

**裁决:** deferred-with-owner — 不影响功能正确性，可在后续 slice 中统一；当前不阻塞。

---

### Finding 3 (OBSERVATION) — `_MetadataBoundaryRunner` 未捕获 request_identity

**Evidence:**
- `tests/engine/test_metadata_boundary.py:130` — `_MetadataBoundaryRunner.call()` 仅执行 `del messages, options, tools, request_identity`，不记录 `request_identity`。
- 对比 `tests/engine/test_agent_phase2.py:219` — `_ScriptedRunner.call()` 记录 `self.request_identities_seen.append(request_identity)`。
- 对比 `tests/engine/test_agent_phase3_tool_call.py:201` — phase3 `_ScriptedRunner.call()` 同样记录。

**Impact:** metadata boundary 测试无法验证 request_identity 传递。不过该 runner 仅用于 metadata 边界测试（验证 EngineEvent 不携带 provider 敏感信息），不测试 Agent 行为正确性，所以实际影响可忽略。

**裁决:** accepted — metadata boundary 测试的职责不包含 Agent identity 传递验证。

---

### Finding 4 (OBSERVATION) — `_fallback_after_tools` RAISE_ERROR 路径不含 client_correlation_id 是正确设计

**Evidence:**
- `dayu/engine/agent.py:1980-1988` — RAISE_ERROR 分支构造 `RunFailedData` 时未传入 `client_correlation_id`，默认 `None`。
- plan §Slice 1 Error handling: "Runner exceptions preserve existing failure behavior and include current client_correlation_id in RunFailedData **when tied to a provider call**."

**Impact:** `max_iterations_exceeded` 和 `consecutive_failed_tool_batches` 是 Agent policy 级决策，不是 provider call 失败。此处的 `client_correlation_id=None` 符合 plan 语义。但是 RunFailedData 终态通过 `run_agent_and_wait` 映射到 `EngineRunOutcomeFailed` 时，`client_correlation_id` 为 `None`，可能影响 Slice 3 Host ingest 的诊断完整性。这属于 Slice 3 的设计决策点。

**裁决:** accepted — 符合 plan 设计，无 bug。

---

### Finding 5 (VERIFIED) — `runner_call_index` 对所有逻辑 Runner 调用正确递增

**Evidence:**
- `dayu/engine/agent.py:632` — `_runner_call_index` 初值为 0。
- `dayu/engine/agent.py:2357-2380` — `_next_runner_request_identity` 唯一递增点，每次调用 `+= 1`，首个调用得 index=1。
- 调用路径验证：
  - **normal iteration** (`run_messages:698` → `_run_runner_iteration:1072` → `_next_runner_request_identity`) ✓
  - **tool-loop re-entry** (tool batch 后 loop continue → next `_run_runner_iteration`) ✓
  - **length continuation** (`_handle_length_final_decision` returns `None` → loop continue → next `_run_runner_iteration`) ✓
  - **force-answer** (`_run_force_answer:2023` → `_run_runner_iteration` → `_next_runner_request_identity`) ✓
  - **RAISE_ERROR fallback** — 不调用 Runner，不递增 ✓
- 测试确认：`tests/engine/test_agent_phase2.py:538` (call_index=1), `test_agent_phase3_tool_call.py:974-977` (call_index=[1,2]), `test_agent_phase3_tool_call.py:1044-1047` (force-answer call_index=[1,2]), `test_agent_phase3_tool_call.py:1968-1971` (continuation call_index=[1,2])。

**结论:** 无遗漏、无重复、无异常路径错用 identity。

---

### Finding 6 (VERIFIED) — digest 格式与编码方案审查通过

**Evidence:**
- `dayu/engine/contracts/runner_identity.py:13-17` — `_CLIENT_CORRELATION_PREFIX = "dayu-"`, `_SHA256_HEX_LENGTH = 64`, 总长度 69。
- `dayu/engine/contracts/runner_identity.py:240-273` — `_encode_canonical_parts` 使用类型前缀编码：`n`（None）、`i:VALUE`（int）、`s:LEN:VALUE`（str），各 part 以 `|` 分隔。类型前缀 + 字符串长度保护避免了 None/integer/string 之间的歧义注入。
- `dayu/engine/contracts/runner_identity.py:228-237` — `_build_client_correlation_id` 使用 `hashlib.sha256().hexdigest()` 产生 64 lowercase hex。
- `tests/engine/contracts/test_runner_identity.py:16-32` — 测试验证了稳定性、lowercase、ASCII、69 字符、不同 iteration/call 产生不同 id。

**结论:** `dayu-` + 64 lowercase SHA-256 hex 的格式要求完全满足；编码方案稳定且抗碰撞。

---

### Finding 7 (VERIFIED) — AgentRunRequest attempt_id/execution_id 成对校验与默认 None 设计合理

**Evidence:**
- `dayu/engine/contracts/agent_run.py:94-95` — `attempt_id: str | None = None`, `execution_id: str | None = None`，默认均为 `None`。
- `dayu/engine/contracts/agent_run.py:107-111` — `__post_init__` 中 XOR 校验：两者必须同时 `None` 或同时非 `None`。
- `tests/engine/contracts/test_agent_run.py:79-107` — 4 个测试覆盖：拒绝不成对、接受成对、默认 None、拒绝空 messages。
- 直接 Engine / compactor 路径均可显式保留默认 `None`（Slice 3 在 `llm_compaction.py` 和 `run_input.py` 处理）。

**结论:** 校验合理，默认 `None` 正确服务了 direct Engine / compactor 路径。

---

### Finding 8 (VERIFIED) — AsyncRunner.call 签名变更最小化

**Evidence:**
- `dayu/engine/contracts/runner.py:25-32` — `call(messages, options, tools, *, request_identity: RunnerRequestIdentity | None)` — 仅新增 keyword-only 参数。
- `dayu/engine/runners/openai/runner.py:250` — `request_identity: RunnerRequestIdentity | None = None` 带默认值，不破坏已有直接 Runner 调用。
- `tests/engine/test_agent_phase2.py:200-201` — fake runner 同步更新 signature。
- `tests/engine/test_agent_phase3_tool_call.py:180-186` — fake runner 同步更新 signature 并记录 identity。
- `tests/host/public_smoke_support.py:554-555` — 2 个 fake runners 同步更新。
- `tests/host/test_phase6_toolruntime_integration.py:178-179` — 1 个 fake runner 同步更新。

**结论:** 所有 fake runner 和 production runner 签名已同步；仅 keyword-only 新增，不改变现有 positional 参数语义。

---

### Finding 9 (VERIFIED) — 额外改动未越过 Slice 1 边界

**Evidence:**
- `dayu/engine/runners/openai/runner.py:253` — `del request_identity`，仅接收并忽略；注释明确标注 "本 slice 仅接收契约，OpenAI header 映射由后续 policy slice 实现"。
- `tests/host/public_smoke_support.py` — 仅签名同步 + `del request_identity`。
- `tests/host/test_phase6_toolruntime_integration.py` — 仅签名同步 + `del request_identity`。
- `docs/host/issues-implementation-control.md` — 仅 gate 状态更新（pre-existing worktree change，非 Slice 1 产生）。

**结论:** 无 Slice 2/3 行为泄漏；OpenAI header 映射、RunnerSpec policy、Host projection 均保留为后续 slice 工作。

---

### Finding 10 (VERIFIED) — docstring 与类型标注审查通过

**Evidence (全量检查):**
- `RunnerRequestIdentity` — 完整中文 docstring（模块级 + 类级 + 字段 + `__post_init__`），所有参数/返回/异常声明。✓
- `build_runner_request_identity` — 完整中文 docstring，参数/返回/异常。✓
- 所有 8 个模块级私有函数 — 完整中文 docstring。✓
- `agent.py` 新增函数 `_client_correlation_id_from_state` — 完整中文 docstring。✓
- `agent.py` 新增方法 `_next_runner_request_identity` — 完整中文 docstring。✓
- `_IterationState` — docstring 更新，新增 `request_identity` 参数。✓
- `_ToolCallsDecision` — docstring 新增全部参数说明。✓
- 所有类型标注 — 无 `Any`、`object`、无类型参数/返回值。✓
- 无 lazy import、无 provider 字符串治理分支、无嵌套函数/类、无兼容性代码。✓

**结论:** 严格符合 AGENTS.md 编码规范。

---

### Finding 11 (VERIFIED) — RunnerEvent 不携带 Host ownership 边界未被打破

**Evidence:**
- `RunnerRequestIdentity` 通过 `AsyncRunner.call()` 进入 Runner（出站 header 的源头），不通过 `RunnerEvent` 返回。
- `RunnerEvent` 及其所有 data 类未新增任何字段。
- `client_correlation_id` 仅在 `EngineEvent` data 类（`RunFailedData`、`IterationCompletedData` 等）中出现，这些是 Engine 提升后的宿主事件。
- plan §Non-Goals: "不改变 RunnerEvent 不携带 Host ownership 的边界" ✓

**结论:** 边界清晰，无反向依赖。

---

## 残余风险与测试缺口

1. **EngineEvent 级 correlation id 值验证缺失** (Finding 1): 当前测试只验证 fake runner 收到的 `request_identity` 对象，不验证 emitted `EngineEvent` 的 `client_correlation_id` 字段值。代码行为正确但断言缺口存在。

2. **3+ call index 路径未显式测试**: 所有测试只验证 index=[1] 或 [1,2] 的场景。对于 3 次以上 Runner 调用的场景（如连续 tool-loop re-entry），递增逻辑相同但未被显式验证。

3. **RAISE_ERROR fallback 路径未验证 client_correlation_id 缺席**: `_fallback_after_tools` 的 RAISE_ERROR 分支产生的 `RunFailedData` 不含 `client_correlation_id`（设计正确），但没有测试显式断言这一行为。未来若有人误加 correlation id，也不会有测试失败。

4. **Slice 3 Host projection 未实现**: Host `RunInputBuilder` 尚未将 `AttemptDispatchSnapshot.attempt_id/execution_id` 投影到 `AgentRunRequest`。所有 Agent 测试使用硬编码的 `attempt_id="attempt_phase2"` 等值，端到端 attempt identity 链路未验证。

5. **Slice 2 OpenAI header 映射未实现**: `AsyncOpenAIRunner` 仅接收并忽略 `request_identity`。当 Slice 2 实现 header 映射时，需要验证 `X-Client-Request-Id` 的发送/不发送行为，以及 transport retry 复用同一 header。

## Blocking Open Questions

无。所有 plan 中标记的 open questions 已在 plan review 阶段关闭；Slice 1 实现未引入新的 blocking questions。

## Docs/README Decision

按 plan §Slice 4，README 同步在当前 Slice 1 **不需要处理**。当前 slice 仅涉及 Engine 公共契约变更，README 更新应在 Slice 4 (Documentation Sync And Final Validation) 中统一完成。

需更新的 README（deferred to Slice 4）:
- `dayu/engine/README.md` — 文档化 `RunnerRequestIdentity`、`client_correlation_id`、Runner call boundary
- `tests/README.md` — 更新测试覆盖描述

## 结论

**pass-with-findings**

- 核心实现（RunnerRequestIdentity、build_runner_request_identity、_runner_call_index 递增、client_correlation_id 在 EngineEvent 中的铺设）完全符合 plan 要求
- digest 格式、编码方案、成对校验、类型安全、docstring 覆盖全部通过审查
- 127 测试通过，pyright 0 errors
- Slice 1 边界严格，无 Slice 2/3 行为泄漏
- 2 条 LOW severity findings（测试覆盖缺口、bijection consistency），建议在后续 slice 中处理
- 0 条 blocking findings
- 无 blocking open questions
