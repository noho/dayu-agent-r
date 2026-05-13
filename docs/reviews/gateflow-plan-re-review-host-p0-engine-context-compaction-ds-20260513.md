# Plan Re-Review — Host Phase 0 / P0 Engine Context Compaction Event 语义前置

- re-review gate: plan re-review
- re-reviewer: AgentDS
- date: 2026-05-13
- re-review target: `docs/host/phase0-engine-context-compaction-plan.md` (revised plan, post plan fix)
- controller adjudication: `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`
- plan fix artifact: `docs/reviews/gateflow-plan-fix-host-p0-engine-context-compaction-20260513.md`
- source review artifacts:
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md`
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`
- conclusion: **pass** — 0 unfixed findings, 0 new blockers

## 0. Re-Review Scope

本次 re-review 仅验证 controller adjudication 中 accepted findings A1-A7 的 plan fixes。不重新打开 deferred D1（reason 字符串自由度），不重新评审 plan 其它部分，不修改代码。

## 1. Finding-by-Finding Verification

### A1-accepted-MiMo-003: Runner HTTP overflow event-path 测试需显式化

**controller required**: 将 Runner HTTP context overflow 回归测试从条件项改为 P0-S1 明确测试要求。

**verification**:
- revised plan §3.1 必然候选 (line 96-98): `test_http_error_event.py` 已从条件候选升为必然候选，明确要求 "补 Runner HTTP context overflow event-path 回归测试，确认 HTTP 400 context overflow body 产出 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、保留 `provider_request_id`，并以 `RunnerDoneData(FinishReason.ERROR)` 收口"。
- §6 P0-S1 Allowed files (line 230): 已列入。
- §6 P0-S1 Exact allowed changes (line 243-244): 明确要求增加该测试及具体断言。
- §6 P0-S1 Tests (line 257): 验证命令包含该测试。
- §7 Validation commands (line 335-336): 包含该测试。
- §6 P0-S1 Expected assertions (line 266): Runner HTTP overflow event-path 断言已列出。

**status**: **fixed**。Runner HTTP context overflow event-path 测试已成为 P0-S1 明确要求，非条件项。

### A2-accepted-MiMo-004: P0-S1 completion signal 必须显式包含 pyright

**controller required**: P0-S1 completion signal 增加 `source .venv/bin/activate && pyright` 通过。

**verification**:
- §6 P0-S1 Completion signal (line 270): "`source .venv/bin/activate && pyright` 通过。" 已作为 P0-S1 completion signal 第三条。

**status**: **fixed**。pyright 已显式纳入 P0-S1 completion signal。

### A3-accepted-DS-002: Phase 5 与 Phase 10 对 budget_state=None 的责任切分需明确

**controller required**:
- residual risk destination 精确拆分为 Phase 5 ingest validation 与 Phase 10 Context Governance semantic interpretation。
- P0 closeout 必须把该切分回写 implementation-control 追踪区。

**verification**:
- §11 Residual Risk Tracking Destination (line 452-456):
  - "Host reactive ingest validation 对 `budget_state=None` 的结构接受：deferred to Phase 5 dispatch / reactive failure closeout。Phase 5 owns EngineEvent ingest validation，必须接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref。"
  - "Host Context Governance semantic interpretation：deferred to Phase 10 Context Governance / Compaction。Phase 10 owns `budget_state=None` 的治理语义，必须在 Engine overflow budget unknown 时使用 Host estimator / policy 生成 before / after budget refs，并决定 compact / recovery。"
- §11 (line 458): "P0 closeout 必须把 Phase 5 / Phase 10 的上述责任切分回写 `docs/host/implementation-control.md` 追踪区。"
- §6 P0-S2 Expected assertions (line 318-319): 明确 "Phase 5 负责 EngineEvent ingest validation 接受 `budget_state=None`；Phase 10 负责在 Engine overflow budget unknown 时用 Host estimator / policy 生成 before / after budget refs 并决策 compact / recovery。"

**status**: **fixed**。责任切分已精确到 Phase 5 ingest validation vs Phase 10 semantic interpretation，P0 closeout 回写要求已明确。

