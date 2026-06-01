# WU-TOOL-01 Plan Re-Review

## 审查角色与真源

- 审查角色：plan re-review specialist
- Plan target：`docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Plan fix artifact：`docs/reviews/wu-tool-01-plan-fix-codex-20260601.md`
- Controller adjudication：`docs/reviews/wu-tool-01-plan-review-controller-adjudication-20260601.md`
- 前序 review artifacts：
  - MiMo: `docs/reviews/wu-tool-01-plan-review-mimo-20260601.md`
  - DS: `docs/reviews/wu-tool-01-plan-review-ds-20260601.md`

## 结论

所有 ADJ-001 至 ADJ-007 已在 plan 中充分修复。剩余 blocking findings: **0**。

## 逐项复核

### ADJ-001 — in-flight 并发协调契约不完整 — FIXED

Controller 要求（4 项）| Plan 修复证据 | 判定
---|---|---
port 改为 async，明确调用方迁移 | §6: `DuplicateGovernancePort` 从 sync Protocol 改为 async Protocol，列出 `async def decide_duplicate()` / `record_accepted()` / `record_durable_missing()`；"all ToolRuntime callers must `await` the port methods" | 满足
owner cancel/exception/accept rejection/accept timeout 时 waiter 返回 governed durable-missing decision，不传播 owner 取消 | §7.6: "Waiters observing `durable_missing` return a governed durable-missing decision … they must not receive the owner `CancelledError` / tool exception / accept exception and must not start a second real tool call in the same in-flight window" | 满足
in-flight record 状态机、notify 时机、claim 释放时机、后续新 caller 行为 | §7.6 完整定义：owner_running → accepted/durable_missing terminal states；notify 发生在 terminal status 写入后、map entry 释放前或同时；waiter 持有 typed in-flight record reference 防止 race；map entry 释放后新 caller 获得 fresh ALLOW 成为新 owner | 满足
不在 condition lock 内执行 tool callable 或 Host accept | §7.7: "Tool callable execution and Host accept must never run while holding the duplicate governance lock or condition lock" | 满足

补充验证：plan §8 Slice 1 明确 `_execute_one()` 的 owner cleanup 在 `finally` 路径调用 `record_durable_missing()`，覆盖 cancel / tool exception / accept rejection / accept timeout 四种场景。

### ADJ-002 — in-flight 测试可构造性不足 — FIXED

Controller 要求（3 项）| Plan 修复证据 | 判定
---|---|---
可控 fake accept port 构造 accepted/rejected/timed out | §8 Slice 1: "Add a controllable fake accept port with accepted, rejected, and timed-out modes; do not depend on durable store timing to force accept outcomes" | 满足
slow tool / asyncio event 控制并发时序 | §8 Slice 1: "Add true concurrent same Attempt tests with a slow `_CountingTool`, `asyncio.Event`, and two `asyncio.create_task(...)` calls … Use events to ensure owner claims before waiter starts, waiter is blocked while owner runs" | 满足
断言 waiter 不执行第二次真实调用 + 后续新 caller fresh allow | §8 Slice 1: 对 rejected/timed-out 路径断言 "tool call count remains 1 inside the same in-flight window"；"After each owner failure window, issue a later third caller … assert it receives fresh `ALLOW` and executes the real tool as a new owner" | 满足

### ADJ-003 — typed duplicate governance module 收敛为明确方案 — FIXED

Controller 要求（3 项）| Plan 修复证据 | 判定
---|---|---
`tool_duplicate_governance.py` 改为必选 | §5: "新增必选模块：`dayu/host/tool_duplicate_governance.py`"；§6: "Add required Host-layer neutral typed module" | 满足
只承载 typed contracts，不含 dispatch/accept-barrier/engine | §6: "must carry duplicate governance typed contracts only; it must not contain dispatch, scheduler, accept barrier, tool callable execution, or Engine integration logic" | 满足
不做 compatibility re-export | §6: "Do not keep compatibility re-exports in `tool_runtime.py`"；§8 Slice 1: "Remove duplicate governance compatibility re-exports … all Host modules must import these typed contracts from `dayu.host.tool_duplicate_governance`"；§12 亦列为 stop condition | 满足

### ADJ-004 — DuplicateGovernanceScope / prior refs validation — FIXED

Controller 要求（3 项）| Plan 修复证据 | 判定
---|---|---
`DuplicateGovernanceScope` 类型和传递路径 | §6: frozen typed dataclass，字段 `kind: Literal["attempt"]` + `attempt_id: str`，`__post_init__` 校验非空；`DuplicateGovernanceRequest` 通过 `scope: DuplicateGovernanceScope` 携带；`DuplicateDecision` 同样携带 `scope: DuplicateGovernanceScope` | 满足
删除 "验证 prior refs top-level attempt_id" 的不明确要求 | §7.9: prior refs 仅来自 `_AttemptDuplicateGovernanceState` 的 same-scope accepted entries，不做 top-level `attempt_id` validation；§8 Slice 3: "The same-Attempt invariant is guaranteed by `_AttemptDuplicateGovernanceState` only storing accepted entries for its own `DuplicateGovernanceScope`" | 满足
不为了 prior refs 额外读 EventLog | §7.9: "This work unit must not read EventLog to validate prior refs"；§8 Slice 3: "Do not add EventLog reads to validate prior refs"；§9 同样列出 | 满足

### ADJ-005 — DuplicateGovernanceMessages 默认值和校验 — FIXED

Controller 要求（3 项）| Plan 修复证据 | 判定
---|---|---
消息字段有默认值，默认语义等价 `_duplicate_message()` | §6: "`DuplicateGovernanceMessages` fields must have default values whose zero-config semantics are equivalent to the current `_duplicate_message()` behavior" | 满足
所有 message 字段必须非空字符串 | §6: "`__post_init__` must reject empty or whitespace-only strings for every message field" | 满足
`DuplicateGovernancePolicy.messages` 使用 `default_factory=DuplicateGovernanceMessages` | §6: `messages: DuplicateGovernanceMessages = field(default_factory=DuplicateGovernanceMessages)`；§8 Slice 2 要求测试验证 `DuplicateGovernancePolicy()` 无参构造可获得非空默认 messages | 满足

### ADJ-006 — allow policy 并发测试显式列入 Slice 1 — FIXED

Controller 要求（2 项）| Plan 修复证据 | 判定
---|---|---
Slice 1 加入 allow policy 并发 / post-owner-completion 测试 | §8 Slice 1: "Add `allow` policy concurrent test" 和 "Add `allow` policy post-owner-completion test"，明确 owner accepted → waiter resume → policy-driven ALLOW，及第一次完成后第二次执行 tool call count=2 | 满足
断言第二次执行是 policy-driven ALLOW，不是 parallel duplicate | §8 Slice 1: "assertions show this is not a pre-governance parallel duplicate"；§9: "not as an ungoverned parallel duplicate" | 满足

### ADJ-007 — run-scope 术语收口显式化 — FIXED

Controller 要求（2 项）| Plan 修复证据 | 判定
---|---|---
Slice 1/Slice 4 显式 grep 检查 | §8 Slice 1: `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py`；§8 Slice 4: 扩展 grep 到 `dayu/host tests/host dayu/host/README.md tests/README.md` | 满足
允许保留 unrelated truncation run-scoped wording | §8 Slice 1: "remaining matches are only allowed if they refer to unrelated truncation wording"；§8 Slice 4: "unrelated truncation run-scoped wording is allowed and should be called out in the slice report"；§9 同样列出 | 满足

## 闭合验证

| 验证项 | 结果 |
|---|---|
| 所有 ADJ 项 plan fix 引用均可在当前 plan 中找到对应文本 | 通过 |
| plan 内部一致性（async protocol / scope / policy / messages / tests 贯穿 §6-§9） | 通过 |
| plan fix artifact 的自检 grep 结果与其声称一致 | 通过（plan 中无 "新增可选"、"if used"、"prior refs whose top-level"、"Add a validation helper if needed" 等残留模糊措辞）|
| 无新的 blocking finding | 通过 |

## 最终判定

- Blocking findings: **0**
- Plan 状态: **code-generation-ready**，可进入 implementation gate
- Re-review artifact: `docs/reviews/wu-tool-01-plan-rereview-ds-20260601.md`
