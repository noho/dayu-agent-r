# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Code Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace diff vs HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted staged changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-ds.md`
- Included scope:
  - `dayu/contracts/tool_result.py`
  - `dayu/host/tool_runtime.py`
  - `tests/contracts/test_tool_result_envelope.py`
  - `tests/host/test_toolruntime_executor.py`
  - `tests/host/test_toolruntime_truncation_fetch_more.py`
  - `tests/host/test_toolruntime_duplicate_governance.py`
  - `tests/fins/test_fins_storage_provider.py`
- Excluded scope:
  - `docs/cli_ci*`, `docs/reviews/code-review-20260710-*` (unrelated untracked)
  - S2/S3 files (wait callback, accepted projection, Fins direct — not yet implemented)
  - `docs/host/issues-implementation-control.md` (gate bookkeeping only, not production code)
- Parallel review coverage: 无（单 reviewer 逐路走读）

## Context Documents Read

- `AGENTS.md` — project constraints and semantic ownership rules
- `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md` — S1 plan
- `docs/reviews/wu-semantic-ownership-01-p3-e-s1-implementation-codex.md` — Codex implementation artifact
- `docs/reviews/wu-semantic-ownership-01-p3-e-s1-controller-validation.md` — controller validation

## Findings

### S1-F1-未修复-中-`tests/tools/` 取消 hint 断言未纳入 S1 范围，将导致全量测试断裂

- **入口/函数**: `ToolRuntimeExecutor.execute()` → `_governed_failure_outcome()` → 取消路径
- **文件(行号)**:
  - `tests/tools/test_doc_tools_provider.py:1210,1263`
  - `tests/tools/web/test_web_tools_provider.py:714`
- **输入场景**: 通过真实 `DefaultToolRuntimeFactory` 构造 `ToolRuntimeHandle`，执行 process-backed 工具并在运行中触发取消 token。
- **实际分支**: 取消 token 触发 → `_runtime_cancelled_policy_decision()` 构造 `policy_decision.reason_code="tool_runtime_cancelled"` → `_governed_failure_outcome(policy_decision)` → `hint=None`（本次 S1 改动）。
- **预期行为**: 如果计划有意限定 S1 只覆盖 5 个测试文件，应在计划中显式声明 `tests/tools/` 的取消 hint 断言已知会断裂，并安排后续修复。否则应将这些测试文件纳入 S1 scope。
- **实际行为**: S1 改动使 `result.hint` 从 `"tool_runtime_cancelled"` 变为 `None`；三处断言 `result.hint == "tool_runtime_cancelled"` 将在全量测试中失败。S1 验证只跑了 5 个指定测试文件（151 passed），未覆盖这些文件。Codex 实现 artifact 亦注明"本 slice 未运行不在 required list 内的全量 Host / Engine 测试"。
- **直接证据**:
  - `dayu/host/tool_runtime.py:7477-7490`: `_governed_failure_outcome` 统一 `hint=None`
  - `dayu/host/tool_runtime.py:264` (`_TOOL_RUNTIME_CANCELLED_REASON = "tool_runtime_cancelled"`): reason_code 仍存在于 policy decision，但不再进入 hint
  - `tests/tools/test_doc_tools_provider.py:1401-1408`: `_execute_doc_runtime_read_file_and_cancel` 通过 `tool_runtime.tool_executor.execute(...)` 走真实取消路径
  - 三处断言行号见上
- **影响**: 全量 `pytest` 运行将失败；CI 若运行完整套件会被阻断。受影响的测试不在 S1 验收范围内，但在同一仓库中，属于可预见的断裂。
- **建议改法和验证点**:
  1. 将三处 `result.hint == "tool_runtime_cancelled"` 改为 `result.hint is None`；
  2. 保留 `policy_decision.reason_code == "tool_runtime_cancelled"` 断言（在相邻行，不受影响）；
  3. 或者，若计划认为工具层测试不应关注 ToolRuntime 内部治理码，可删除 hint 断言：`result.hint is None` 已覆盖意图；
  4. 运行 `pytest tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q` 验证通过。
