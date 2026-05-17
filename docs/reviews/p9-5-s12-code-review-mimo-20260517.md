# P9.5 S12 ToolRuntime Truncation / Duplicate Defensive Hardening Code Review

## Gate

- Work unit: P9.5 S12 ToolRuntime Truncation / Duplicate Defensive Hardening
- Review agent: AgentMiMo
- 审查目标：当前未提交 S12 diff
- 审查范围：`dayu/host/tool_runtime.py`、`tests/host/test_toolruntime_truncation_fetch_more.py`、`tests/host/test_toolruntime_duplicate_governance.py`、`tests/host/test_toolruntime_accept_barrier.py`、`dayu/host/README.md`、`tests/README.md`、`docs/reviews/p9-5-s12-toolruntime-truncation-duplicate-hardening-implementation-20260517.md`

## 审查方法

1. 逐行审查 diff 中新增/修改的生产代码与测试代码
2. 对照生产构造路径验证新校验不会误拒合法 candidate
3. 对照 `_duplicate_reason_code` / `_duplicate_message` 单一真源验证 reason/message 严格匹配
4. 对照 S12 plan 目标和边界验证实现是否越界

## Finding Summary

- Blocking findings: 0
- Non-blocking findings: 0
- Residual risks: 3

## 审查结论

### 1. 新校验是否会误拒合法 timeout/cancellation/plain governed_error

**结论：不会误拒。**

直接证据：

- timeout 构造路径 (`_runtime_timeout_policy_decision`, tool_runtime.py:4978-4982): `kind=GOVERNED_ERROR`, `reason_code=_TOOL_RUNTIME_TIMEOUT_REASON`, `message=f"tool execution timed out after {elapsed_seconds:.6f} seconds"`。
- cancellation 构造路径 (`_runtime_cancelled_policy_decision`, tool_runtime.py:4954-4968): `kind=GOVERNED_ERROR`, `reason_code=_TOOL_RUNTIME_CANCELLED_REASON`, `message` 可变（含可选 reason 附加文本）。
- 这两类 candidate 的 `reuse_prior_event_refs = ()`（tool_runtime.py:4458-4462，`duplicate_governed=False`）。
- `_validate_governed_error_candidate` (tool_runtime.py:3691-3709) 的检查序列：
  1. `kind in (ALLOW, REUSE)` → False → 不拒绝
  2. `kind is GOVERNED_ERROR` → True → 检查 `reuse_prior_event_refs` → 空 tuple 为 falsy → return
- `_validate_policy_decision_fields` (tool_runtime.py:3667-3688) 对非 ALLOW 决策要求 `reason_code is not None` and `message is not None`，不要求固定值。timeout/cancellation 的 reason_code 和 message 均非 None，通过。
- scope mismatch 路径 (tool_runtime.py:2360-2365) 同理：`kind=GOVERNED_ERROR`, `duplicate_decision.kind=ALLOW`, `reuse_prior_event_refs=()`，通过 `_validate_governed_error_candidate` 的 `kind is GOVERNED_ERROR` 分支。

### 2. 普通 completed/failed/cancelled fact 要求 allow policy 是否正确

**结论：正确。**

直接证据：

- `_tool_fact_kind` (tool_runtime.py:4657-4678) 映射逻辑：`policy_decision.kind is not ALLOW` → `GOVERNED_ERROR`；`ALLOW` + `ToolCompletedOutcome` → `COMPLETED`；`ALLOW` + `ToolFailedOutcome` → `FAILED`；`ALLOW` + `ToolCancelledOutcome` → `CANCELLED`。
- 生产构造路径中 COMPLETED/FAILED/CANCELLED 的 `policy_decision.kind` 必定是 ALLOW（由 `_tool_fact_kind` 保证）。
- 新增 `_validate_result_fact_policy` (tool_runtime.py:3742-3752) 断言 `kind is ALLOW`，与 `_tool_fact_kind` 的映射逻辑一致，属于构造期双重防御。
- timeout/cancellation 走 `_normalize_runtime_outcome` 覆盖 policy_decision 为 GOVERNED_ERROR 后，`_tool_fact_kind` 返回 `GOVERNED_ERROR`，不走 `_validate_result_fact_policy`。