### A4-accepted-DS-003: Sentinel 搜索需补充多行构造防线

**controller required**:
- sentinel 搜索补充多行构造检查。
- implementation report 说明多行构造检查结果。
- 生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。

**verification**:
- §6 P0-S1 Completion signal (line 271-272): "implementation report 必须记录多行构造检查结果，至少包括对 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照` 的搜索与人工核对结论。"
- §7 Sentinel search command (line 355): `rg -n "ContextBudgetSnapshot\\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests docs README.md`
- §7 (line 358): implementation report 必须说明多行构造检查结果。
- §6 P0-S2 Tests/validation (line 311-312): 文档 slice 后同样运行 sentinel 检查并记录多行构造检查结果。

**status**: **fixed**。多行构造检查防线已补足，覆盖 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照` 六个 pattern，并要求 implementation report 说明人工核对结论。

### A5-accepted-DS-004: Contract test 应覆盖 None 与真实 snapshot 两条合法路径

**controller required**:
- P0-S1 contract tests 同时覆盖 `budget_state=None` 合法与 `ContextBudgetSnapshot(1000, 500, 1500)` 合法。
- 文档说明 `0/0/0` 不得作为 unknown sentinel；不要求 dataclass 类型级禁止零值。

**verification**:
- §6 P0-S1 Exact allowed changes (line 241-242):
  - "更新或新增测试断言 `ContextCompactionRequestedData(..., budget_state=None, ...)` 合法。"
  - "更新或新增测试断言 `ContextCompactionRequestedData(..., budget_state=ContextBudgetSnapshot(1000, 500, 1500), ...)` 这类真实 snapshot 合法。"
- §4.1 (line 146): "P0 不要求在 `ContextBudgetSnapshot` dataclass 类型级禁止零值；禁止的是把 `0/0/0` 当作 unknown sentinel。若未来调用方能证明某个真实 snapshot 数值为零，应按真实 snapshot 语义处理，而不是 unknown。"
- §6 P0-S1 Expected assertions (line 260-262):
  - "`budget_state=None` 是合法 unknown。"
  - "`budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 这类真实 snapshot 合法。"
  - "`ContextBudgetSnapshot(0, 0, 0)` 不得作为 unknown sentinel，但本 P0 不要求 dataclass 类型级禁止零值。"

**status**: **fixed**。两条合法路径均已要求覆盖，零值不是类型级非法，sentinel 语义禁止已明确。

### A6-accepted-DS-005: P0-S2 需目检 runner_events docstring

**controller required**:
- `dayu/engine/contracts/runner_events.py` 作为 P0-S2 可选检查文件。
- 若无需修改，implementation artifact 记录 `checked, no change needed`。

**verification**:
- §6 P0-S2 Allowed files (line 286): `dayu/engine/contracts/runner_events.py` 已列为 P0-S2 允许文件。
- §6 P0-S2 Exact allowed changes (line 297): "检查 `dayu/engine/contracts/runner_events.py` 中 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 等相关 docstring。若没有旧 `0/0/0`、Engine budget governance 或 Engine compact/retry 暗示，不修改该文件，并在 implementation artifact 记录 `checked, no change needed`。"
- §6 P0-S2 Expected assertions (line 317): "`dayu/engine/contracts/runner_events.py` 已检查；如未修改，implementation artifact 写明 `checked, no change needed`。"

**status**: **fixed**。runner_events.py docstring 目检已纳入 P0-S2，`checked, no change needed` 记录要求已明确。

### A7-accepted-MiMo-002-and-DS-006: dayu/README.md 应精化已有术语而非机械追加

**controller required**:
- `dayu/README.md` 操作从 "补充" 改为 "精化已有 Context Governance 术语条目"。
- 只说明当前边界，不把未来 Phase 10 写成已完成。

**verification**:
- §3.3 (line 119): "应精化已有 Context Governance 术语条目，加入 budget unknown 边界。不要机械追加重复段落，不要把未来 Phase 10 写成已完成。"
- §6 P0-S2 Exact allowed changes (line 298): "精化 `dayu/README.md` 已有 Context Governance 术语条目：只说明当前边界，即 Engine reactive event 在 provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator / policy；不得机械追加重复段落，不得写成 Phase 10 已完成。"
- §8 (line 382-383): "只精化已有 Context Governance 术语条目，避免冗余，不把未来 Phase 10 写成已完成。"

