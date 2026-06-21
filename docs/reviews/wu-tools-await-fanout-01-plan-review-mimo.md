# WU-TOOLS-AWAIT-FANOUT-01 Plan Review — AgentMiMo

## Review Target

- Plan artifact: `docs/host/wu-tools-await-fanout-01-plan.md`
- Work unit: WU-TOOLS-AWAIT-FANOUT-01 / GitHub Issue #111
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Review Decision

**pass-with-nits**

## Assumptions Tested

1. **Root cause 成立**: `_accept_awaiting` 成功后未设置 `duplicate_terminal_recorded=True`，导致 `finally` 块误记 `DURABLE_MISSING`，waiter 重新竞争 owner。→ **已由代码证实**。
2. **轻量方案可满足 #111**: 不需要 durable schema 或 public contract 扩张。→ **成立**。
3. **当前 duplicate state machine 缺少 awaiting accepted terminal**: `_InFlightDuplicateState` 只有 `OWNER_RUNNING`、`ACCEPTED`、`DURABLE_MISSING`。→ **已由代码证实**。
4. **Engine confirmation 只读 durable truth**: `_validate_waiting_confirmation` 只确认 Host accepted wait record，不创建 wait record。→ **已由代码证实**。
5. **`host_wait_records` 单 active wait per Run 约束存在**: `host_wait_records_one_active_per_run` partial unique index。→ **已由 schema 证实**。
6. **Engine sequential batch processing**: Engine agent loop 在一个 batch 中顺序处理 tool calls，owner 返回 `ToolAwaitingOutcome` 后立即产出 `run_suspended` 终态。→ **已由代码证实，且与 plan 主场景描述存在张力**。

## Findings

### 01-未修复-中-AWAITING_FANOUT 在当前 Engine 架构下不可达

- **位置**: §4 Root Cause, §8 Waiter Fanout, §9 Slice S1
- **问题类型**: 代码证据与场景描述不一致
- **当前写法**: Plan 假设 owner 和 waiter 在同一 Attempt 内可同时存在，waiter 命中 `AWAITING_ACCEPTED` 后走 `AWAITING_FANOUT` 路径。§4 root cause 描述 "waiter 重新成为 owner，进而可能重复执行业务 callable 与 external job"。
- **反例/失败场景**: Engine agent loop（`dayu/engine/agent.py`）对 batch 内 tool calls 按 `index_in_iteration` 顺序处理。当 owner 返回 `ToolAwaitingOutcome` 时，agent loop 立即产出 `tool_awaiting` + `run_suspended` 终态并结束本次 run（Engine design §12: "对包含 awaiting 的 batch，先产出同批普通 outcome 的 `tool_result_accepted`，再产出 `tool_awaiting` 和 `run_suspended`，结束本次 run"）。因此：
  - **同一 batch**: owner 先执行并返回 `ToolAwaitingOutcome` → agent loop 产出 `run_suspended` → waiter 从未被执行。
  - **同一 Attempt 不同 batch**: owner batch 产出 `run_suspended` → Attempt 进入 `SUSPENDED` → waiter batch 无法在同 Attempt 内执行。
  - **不同 Attempt**: wait resolve 后创建新 Attempt → duplicate governance 是 attempt-local → 新 Attempt 内存状态为空 → waiter 看不到 owner 的 `AWAITING_ACCEPTED`。
- **为什么有问题**: Plan 的主场景（owner 和 waiter 在同一 Attempt 内、waiter 命中 `AWAITING_FANOUT`）在当前 Engine 行为下无法发生。`AWAITING_FANOUT` 逻辑不会被触发。但 `record_awaiting_accepted` 修复 `duplicate_terminal_recorded` 缺口仍然正确且必要。
- **直接证据**:
  - `dayu/host/tool_runtime.py:2354-2366`: owner 返回 `ToolAwaitingOutcome` 后直接 return，不进入后续 waiter 处理。
  - Engine design §12: "awaiting 路径不产出 `tool_calls_batch_done`"，"结束本次 run"。
  - `dayu/host/tool_duplicate_governance.py:361`: `InMemoryAttemptDuplicateGovernance` 是 attempt-local。