- **修复风险（低）**: 修改为 `hint is None` 是纯断言对齐；不改变被测代码行为，不影响其他测试。
- **严重程度（中）**: 不属于 correctness/stability regression，但会导致 CI 全量断裂，阻碍 merge。

### S1-F2-未修复-低-`_truncation_failure` 的 `reason_code` 参数成为死参数

- **入口/函数**: `_truncation_failure(reason_code: str, message: str) -> ToolFailedOutcome`
- **文件(行号)**: `dayu/host/tool_runtime.py:7462-7474`
- **输入场景**: 任何截断/补读失败路径（cursor 缺失、scope 不匹配、token 不匹配、TTL 过期、cursor 已使用、digest 不匹配、非法请求等）。
- **实际分支**: `_truncation_failure` 接收 `reason_code` 但不使用——既不写入 `error`（固定为 `_TRUNCATION_ERROR_CODE`），也不写入 `hint`（固定为 `None`），也不写入 `message`（由调用方单独传入）。
- **预期行为**: 计划声明"The specific reason remains in `error` plus message / trace path"。实现中 `error` 始终为 `truncation_error`（无区分度），`message` 承载人类可读区分但非机器可解析，`reason_code` 参数被静默丢弃。若计划本意是 `reason_code` 不再作为结构化字段暴露，应删除参数或保留到 `error` 中以区分截断子类。
- **实际行为**: 11 个调用点传入 7 种不同 reason 常量（`missing_cursor`、`scope_mismatch`、`scope_token_mismatch`、`cursor_expired`、`cursor_already_used`、`remainder_digest_mismatch`、`invalid_fetch_more_request`、`unsupported_truncation_target`），全部在函数体内被静默丢弃。这些常量现在唯一的作用是作为死参数实参。
- **直接证据**:
  - `dayu/host/tool_runtime.py:7462-7474`: 函数体不含任何对 `reason_code` 的引用
  - `dayu/host/tool_runtime.py:294-302`: 7 个 truncation reason 常量仅在 `_truncation_failure` 调用处使用
  - `dayu/host/tool_runtime.py:7470-7473`: `error=_TRUNCATION_ERROR_CODE`（固定值），`hint=None`
- **影响**: 低——不影响运行时正确性（`message` 仍区分具体场景），但产生死代码：7 个常量、11 个调用点的 `reason_code` 实参、函数签名的 `reason_code` 形参。后续维护者可能误以为 `reason_code` 仍被消费，或需要新增截断子类时困惑于往哪里写。
- **建议改法和验证点**:
  1. 若确认截断子类区分不再需要结构化字段：删除 `reason_code` 形参，更新所有 11 个调用点去掉第一个实参，删除 7 个不再使用的 truncation reason 常量；
  2. 若需要保留子类区分：将 `reason_code` 嵌入 `error` 字段如 `f"truncation_error:{reason_code}"` 或保留到 `message` 前缀；
  3. 更新测试以验证具体错误场景的 `error` 或 `message` 内容。
- **修复风险（低）**: 删除死参数是纯清理；若改为嵌入 `error`，需确认无下游代码解析 `error == "truncation_error"` 做精确匹配。
- **严重程度（低）**: 不改变运行时行为，不产生错误结果，仅产生死代码和维护困惑。

### S1-F3-未修复-低-截断测试未按计划补加 `error`/`message` 断言