**status**: **fixed**。三处均使用"精化"措辞，明确禁止机械追加和把 Phase 10 写成已完成。

## 2. Cross-Cutting Verification

### 2.1 不夹带 Host implementation code

§2 Non-Goals 明确列出："不修改 Host implementation code"。§5.2 Ownership Boundaries (line 201): "Host 语义以 `docs/host/design.md` 为准；P0 不能重新定义 Host 架构。" §9 Stop conditions (line 410): "任何实现需要修改 Host implementation code" 为 stop condition。

**验证**: 不夹带。

### 2.2 不夹带 Engine proactive governance / compact / retry / tokenizer / policy

§2 Non-Goals 逐一排除：
- "不让 Engine compact、retry、重构 messages、计算 threshold、调用 tokenizer 或持久化 compact artifact。"
- "不把 proactive context governance 放进 Engine。"
- "不实现 Host compact policy、budget estimator、RunInputBuilder compact provider、EventLog canonical compact events 或 recovery state machine。"

§4.3 (line 178): "Engine context overflow 不属于 Engine compact / retry。"

§9 Stop conditions (line 411-412): "任何实现把 proactive context governance 放进 Engine"、"任何实现要求 Engine compact、retry、估算 provider-aware budget 或新增 tokenizer" 均为 stop condition。

**验证**: 不夹带。

### 2.3 Residual risk destination 无悬空项

§11 Residual Risk Tracking Destination 逐项归类：

| 风险 | destination | 状态 |
| --- | --- | --- |
| Engine overflow budget unknown 已修复 | `docs/host/implementation-control.md` 追踪区 | ✓ |
| Host reactive ingest validation 对 `budget_state=None` 的结构接受 | Phase 5 | ✓ |
| Host Context Governance semantic interpretation | Phase 10 | ✓ |
| Host estimator / policy / compact artifact | Phase 10 | ✓ |
| Provider-specific tokenizer adapter | Host later capability | ✓ |
| P0 closeout 责任切分回写 | `docs/host/implementation-control.md` 追踪区 | ✓ |

§11 (line 459): "不得关闭 slice 或 work unit，除非每个 residual risk 都有上述 destination。"

**验证**: 无悬空项。

### 2.4 D1 未被重新打开

D1 (reason 字符串自由度) 保持 controller adjudication 的 `deferred-with-owner` 状态。revised plan §10 Non-Blocking Risks #1 保持原风险描述，归属 Phase 5 / Phase 10。plan fix artifact 明确声明 "未处理 deferred finding D1"。

**验证**: D1 未被重新打开，未引入新 blocker。

## 3. New Blocker Check

逐项检查 plan fix 是否引入新问题：

- A1 将条件项改为必做项：不改变 scope，只在 P0-S1 已有文件边界内增加测试要求。无新风险。
- A2 pyright 纳入 completion signal：强化验证，不改变代码范围。无新风险。
- A3 责任切分精确化：澄清 Phase 5/10 边界，减少后续 phase 歧义。无新风险。
- A4 多行 sentinel 搜索：强化 defense-in-depth，不改变代码。无新风险。
- A5 两条合法路径覆盖：补充测试覆盖，不改变类型系统。无新风险。
- A6 runner_events docstring 目检：被动检查，不强制修改文件。无新风险。
- A7 精化措辞：降低文档冗余，不改变语义边界。无新风险。

**结论**: 无新增 blocker。

## 4. Re-Review Conclusion

**结论: pass**

7 个 accepted findings (A1-A7) 全部 fixed。revised plan 仍不夹带 Host implementation code、Engine proactive governance、compact / retry / tokenizer / policy。residual risk destination 无悬空项。D1 未被重新打开。无新增 blocker。

revised plan 可直接进入 user confirmation。

## 5. Controller Decision Status

controller decision status: **pending-controller-decision**

## 6. Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p0-engine-context-compaction-ds-20260513.md`
