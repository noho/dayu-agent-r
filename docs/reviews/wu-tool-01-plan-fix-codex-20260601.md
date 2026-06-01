# WU-TOOL-01 Plan Fix Artifact

## Gate

plan fix

## Source Review Artifacts

- `docs/reviews/wu-tool-01-plan-review-mimo-20260601.md`
- `docs/reviews/wu-tool-01-plan-review-ds-20260601.md`

## Controller Adjudication

- `docs/reviews/wu-tool-01-plan-review-controller-adjudication-20260601.md`

## Accepted Finding IDs

- `ADJ-001`
- `ADJ-002`
- `ADJ-003`
- `ADJ-004`
- `ADJ-005`
- `ADJ-006`
- `ADJ-007`

## Per-finding Fix Status

### ADJ-001 - fixed - in-flight 并发协调契约不完整

- Plan §6 明确 `DuplicateGovernancePort` 从同步 Protocol 变更为 async Protocol，并列出 `decide_duplicate()`、`record_accepted()`、`record_durable_missing()` 的 await 契约。
- Plan §7 明确 in-flight claim 状态机：owner claim、waiter wait、accepted terminal、durable-missing terminal、notify 时机、map entry 释放时机、后续 caller fresh `ALLOW` 行为。
- Plan §7 明确 owner cancel、tool exception、Host accept rejection、Host accept timeout 时 waiter 返回 governed durable-missing decision，不传播 owner failure。
- Plan §7 与 §8 Slice 1 明确 tool callable 与 Host accept 不得在 duplicate governance lock / condition lock 内执行。
- Plan §8 Slice 1 明确 owner cleanup 需在 `finally` 路径调用 `record_durable_missing()`。

### ADJ-002 - fixed - in-flight 测试可构造性不足

- Plan §8 Slice 1 明确新增 controllable fake accept port，覆盖 accepted、rejected、timed-out 三类 accept 路径。
- Plan §8 Slice 1 明确使用 slow `_CountingTool`、`asyncio.Event`、`asyncio.create_task(...)` 控制 owner/waiter 并发时序。
- Plan §8 Slice 1 与 §9 明确 owner failure window 内 waiter 不执行第二次真实工具调用，且后续第三个 caller fresh `ALLOW` 并可成为新 owner。

### ADJ-003 - fixed - typed duplicate governance module 收敛为明确方案

- Plan §5 将 `dayu/host/tool_duplicate_governance.py` 改为新增必选模块。
- Plan §6 明确该模块只承载 duplicate governance typed contracts，不包含 dispatch、scheduler、accept barrier、tool callable execution 或 Engine integration logic。
- Plan §6、§8 Slice 1、§12 明确禁止 compatibility re-export，Host modules 必须从 `dayu.host.tool_duplicate_governance` 导入 typed contracts。

### ADJ-004 - fixed - DuplicateGovernanceScope / prior refs validation

- Plan §6 明确 `DuplicateGovernanceScope` 为 frozen typed dataclass，字段为 `kind: Literal["attempt"]` 与 `attempt_id: str`。
- Plan §6 明确 `DuplicateGovernanceRequest` 和 `DuplicateDecision` 通过 `scope: DuplicateGovernanceScope` 传递 attempt scope。
- Plan §7 与 §8 Slice 3 删除 prior refs top-level `attempt_id` validation 的不明确要求，改为由 attempt-local accepted entries 保证 same-Attempt invariant。
- Plan §7、§8 Slice 3、§9 明确本 work unit 不为了 prior refs 额外读取 EventLog。

### ADJ-005 - fixed - DuplicateGovernanceMessages 默认值和校验

- Plan §6 明确 `DuplicateGovernanceMessages` 每个字段都有默认值，零配置语义等价当前 `_duplicate_message()` 行为。
- Plan §6 与 §8 Slice 1 明确 `DuplicateGovernanceMessages.__post_init__` 拒绝 empty / whitespace-only message。
- Plan §6、§8 Slice 1、§8 Slice 2、§9 明确 `DuplicateGovernancePolicy.messages = field(default_factory=DuplicateGovernanceMessages)`，并要求测试覆盖默认构造。

### ADJ-006 - fixed - allow policy 并发测试显式列入 Slice 1

- Plan §8 Slice 1 明确加入 `allow` policy concurrent test：owner accepted 后 waiter resume，decision 为 policy-driven `ALLOW`，第二次真实执行只能在 owner completion 后开始。
- Plan §8 Slice 1 明确加入 `allow` policy post-owner-completion test：第一次完成后第二次同 key 调用执行，tool call count 为 2。
- Plan §9 明确 `allow` 测试断言必须证明它不是 pre-governance parallel duplicate。

### ADJ-007 - fixed - run-scope 术语收口显式化

- Plan §8 Slice 1 明确运行 `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py`。
- Plan §8 Slice 4 明确运行 `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md`。
- Plan §8 Slice 4 与 §9 明确 duplicate governance 区域不得残留 run-scope 术语，允许 unrelated truncation run-scoped wording 并需在 slice report 中说明。

## Changed Files

- `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- `docs/reviews/wu-tool-01-plan-fix-codex-20260601.md`

## Validation Performed

- Ran self-check grep on the plan for stale ambiguous wording:
  - `新增可选`
  - `if used`
  - `prior refs whose top-level`
  - `Add a validation helper if needed`
- Ran self-check grep on the plan for required fix markers:
  - `tool_duplicate_governance.py`
  - `DuplicateGovernancePort`
  - `record_durable_missing`
  - `fake accept`
  - `timed-out`
  - `allow policy`
  - `default_factory`
  - `EventLog reads`
- Did not run tests or pyright because this gate only modified plan/review documentation and did not change source or tests.

## New Risks / Open Questions

- New risks: none identified in plan-fix scope.
- Open questions: none.

## Residual Risk Classification

- In-flight async implementation complexity: classified as implementation-phase risk covered by Plan §7, §8 Slice 1 tests, and §12 stop conditions.
- Import churn from required `dayu/host/tool_duplicate_governance.py`: classified as implementation-phase risk covered by Plan §6, §8 Slice 1/Slice 2, and §12 stop conditions.
- Tool trace metadata shape uncertainty: classified as implementation-phase risk covered by Plan §8 Slice 3 stop condition.

## Completion / Stop Status

- Completion status: plan-fix artifact complete.
- Stop status: no stop condition hit.
