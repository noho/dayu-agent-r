# Code Review

## Scope

- Mode: PR
- PR: #106 — Host duplicate governance attempt scope
- Author: noho
- Head branch: fix/wu-tool-01-attempt-scoped-duplicate-governance (0c1640d)
- Base branch: main (07cf34d)
- URL: https://github.com/noho/dayu-agent-r/pull/106
- Output file: docs/reviews/pr-106-agentmimo-duplicate-governance-config-review.md
- Included scope: PR diff 全量，重点审查 dayu/config/execution_profiles.json、dayu/runtime/config_loader.py、dayu/service/host_assembly.py、dayu/host/tool_duplicate_governance.py、dayu/host/tool_runtime.py、dayu/host/tooling.py、dayu/host/dispatch.py、dayu/host/tool_trace.py、utils/smoke_host_public_diagnostics.py、tests/、README
- Excluded scope: docs/reviews/ 下的 review artifacts（非生产代码）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为低严重度 maintainability 观察，不阻断 merge：

## Controller Follow-up Resolution

- Finding 1 已处理：`DuplicateGovernanceMessages.message_for` 现在显式处理 `DuplicateDecisionKind.DURABLE_MISSING`，未知决策类型会 fail fast。
- Finding 2 已处理：`_duplicate_decision_from_config` 现在包装 enum 映射失败并输出 `unsupported duplicate governance decision: ...` 上下文。
- 补充验证：`pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_tooling_options.py tests/runtime/test_smoke_host_public_multiturn_assembly.py` 通过，`pyright` 0 errors。

### 1-未修复-低-DuplicateGovernanceMessages.message_for 对 DURABLE_MISSING 使用隐式 else 分支

- **入口/函数**: `DuplicateGovernanceMessages.message_for` (dayu/host/tool_duplicate_governance.py:119-136)
- **文件(行号)**: dayu/host/tool_duplicate_governance.py:119-136
- **输入场景**: `kind` 为 `DuplicateDecisionKind.DURABLE_MISSING` 时
- **实际分支**: 走到 `else` 分支，返回 `self.prior_accept_missing`
- **预期行为**: 每个 `DuplicateDecisionKind` 枚举值应有显式映射
- **实际行为**: `ALLOW`/`REUSE`/`HINT`/`REQUIRE_JUSTIFICATION`/`HARD_STOP` 有显式 `if` 分支；`DURABLE_MISSING` 通过 `else` fallthrough 返回 `prior_accept_missing`
- **直接证据**: tool_duplicate_governance.py:126-136 — 无 `if kind is DuplicateDecisionKind.DURABLE_MISSING` 分支
- **影响**: 当前语义正确（durable missing 确实意味着 prior accept missing）；若未来枚举新增值，会静默落入 `prior_accept_missing` 而非 fail fast
- **建议改法和验证点**: 为 `DURABLE_MISSING` 添加显式 `if` 分支返回 `self.prior_accept_missing`；可选在末尾加 `raise ValueError` 防御未知枚举值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-Host 层 decision 枚举到 config 字符串的映射依赖上游 allowlist 同步

- **入口/函数**: `_duplicate_decision_from_config` (dayu/service/host_assembly.py:1053-1063)
- **文件(行号)**: dayu/service/host_assembly.py:1053-1063
- **输入场景**: execution profile 中 `default_duplicate_decision` 或 `decisions_by_tool_name` 的值
- **实际分支**: 直接调用 `DuplicateDecisionKind(value)` 构造枚举
- **预期行为**: 枚举构造失败时应在 assembly 期抛出明确错误
- **实际行为**: `DuplicateDecisionKind(value)` 在 value 不在枚举内时抛出 `ValueError`，错误消息为枚举默认格式，不如 config 层的 `ConfigFieldError` 清晰
- **直接证据**: host_assembly.py:1063 — `return DuplicateDecisionKind(value)` 无额外上下文包装
- **影响**: 当前安全，因为 config 层 `_TOOL_DUPLICATE_GOVERNANCE_DECISIONS` allowlist 与 `DuplicateDecisionKind` 枚举值完全一致。若未来两者不同步，会在 assembly 期而非 config load 期报错，错误上下文较弱
- **建议改法和验证点**: 可选在 `_duplicate_decision_from_config` 中捕获 `ValueError` 并包装为更清晰的 assembly 错误消息；或添加断言确保两处 allowlist 一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- 测试 helper `_AcceptingPort` 不调用 `_validate_duplicate_fields`，仅生产 `DefaultHostToolFactAcceptPort` 执行验证。当前测试通过 accept barrier 专项测试覆盖了验证逻辑，但若未来 `_validate_duplicate_fields` 新增约束，test helper 不会捕获回归。
- `DURABLE_MISSING` 是新增枚举值，当前 `message_for` 的 else fallthrough 行为正确但隐式。若枚举继续扩展，需同步更新 `message_for`。
- smoke diagnostics (`utils/smoke_host_public_diagnostics.py`) 打印 policy 摘要但不校验结果正确性，仅用于人工观察。
