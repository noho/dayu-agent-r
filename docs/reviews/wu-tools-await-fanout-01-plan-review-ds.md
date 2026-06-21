# WU-TOOLS-AWAIT-FANOUT-01 Plan Review — AgentDS

## Review Metadata

| 项目 | 内容 |
|---|---|
| Work unit | WU-TOOLS-AWAIT-FANOUT-01 |
| GitHub Issue | #111 |
| Gate | Plan review |
| Plan artifact | `docs/host/wu-tools-await-fanout-01-plan.md` |
| Review agent | AgentDS |
| Timestamp | 2026-06-21T14:04:04+08:00 |
| Design sources | `docs/host/design.md`, `docs/engine/design.md` |
| Control source | `docs/host/issues-implementation-control.md` |
| Review focus | Plan correctness, root cause, lightweight constraint, slice, tests |

## Review Decision

**Decision: pass-with-findings**

Blocking findings: 0
Non-blocking findings: 3 (see below)
Accepted-risk candidates: Engine alias diagnostic ambiguity, `record_awaiting_accepted` best-effort failure

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 | Root cause: `_accept_awaiting` doesn't record duplicate terminal → `finally` marks durable missing → waiter re-competes | **Confirmed** | `tool_runtime.py:2708-2711` (`del duplicate_request`), `tool_runtime.py:2422-2426` (finally check) |
| A2 | Current `_InFlightDuplicateState` has no `AWAITING_ACCEPTED` state | **Confirmed** | `tool_duplicate_governance.py:40-45` — only `OWNER_RUNNING`, `ACCEPTED`, `DURABLE_MISSING` |
| A3 | `host_wait_records_one_active_per_run` partial unique index constrains single active wait per Run | **Confirmed** | `durable/schema.py:1098-1102` |
| A4 | `_engine_awaiting_record_mismatch` requires `tool_call_id` equality | **Confirmed** | `engine_ingest.py:3699-3703` |
| A5 | `_resume_wait_message_from_current_start` only projects one accepted wait result | **Confirmed** | `run_input.py:3984-4030` |
| A6 | Plan does not expand durable schema or public contract | **Confirmed** | Plan §7 — no schema change, no public contract change |
| A7 | Attempt-local memory fanout suffices — cross-Attempt durable duplicate ledger is not a correctness prerequisite | **Confirmed** | Design: Attempt duplicate index is attempt-scoped by design; Run recovery creates new Attempt |
| A8 | `DuplicateGovernancePort` protocol supports adding `record_awaiting_accepted` | **Confirmed** | Protocol in `tool_duplicate_governance.py:287-331` — new method is backward-compatible |

## Findings

### F01 — 未修复 — 中 — Engine alias confirmation 路径实现时决策不完整

- **位置**: Plan §8 "Engine Awaiting Confirmation" (lines 213-229), §6 affected file `engine_ingest.py`
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: Plan 说 "如果 Engine 当前顺序永远只会产出 owner record，不需要 alias confirmation 改动，也必须保留测试证明 waiter 不会导致第二 wait record；但 plan 推荐补最小 alias diagnostic，以免 future batch/concurrency 路径回归"（lines 229-230）。
- **反例/失败场景**: 当 waiter 通过 fanout 返回 owner 的 `ToolAwaitingOutcome` 后，Engine 仍可能为 waiter 的 `tool_call_id` 生成独立的 `TOOL_AWAITING` EngineEvent。该 event 进入 `_confirm_waiting_engine_event` → `_validate_waiting_confirmation` → `_engine_awaiting_record_mismatch`，当前代码 `engine_ingest.py:3699-3703` 严格要求 `record.call.tool_call_id != wait_record.tool_call_id` 匹配，waiter 的 `tool_call_id` 必然不匹配 owner 的 wait record，返回 `"awaiting_tool_identity_mismatch"`，导致 Engine event 被拒绝。
- **为什么有问题**: Plan 在此处的 "不需要 alias confirmation 改动" 断言与代码证据冲突——代码证据显示当前 Engine ingest 严格校验 `tool_call_id` 必须等于 wait record owner 的 `tool_call_id`。Plan 没有说明 Engine 在什么条件下不会为 waiter 产出 event，也没有给出如果 Engine 确实产出 waiter event 时的具体修改方案。
- **直接证据**:
  - `engine_ingest.py:3699-3703`：`record.call.tool_call_id != wait_record.tool_call_id` 严格匹配
  - `engine_ingest.py:3336`：`len(active_waits) != 1` 拒绝多 active wait
  - Plan lines 229-230 将决策推迟到实现阶段