### 3. reuse 和 duplicate governed 的 reason/message 严格匹配是否与生产构造函数一致

**结论：一致。**

直接证据：

- `_policy_decision_from_duplicate` (tool_runtime.py:4334-4348) 使用 `_duplicate_reason_code(decision.kind)` 和 `_duplicate_message(decision.kind)` 构造 policy_decision。
- `_validate_duplicate_governed_candidate` (tool_runtime.py:3712-3739) 使用相同的 `_duplicate_reason_code(decision)` 和 `_duplicate_message(decision)` 作为 expected 值。
- `_validate_reuse_candidate` (tool_runtime.py:3755-3780) 使用 `_duplicate_reason_code(DuplicateDecisionKind.REUSE)` 和 `_duplicate_message(DuplicateDecisionKind.REUSE)`。
- `_duplicate_reason_code` (tool_runtime.py:4351-4366) 和 `_duplicate_message` (tool_runtime.py:4369-4384) 是模块级私有函数，返回固定字符串，是 reason/message 的单一真源。
- accept_barrier 测试中 `_reuse_candidate` 的 message 从 `"reuse prior accepted result"` 修正为 `"reuse prior accepted tool result"` (test_toolruntime_accept_barrier.py:548)，与 `_duplicate_message(REUSE)` 返回值一致。

### 4. truncation 的 text_lines/list_items/binary_bytes/used cursor/invalid limit 测试是否直接覆盖真实路径

**结论：直接覆盖。**

直接证据：

- `test_text_lines_truncation_fetch_more_returns_remaining_lines` (test_toolruntime_truncation_fetch_more.py): 构造 TEXT_LINES 策略、max_lines=2、输入含换行文本，断言首次 outcome 只含前 2 行，fetch_more 返回剩余行。
- `test_list_items_truncation_fetch_more_returns_remaining_items`: 构造 LIST_ITEMS 策略、max_items=1、输入为异构 list，断言首次 outcome 只含首项，fetch_more 返回剩余项。
- `test_binary_bytes_truncation_fetch_more_returns_base64_remainder`: 构造 BINARY_BYTES 策略、max_bytes=2、输入 base64 字符串，断言按字节截断后 base64 编码正确，fetch_more limit=2 返回下一段。
- `test_fetch_more_rejects_used_cursor`: 通过 `replace(stored, used_at=stored.created_at)` 模拟 cursor 已使用，断言返回 `cursor_already_used`。
- `test_fetch_more_rejects_invalid_limit`: limit=0，断言返回 `invalid_fetch_more_request`。
- 所有测试通过 `DefaultToolRuntimeFactory(...).create_tool_runtime(...)` 真实构造 ToolRuntime，走真实 `TruncationManager` / `EffectiveToolBundleBuilder` / `ToolExecutor` 路径。

### 5. duplicate governed candidate validation tests 是否覆盖关键防御矩阵

**结论：覆盖。**

直接证据：

- `test_governed_duplicate_candidate_validation_rejects_missing_prior_refs`: 通过 `_governed_duplicate_candidate(HINT)` 构造真实 duplicate governed candidate，再 `replace(reuse_prior_event_refs=())`，断言 `requires prior event refs`。
- `test_governed_duplicate_candidate_validation_rejects_policy_mismatch`: HINT candidate 换成 HARD_STOP policy，断言 `policy kind must match decision`。
- `test_governed_duplicate_candidate_validation_rejects_reason_mismatch`: HARD_STOP candidate 换成 hint reason，断言 `reason must match decision`。
- `test_governed_duplicate_candidate_validation_rejects_message_mismatch`: REQUIRE_JUSTIFICATION candidate 换成错误 message，断言 `message must match decision`。
- `test_governed_error_candidate_validation_rejects_allow_policy`: HINT candidate 换成 ALLOW policy + 无 duplicate_decision，断言 `requires governed policy decision`。
- `_governed_duplicate_candidate` helper 通过真实 ToolRuntime 执行两次相同调用触发 duplicate governance，返回第二次的 governed candidate，不走 mock。

### 6. README / tests README 是否只写当前事实

**结论：只写当前事实。**

直接证据：