- **影响**: Implementation agent 可能花精力实现 `AWAITING_FANOUT` 分支，但该分支在当前架构下无法被测试覆盖（需要修改 Engine 才能触发）。测试矩阵中 "并发同 key awaiting 调用只执行一次业务 callable" 等断言需要 Engine 修改才能验证。
- **建议改法和验证点**:
  1. Plan 应明确说明 `AWAITING_ACCEPTED` / `AWAITING_FANOUT` 是防御性状态机改进，当前 Engine 架构下不会被触发。
  2. Plan 应说明 `record_awaiting_accepted` 修复 `duplicate_terminal_recorded` 缺口是本 WU 的核心实际修复。
  3. 测试应聚焦于验证 `record_awaiting_accepted` 后 `duplicate_terminal_recorded=True`、`finally` 不再误记 `DURABLE_MISSING`。
  4. `AWAITING_FANOUT` 分支的端到端测试可标记为 `xfail` 或 `skip`，注明需要 Engine batch 处理变更。
  5. 若 plan 认为 Engine 需要同步修改才能让 `AWAITING_FANOUT` 生效，应明确在 plan 中说明，或作为后续 WU。
- **修复风险**: 低 — 只需澄清 plan 描述，不需改变技术方向。
- **严重程度**: 中 — 不阻塞实施，但会导致 implementation agent 对场景理解偏差，浪费精力实现不可达分支。

**Status**: accepted recommendation candidate

### 02-未修复-低-DuplicateDecision contract 新增字段与 prior_outcome 类型关系未明确

- **位置**: §7 Internal Contract, §8 Waiter Fanout
- **问题类型**: 契约规格不够明确
- **当前写法**: Plan 提出 `DuplicateDecision` 新增可选字段 `prior_awaiting_outcome: ToolAwaitingOutcome | None` 和 `prior_wait_id: str | None`。
- **反例/失败场景**: 当前 `DuplicateDecision` 已有 `prior_outcome: ToolExecutionOutcome | None` 字段（`tool_duplicate_governance.py:279`）。`ToolAwaitingOutcome` 是 `ToolExecutionOutcome` 的子类型（封闭联合成员）。Implementation agent 可能困惑：为何不复用 `prior_outcome` 字段？新增字段与 `prior_outcome` 的互斥关系是什么？
- **为什么有问题**: 如果 `AWAITING_FANOUT` 决策同时设置 `prior_outcome` 和 `prior_awaiting_outcome`，语义会混乱。如果只设置 `prior_awaiting_outcome`，`prior_outcome` 应为 `None`，但 plan 未明确说明。
- **直接证据**: `dayu/host/tool_duplicate_governance.py:279`: `prior_outcome: ToolExecutionOutcome | None`。`dayu/contracts/tool_outcome.py`: `ToolAwaitingOutcome` 是 `ToolExecutionOutcome` 封闭联合成员。
- **影响**: Implementation agent 可能做出与 plan 意图不同的类型设计。
- **建议改法和验证点**: Plan 应明确 `AWAITING_FANOUT` 决策中 `prior_outcome=None`，`prior_awaiting_outcome` 和 `prior_wait_id` 承载 fanout 语义。或者说明为何不复用 `prior_outcome`。
- **修复风险**: 低 — 只需补充一句说明。
- **严重程度**: 低 — 不阻塞实施，implementation agent 可自行裁决。

**Status**: accepted recommendation candidate

### 03-未修复-低-Resume material 描述与当前实现不匹配

- **位置**: §8 Resolve Wait Resume Material
- **问题类型**: 实现细节规格不够具体
- **当前写法**: Plan 提出 resume message 追加 "This wait result is the accepted result for the interrupted tool request..." 自解释说明。
- **反例/失败场景**: 当前 `_resume_wait_message_from_current_start`（`run_input.py:3984-4030`）生成的 message 格式为：
  ```
  <RESUME_GUIDANCE_PREFIX>
  A previous interrupted step has an accepted wait result.
  tool_name=...
  resolution_kind=...
  tool_fact_kind=...
  result=...
  ```
  Plan 的 "追加" 操作未说明是在现有内容后追加，还是替换现有内容，或修改 `_RESUME_GUIDANCE_PREFIX`。
- **为什么有问题**: Implementation agent 需要知道具体修改位置和方式。
- **直接证据**: `dayu/host/run_input.py:4018-4030`: 当前 `_resume_wait_message_from_current_start` 的 content 构造逻辑。
- **影响**: Implementation agent 可能以不同方式实现 resume material 扩展，导致 review 时需要额外确认。
- **建议改法和验证点**: Plan 应明确修改 `_resume_wait_message_from_current_start` 的 content 构造，在现有行之后追加自解释 duplicate 说明。建议给出修改后的完整 content 示例。
- **修复风险**: 低 — 只需补充实现细节。
- **严重程度**: 低 — implementation agent 可自行推断。

**Status**: accepted recommendation candidate

### 04-未修复-低-Engine confirmation alias 处理需修改现有校验逻辑