- **入口/函数**: `tests/host/test_toolruntime_truncation_fetch_more.py` 中的 8 个 fetch_more 失败测试
- **文件(行号)**: `tests/host/test_toolruntime_truncation_fetch_more.py:237,383,399,417,433,449,491,517`
- **输入场景**: cursor 缺失、scope token 不匹配、cursor 已使用、非法 limit、TTL 过期、scope 不匹配、digest 不匹配等截断失败场景。
- **实际分支**: 测试从 `assert result.hint == "<specific_reason>"` 改为 `assert result.hint is None`，但未按计划建议补加 `result.error` 或 `result.message` 内容的断言。
- **预期行为**: 计划明确要求"while separately asserting `error`, `message`, diagnostic emitter records, `failure_metadata.diagnostic_refs`, and durable cleanup reasons remain intact"。即测试不仅要断言 `hint is None`，还应断言诊断信息已迁移到 `error`/`message` 而非丢失。
- **实际行为**: 所有 8 处截断失败测试仅断言 `hint is None`，不验证 `error` 是否为 `truncation_error`，不验证 `message` 是否包含正确场景描述。这意味着一个回归（如 `_truncation_failure` 被错误重构导致所有截断错误变成空 `message`）不会被测试捕获。
- **直接证据**:
  - `tests/host/test_toolruntime_truncation_fetch_more.py:237`: `assert second_outcome.result.hint is None`，无 `error`/`message` 断言
  - 其余 7 处同模式（行号见上）
  - 计划原文（S1 Tests 节）："while separately asserting `error`, `message`..."
- **影响**: 低——测试仍然通过，且截断错误在 change 前后都有各自的 `message` 区分。但测试强度下降：过去 `hint == "missing_cursor"` 至少隐含验证了"进入了 cursor 缺失分支"，现在 `hint is None` 不区分任何截断子类。
- **建议改法和验证点**:
  1. 在每处 `assert result.hint is None` 后追加 `assert result.error == "truncation_error"` 和针对具体场景的 `assert "cursor" in result.message` 或类似断言；
  2. 或至少追加 `assert result.error is not None and result.message is not None` 防止空字段回归。
- **修复风险（低）**: 追加断言不改变被测行为。
- **严重程度（低）**: 测试仍通过，但覆盖强度轻微下降；不构成 correctness 风险。

## Review Focus Verification

### Runtime ok 不变量正确性及测试是否真正绕过静态类型

- `ToolResultSuccess.__post_init__`: 使用 `self.ok is not True` 做 identity check，能够捕获 `cast(Literal[True], False)` 等运行时绕过。比 `!= True` 更严格（`1 is not True` 为 `True`，也会被拦截）。
- `ToolResultFailure.__post_init__`: 使用 `self.ok is not False` 做 identity check，先校验判别字段再校验 `error`/`message`/`hint`，顺序正确。
- 测试 `test_success_envelope_rejects_runtime_false_ok` 使用 `cast(Literal[True], False)` — **真正绕过了静态类型检查**，证明运行时 `__post_init__` 生效。
- 测试 `test_failure_envelope_rejects_runtime_true_ok` 使用 `cast(Literal[False], True)` — **同样真正绕过静态类型检查**。
- 结论: **通过，不变量实现和测试均正确。**

### ToolRuntime 不再通过 LLM-facing hint 泄漏治理 reason code 等

- `_truncation_failure`: `hint=None`（原为 `hint=reason_code`）✅
- `_governed_failure_outcome`: `hint=None`（原为 `hint=policy_decision.reason_code`）✅
- `_accept_failure_outcome`: `hint=None`（原为 `hint=accept_rejected:...` 或 `hint=last_error_code`）✅
- `_awaiting_accept_failure_outcome`: `hint=None`（原为 `hint=accept_rejected:...` 或 `hint=last_error_code;diagnostic_refs=...`）✅
- `_tool_failed_outcome` 的其他调用点（unknown tool、callable exception、capsule build failed、process-backed failed/unsupported/malformed）均已 `hint=None` ✅
- Engine 投影响应: `dayu/engine/agent.py:444-445` 仅在 `result.hint is not None` 时投影 `hint` → `hint=None` 意味着 LLM 不再看到这些治理码 ✅
- 结论: **通过，四类治理 hint 泄漏均已消除。**

### last_error_code 和 diagnostic refs 未丢失

