# WU-TOOL-01 Slice 1 Code Review Controller Adjudication

## 结论

Slice 1 核心 attempt-scoped duplicate governance 实现方向正确，目标测试和 pyright 均通过，但当前不能进入 re-review/pass。基于 approved plan、`docs/host/design.md` 和 AGENTS.md 的“禁止兼容性 re-export / wrapper / facade”约束，`tool_runtime.py` 中残留的 duplicate governance re-export、Run-scoped registry facade 和 `DuplicateGovernancePort` 归属问题必须先修复。

下一步进入 code fix。为彻底删除 run-scoped compatibility surface，本次 fix 允许最小范围扩展到 `dayu/host/dispatch.py` 和 `tests/host/test_dispatch_scheduler.py`，因为旧 registry 仍被 dispatch 引用；保留 facade 等待 Slice 2 不符合项目编码硬约束。

## Review Artifacts

- MiMo: `docs/reviews/wu-tool-01-code-review-slice1-mimo-20260601.md`
- DS: `docs/reviews/wu-tool-01-code-review-slice1-ds-20260601.md`
- Implementation: `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`

## Accepted Findings

### CR1 accepted: `tool_runtime.py.__all__` re-export duplicate governance typed contracts

来源：MiMo finding 1，DS M2。

裁决：accepted，blocking。

理由：approved plan 明确要求 callers 从 `dayu.host.tool_duplicate_governance` 导入 typed contracts；`tool_runtime.py.__all__` 继续导出这些类型是兼容性 re-export。基于项目编码约束，这是当前 slice 必须修复的问题。

Fix 要求：

- 从 `tool_runtime.py.__all__` 删除 `DuplicateAcceptedEntry`、`DuplicateDecision`、`DuplicateDecisionKind`、`DuplicateDurableMissingReason`、`DuplicateGovernanceMessages`、`DuplicateGovernancePolicy`、`DuplicateGovernanceRequest`、`DuplicateGovernanceScope`、`InMemoryAttemptDuplicateGovernance`。
- 若 `tool_runtime.py` 内部仍需使用这些类型，可以保留普通 imports；不得作为 public compatibility path 暴露。

### CR2 accepted: Run-scoped registry compatibility facade 未删除

来源：MiMo finding 2，DS M1。

裁决：accepted，blocking。

理由：当前 `InMemoryRunScopedDuplicateGovernanceRegistry` 已经不再表达真实 run-scoped 语义，只是为了让 dispatch 旧装配路径继续编译的 facade。AGENTS.md 禁止此类兼容 wrapper/facade，approved plan 也要求删除旧 run-scoped symbol。虽然原 Slice 1 handoff 禁止编辑 `dispatch.py`，但该限制与更高优先级的编码硬约束冲突；本次 fix 必须最小扩展到 dispatch wiring。

Fix 要求：

- 删除 `RunScopedDuplicateGovernanceRegistry` Protocol。
- 删除 `InMemoryRunScopedDuplicateGovernanceRegistry` class。
- 删除 `ToolRuntimeBuildRequest.duplicate_governance_registry` 字段和 docstring。
- 更新 `dayu/host/dispatch.py`，移除 registry import、scheduler field、clear calls、build request argument。
- 更新 `tests/host/test_dispatch_scheduler.py`，删除对 `_duplicate_governance_registry.active_run_count()` 等私有 registry 生命周期断言；如需保留覆盖，改成与当前 slice/plan 一致的行为断言或移至后续 slice 明确实现。

### CR3 accepted: `DuplicateGovernancePort` 应迁移到 typed contract module

来源：MiMo finding 3。

裁决：accepted，blocking。

理由：`DuplicateGovernancePort` 依赖的 request / decision / entry / durable missing 类型均已迁移到 `dayu.host.tool_duplicate_governance`。继续把 port 留在 `tool_runtime.py` 会让 contract 与实现模块耦合，削弱 Slice 1 的 typed contract module 边界。

Fix 要求：