- **位置**: §8 Engine Awaiting Confirmation
- **问题类型**: 实现路径不够明确
- **当前写法**: Plan 提出 "如果 `RUN_SUSPENDED.awaiting_records` 包含多个 records，允许其中一个 owner record 匹配 wait record；其余 records 只能作为 fanout alias diagnostic"。
- **反例/失败场景**: 当前 `_engine_awaiting_record_mismatch`（`engine_ingest.py:3691`）对 `RUN_SUSPENDED` 的检查是 `if len(data.awaiting_records) != 1: return "run_suspended_awaiting_record_count_mismatch"`。Plan 描述的 "允许多个 records" 需要修改此检查。但 plan 的 allowed files 列表包含 `engine_ingest.py`，且 §6 明确 "最小扩展等待 confirmation diagnostic"，所以修改是允许的。只是 plan 未明确说明需要修改哪一行。
- **为什么有问题**: 结合 Finding 01（当前 Engine 不会产出多条 awaiting records），此修改在当前架构下不会被触发。
- **直接证据**: `dayu/host/engine_ingest.py:3691`: `if len(data.awaiting_records) != 1`。
- **影响**: 如果 implementation agent 实现了此修改但无法测试（因为 Engine 不产出多条 records），会留下不可验证的代码。
- **建议改法和验证点**: Plan 应明确说明此修改是防御性的，当前 Engine 不会触发。测试可使用 mock data 直接调用 `_validate_waiting_confirmation` 或 `_engine_awaiting_record_mismatch`。
- **修复风险**: 低。
- **严重程度**: 低 — 与 Finding 01 同源。

**Status**: accepted recommendation candidate

## Slice Principle Assessment

Plan 提出 1 个 implementation slice：`S1 轻量 awaiting fanout 闭环`。

**评估**: 符合 control doc Slice 切分原则。

- 本 WU 是小型 execution-correctness cleanup，代码范围跨 4 个模块但语义属于同一个 contract cleanup。
- Plan 正确指出 "单独实现 duplicate state 而不处理 Engine / resume material，会留下半成品"。
- 1 个 slice 符合 "小型同一语义 cleanup：1-3 个 implementation slices" 的默认切分上限。
- 不存在过度拆分或把不同风险硬塞进一个 slice 的问题。

## Lightweight Constraint Assessment

**评估**: 轻量约束已保留。

- Plan 明确 "不新增重型 wait follower 表、durable duplicate ledger、跨 Attempt durable duplicate table、跨进程 waiter 队列或新的 public await lifecycle contract"。
- `host_wait_records` schema 不变。
- Host / Engine public contract 不变。
- 新增的 `DuplicateDecisionKind.AWAITING_FANOUT`、`DuplicateAwaitingEntry`、`record_awaiting_accepted` 都是 Host internal contract。
- 不重新引入 issue-129 two-phase activation。

## Missing Tests / Validation Gaps

1. **`AWAITING_FANOUT` 端到端测试**: 由于 Finding 01，"并发同 key awaiting 调用只执行一次业务 callable" 等断言在当前 Engine 下无法通过端到端路径触发。建议使用 unit test 直接测试 `InMemoryAttemptDuplicateGovernance` 的 `decide_duplicate` 在 `AWAITING_ACCEPTED` 状态下的行为，以及 `_execute_one` 在命中 `AWAITING_FANOUT` 时的 return path。
2. **`record_awaiting_accepted` 后 `finally` 不误记**: 测试应验证 owner accepted awaiting 后 `duplicate_terminal_recorded=True`，`finally` 块不调用 `record_durable_missing`。
3. **Engine confirmation alias**: 测试可使用 mock `RunSuspendedData` 直接调用 `_engine_awaiting_record_mismatch`，验证多条 records 的处理逻辑。

## Residual Risks

| 风险 | Owner / Destination |
|---|---|
| `AWAITING_FANOUT` 在当前 Engine 架构下不可达，需要 Engine batch 处理变更才能生效 | 本 WU plan 澄清 + 后续 WU（若需要 Engine 修改） |
| `record_awaiting_accepted` 失败只能 best-effort diagnostic | 本 WU（plan §12 已记录） |
| Engine 当前对 waiting confirmation 的 owner `tool_call_id` 匹配较严格 | 本 WU（plan §12 已记录） |

## Required Follow-up for Controller

1. **Finding 01**: Controller 需要裁决 `AWAITING_FANOUT` 分支是否仍应在本 WU 实现（作为防御性改进），还是推迟到 Engine batch 处理变更后的 WU。当前建议：保留 `AWAITING_ACCEPTED` / `AWAITING_FANOUT` 状态机设计作为防御性改进，但 plan 应明确说明当前 Engine 下不可达，测试应聚焦于 `record_awaiting_accepted` 修复 `duplicate_terminal_recorded` 缺口。
2. **Finding 02-04**: 低严重度，implementation agent 可自行裁决，不阻塞 plan。