- `last_error_code` 在 `_accept_failure_outcome` 和 `_awaiting_accept_failure_outcome` 中通过 `_accept_timeout_message` 嵌入 `message`（格式: `"... (last_error_code=xxx)"`）✅
- `last_error_code` 在 `_accept_with_retry` 和 `_accept_awaiting_with_retry` 中仍流经 accept 状态机并持久化到 `ToolFactAcceptTimedOut` / `ToolAwaitingAcceptTimedOut` 合约字段 ✅
- `last_error_code` 在日志中保留（`dayu/host/tool_runtime.py:4177-4186`）✅
- Tool Trace diagnostic: `_accept_with_retry` 和 `_accept_awaiting_with_retry` 仍在 timeout/rejected 时发出 `ToolTraceDiagnosticRecord` ✅
- `failure_metadata.diagnostic_refs` 路径未被 S1 改动（plan 明确"Preserve existing ... failure_metadata.diagnostic_refs ... fields; do not add new payload fields"）✅
- 测试验证: `test_accept_timeout_bounded_retry_returns_governed_error` 断言 `"last_error_code=ack_lost" in record.outcome.result.message` ✅
- 测试验证: `test_awaiting_accept_timeout_returns_governed_error` 断言 `"last_error_code=accept_ack_lost" in record.outcome.result.message` ✅
- 测试验证: `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` 断言 `diagnostics.records[-1].reason_code == "accept_timeout"` ✅
- 结论: **通过，last_error_code 和 diagnostic ref 在 owner 诊断路径中完整保留。**

### Hidden hint helper/constants 已真实删除

- `_hint_with_diagnostic_refs(...)`: **已删除**，grep 全仓库无命中 ✅
- `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`: **已删除**，grep 全仓库无命中 ✅
- `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`: **已删除**，grep 全仓库无命中 ✅
- `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`: **已删除**，grep 全仓库无命中 ✅
- `accept_rejected:` 格式字符串: **已删除**，grep 全仓库无命中 ✅
- 残留常量 `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON` / `_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON`: 仅用作 `ToolTraceDiagnosticRecord.reason_code`（owner 诊断路径），非 hint 路径 ✅
- 结论: **通过，hidden hint 协议完全清除，无死协议残留。**

### Business-authored process-backed failed envelope hints 未被误删

- `_tool_outcome_from_process_envelope` 中 `ProcessToolFailedEnvelope` 分支: `hint=parsed.hint` — **保留业务 hint** ✅
- `test_toolruntime_executor.py:1834`: `assert record.outcome.result.hint == "retry with a narrower filing range"` — **此测试未修改且应继续通过**（走 `ProcessToolFailedEnvelope` 路径）✅
- `dayu/fins/tools/` 下的业务 hint（read/download/upload/preprocess tools）均通过工具自身构造 `ToolResultFailure`，不走 ToolRuntime synthetic 路径，未受影响 ✅
- 结论: **通过，业务 hint 路径完整保留。**

### 测试覆盖有意义行为而非仅弱化断言

- 合约测试: 新增 2 个运行时 invariant 测试，绕过静态类型 ✅
- ToolRuntime executor 测试: `test_accept_timeout_bounded_retry_returns_governed_error` 同时断言 `hint is None` + `"last_error_code=ack_lost" in message` + `diagnostics.records[-1].reason_code == "accept_timeout"` — 有意义的三向断言 ✅
- `test_awaiting_accept_timeout_returns_governed_error`: 断言 `hint is None` + `"last_error_code=accept_ack_lost" in message` ✅
- `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref`: 断言 `hint is None` + `last_error_code` in message + diagnostic record count ✅
- 截断测试: 仅将 `hint == "X"` 改为 `hint is None`，未补加 `error`/`message` 断言 — 见 S1-F3 ⚠️
- 重复治理测试: 更新 `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter` 中 owner outcome `hint is None` ✅
- 结论: **通过但有一个低严重度发现（S1-F3）。**

### README no-op 决策有效性

- `dayu/host/README.md` 当前不声明治理 reason code 会进入 `ToolResultFailure.hint`；S1 未改变 Host 架构边界或 ToolRuntime owner 定位 ✅
- `tests/README.md` 当前不声明测试分层变更；S1 未新增测试目录或层级 ✅
- 业务-authored process-backed hint 映射未改变，不触发 README 更新 ✅
- `dayu/fins/README.md`: 不在 S1 scope（属于 S3）✅
- 结论: **no-op 决策有效。**