- **影响**: 实施 Agent 可能在实现时发现 Engine 需要修改，触发 stop condition，导致返工。但 plan 的 stop condition（§12 line 435 "若 Engine contract 必须新增字段才能区分 owner 与 alias，必须停止并交回总控裁决"）覆盖了此场景。
- **建议改法和验证点**:
  - Plan 应在 §8 Engine 部分显式列出实现时的第一步验证：确认 Engine 在 waiter fanout 返回 owner outcome 后是否产出 `TOOL_AWAITING` / `RUN_SUSPENDED` event。
  - 如果 Engine 不产出额外 event，实现只需保留测试证明此行为并保持现状。
  - 如果 Engine 产出额外 event，implementation 必须停止，因为需要修改 Engine ingest 的 `tool_call_id` 匹配逻辑、`awaiting_records` 长度校验或新增 alias 诊断路径——这些可能触及 "Engine contract 必须新增字段" 的 stop condition。
  - 对应测试已在 §10 `test_engine_ingest_mapping.py` 覆盖此场景：`"alias / fanout record 不创建第二 wait record"`、`"mismatched alias 只产生 diagnostic"`。
- **修复风险**: 低 — plan 已有 stop condition，实施时判断即可
- **严重程度**: 中 — 非阻塞，但需实施 Agent 明确第一步验证

**Controller note**: 建议 accepted-candidate。该 finding 不阻塞 plan 进入 implementation gate，但 implementation agent 必须按 §12 stop condition 在第一步验证 Engine event 产出行为。如果 Engine 产出额外的 waiter event，必须停止。

---

### F02 — 未修复 — 低 — `DuplicateDecision` 新增 `prior_awaiting_outcome` 与 `prior_outcome` 类型冲突未澄清

- **位置**: Plan §7 "Internal Contract" (lines 159-162)
- **问题类型**: 契约缺失
- **当前写法**: Plan 建议 `DuplicateDecision` 新增可选字段 `prior_awaiting_outcome: ToolAwaitingOutcome | None` 和 `prior_wait_id: str | None`。
- **反例/失败场景**: `DuplicateDecision` 当前有 `prior_outcome: ToolExecutionOutcome | None`（`tool_duplicate_governance.py:279`）。`ToolAwaitingOutcome` 是否继承自 `ToolExecutionOutcome`？如果不是，`AWAITING_FANOUT` 决策的 `prior_outcome` 应该设为 `None`（因为 awaiting 不是 completed result 可复用），实际 waiting 信息通过 `prior_awaiting_outcome` 字段传递。
- **为什么有问题**: Plan 没有说明 `AWAITING_FANOUT` 决策中 `prior_outcome` 与 `prior_awaiting_outcome` 的互斥关系（一个为 `None` 时另一个有值），也没有说明两个字段的语义边界。实施 Agent 可能在两个字段中重复填充或做出不一致选择。
- **直接证据**: `tool_duplicate_governance.py:276-284` 当前 `DuplicateDecision` 定义，`prior_outcome` 为 `ToolExecutionOutcome | None`。
- **影响**: 轻微 — 实施 Agent 需要自行裁决字段语义，但类型系统可防止大错误
- **建议改法和验证点**: Plan §7 应补充说明：`AWAITING_FANOUT` 决策中 `prior_outcome=None`（awaiting 不是 completed result），实际 waiting 引用通过 `prior_awaiting_outcome` 和 `prior_wait_id` 传递。两者互斥：普通 completed duplicate 用 `prior_outcome`，awaiting fanout 用 `prior_awaiting_outcome`。
- **修复风险**: 低
- **严重程度**: 低

**Controller note**: 建议 accepted-candidate。实施 Agent 可自行裁决字段语义。

---

### F03 — 未修复 — 低 — 并发 N (>2) waiter 场景无明确测试断言

