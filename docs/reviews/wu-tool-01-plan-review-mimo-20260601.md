# WU-TOOL-01 Plan Review

## 结论

Plan 基本满足 design_doc 设计目标和 WU-TOOL-01 验收信号。attempt-scope 关闭 run-scope 的方向正确，用户新增要求（typed configurable duplicate policy / messages / justification）已纳入 contract 变更。non-goals 边界合理，未引入过度设计。

有 2 个 blocking finding 和 4 个 non-blocking finding。blocking finding 集中在 in-flight 并发协调的契约完整性和测试可构造性。

## Findings

### 1-未修复-blocking-in-flight 并发协调契约不完整

**位置**: plan section 7.5, section 9, section 13

**问题**: plan 要求 `_AttemptDuplicateGovernanceState` 使用 `asyncio.Condition` 实现 in-flight 串行化，但以下关键契约未定义：

1. **owner 任务取消时 waiter 行为**: plan section 13 提到"implementation must complete/notify waiters in `finally` and return governed durable-missing error"，但 section 7.5 只说"waiters must not start a duplicate real execution"和"must receive a governed error with `prior_accept_missing` diagnostic"。`finally` 中 waiter 收到的是 exception 还是 `DuplicateDecision`？如果 `decide_duplicate` 变成 async，owner cancel 时 waiter 的 `await` 会抛 `CancelledError` 还是被 Condition notify 后收到一个 durable-missing decision？这两种路径的实现和测试策略完全不同。

2. **`decide_duplicate` 同步变异步的 Protocol 兼容**: `DuplicateGovernancePort` 是公开 Protocol（`tool_runtime.py:1123`）。当前 `decide_duplicate` 是同步签名。plan 要求改成 async 以支持 `asyncio.Condition` 等待。这是 Protocol 公开契约变更，plan 未在 section 6 "Public interface" 中显式声明此变更，也未说明是否有非 in-flight 场景仍需同步调用。

3. **死锁边界**: 如果 owner 在 `decide_duplicate` 的 `async with condition` 内被 cancel，`finally` 中的 `condition.notify_all()` 是否能正确唤醒 waiter？`asyncio.Condition` 的 `notify_all` 只唤醒已进入 `wait()` 的 waiter；如果 waiter 还没进入 `wait()`（时序窗口），notify 会丢失。需要确认实现是否需要额外状态标记来处理此窗口。

**影响**: 不解决这些契约问题，implementation agent 无法确定 in-flight 协调的正确实现路径，可能导致实现与设计意图不符或引入死锁。

**建议**: 在 plan section 7.5 中补充：
- owner cancel 时 waiter 的精确返回路径（`DuplicateDecision` with `prior_accept_missing`，还是 exception）
- `DuplicateGovernancePort` Protocol 变更声明（sync -> async）
- `asyncio.Condition` 使用的精确生命周期和 cancel-safe 保证

### 2-未修复-blocking-in-flight 测试可构造性未验证

**位置**: plan section 8 Slice 1 "Exact changes" 和 section 9

**问题**: plan 要求两个关键并发测试：

1. "Add owner accept-timeout/durable-missing concurrent test if in-flight owner can be forced to fail accept" — 但 plan 未说明如何在测试中强制 accept 失败。是 mock accept_port？注入延迟？构造一个会 reject 的 accept barrier？测试的前置条件和构造路径不明确。

2. "Add true concurrent same Attempt test with a slow `_CountingTool` and two `asyncio.create_task(...)` calls" — 假设 `decide_duplicate` 变成 async，两个 task 都需要 `await decide_duplicate()`。测试需要精确控制 owner task 的执行顺序（先 dispatch、再 accept、再让 waiter 重评）。如果 accept 是真实的 Host accept barrier，测试会依赖 durable store，这超出了 ToolRuntime unit test 范围。

**影响**: 如果测试路径不可构造，section 9 的验收断言（"In-flight owner accepts no durable fact because accept timeout/rejection occurs: waiter must not start a second true execution"）无法验证，核心并发 invariant 没有测试覆盖。

**建议**: 明确 accept-timeout/durable-missing 测试的构造方案：
- 使用可注入的 mock accept port，构造 accept reject / timeout 场景
- 或者明确说明该测试在 section 8 Slice 3 的 diagnostics test 中覆盖（如果 governed event 构造路径已经过 accept barrier）
- 在 Slice 1 stop condition 中加入"如果 in-flight 测试需要 durable store 依赖，报告 controller"

### 3-未修复-non-blocking-`DuplicateGovernanceScope` 未纳入 implementation slice

**位置**: plan section 6 vs section 8

**问题**: section 6 定义了 `DuplicateDecision` 应携带 `DuplicateGovernanceScope` dataclass（包含 `attempt_id`），section 6 也要求 `TOOL_CALL_GOVERNED` payload 包含 `duplicate_scope: {"kind": "attempt", "attempt_id": ...}`。但 section 8 的三个 slice 的 "Exact changes" 中都没有明确提到定义 `DuplicateGovernanceScope` dataclass 并将其添加到 `DuplicateDecision`。