- `dayu/host/README.md` 变更：
  - 补充 "截断策略覆盖 `text_chars`、`text_lines`、`list_items` 与 `binary_bytes`" — 与 `ToolTruncationStrategy` 枚举一致。
  - 补充 "cursor 校验覆盖 ... invalid limit 与 remainder digest mismatch" — 与新增测试一致。
  - 补充 "duplicate governed candidate 会校验 policy kind、prior refs、reason 与 message 均匹配当前 duplicate decision" — 与新增校验逻辑一致。
- `tests/README.md` 变更：
  - 在覆盖列表中补充 "`text_chars` / `text_lines` / `list_items` / `binary_bytes` truncation"、"invalid limit"、"duplicate governed candidate 字段一致性" — 与新增测试名一致。
  - 未添加未来设计或承诺。

### 7. TruncationManager 初始化成本

**结论：无 Phase 15 问题。**

直接证据：

- `DefaultToolRuntimeFactory.create_tool_runtime` (tool_runtime.py:2900-2909) 新增注释记录：构造期只保存 identity、effective bundle 截断声明只读视图和空 cursor dict；不打开文件、DB、后台任务或 durable cursor table。
- 这是 run-scoped 轻量对象，当前无生产规模修复需求。

## 残余风险

### R1: `_validate_governed_error_candidate` 未显式防御 policy kind=HINT/REQUIRE_JUSTIFICATION/HARD_STOP + duplicate_decision=None 的组合

- 入口：`_validate_governed_error_candidate` (tool_runtime.py:3691-3709)
- 场景：若通过 `dataclasses.replace` 构造 policy_decision.kind=HINT 但 duplicate_decision=None 的 candidate
- 实际行为：`_validate_governed_error_candidate` 跳过 `kind is GOVERNED_ERROR` 分支，进入 `_validate_duplicate_governed_candidate`，命中 `decision is None` 检查，抛出 `duplicate governed error requires duplicate decision`
- 预期行为：应抛出更精确的错误（如 "governed policy without duplicate decision"）
- 影响：仅影响错误消息精确度，不影响正确性；生产路径通过 `_policy_decision_from_duplicate` 保证 policy kind 与 duplicate decision 同源
- 严重程度：informational

### R2: duplicate reason_code / message 字符串单一真源依赖模块级私有函数

- 入口：`_duplicate_reason_code` / `_duplicate_message` (tool_runtime.py:4351-4384)
- 场景：若未来修改这两个函数的返回值但未同步更新 `_validate_duplicate_governed_candidate` / `_validate_reuse_candidate` 的预期
- 实际行为：当前两个函数是唯一的构造和校验真源，不会不同步
- 影响：若未来重构导致构造和校验使用不同函数，会产生误拒
- 严重程度：low（当前架构已通过单一函数避免此风险）

### R3: truncation 策略测试为集成级，无 TruncationManager 单元级测试

- 入口：`test_toolruntime_truncation_fetch_more.py`
- 场景：text_lines / list_items / binary_bytes 测试通过完整 ToolRuntime 路径验证，不直接测试 TruncationManager 内部方法
- 实际行为：测试覆盖了真实构造路径和端到端行为，属于功能正确性验证
- 影响：若 TruncationManager 内部有未被端到端路径触发的边界，可能未被发现
- 严重程度：informational（当前端到端测试已覆盖所有已知截断策略的首次截断和 fetch_more 补读路径）

## 边界合规检查

- [x] 未引入 durable cursor table
- [x] 未引入 durable duplicate ledger
- [x] 未引入 Tool Trace projection
- [x] 未变更 duplicate policy 默认值
- [x] 未引入 Host/Engine 特化 fetch_more 分支
- [x] 未变更 public API / error taxonomy
- [x] 未引入 business-specific rules
- [x] 未引入兼容性 wrapper / re-export / lazy import seam

## 建议验证点

无需额外验证。实现 artifact 报告的验证结果（60 passed、0 pyright errors、git diff --check 通过）已足够。

## 结论

**建议通过。** 无 blocking finding。S12 实现正确收紧了 `ToolFactAcceptCandidate` 构造期校验，补充了 truncation / duplicate focused tests，所有新校验与生产构造路径一致，README 更新只反映当前事实。3 项残余风险均为 informational / low 级别，不影响正确性或稳定性。