- **位置**: Plan §10 "Tests / Validation Commands" (lines 341-367)
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求 "并发同 key awaiting 调用只执行一次业务 callable" 和 "awaiting accept port 只收到一次 candidate"（lines 348-349）。
- **反例/失败场景**: 当 3+ 个调用者同时竞争同一 duplicate key 时，owner 被 accepted，waiter 1 和 waiter 2 都应 fanout 到同一个 owner wait。当前测试描述只覆盖 2 个调用者（owner + 1 waiter）。N-waiter fanout 在状态机中的行为（`AWAITING_ACCEPTED` in-flight entry 不 pop，持续服务后续 waiter）应被验证。
- **为什么有问题**: `AWAITING_ACCEPTED` in-flight entry 在 `decide_duplicate` 中不被 pop，后续 waiter 会继续命中同一 entry。如果实现错误地在第一次 waiter fanout 后 pop 了 in-flight entry，第 3+ waiter 会误以为没有 in-flight owner 并重新竞争。当前 plan 的测试断言未覆盖此场景。
- **直接证据**: Plan §10 `test_toolruntime_duplicate_governance.py` assertions only mention "owner `record_awaiting_accepted` 后 waiter 得到 `AWAITING_FANOUT`" — 单数 waiter。
- **影响**: 轻微 — 3+ waiter 并发在典型 LLM 工具调用中不常见，但如果发生会导致第二 external job
- **建议改法和验证点**: 在 `test_toolruntime_duplicate_governance.py` 增加 "owner accepted awaiting 后多个 waiter 均得到 `AWAITING_FANOUT`，且无一重新竞争 owner" 的 3-caller 断言。
- **修复风险**: 低 — 新增一条测试即可
- **严重程度**: 低

**Controller note**: 建议 accepted-candidate。实施 Agent 可在 focused test 中补充 3-caller 场景。

---

## Slice Principle Assessment

Plan 提出 1 个 implementation slice：`S1 轻量 awaiting fanout 闭环`。

**评估：通过。**

对照 Control Doc Slice 切分原则：

| 原则 | 评估 |
|---|---|
| 语义闭环 | ✅ S1 包含 duplicate governance state、ToolRuntime return path、Engine confirmation diagnostic、RunInputBuilder resume wording — 共同构成 owner/waiter fanout 状态机闭环 |
| 依赖顺序 | ✅ 不依赖其他 WU；所有变更在同一闭包内 |
| 可独立验证 | ✅ §10 定义了完整验证矩阵：pytest + pyright + specific assertions |
| 代码范围合理 | ✅ 4 个生产模块 + ~6 测试文件，均为小型增量变更 |
| 不产生孤立半成品 | ✅ S1 done signal 覆盖全部 5 个行为断言 |
| 非机械按模块拆分 | ✅ Plan §9 明确解释了为什么不应按文件拆分：单独实现 duplicate state 而不处理 Engine/resume material 会留下半成品 |

Plan §9 的切分依据论述充分：本 WU 是小型 execution-correctness cleanup，duplicate governance state、ToolRuntime return path、Engine confirmation diagnostic、RunInputBuilder resume wording 共同构成一个行为闭环。单独实现任何一部分都会留下不完整的语义——例如单独修 duplicate state 而不处理 Engine，会让 waiter 有内存 fanout 但恢复语义缺失。

对照 Control Doc "小型跨模块 cleanup 的默认切分上限是 3 个 implementation slices" 规则：本 WU 为 1 个 slice，在合理范围内。

**无过度拆分，无过度合并。**

## Lightweight Constraint Assessment

Plan §5 明确声明轻量方案可满足 #111，并详细解释了为什么不需要重型 durable await 设计。

**评估：通过。**

逐项对照：

| 约束 | 状态 | 证据 |
|---|---|---|
| 不新增重型 durable follower table | ✅ | Plan §7 — 不修改 `host_wait_records` schema |
| 不新增 durable duplicate ledger | ✅ | Plan §5 — "follower / alias 不进入 `host_wait_records`" |
| 不新增跨 Attempt duplicate table | ✅ | Plan §5 — fanout entry 只在当前 Attempt 内存中 |
| 不新增跨进程 waiter queue | ✅ | Plan §5 — attempt-local in-memory 索引 |
| 不新增 public await lifecycle contract | ✅ | Plan §7 — "不新增或修改 Host public contract" |
| 不实现 #129 two-phase activation | ✅ | Plan §2 — 列为 non-goal |
| 保留薄 wait record + lightweight observation handle | ✅ | Plan §5 — "durable truth 仍只有 owner 的 wait record" |
| 在 attempt-local duplicate governance 上补齐 fanout | ✅ | Plan §7 — 新增 `_InFlightDuplicateState.AWAITING_ACCEPTED` + `DuplicateDecisionKind.AWAITING_FANOUT` |