- 将 `DuplicateGovernancePort` Protocol 移入 `dayu/host/tool_duplicate_governance.py`。
- `tool_runtime.py` 从 `dayu.host.tool_duplicate_governance` 导入该 Protocol 供内部类型标注使用。
- 不在 `tool_runtime.py.__all__` re-export。

### CR4 accepted: owner cancellation 并发测试缺口

来源：MiMo non-blocking finding 4，DS L1。

裁决：accepted，must-fix in current code fix。

理由：approved plan 和 plan fix 已明确 owner cancel / exception / rejection / timeout 都应让 waiter 得到 durable-missing decision。当前测试覆盖 exception/rejected/timeout，但缺少 cancellation token 并发路径。该路径是 in-flight correctness 的同类失败分支，测试成本低，应当前补齐。

Fix 要求：

- 在 `tests/host/test_toolruntime_duplicate_governance.py` 增加可控 cancellation token。
- 添加 owner cancellation 并发测试，断言 waiter 得到 `duplicate_prior_accept_missing`，不执行第二次真实工具调用，后续 fresh caller 可重新成为 owner。

### CR5 accepted: timeout durable-missing 测试断言过弱

来源：DS L2。

裁决：accepted，must-fix in current code fix。

理由：timeout 与 rejected / exception 同属 owner durable-missing 分支，当前只断言 call count，覆盖不够。需要与 rejected 测试保持等价断言，避免假阳性。

Fix 要求：

- timeout 测试断言 owner/waiter outcome 类型。
- 断言 waiter hint 为 `duplicate_prior_accept_missing`。
- 断言后续第三次同 key 调用可 fresh allow 并再次执行。

### CR6 accepted: `_duplicate_message()` fallback 不应脱离 configured policy

来源：MiMo non-blocking finding 5，DS M4。

裁决：accepted，must-fix in current code fix。

理由：虽然当前主路径会携带 configured message，但 fallback 创建默认 `DuplicateGovernanceMessages()` 与“提示可配置”目标相悖。最佳实践是删除 fallback 或让候选/decision message 成为必填治理字段，不保留默认消息旁路。

Fix 要求：

- 删除 `_duplicate_message()` fallback，或改成不可能绕过 configured message 的显式校验。
- 更新 validation，使 duplicate governed/reuse candidate 缺少 `duplicate_decision_message` 时 fail fast，而不是回退默认 message。
- 保持现有 configured/default policy 路径通过 `DuplicateGovernancePolicy.messages` 生成 message。

## Deferred / Rejected Findings

### DS M3 awaiting path 与 duplicate in-flight 交互

裁决：needs-more-evidence / deferred-with-owner。

理由：review 指出的是 awaiting 工具与同 Attempt 并发 duplicate 的窄边界。当前实现对 awaiting owner 释放 waiter 为 durable-missing，是 fail-closed 行为，不会让 LLM 消费未 accepted 工具事实，也不引入跨 Attempt reuse。现有 approved Slice 1 不包含 awaiting fanout 语义设计；贸然在本 fix 中新增 awaiting duplicate terminal state 会扩大 scope 到 wait/awaiting 语义。记录为后续 WU-TOOL awaiting hardening 候选；若后续 Slice 2/3 或 aggregate review 发现可复现 correctness 失败，再升级。

### DS L3 tool_trace.py 未携带 duplicate_scope

裁决：deferred-with-owner，owner 为 approved plan Slice 3。

理由：approved plan 明确 Slice 3 负责 `tool_trace.py` 的 `duplicate_scope` 投影；当前 Slice 1 已在 `TOOL_CALL_GOVERNED` payload 层写入 scope。该项不阻塞 Slice 1 fix。

## Required Validation After Fix

```bash
source .venv/bin/activate
python -m pytest tests/host/test_toolruntime_duplicate_governance.py
python -m pytest tests/host/test_dispatch_scheduler.py
pyright
```

如果 `test_dispatch_scheduler.py` 受影响范围过大，fix artifact 必须说明具体失败和 stop condition，不得通过恢复 compatibility facade 绕过。
