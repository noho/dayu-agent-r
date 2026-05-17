# P9.5 Pre-P10 Cross-Repository Hardening Plan Review

- Reviewer: AgentMiMo
- Date: 2026-05-17
- Plan artifact: `docs/host/p9-5-pre-p10-hardening-plan.md`
- Gate: implementation-ready handoff plan review

## Verdict

**PASS with non-blocking findings.** 无 blocking finding。计划在动机、scope、切片、sequencing、测试、架构边界和 residual-risk tracking 方面均满足 design truth 和 implementation-control truth 要求。以下 findings 为实施阶段需关注的非阻塞改进项。

## Findings

### F-01 [LOW] Slice 间依赖未显式声明

- Evidence: 计划 §Implementation Decisions 第 1 点提到 "Engine protocol decoupling and parser hardening happen before Host ingestion checks that rely on Engine event shape. Durable schema / helper tightening happens before read / command behavior tests depend on fail-closed invariants"，但各 slice（S0-S18）之间没有显式的 `depends_on` 或 `blocked_by` 声明。
- Why: 实施 agent 可能尝试并行执行无显式依赖的 slice，导致合并冲突或测试不稳定。例如 S14（memory catch-up wiring）依赖 S10（dispatch lifecycle）的 dispatch 路径 cleanup；S16（Contract Ownership audit）理论上可独立执行但其发现可能影响 S3/S11。
- Required fix: 建议在实施阶段由 controller 在 dispatch 前确认依赖图；计划层面无需修改，但 controller dispatching 时应显式声明执行顺序约束。
- Blocks implementation: No。

### F-02 [LOW] S15 Logger 注入模式未指定

- Evidence: S15 Exact changes 提到 "Add VERBOSE skeleton logs"、"Add DEBUG logs"、"Add WARN/ERROR/CRITICAL"，但未指定 logger 获取方式（`logging.getLogger(__name__)` vs 构造函数注入 vs module-level logger）。S15 Targeted tests 包含 caplog 测试。
- Why: 不同的 logger 获取方式影响测试策略。若使用 module-level `logger = logging.getLogger(__name__)`，caplog fixture 需要知道 logger name；若使用构造函数注入，测试可替换 mock logger。当前代码大概率使用 module-level logger（Python 标准实践），但计划应确认这一点以避免实施 agent 自行决定引入构造函数注入增加不必要复杂度。
- Required fix: 实施时统一使用 `logging.getLogger(__name__)` module-level logger，与项目现有模式一致。无需修改计划，实施 agent 按标准实践即可。
- Blocks implementation: No。

### F-03 [LOW] S14 "current_goal first-write-wins" 实施指令偏模糊

- Evidence: S14 Exact changes 第 1 项 "Enforce `current_goal` first-write-wins if current code does not." 未说明 current code 是否已实现该语义、若未实现需要在哪里写入 enforcement、以及 enforcement 失败时的行为。
- Why: 实施 agent 可能花费过多时间调查 current code 状态，或错误地在不该写入 enforcement 的位置写入。implementation-control.md:1077 也使用了 "只收口...不涉及 snapshot history 保留模型的 cleanup / tests" 的模糊表述。
- Required fix: 实施 agent 若发现 current code 已实现 first-write-wins，只需补测试确认；若未实现，在 memory projection catch-up 路径添加 enforcement 并补测试。这是实施阶段的调查任务，不需要修改计划。
- Blocks implementation: No。

### F-04 [LOW] S6 "direct DB row mutation" 测试策略混合了 DB CHECK 与 Python 验证

- Evidence: S6 Exact changes "Add unknown raw value tests by direct DB row mutation where feasible"，而 S5 正是添加 DB CHECK 约束。S6 的 enum mapping 测试应区分：(a) Python-level enum 映射的 unknown value 处理，(b) DB-level CHECK 约束拒绝非法值。
- Why: 若 S5 已添加 CHECK 约束，S6 的 "direct DB row mutation" 测试在 SQLite 层就会被拒绝，无法测试 Python mapping 层的 fail-closed 行为。实施 agent 需要理解测试目标层级。
- Required fix: S6 的 unknown value 测试应通过 Python 构造非法 durable row dataclass（而非直接 SQL INSERT）来测试 mapping helper 的 fail-closed 行为。S5 负责 DB 层。实施时注意区分即可。
- Blocks implementation: No。

### F-05 [LOW] S18 未指定 slice commits 的 git 组织策略

- Evidence: §Review Gates 提到 "each implementation slice must have implementation artifact, code review, accepted finding fix, re-review, and accepted local slice commit before the next slice"，但未说明 slice commit 是 squash 到单个 commit、保持独立 commit、还是使用 interactive rebase 整理。
- Why: 19 个 slice 若每个都产生独立 commit，PR 历史会非常长；若全部 squash，aggregate deepreview 失去细粒度 blame 能力。
- Required fix: 建议 controller 在 dispatch 时指定：相邻低风险 slice 可合并 commit，高风险 slice 保持独立 commit 便于 review。这是实施阶段的 git 策略决策，不需要修改计划。
- Blocks implementation: No。

