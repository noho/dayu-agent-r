# P9.5 S12 ToolRuntime Truncation / Duplicate Hardening Controller Adjudication

日期：2026-05-17
总控 Agent：AgentController

## 审查对象

- Implementation artifact：`docs/reviews/p9-5-s12-toolruntime-truncation-duplicate-hardening-implementation-20260517.md`
- AgentMiMo review：`docs/reviews/p9-5-s12-code-review-mimo-20260517.md`
- AgentDS review：`docs/reviews/p9-5-s12-code-review-ds-20260517.md`
- 当前 S12 diff：
  - `dayu/host/tool_runtime.py`
  - `tests/host/test_toolruntime_truncation_fetch_more.py`
  - `tests/host/test_toolruntime_duplicate_governance.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `dayu/host/README.md`
  - `tests/README.md`

## 设计真源裁决

S12 动机成立。当前代码已有 run-scoped truncation / `fetch_more`、run-local duplicate governance 和 accept barrier，但 focused tests 对 `text_lines`、`list_items`、`binary_bytes`、used cursor、invalid limit 与 duplicate governed candidate 字段组合覆盖不足；`ToolFactAcceptCandidate` 对 `GOVERNED_ERROR` / duplicate governed outcome 的构造期防御也偏宽。

当前实现只收紧构造期不变量和补充 targeted tests，未引入 durable cursor table、durable duplicate ledger、Tool Trace projection、policy default change、Host / Engine special `fetch_more` branch、public API / error taxonomy change 或 business-specific rules。`TruncationManager` 初始化成本被直接核对为 run-scoped 轻量对象，不需要 Phase 15 reassign。

## Review Finding 裁决

| 来源 | Finding / Risk | 裁决 | 理由 |
|---|---|---|---|
| AgentMiMo | R1 `policy_decision.kind` 为 duplicate governed 类型但 `duplicate_decision=None` 时错误消息不够精确 | rejected-with-reason | 当前仍 fail closed，且生产路径通过 `_policy_decision_from_duplicate` 保证两者同源。错误消息精度不是 S12 blocker。 |
| AgentMiMo | R2 duplicate reason / message 依赖模块级私有函数单一真源 | accepted-as-non-blocking | 这是正确设计：构造与校验共用 `_duplicate_reason_code` / `_duplicate_message`。未来若拆分，S16 可复核。 |
| AgentMiMo | R3 truncation 策略为集成级测试，无 `TruncationManager` 单元测试 | rejected-with-reason | S12 要求真实路径 focused tests；当前测试通过 `DefaultToolRuntimeFactory` / `TruncationManager` / `FetchMoreToolCallable` 端到端覆盖，更符合防回归目标。 |
| AgentDS | N1 `ToolPolicyDecisionKind` 与 `DuplicateDecisionKind` 通过 `.value` 隐式耦合 | accepted-as-non-blocking | 两个 enum 同模块同 owner，当前值集合一致；若未来漂移会在构造期 fail closed。S16 Contract Ownership audit 可复核是否需要显式约束。 |

## 验证

Controller 复跑验证：

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py`：60 passed。
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_*.py tests/host/test_phase6_toolruntime_integration.py`：67 passed。
- `source .venv/bin/activate && pytest tests/host`：544 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors / 0 warnings / 0 informations。
- `source .venv/bin/activate && python -m pyright dayu tests`：0 errors / 0 warnings / 0 informations。
- `git diff --check`：clean。

## 文档裁决

本 slice 修改 `dayu/host/` 与 `tests/`，README 更新符合触发规则。`dayu/host/README.md` 只同步当前已实现的 truncation 策略覆盖、cursor 校验和 duplicate governed candidate 字段一致性；`tests/README.md` 只同步测试覆盖事实。未写未来设计、未扩大文档职责。

## 结论

P9.5 S12 code review gate passed。两份独立 review 均为 0 blocking finding；controller 不接受任何需要 S12 fix pass 的 finding。S12 可进入 accepted slice commit。

剩余风险均有 owner：

- truncation cursor 仍是 memory / run-scoped / ToolRuntime-local capability，不支持 crash / restart / cross-run recovery；后续如需持久化必须进入对应 owner。
- duplicate registry 仍是同进程 run-local memory，不提供 durable duplicate ledger；这是当前设计边界。
- enum value 耦合可在 S16 Contract Ownership audit 中复核。
