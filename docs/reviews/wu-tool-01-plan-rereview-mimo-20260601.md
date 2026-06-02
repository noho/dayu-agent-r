# WU-TOOL-01 Plan Re-Review

## Gate

plan re-review

## Plan

`docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`

## Source Artifacts

- Plan fix: `docs/reviews/wu-tool-01-plan-fix-codex-20260601.md`
- Controller adjudication: `docs/reviews/wu-tool-01-plan-review-controller-adjudication-20260601.md`
- Original MiMo review: `docs/reviews/wu-tool-01-plan-review-mimo-20260601.md`
- Original DS review: `docs/reviews/wu-tool-01-plan-review-ds-20260601.md`

## 结论

ADJ-001 至 ADJ-007 全部在 plan 中充分修复，无 remaining blocking finding。Plan 可进入 implementation gate。

## 逐项复核

### ADJ-001 — closed — in-flight 并发协调契约不完整

**裁决要求**: async Protocol 变更声明；owner cancel/exception/accept rejection/accept timeout 时 waiter 返回 durable-missing decision 不传播 owner 失败；in-flight 状态机含 notify/claim release/后续 caller 行为；不在 lock 内执行 tool callable 或 Host accept。

**Plan 覆盖**:

- §6 明确 `DuplicateGovernancePort` 从 sync 变 async Protocol，三个方法均需 `await`，所有 ToolRuntime caller 必须迁移。
- §7.6 完整定义 in-flight claim 状态机：owner_running → accepted / durable_missing 两个 terminal；明确 notify 时机（terminal status written 后、map entry release 前/中）；明确 claim release 后后续 caller 看到空 in-flight + 空 accepted entry 获得 fresh `ALLOW`。
- §7.6 明确 owner cancel、tool exception、Host accept rejection、Host accept timeout 四条路径均在 `finally` 中调用 `record_durable_missing()`；waiter 收到 governed durable-missing decision 使用 `policy.messages.prior_accept_missing`，不接收 owner CancelledError / tool exception / accept exception，不执行第二次真实工具调用。
- §7.7 明确 state lock / condition lock 只保护 claim 创建、accepted-entry 读写、terminal state 更新、waiter 注册/通知、map entry release；tool callable 和 Host accept 不得在 lock 内执行。

**判定**: 充分修复，无遗留 blocking 问题。

### ADJ-002 — closed — in-flight 测试可构造性不足

**裁决要求**: 可控 fake accept port 覆盖 accepted/rejected/timed-out；slow tool + asyncio.Event 控制并发时序；owner failure 后 waiter 不执行第二次真实执行、后续新 caller fresh ALLOW。

**Plan 覆盖**:

- §8 Slice 1 exact changes 明确新增 controllable fake accept port，带 accepted、rejected、timed-out 三种模式，不依赖 durable store timing。
- §8 Slice 1 明确使用 slow `_CountingTool`、`asyncio.Event`、`asyncio.create_task(...)` 控制 owner/waiter 并发时序，events 确保 owner claims before waiter starts、waiter blocked while owner runs、second real execution cannot begin before owner terminal notification。
- §8 Slice 1 明确 owner failure window 内 waiter 不执行第二次真实工具调用；后续第三个 caller 同 Attempt/key 获得 fresh `ALLOW` 并成为新 owner。
- §9 expected assertions 对应覆盖 reuse / rejected / timed-out / owner cancellation 四类并发路径和 post-failure fresh ALLOW。

**判定**: 充分修复，测试构造路径明确可执行。

### ADJ-003 — closed — typed duplicate governance module 必须收敛为明确方案

**裁决要求**: `tool_duplicate_governance.py` 为必选新增模块；只承载 typed contracts；不做 compatibility re-export。

**Plan 覆盖**:

- §5 affected files 将 `dayu/host/tool_duplicate_governance.py` 列为 production 必选模块（非"可选"）。
- §6 contract changes 第一条明确该模块只承载 duplicate governance typed contracts，不得包含 dispatch、scheduler、accept barrier、tool callable execution 或 Engine integration logic。
- §6 明确不做 compatibility re-export，Host modules 必须从 `dayu.host.tool_duplicate_governance` 导入。
- §8 Slice 1 exact changes 将所有 typed contracts 移入该模块并删除 `tool_runtime.py` 中的 compatibility re-exports。