Plan §5 的 "为什么不回到重型 durable await 设计" 论证充分：
1. 当前问题只发生在同一 Attempt 的 in-flight duplicate window（正确）
2. Host 已有 awaiting accept ack、wait record、resolve_wait、late rejection、WAITING cancel 和 resume Attempt 机制（正确）
3. `host_wait_records` 已通过 unique active wait per Run 约束 single wait owner（正确）
4. Run 恢复后创建新 Attempt，不继承旧 Attempt duplicate index（符合设计真源）
5. #129 的 two-phase activation 修不同窗口（正确）

## Missing Tests / Validation Gaps

| # | Gap | Severity | Plan Coverage |
|---|---|---|---|
| G1 | 3+ concurrent caller fanout 测试（见 F03） | 低 | Plan 只要求 2-caller（owner + 1 waiter），未覆盖 N-waiter |
| G2 | `record_awaiting_accepted` 失败后 waiter 回退到 re-compete 路径的集成测试 | 低 | Plan §8 提到 best-effort，但 §10 无对应断言 |
| G3 | Engine 在 waiter fanout 返回 owner outcome 后是否产出 `TOOL_AWAITING` event 的行为测试 | 中 | Plan §10 `test_engine_ingest_mapping.py` 覆盖了 "alias / fanout record 不创建第二 wait record"，但前置依赖 Engine 实际行为 |

## Residual Risks

| Risk | Owner / Destination | Note |
|---|---|---|
| R1: Engine 为 waiter 产出额外 `TOOL_AWAITING` event | WU-TOOLS-AWAIT-FANOUT-01 implementation gate / Controller | Plan stop condition §12 覆盖；implementation agent 第一步验证后决定是否停止 |
| R2: `record_awaiting_accepted` best-effort 失败后 waiter 重新竞争 | Accepted | Plan 已明确这是可接受的回退：waiter 重新竞争 owner，回到当前行为，不产生数据损坏 |
| R3: Resume material "shared duplicate result" 文本是否足够让模型理解不重复调用 | WU-TOOLS-AWAIT-FANOUT-01 implementation gate | 需要 AgentMiMo 在 LLM-facing 文本 review 中确认自解释性和不泄漏约束 |
| R4: `AWAITING_FANOUT` 决策的 `DuplicateDecision` 字段语义互斥性 | Accepted (F02) | 轻微，实施 Agent 可自行裁决 |

## Required Follow-up for Controller

1. **裁决 F01** (Engine alias confirmation 路径): 接受为 accepted-candidate，不阻塞 plan gate，但 implementation agent 必须在第一步验证 Engine event 产出行为。
2. **裁决 F02** (`prior_awaiting_outcome` / `prior_outcome` 字段互斥): 接受为 accepted-candidate，implementation agent 自行裁决。
3. **裁决 F03** (3+ waiter 测试): 接受为 accepted-candidate，implementation agent 可选补 3-caller 测试。
4. **Implementation gate 前确认**: 确保 AgentMiMo 的 plan review 也从 LLM-facing resume material 和 Engine contract 角度完成了 review。
5. **No blocking findings** — plan 可进入 implementation gate，但 implementation agent 必须严格遵循 §12 stop conditions。

## Validation Performed

Plan gate 限定的只读核对命令（来自 plan §10）：

```bash
pwd
rg --files docs dayu tests | rg '...'  # 确认关键文件存在
git status --short                       # 确认 dirty state 为预期 plan/control artifacts
git branch --show-current                # 确认在 phase/wu-tools-await-fanout-01
```

直接代码证据核对：
- `dayu/host/tool_duplicate_governance.py` — 完整读取
- `dayu/host/tool_runtime.py` — `_execute_one` (lines 2264-2463), `_accept_awaiting` (lines 2637-2759)
- `dayu/host/waiting.py` — 完整读取
- `dayu/host/durable/schema.py` — `host_wait_records` DDL (lines 1098-1102)
- `dayu/host/engine_ingest.py` — `_validate_waiting_confirmation` (lines 3303-3364), `_engine_awaiting_record_mismatch` (lines 3671-3721)
- `dayu/host/run_input.py` — `_resume_wait_message_from_current_start` (lines 3984-4030)

Plan 和 control doc 已完整读取。

Tests 和 pyright 未在 plan gate 运行（plan §10 明确说明 implementation gate 负责）。