## Open Questions

1. **`tests/tools/` 断裂测试由谁修复？** S1-F1 指出的三处断言断裂是否应在 S1 closeout 前修复，还是由 S2/S3 或独立 follow-up 处理？若 CI 当前不跑全量套件，可 deferred；若 CI 跑全量，则 blocking。
2. **`_truncation_failure` 的 `reason_code` 参数是否需要结构化保留？** 当前 `error` 字段固定为 `truncation_error`，所有截断子类共用同一错误码。是否有下游代码依赖 `result.hint` 中的 reason code 来区分截断子类？若没有，死参数可安全删除。rg 全量扫描未发现 `result.hint` 的截断 reason code 消费方（原有测试已改为 `hint is None`）。
3. **S1 scope 是否应扩大以覆盖 `tests/tools/` 中的取消 hint 断言？** 这取决于 CI 配置和项目对"S1 独立可 ship"的定义。

## Residual Risk

1. **`tests/tools/` 全量断裂未验证**: `tests/tools/test_doc_tools_provider.py` 和 `tests/tools/web/test_web_tools_provider.py` 中三处 `hint == "tool_runtime_cancelled"` 断言已知会断裂，但未在 S1 内验证/修复。若这些文件在全量 CI 中运行，S1 无法独立 merge。
2. **Coverage gap**: `dayu/host/tool_runtime.py` 在排除 process-backed 测试后达到 84%（controller 已验证），但 process-backed 路径的 hint 行为（如 `ProcessToolFailedEnvelope` 保留业务 hint）未在 coverage 命令下验证。
3. **未验证全量 Host/Engine 测试**: S1 仅运行了 5 个指定测试文件（151 passed），未运行 `tests/host/` 或 `tests/engine/` 下的其他测试。rg 扫描已确认 hidden-hint 协议无残留，但下游消费者的集成行为未验证。
4. **`_SIDE_EFFECT_IDEMPOTENCY_HINT` 常量命名误导**: 该常量名为 "HINT" 但实际用作 `ToolPolicyDecision.message`（经 `_governed_failure_outcome` 写入 `ToolResultFailure.message`）。非本次引入，S1 未改变其语义路径，但命名与用途不一致，后续维护者可能误解。非 S1 修复范围。
5. **`_truncation_failure` 死代码**: 函数签名中的 `reason_code` 参数和 7 个截断 reason 常量成为死代码（见 S1-F2）。不影响正确性，但降低代码可维护性。

## Conclusion

**Pass with findings (3 material findings, 0 blocking)**

S1 实现正确完成了其核心目标：
- `ToolResultSuccess.ok` / `ToolResultFailure.ok` 运行时 invariant 正确实施，测试真正绕过静态类型检查；
- ToolRuntime 四种 synthetic failure 路径（截断、治理、accept、awaiting-accept）不再向 LLM-facing `hint` 泄漏治理 reason code、`last_error_code`、`accept_rejected:` 字符串或 diagnostic refs；
- `last_error_code` 和 diagnostic refs 保留在 owner 诊断路径（`message`、`failure_metadata.diagnostic_refs`、Tool Trace、contract 字段）；
- Hidden hint helper 和格式常量完全删除，无残留；
- Business-authored process-backed failed envelope hints 完整保留。

三个 findings 为：
- **S1-F1（中）**: `tests/tools/` 三处取消 hint 断言未纳入 S1 scope，将导致全量 CI 断裂；
- **S1-F2（低）**: `_truncation_failure` 的 `reason_code` 参数成为死参数，7 个常量仅作为死参数实参；
- **S1-F3（低）**: 截断测试未按计划补加 `error`/`message` 断言，仅弱化 hint 断言。

S1-F1 需要在 merge 前处理（修复或确认 CI 不跑这些文件）；S1-F2 和 S1-F3 不阻塞 merge，但建议在 closeout 前清理。
