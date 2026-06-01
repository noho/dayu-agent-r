# WU-TOOL-01 Plan Review Controller Adjudication

## 结论

Plan 方向正确，但暂不进入 implementation gate。MiMo 提出的 2 个 blocking finding 成立；DS 的 medium finding 与 in-flight claim 生命周期同源，也应并入 plan fix。基于 `docs/host/design.md` 的设计目标和第一性原理，WU-TOOL-01 的核心风险是 attempt-local duplicate governance 的 correctness；如果 in-flight owner cancel / accept failure / waiter notification 契约不完整，implementation agent 会被迫重新设计并可能引入死锁或未治理重复执行。

下一步进入 plan fix，修订 `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`，然后进行 plan re-review。

## Review Artifacts

- MiMo: `docs/reviews/wu-tool-01-plan-review-mimo-20260601.md`
- DS: `docs/reviews/wu-tool-01-plan-review-ds-20260601.md`
- Plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`

## 裁决

### ADJ-001 accepted: in-flight 并发协调契约不完整

来源：MiMo finding 1，DS F-TOOL-01-PR-001。

裁决：accepted，blocking。

理由：design_doc 要求同一 Attempt 内重复工具调用可治理、可追溯；plan 只描述了 owner / waiter 大方向，没有冻结 owner cancel、accept timeout、notify、claim release 和 sync-to-async protocol 边界。实现前必须把这些契约写清，否则无法保证 correctness。

Plan fix 要求：

- 明确 duplicate governance port 是否改为 async，以及所有调用方如何迁移。
- 明确 owner cancel / exception / accept rejection / accept timeout 时 waiter 返回受治理 durable-missing decision，不传播 owner 的取消为 waiter 取消。
- 明确 in-flight record 的状态机、notify 时机、claim 释放时机和后续新 caller 行为。
- 明确不在 condition lock 内执行工具 callable 或 Host accept。

### ADJ-002 accepted: in-flight 测试可构造性不足

来源：MiMo finding 2。

裁决：accepted，blocking。

理由：WU-TOOL-01 验收信号要求同 Attempt 并发 duplicate 有明确测试；当前 plan 对 accept failure / durable missing 的构造方式不够具体。没有可构造测试，核心并发 invariant 无法验证。

Plan fix 要求：

- 指定使用可控 fake accept port 构造 accepted、rejected、timed out 三类路径。
- 指定 slow tool / asyncio event 控制并发 owner 和 waiter 时序。
- 指定测试断言：owner failure 同一 in-flight window 的 waiter 不执行第二次真实工具调用，后续新 caller 可 fresh allow。

### ADJ-003 accepted: typed duplicate governance module 必须收敛为明确方案

来源：MiMo finding 4。

裁决：accepted，blocking for plan clarity。

理由：`dayu.host.tooling` 是 Host construction typed input owner，而 `tool_runtime.py` 已 import `tooling.py`；把 policy 留在 `tool_runtime.py` 再让 `tooling.py` import 它会制造反向依赖或循环风险。当前 phase 最佳实践是新增层内中立模块承载 duplicate policy 类型。

Plan fix 要求：

- 将 `dayu/host/tool_duplicate_governance.py` 改为必选新增模块。
- 明确该模块只承载 duplicate governance typed policy、messages、scope、decision/request/state 需要的层内类型；不得包含 dispatch、accept barrier、tool callable 执行或 scheduler 逻辑。
- 明确不做 compatibility re-export。

### ADJ-004 accepted with clarification: DuplicateGovernanceScope / prior refs validation

来源：MiMo finding 3、finding 5。

裁决：accepted with clarification，non-blocking but must be fixed while revising plan。

理由：machine-readable attempt scope 必须稳定，但不应为了验证 `HostEventRef` 再引入 EventLog lookup。最小正确方案是 typed `DuplicateGovernanceScope(kind=ATTEMPT, attempt_id=...)` 随 request/decision/payload 传播；prior refs 的同 Attempt invariant 由 attempt-local state 生成保证，candidate validation 不做 durable ref lookup。

Plan fix 要求：

- 明确 `DuplicateGovernanceScope` 的类型和传递路径。
- 删除或改写“验证 prior refs top-level attempt_id”的不明确要求。
- 写清本 work unit 不为了 prior refs 额外读 EventLog；跨 Attempt refs 不能由 attempt-local state 产生。

### ADJ-005 accepted: DuplicateGovernanceMessages 默认值和校验必须明确

来源：MiMo finding 6，DS F-TOOL-01-PR-002。

裁决：accepted，non-blocking but must be fixed while revising plan。

理由：用户要求提示可配置，但零配置路径也必须稳定；如果默认值和非空校验不明确，implementation agent 会自行选择，造成契约漂移。

Plan fix 要求：

- 明确 `DuplicateGovernanceMessages` 有默认值，默认语义等价当前 `_duplicate_message()` 文案。
- 明确所有 message 字段必须非空字符串。
- 明确 `DuplicateGovernancePolicy.messages` 使用 `default_factory=DuplicateGovernanceMessages`。

### ADJ-006 accepted: allow policy 并发测试显式列入 Slice 1

来源：DS F-TOOL-01-PR-003。

裁决：accepted，non-blocking but must be fixed while revising plan。

理由：`allow` 不能被实现成隐式 reuse，也不能成为未治理并发重复执行。必须在 Slice 1 明确测试，保护 policy 语义。

Plan fix 要求：

- Slice 1 加入 `allow` policy 并发 / post-owner-completion 测试。
- 断言第二次执行是 policy-driven `ALLOW`，不是等待前绕过治理的 parallel duplicate。

### ADJ-007 accepted: run-scope 术语收口必须显式化

来源：DS F-TOOL-01-PR-004。

裁决：accepted，non-blocking but must be fixed while revising plan。

理由：本 work unit 明确要求清理 run-local/run-scoped duplicate 路径；docstring 和测试名如果残留旧语义，会误导后续维护。

Plan fix 要求：

- Slice 1 / Slice 4 明确 `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run"` 检查 duplicate 相关区域。
- 允许保留 unrelated truncation run-scoped wording。

## Rejected / Deferred Findings

无。所有 review findings 都至少需要在 plan 中澄清；blocking findings 需 plan fix 后 re-review。
