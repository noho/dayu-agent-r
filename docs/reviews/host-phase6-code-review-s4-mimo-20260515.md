# Code Review

## Scope

- Mode: current changes (P6-S4 workspace diff)
- Branch: `feat/host-phase-6-toolruntime`
- Base: `main` (commit `17bfb19` as HEAD, workspace unstaged changes)
- Output file: `docs/reviews/host-phase6-code-review-s4-mimo-20260515.md`
- Included scope: P6-S4 未提交 workspace diff，包含 `dayu/host/tool_runtime.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/test_toolruntime_truncation_fetch_more.py`、`tests/host/test_toolruntime_effective_bundle.py`、`tests/host/test_phase6_toolruntime_integration.py` 的修改与新增
- Excluded scope: P6-S1 到 P6-S3 已提交代码；Engine / Service / UI / Fins / Remote
- Parallel review coverage: 无

## Findings

未发现 blocking 实质性问题。

### 01-未修复-低-`limit` 参数行为缺少测试覆盖

- **入口/函数**: `TruncationManager.fetch_more` / `_fetch_more_value`
- **文件(行号)**: `dayu/host/tool_runtime.py:1160-1192`, `dayu/host/tool_runtime.py:3192-3222`
- **输入场景**: LLM 调用 `fetch_more(cursor, scope_token, limit=2)` 时，`limit` 参数会截断剩余内容
- **实际分支**: `_fetch_more_value` 对 `TextCharsRemainderRef` 执行 `remaining_text[:limit]`，对 `TextLinesRemainderRef` 执行 `remaining_lines[:limit]`，对 `ListItemsRemainderRef` 执行 `remaining_items[:limit]`，对 `BinaryBytesRemainderRef` 执行 `remaining_bytes[:limit]`
- **预期行为**: plan §7 testing matrix 要求 `cursor single-use, TTL, scope mismatch, token mismatch, missing cursor and digest mismatch return ordinary tool errors`，但 `limit` 参数作为 `FetchMoreRequest` 的显式契约字段也应有测试
- **实际行为**: `test_toolruntime_truncation_fetch_more.py` 中所有 `fetch_more` 测试均不传 `limit` 参数，`limit` 截断行为未被验证
- **直接证据**: `tests/host/test_toolruntime_truncation_fetch_more.py` 7 个测试均使用 `_fetch_more_call(tool_call_id, cursor, scope_token)` 构造请求，该 helper 不传 `limit`
- **影响**: `limit` 参数的截断逻辑（包括 `None` 全量返回、正整数截断、边界值 1）未被测试覆盖，若 `_fetch_more_value` 的 limit 分支出现回归不会被发现
- **建议改法和验证点**: 补充一个测试用例，验证 `fetch_more` 带 `limit=2` 时只返回剩余内容的前 2 项/行/字符
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-测试直接访问 `TruncationManager._cursors` 内部状态

- **入口/函数**: `test_fetch_more_rejects_scope_mismatch` / `test_fetch_more_rejects_remainder_digest_mismatch`
- **文件(行号)**: `tests/host/test_toolruntime_truncation_fetch_more.py:248-265`, `tests/host/test_toolruntime_truncation_fetch_more.py:267-291`
- **输入场景**: 测试需要构造 scope mismatch 和 remainder digest mismatch 的 cursor 状态
- **实际分支**: 测试通过 `manager._cursors[cursor] = replace(stored, run_id="other-run")` 和 `manager._cursors[cursor] = replace(stored, remaining_ref=TextCharsRemainderRef(remaining_text="tampered", digest=stored.remaining_ref.digest))` 直接修改内部字典
- **预期行为**: 测试应通过可控的构造路径（如不同 run_id 的 manager 实例）触发 scope mismatch
- **实际行为**: 测试绕过公共 API 直接修改 `_cursors` 字典，测试的是"内部状态被篡改后校验是否拦截"，而非"跨 scope 调用是否被拦截"
- **直接证据**: `test_toolruntime_truncation_fetch_more.py:255-256` 和 `test_toolruntime_truncation_fetch_more.py:276-282`
- **影响**: 测试与实现耦合度高，若 `_cursors` 内部存储重构（如改用 `_cursor_store`），测试会断裂；但当前行为本身正确
- **建议改法和验证点**: scope mismatch 测试可通过构造不同 `run_id` 的 `TruncationManager` 实例来触发；remainder digest mismatch 测试可通过外部篡改 cursor 数据后再调用 fetch_more 来触发，无需直接访问内部字典
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- 当前测试只覆盖 `TEXT_CHARS` 截断策略；`TEXT_LINES`、`LIST_ITEMS`、`BINARY_BYTES` 策略的截断与 `fetch_more` 补读行为未被独立测试。这些策略由 `_truncated_value_for_strategy` 分派，各策略的类型守卫（`isinstance(value, str)` / `isinstance(value, list)` / base64 解码）与边界条件（空字符串、空列表、非法 base64）未被覆盖。当前 slice 只要求 `text_chars` 策略有显式测试，其余策略属于同一实现路径的低风险扩展，但后续 slice 或维护者应注意补充。
- `FetchMoreToolCallable` 在 `_manager is None` 时返回 `_TRUNCATION_CURSOR_MISSING_REASON`，而非更精确的 `_TRUNCATION_INVALID_REQUEST_REASON`。这是有意的防御性设计（避免暴露内部状态），但若未来 `fetch_more` 需要区分"manager 未启用"与"cursor 不存在"，可能需要更细粒度的错误码。
- `TruncationManager._validate_cursor` 同时校验 `cursor.run_id` 与 `context.run_id` 是否等于 `self._run_id`，这是 defense-in-depth 设计。正常路径下 cursor 和 context 都来自同一个 ToolRuntime 实例，run_id 一定一致；但该双重校验防止了构造错误或测试注入场景下的 scope 泄漏。