### F-06 [LOW] S2 "directly evidenced parser defects" 判定标准未明确

- Evidence: S2 Exact changes "Fix only directly evidenced parser defects. Do not re-open usage-only / partial tool-call-delta retry granularity."
- Why: "directly evidenced" 是主观判定。一个 parser edge case 可以通过 SSE 文档、provider 行为观察或测试失败来 "evidence"，但哪种证据算 "direct" 未定义。
- Required fix: 实施 agent 应以现有测试失败、SSE 规范文档或 provider 官方行为作为 "direct evidence"；仅有推断或理论可能性的不修。这是实施阶段的判断标准，不需要修改计划。
- Blocks implementation: No。

### F-07 [INFO] 计划未提及 pyright 现有报错的处理策略

- Evidence: §Tests And Validation Matrix 要求 `python -m pyright dayu tests`，CLAUDE.md 要求 "任何新增或修改代码都必须通过 pyright；禁止新增、扩散、掩盖或绕过类型错误。若修改范围触及已有 pyright 报错，必须一并修复"。但计划未提及当前 pyright baseline 状态。
- Why: 若当前 pyright 已有报错，S1-S16 的实施 agent 需要知道哪些是 baseline 错误（不应在本 slice 修）、哪些是新引入的。否则每个 slice 都可能试图修无关的 pyright 错误，导致 scope creep。
- Required fix: S0 Controller Preflight 应包含 `python -m pyright dayu tests` baseline 记录，明确当前已有的报错不属于 P9.5 scope（除非被 slice 修改范围触及）。这是 S0 实施时的补充，不需要修改计划结构。
- Blocks implementation: No。

### F-08 [INFO] S11 ToolRuntime 模块拆分的 "mechanically extract" 边界

- Evidence: S11 Exact changes "If `tool_runtime.py` remains too large for targeted changes, mechanically extract private helpers by owner"。计划列出了 5 个提取方向：effective bundle/schema projection、accept barrier、duplicate governance、truncation/fetch_more、diagnostics。
- Why: 5 个提取方向意味着可能产生 5 个新模块。如果全部提取，`tool_runtime.py` 本身可能变得太薄，而新模块之间的依赖关系需要仔细管理。计划的 stop condition "extraction requires public compatibility wrappers, semantic changes, or moving ToolRuntime into contracts/runtime" 是好的边界，但未说明提取粒度的上限。
- Required fix: 实施 agent 应按需提取，不是所有 5 个方向都必须拆出独立模块。若某个方向只有少量代码，保留在 `tool_runtime.py` 即可。这是实施判断，不需要修改计划。
- Blocks implementation: No。

## Residual Risks

以下为计划已识别的 residual risks，本 review 确认其评估合理：

1. **Message/tool result size governance 可能发现无现有 typed public detail 适配超限错误。** 计划已要求 controller 决定是否添加 typed detail variant。合理。

2. **Contract Ownership audit 可能发现 documented public exports 实际是 misplaced。** 计划已要求停止并由 controller adjudicate。合理。

3. **Schema CHECK hardening 可能需要 schema version bump。** 计划已允许 fresh-schema bump，禁止旧库兼容。合理。

4. **ToolRuntime 模块拆分可能过宽。** 计划已要求停止并重新切片。合理。

5. **Production memory catch-up wiring 可能暴露 snapshot history 耦合。** 计划已要求 reassign 到单独 PR。合理。

## Evidence Of Compliance With Design Truth

- 计划正确引用了 `docs/host/design.md` §4/§10/§12/§16/§17/§18/§24 作为设计章节对应。
- 计划正确引用了 `docs/host/implementation-control.md:935-1099` 的 P9.5 scope、允许/禁止修改范围和收口清单。
- 计划正确引用了 `dayu/README.md` 的日志级别语义、Contract Ownership 和工具定义与执行边界。
- 计划正确引用了 `dayu/engine/README.md` 的 Runner 接口和非接口边界。
- 计划的 Non-Goals 完整覆盖了 implementation-control.md 的排除项。
- 计划的 Forbidden Changes 与 implementation-control.md 的禁止修改范围一致。
- 计划的 Stop Conditions 覆盖了所有需要退回 controller 的场景。
- 计划未引入 runner factory/registry、compat re-export/wrapper、lazy import seam、extra payload bag、Any/object 签名、无 owner 的 God cleanup。
- 计划未引入 P10+ 语义（Context Governance、RECOVERING、ToolsDiscovery、Audit/Tool Trace/Outbox sinks、RemoteProxy、purge/retention）。
