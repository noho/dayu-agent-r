# WU-TOOL-01 Plan Review

## 审查角色与真源

- 审查角色：plan review specialist
- Plan target：`docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- 设计真源：`docs/host/design.md`
- 总控文档：`docs/host/host-core-followup-implementation-control.md`
- 前序 artifact：`docs/reviews/wu-tool-01-discussion-code-inspection-20260601.md`

## 结论

Plan 通过。无 blocking finding。4 个 non-blocking finding（1 medium，3 low），均可在实现过程中自然消解，不阻塞进入 implementation gate。

## 逐项审查矩阵

| 审查项 | 结果 | 依据 |
|---|---|---|
| 满足 design.md §18.3 设计目标 | 通过 | attempt_id 入 key、typed policy、跨 Attempt 不继承、TOOL_CALL_GOVERNED 表达 scope，全部对齐 2077-2116 |
| 满足 control doc WU-TOOL-01 验收信号 | 通过 | 6 条验收信号（414-437）均有对应 slice、测试断言或 stop condition |
| attempt-scope 真正关闭 run-scope registry/key/tests | 通过 | Slice 1 删除 `RunScopedDuplicateGovernanceRegistry`/`InMemoryRunLocalDuplicateGovernance` 命名并移出 `__all__`；Slice 2 删除 scheduler `_duplicate_governance_registry`；Slice 4 删除 run-scope 测试并补 attempt-scope 回归；无兼容路径保留 |
| duplicate policy/message/justification typed configurable | 通过 | §6 定义 `DuplicateGovernanceMessages` typed fields + `message_for()`；`DuplicateGovernancePolicy` 承载 messages；`HostToolingOptions` 承载 policy；§7.8 删除 `_duplicate_message()` 硬编码分支 |
| 无 extra payload/raw dict | 通过 | §6 明确 `DuplicateGovernanceMessages` 为 typed fields，不是 untyped payload；§12 stop condition 阻止回退到 raw dict |
| 同 Attempt 并发 duplicate in-flight 设计可实现、可测试 | 通过（附 F-TOOL-01-PR-001 注意事项） | §7.5 设计 `asyncio.Condition` + 原子 claim；Slice 1 含并发测试；§13 覆盖取消死锁风险 |
| 不改变 allow 语义或导致死锁 | 通过 | §7.6 明确 `allow` = "policy explicitly allows a second execution"，与 reuse 区分；§13 注明 `finally` 通知 waiter 防止死锁 |
| 不引入 durable ledger/跨 Attempt 复用/tool freshness/side-effect 幂等/config assembly | 通过 | §3 non-goals 完整列出；§12 stop condition 拦截 scope creep |
| slice code-generation-ready | 通过（附 F-TOOL-01-PR-002/003/004） | 4 个 slice 均有 allowed files、exact changes、expected outcome、stop condition；file ownership 明确 |

## Findings

### F-TOOL-01-PR-001 — 未修复 — Medium — In-flight claim 释放时机未在 plan 中显式定义

§7.5 规定：
- 首个 caller 原子 claim in-flight ownership；
- 并发 caller 等待 owner 完成；
- owner 产生 accepted ack 后，waiter 按 typed policy 决策；
- owner accept 失败/超时后，waiter 收到 `prior_accept_missing` governed error，"must not start a duplicate real execution in the same in-flight window"。

但 plan 未显式定义 in-flight window 何时关闭、claim 何时释放。关键场景：owner accept 失败后，waiters 收到 governed error，claim 应在最后一个 waiter 被通知后释放，使得**后续新到达的 caller** 能看到空 in-flight + 空 accepted entry，获得 fresh ALLOW 决策并自己成为新 owner。

若实现时 claim 释放过早（waiter 未全部通知就释放），可能出现 waiter 读到空 in-flight 后自行执行；若释放过晚（永不释放），后续 caller 永久阻塞。

**建议**：实现时确保 claim 释放发生在所有 waiter 被 `Condition.notify_all()` 之后、但最迟在 `finally` 块中。Slice 1 并发测试应覆盖"owner accept 失败 → waiters 收到 governed error → 新 caller（非 concurrent batch 内）获得 fresh ALLOW"三级时序。若实现在此点有歧义，应停下来补充设计决策再继续。

### F-TOOL-01-PR-002 — 未修复 — Low — `DuplicateGovernancePolicy.messages` 的 default_factory 未显式声明

Plan §6 定义 `DuplicateGovernanceMessages` 但未明确该字段在 `DuplicateGovernancePolicy` 中的默认构造方式。如果实现时 `messages` 是必填字段（无 default），则所有现有 `DuplicateGovernancePolicy()` 调用点（含测试 helper）编译失败。

当前 `DuplicateGovernancePolicy(default_duplicate_decision=..., decisions_by_tool_name=..., justification_argument_names_by_tool_name=...)` 的所有三个字段均有默认值。新增 `messages: DuplicateGovernanceMessages = field(default_factory=DuplicateGovernanceMessages)` 可保持向后兼容。如果 `DuplicateGovernanceMessages` 本身有 `default_factory` 产生合理中文默认文案，则零配置路径不受影响。

**建议**：实现时确保 `DuplicateGovernancePolicy.messages` 使用 `default_factory=DuplicateGovernanceMessages`（其默认值产生与当前 `_duplicate_message()` 等价的默认文案），并在 Slice 1 的 `test_tooling_options.py` 扩展中验证默认 policy 可无参构造。

### F-TOOL-01-PR-003 — 未修复 — Low — `allow` policy after prior accepted 的显式测试未分配 slice

Plan §7.6 和 §9 明确要求"`allow` policy remains explicit allow；test name and assertions must show it is policy-driven after in-flight owner completion, not a parallel ungoverned duplicate"。但 Slice 1 exact changes 中只为 `reuse` policy 列出了并发测试，未显式列出 `allow` policy 并发测试。

如果实现 agent 只按 Slice 1 文字清单实施，可能遗漏 `allow` policy 并发场景测试。

**建议**：在 Slice 1 实现时将 `allow` policy 并发测试作为与 `reuse` 并发测试对等的显式项。测试应：同一 Attempt，policy=`allow`，第一次调用完成后第二次同 key 调用进入——断言第二次确实执行了（tool call count=2），且 decision.kind=`ALLOW`，不是 ungoverned parallel execution。

### F-TOOL-01-PR-004 — 未修复 — Low — 协议与枚举 docstring 的 attempt-scope 术语更新未逐项枚举

以下 docstring/注释当前仍携带 run-scope 术语，plan 要求在 Slice 1 改名但未在 exact changes 中逐项列出：

- `DuplicateGovernancePort.decide_duplicate()` docstring："判断当前工具调用是否与同 Run 既有调用重复"
- `DuplicateGovernancePort.record_accepted()` docstring："记录已 accepted 工具事实供同 Run 后续治理复用"
- `DuplicateDecisionKind` enum docstring："同 Run 语义级重复工具调用决策类别"
- `tool_runtime.py` 模块级 docstring line 8："run-scoped in-memory duplicate governance"
- `DuplicateGovernancePolicy` docstring："run-local duplicate governance 策略"
- `DuplicateDecision` docstring line 877："可复用的既有事件引用；无复用时为空元组"（不涉及 run，但应确认不需要加 attempt scope 说明）

这些术语更新是实现 attempt-scope 的语义闭环的一部分。如果遗漏，会导致文档/代码注释与实现行为不一致。

**建议**：实现 Slice 1 时全量 grep `Run\b|run-local|run-scoped` 在 `tool_runtime.py` 的 duplicate 相关区域，确保术语全部收敛为 attempt-scoped。Slice 4 的 regression matrix 应检查残留 run-scope 术语。

## 设计一致性校验

| 设计真源要求 | Plan 覆盖 | 位置 |
|---|---|---|
| duplicate key 包含 attempt_id（design.md:2086） | 是 | §7.2 |
| typed 配置或 Attempt snapshot 传入 policy/message/justification（design.md:2098） | 是 | §6, §7.8-7.10 |
| TOOL_CALL_GOVERNED 包含 scope、key、decision、prior refs（design.md:2106） | 是 | §6, Slice 3 |
| 跨 Attempt 不继承 duplicate index（design.md:2086） | 是 | §2, §7.4, Slice 1/4 tests |
| 不引入 durable duplicate ledger（design.md:2088） | 是 | §3 |
| 不跨 Attempt 复用（design.md:2113-2114） | 是 | §3 |
| WAITING resume 是新 Attempt，duplicate governance 不跨 Attempt 复用（design.md:2264, 2327） | 是 | §2, Slice 4 regression tests |

## 过度设计检查

| 潜在过度设计 | 状态 | 判断 |
|---|---|---|
| durable duplicate ledger | 明确排除 | §3 non-goals |
| 跨 Attempt/Run/Session 复用 | 明确排除 | §3 non-goals |
| tool freshness / 行情 / 汇率 | 明确排除 | §3 non-goals |
| side-effect 幂等策略 | 明确排除 | §3 non-goals |
| ToolsDiscovery / ScenePrepare / ConfigLoader | 明确排除 | §3 non-goals |
| EventLog 重建 duplicate index | 明确排除 | §3 non-goals |
| `dayu/host/tool_duplicate_governance.py` 新模块 | 条件允许 | §7 item 1, Slice 2 stop condition——仅当 import cycle 无法在 tool_runtime.py 内解决时使用，非预设过度拆分 |

## 风险追踪

| 风险 | Plan 处理 | 评价 |
|---|---|---|
| `allow` 语义被误读为禁止重复执行 | §13 non-blocking risk，含 signal to revisit | 恰当——已在 §7.6 明确解释 |
| 新模块 import 可能触碰大量引用 | §13 non-blocking risk，仅在避免 circular import 时接受 | 恰当 |
| asyncio.Condition 取消死锁 | §13 non-blocking risk，要求 `finally` 通知 waiter | 恰当 |
| ToolTraceDiagnosticRecord 不支持 structured metadata | §13 non-blocking risk，含降级方案（EventLog payload 承载） | 恰当——Slice 3 stop condition 亦覆盖此点 |

## Stop Conditions 完备性

§12 列出 6 条 stop condition，覆盖：Engine contract 变更、新 public tool outcome contract、HostToolingOptions 扩散、allow 语义冲突、pyright 扩散、README 越界。逐一评估：

- 全部 stop condition 均有明确触发条件和上报目标（controller）
- 每条 stop condition 都预防了 scope creep 或架构边界突破
- 无遗漏的关键风险点

## 测试覆盖评估

| 测试维度 | Slice | 状态 |
|---|---|---|
| duplicate_key 含 attempt_id | Slice 1 | 新增 `test_duplicate_key_includes_attempt_id` |
| 同 Attempt reuse 并发（callable 执行 1 次） | Slice 1 | 新增 `asyncio.create_task` 并发测试 |
| owner accept 失败 → waiter governed error | Slice 1 | 新增 "如果 in-flight owner can be forced to fail accept" 条件测试 |
| 跨 Attempt 不继承（两个 ToolRuntime handle） | Slice 1/4 | Slice 1 替换 run-scope test + Slice 4 regression |
| worker/Host restart 不继承 | Slice 4 | 构造新 `InMemoryAttemptDuplicateGovernance` 同 Attempt id 断言无旧 refs |
| `allow` 语义（policy-driven, not ungoverned） | Slice 1 | 需按 F-TOOL-01-PR-003 补充显式分配 |
| typed policy 配置（message/justification） | Slice 2 | `test_tooling_options.py` 覆盖 default/custom/empty |
| TOOL_CALL_GOVERNED payload duplicate_scope | Slice 3 | accept barrier test 断言 |
| tool trace summary 含 duplicate_scope | Slice 3 | projection test 断言 |
| scheduler 不再持有/清理 registry | Slice 2 | 删除 `active_run_count` 断言，替换为行为测试 |
| `require_justification` 降级 hint（无 argument name） | Slice 1 | §9 failure paths 列出，现有测试 `test_require_justification_without_argument_binding_downgrades_to_hint` 应保留并更新 |
| prior refs 同 Attempt 校验 | Slice 3 | candidate validation 拒绝跨 Attempt refs |

## README 同步评估

Plan §10 判定需更新 `dayu/host/README.md` 和 `tests/README.md`，不更新 root `README.md` 和 `dayu/README.md`。判定依据与 CLAUDE.md README 触发规则一致：

- `dayu/host/tool_runtime.py`、`dispatch.py`、`tooling.py` 变更 → 触发 `dayu/host/README.md` ✓
- `tests/host/` 多文件变更 → 触发 `tests/README.md` ✓
- 无 CLI/render/config 入口变更 → 不触发 root `README.md` ✓
- 无分层/装配边界变更 → 不触发 `dayu/README.md` ✓

## 最终判定

- **Blocking findings**：0
- **Non-blocking findings**：4（1 medium，3 low）
- **Plan 状态**：code-generation-ready，可进入 implementation gate
- **建议**：实现 agent 应在 Slice 1 开始前阅读 F-TOOL-01-PR-001 至 F-TOOL-01-PR-004，在实现过程中逐项消解