**判定**: 充分修复，module 定位从可选收敛为必选。

### ADJ-004 — closed — DuplicateGovernanceScope / prior refs validation

**裁决要求**: `DuplicateGovernanceScope` 类型和传递路径明确；删除不明确的 prior refs top-level `attempt_id` validation；不为 prior refs 读 EventLog。

**Plan 覆盖**:

- §6 明确 `DuplicateGovernanceScope` 为 frozen typed dataclass，`kind: Literal["attempt"]`，`attempt_id: str`，`__post_init__` 校验非空。
- §6 明确 `DuplicateGovernanceRequest` 和 `DuplicateDecision` 通过 `scope: DuplicateGovernanceScope` 传递。
- §7.9（原 §7.7 重编号）删除 prior refs top-level `attempt_id` validation 的不明确要求，改为由 attempt-local accepted entries 保证 same-Attempt invariant，candidate validation 不做 durable ref lookup。
- §7.9 明确本 work unit 不为 prior refs 额外读 EventLog。

**判定**: 充分修复，scope 类型稳定，prior refs 验证策略清晰。

### ADJ-005 — closed — DuplicateGovernanceMessages 默认值和校验

**裁决要求**: 每个字段有默认值，零配置等价当前 `_duplicate_message()`；`__post_init__` 拒绝 empty/whitespace；`default_factory=DuplicateGovernanceMessages`。

**Plan 覆盖**:

- §6 明确 `DuplicateGovernanceMessages` 字段有默认值，零配置语义等价当前 `_duplicate_message()` 行为。
- §6 明确 `__post_init__` 拒绝 empty / whitespace-only message。
- §6 明确 `DuplicateGovernancePolicy.messages = field(default_factory=DuplicateGovernanceMessages)`。
- §8 Slice 1 exact changes 和 §8 Slice 2 test_tooling_options 要求覆盖默认构造和空消息校验。

**判定**: 充分修复，默认值策略和校验规则明确。

### ADJ-006 — closed — allow policy 并发测试显式列入 Slice 1

**裁决要求**: Slice 1 加入 allow policy 并发/post-owner-completion 测试；断言是 policy-driven ALLOW 不是 pre-governance parallel duplicate。

**Plan 覆盖**:

- §8 Slice 1 exact changes 倒数第二条明确加入 `allow` policy concurrent test：owner accepted first, waiter resumes after owner terminal notification, decision is policy-driven `ALLOW`, second real execution starts only after owner completion。
- §8 Slice 1 exact changes 最后一条明确加入 `allow` policy post-owner-completion test：first call completes, second same-key call is policy-driven `ALLOW`, tool call count becomes 2。
- §9 expected assertions 明确 `allow` 测试断言必须证明不是 pre-governance parallel duplicate。

**判定**: 充分修复，allow 测试已与 reuse 并发测试对等列入。

### ADJ-007 — closed — run-scope 术语收口显式化

**裁决要求**: Slice 1/Slice 4 明确 rg 检查；duplicate governance 区域不得残留 run-scope 术语；允许 unrelated truncation wording。

**Plan 覆盖**:

- §8 Slice 1 exact changes 最后一条明确运行 `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py`，remaining matches 只允许 unrelated truncation wording 或 implementation removes 的 direct evidence comments。
- §8 Slice 4 exact changes 明确运行相同 rg pattern 覆盖 `dayu/host tests/host dayu/host/README.md tests/README.md`。
- §9 expected assertions 最后一条明确 terminology grep 必须显示无 duplicate-governance run-scope 残留（unrelated truncation 除外）。

**判定**: 充分修复，术语收口检查已嵌入两个 slice 的验收流程。

## Remaining Blocking Findings

无。

## 总结

| ADJ ID | 主题 | 状态 |
|---|---|---|
| ADJ-001 | in-flight 并发协调契约 | closed |
| ADJ-002 | in-flight 测试可构造性 | closed |
| ADJ-003 | tool_duplicate_governance module 必选 | closed |
| ADJ-004 | DuplicateGovernanceScope / prior refs | closed |
| ADJ-005 | DuplicateGovernanceMessages 默认值 | closed |
| ADJ-006 | allow policy 并发测试 | closed |
| ADJ-007 | run-scope 术语收口 | closed |

- **Remaining blocking findings**: 0
- **Plan 状态**: code-generation-ready，可进入 implementation gate
