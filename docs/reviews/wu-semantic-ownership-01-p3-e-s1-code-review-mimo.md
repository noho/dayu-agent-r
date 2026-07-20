# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: unstaged changes (working tree diff)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-mimo.md`
- Included scope:
  - `dayu/contracts/tool_result.py`
  - `dayu/host/tool_runtime.py`
  - `tests/contracts/test_tool_result_envelope.py`
  - `tests/host/test_toolruntime_executor.py`
  - `tests/host/test_toolruntime_truncation_fetch_more.py`
  - `tests/host/test_toolruntime_duplicate_governance.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `docs/host/issues-implementation-control.md` (gate bookkeeping only)
- Excluded scope: unrelated untracked `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`, S2/S3 files
- Parallel review coverage: 无

## Findings

### 1-未修复-中-_truncation_failure 死参数 reason_code 导致截断原因码丢失

- **入口/函数**: `_truncation_failure(reason_code, message)` at `dayu/host/tool_runtime.py:7462`
- **文件(行号)**: `dayu/host/tool_runtime.py:7462-7474`
- **输入场景**: 所有截断 / fetch_more 失败路径（missing cursor、scope mismatch、token mismatch、expired cursor、used cursor、remainder digest mismatch、invalid request、unsupported target）
- **实际分支**: `_truncation_failure` 接收 `reason_code` 参数但完全忽略；`hint=None`、`error` 固定为 `_TRUNCATION_ERROR_CODE = "truncation_error"`
- **预期行为**: 按 S1 计划，`reason_code` 不应进入 `hint`，但 `error` 或 `message` 应保留可区分的截断原因语义，或 `reason_code` 参数应从签名中移除以避免误导
- **实际行为**: 8 个截断原因常量（`_TRUNCATION_CURSOR_MISSING_REASON` 等）仍被定义、被传参，但对 failure outcome 无任何效果。`error` 字段始终为泛化 `"truncation_error"`，`message` 由调用方提供但不包含机器可解析的原因码。LLM 和下游消费者无法从 failure outcome 区分不同截断失败类型
- **直接证据**:
  - `dayu/host/tool_runtime.py:7462-7474`: `_truncation_failure` 签名包含 `reason_code` 但函数体只用 `error=_TRUNCATION_ERROR_CODE, message=message, hint=None`
  - `dayu/host/tool_runtime.py:2088-2091`: 调用 `_truncation_failure(_TRUNCATION_CURSOR_MISSING_REASON, "truncation cursor is missing...")` — reason_code 被丢弃
  - `dayu/host/tool_runtime.py:2197-2200`: 调用 `_truncation_failure(_TRUNCATION_SCOPE_MISMATCH_REASON, "truncation cursor does not belong to...")` — 同上
  - 所有 12 处调用点均传入不同 reason_code 但 outcome 无法区分
- **影响**: 维护误导 + 语义降级。开发者看到传参会误认为 reason_code 生效；LLM 收到的 `error` 和 `message` 丢失了截断失败的具体分类信息，降低了可恢复性
- **建议改法和验证点**:
  - 方案 A（推荐）: 从 `_truncation_failure` 签名移除 `reason_code` 参数，更新所有调用点，删除 8 个截断原因常量（若无其它引用）。添加 source scan 确认常量无其它用途
  - 方案 B: 若截断原因码需要对 LLM 可见，将 reason_code 编码进 `message`（如 `_accept_timeout_message` 的做法），保持 `hint=None`
  - 验证: 更新后运行 `pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_executor.py -q`，source scan 确认无残留引用
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-截断相关测试断言弱化为仅检查 hint is None

- **入口/函数**: `tests/host/test_toolruntime_truncation_fetch_more.py` 中 7 个测试
- **文件(行号)**: `tests/host/test_toolruntime_truncation_fetch_more.py:234, 380, 396, 415, 431, 447, 469, 489, 515`
- **输入场景**: fetch_more 各种失败条件
- **实际分支**: 测试从 `assert record.outcome.result.hint == "missing_cursor"` 改为 `assert record.outcome.result.hint is None`
- **预期行为**: 测试应证明截断失败的关键语义信息（原因分类）在 `hint` 清理后仍通过 `error`、`message` 或其它可观测路径保留
- **实际行为**: 测试只断言 `hint is None`，不再验证任何截断原因信息的保留。如果 `message` 或 `error` 被意外改为空或泛化值，测试不会捕获
- **直接证据**: `test_fetch_more_missing_cursor_returns_ordinary_tool_error` 旧断言 `hint == "missing_cursor"` → 新断言 `hint is None`，无其它原因码断言
- **影响**: 测试回归检测能力降低。若未来有人误改 message 内容或移除错误码，测试不会发现
- **建议改法和验证点**: 至少为每个截断失败类型添加 `assert "cursor" in record.outcome.result.message` 或类似语义断言，证明 message 仍携带可区分信息。或接受当前弱化并记录为已知测试债务
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-accept_rejected 路径的 rejection reason 保留缺少显式测试证明

- **入口/函数**: `test_accept_rejected_does_not_expose_raw_fake_result` at `tests/host/test_toolruntime_executor.py:1424`
- **文件(行号)**: `tests/host/test_toolruntime_executor.py:1424-1428`
- **输入场景**: accept rejected（idempotency conflict）
- **实际分支**: 测试断言 `error == "tool_accept_rejected"`, `hint is None`, `message` 不含 raw fake result
- **预期行为**: 按 S1 计划，accept rejection 的 reason code 应保留在 `message` 或 owner diagnostics 中；测试应证明这一点
- **实际行为**: 测试不验证 rejection reason（`idempotency_conflict`）是否出现在 `message` 或 diagnostics 中。`_accept_failure_outcome` 正确使用 `result.message`，但测试未覆盖
- **直接证据**: `_accept_failure_outcome` line 7505 使用 `message=result.message`，但测试不检查 message 内容是否含 rejection reason
- **影响**: 若 `ToolFactRejectedAck.message` 未来为空或不含 reason，测试不会发现
- **建议改法和验证点**: 添加 `assert "idempotency" in record.outcome.result.message` 或 assert diagnostics record 包含 `accept_rejected` reason code
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。所有 finding 基于直接代码证据，不阻碍 confident judgment。

## Residual Risk

- Coverage residual: pytest-cov 与 process-backed spawn 测试组合在当前环境失败，`tool_runtime.py` 单文件 coverage 84%（排除 process-backed cases），`tool_result.py` 100%。controller validation 已接受此限制。
- S2/S3 未实施，不在本 review 范围。
- `_TRUNCATION_CURSOR_MISSING_REASON` 等 8 个常量目前无其它生产引用（仅作为 `_truncation_failure` 的死参数传入），但需 source scan 确认后方可删除。

## Conclusion

**pass-with-findings**

三个 finding 均为 Low-Medium 严重程度，不阻塞 merge。Finding 1（`_truncation_failure` 死参数）是最值得修复的：它导致 8 个截断原因常量成为空传参，增加了维护误导风险。Finding 2 和 3 是测试质量问题，可作为 follow-up 处理。

核心目标已达成：
- `ToolResultSuccess.ok` / `ToolResultFailure.ok` runtime invariant 正确执行
- ToolRuntime 不再通过 `hint` 泄露治理 reason code、accept rejection reason、diagnostic refs
- `last_error_code` 在 accept timeout 路径正确保留在 `message` 中
- hidden hint helper/constants 已完全删除
- 业务-authored process-backed failed envelope hints（Fins tools）未受影响
- pyright 通过，测试通过