Slice 3 提到 `TOOL_CALL_GOVERNED` payload 的 `duplicate_scope`，但这是 payload dict 字段，不是 `DuplicateDecision` 上的 typed dataclass。

**影响**: implementation agent 可能跳过 `DuplicateGovernanceScope` 的定义，或者在 `DuplicateDecision` 上直接加 `attempt_id` 字段而不是使用 dataclass，导致 section 6 的设计意图未完全落地。

**建议**: 在 Slice 1 的 "Exact changes" 中加入 `DuplicateGovernanceScope` dataclass 的定义和到 `DuplicateDecision` 的集成。

### 4-未修复-non-blocking-`tool_duplicate_governance.py` 不应标记为可选

**位置**: plan section 5, section 8 Slice 1

**问题**: plan section 5 将 `dayu/host/tool_duplicate_governance.py` 标记为"新增可选模块"。但 section 7.10 明确指出 import cycle 风险：`HostToolingOptions`（在 `tooling.py`）需要 `DuplicateGovernancePolicy`，而 `DuplicateGovernancePolicy` 当前在 `tool_runtime.py`。`tooling.py` 已经 import `tool_runtime.py` 的多个类型（通过 `ToolRuntimeBuildRequest`），如果 `DuplicateGovernancePolicy` 保留在 `tool_runtime.py` 并添加 `messages` 子类型，`tooling.py` 需要 import 新的 `DuplicateGovernanceMessages`，而 `DuplicateGovernanceMessages` 又引用 `DuplicateDecisionKind`（在 `tool_runtime.py`）。这不是循环但增加了 `tooling.py` 对 `tool_runtime.py` 内部类型的依赖。

Section 8 Slice 2 的 stop condition 也说"Stop if adding duplicate policy to `HostToolingOptions` creates an import cycle that cannot be solved without moving policy types to a neutral Host module. The allowed resolution is the new `dayu/host/tool_duplicate_governance.py` module"。

**影响**: 如果 implementation agent 把 `tool_duplicate_governance.py` 当作可选而不创建，可能在 Slice 2 遇到 import 问题后才回退创建，浪费一个 slice iteration。

**建议**: 将 `tool_duplicate_governance.py` 标记为"required if moving policy types"，并在 Slice 1 中决定是否从一开始就使用该模块。

### 5-未修复-non-blocking-section 7.7 validation helper 未指定实现

**位置**: plan section 7.7

**问题**: "Duplicate governed candidates and reuse candidates must only reference prior event refs whose top-level `attempt_id` equals current `ToolRuntimeExecutionScope.attempt_id`. Add a validation helper if needed." 这个 "if needed" 不确定。当前代码是否已经验证 prior refs 的 `attempt_id`？如果没有，implementation agent 需要知道在哪里添加这个 helper、它的签名是什么、以及谁调用它。

**影响**: 低风险。如果 prior refs 来自同一 `_AttemptDuplicateGovernanceState` 实例（已经是 attempt-local），则 prior refs 天然属于同一 Attempt，validation 可能不需要。但 plan 应该明确这一点。

**建议**: 将 "if needed" 改为明确判断："由于 `_AttemptDuplicateGovernanceState` 是 attempt-local，prior refs 天然属于当前 Attempt；validation helper 仅在 future cross-Attempt retrieval 场景需要。本 work unit 不实现该 helper。"

### 6-未修复-non-blocking-`DuplicateGovernanceMessages` 默认值未定义

**位置**: plan section 6

**问题**: `DuplicateGovernanceMessages` 定义了 7 个字段（`allow`, `reuse`, `hint`, `require_justification`, `hard_stop`, `attempt_scope_diagnostic`, `prior_accept_missing`）和一个 `message_for` 方法。但 plan 未说明：
- 这些字段是否有默认值（`field(default_factory=...)` 还是 required）
- 默认值是什么（当前 `_duplicate_message()` 的硬编码文本？空字符串？）
- 空字符串是否合法（`__post_init__` 是否校验非空）

Section 8 Slice 2 的 test_tooling_options 要求覆盖 "custom message policy" 和 "validation of empty message/argument names"，暗示空消息应该被校验拒绝。但 plan 未明确默认消息文本。

**影响**: 低风险，但 implementation agent 可能需要自行决定默认值，导致不一致。

**建议**: 在 section 6 中补充 `DuplicateGovernanceMessages` 的默认值策略（使用当前 `_duplicate_message()` 的文本作为默认值，或标记为 required 无默认值）。

## 总结

| 类别 | 数量 |
|---|---|
| blocking findings | 2 |
| non-blocking findings | 4 |

blocking findings 要求在进入 implementation 前解决：in-flight 并发协调的完整契约定义和测试可构造性验证。
