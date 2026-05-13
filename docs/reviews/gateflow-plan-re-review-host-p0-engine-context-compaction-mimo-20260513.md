# Gateflow Plan Re-Review — Host Phase 0 / P0 Engine Context Compaction

- work gate: plan re-review
- reviewer: AgentMiMo
- re-review date: 2026-05-13
- reviewed plan: `docs/host/phase0-engine-context-compaction-plan.md` (revised)
- source review artifacts:
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md`
  - `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`
- controller adjudication: `docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-controller-adjudication-20260513.md`
- plan fix artifact: `docs/reviews/gateflow-plan-fix-host-p0-engine-context-compaction-20260513.md`
- controller decision status: **pending-controller-decision**

## Re-Reviewer Conclusion

**PASS — 0 unfix finding, 0 new blocker。**

A1-A7 均已写回 revised plan，且写入质量满足 controller adjudication 要求。revised plan 仍不夹带 Host implementation code、Engine proactive governance、compact / retry / tokenizer / policy。residual risk destination 已精确到 Phase 5 / Phase 10 / P0 closeout，无悬空项。revised plan 可直接交给 implementation agent 实施。

---

## Accepted Findings Verification

### A1 — Runner HTTP context overflow event-path 测试已成为 P0-S1 明确要求

**status: fixed**

controller 要求：将 Runner HTTP context overflow 回归测试从条件项改为 P0-S1 的明确测试要求。

revised plan 验证：

- §3.1 必然候选中 `tests/engine/runners/openai/test_http_error_event.py` 已从条件候选提升为必然候选，与 A1 要求一致。
- §6 P0-S1 Exact allowed changes 写明："在 `tests/engine/runners/openai/test_http_error_event.py` 增加 Runner HTTP context overflow event-path 测试，断言 400 context overflow body 产出 `RunnerHTTPErrorData.error_code is RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、保留 `provider_request_id`、后续 `RunnerDoneData.finish_reason is FinishReason.ERROR`。"
- §6 P0-S1 Expected assertions 第 8 条："Runner HTTP overflow event-path 测试确认 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、`provider_request_id` 与 `RunnerDoneData(FinishReason.ERROR)` 均不回归。"
- §6 P0-S1 Tests 命令包含 `<new_context_overflow_test_name>` 占位。
- §7 Expected failure paths 包含："如果 Runner context overflow 被误归为普通 `CLIENT_ERROR`，Runner classifier / HTTP overflow event-path 测试应失败。"

结论：条件候选已清除，P0-S1 明确要求该测试，且 expected assertions 和 failure paths 均覆盖。

---

### A2 — P0-S1 completion signal 已显式包含 pyright

**status: fixed**

controller 要求：P0-S1 completion signal 增加 `source .venv/bin/activate && pyright` 通过。

revised plan 验证：

- §6 P0-S1 Completion signal 现为三条：
  1. "Slice tests 通过。"
  2. "`source .venv/bin/activate && pyright` 通过。"
  3. "sentinel 检查通过：……"

结论：pyright 已作为 P0-S1 completion signal 的显式条件，implementation agent 不会遗漏。

---

### A3 — Phase 5 ingest validation 与 Phase 10 semantic interpretation 对 budget_state=None 的责任切分已清楚，P0 closeout 回写 implementation-control 已要求

**status: fixed**

controller 要求：
1. Phase 5 owns EngineEvent ingest validation：接受 `budget_state=None`，不把 `None` 当协议错误。
2. Phase 10 owns Context Governance semantics：用 Host estimator / policy 生成 before / after budget refs。
3. P0 closeout 必须把切分回写 `docs/host/implementation-control.md` 追踪区。

revised plan 验证：

- §10 Non-Blocking Risks #3 已拆分 Phase 5 和 Phase 10 归属，措辞精确。
- §11 Residual Risk Tracking Destination 第 2 条："Phase 5 owns EngineEvent ingest validation，必须接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref。"
- §11 第 3 条："Phase 10 owns Context Governance semantic interpretation，并用 Host estimator / policy 生成 before / after budget refs，并决定 compact / recovery。"
- §11 最后一条："P0 closeout 必须把 Phase 5 / Phase 10 的上述责任切分回写 `docs/host/implementation-control.md` 追踪区。"
- §6 P0-S2 Expected assertions 第 4 条："`docs/host/implementation-control.md` 追踪区可以被 Phase 5 / Phase 10 plan 读取到：Phase 5 负责 EngineEvent ingest validation 接受 `budget_state=None`；Phase 10 负责在 Engine overflow budget unknown 时用 Host estimator / policy 生成 before / after budget refs 并决策 compact / recovery。"

结论：责任切分精确到 Phase 5（结构接受）和 Phase 10（语义解释），P0 closeout 回写要求明确，无歧义。

---

### A4 — sentinel 搜索/多行构造检查防线已补足

**status: fixed**

controller 要求：补充更稳妥的 sentinel 检查，要求 implementation report 说明多行构造检查结果。允许历史 review artifact 命中旧文本；生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。

revised plan 验证：

- §6 P0-S1 Completion signal："implementation report 必须记录多行构造检查结果，至少包括对 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照` 的搜索与人工核对结论。"
- §7 sentinel 搜索命令更新为：`rg -n "ContextBudgetSnapshot\\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests docs README.md`
- §7 命令后说明："implementation report 必须说明上述命中的多行构造检查结果。允许历史 review artifact 命中旧文本；生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。"
- §6 P0-S2 Tests / validation 中同样包含多行构造检查要求。

结论：sentinel 搜索已扩展为 6 个 pattern，implementation report 必须记录多行构造检查结果，历史 artifact 豁免条款清晰。

---

### A5 — contract tests 同时覆盖 budget_state=None 和真实 ContextBudgetSnapshot(1000, 500, 1500)，且没有把零值变成类型级非法

**status: fixed**

controller 要求：
1. P0-S1 contract tests 同时覆盖 `budget_state=None` 合法，以及 `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 合法。
2. 文档说明 `0/0/0` 不得作为 unknown sentinel；不要求 dataclass 校验禁止零值。

revised plan 验证：

- §4.1："不得用 `ContextBudgetSnapshot(0, 0, 0)`、负数或其它 sentinel 表达 unknown。" + "P0 不要求在 `ContextBudgetSnapshot` dataclass 类型级禁止零值；禁止的是把 `0/0/0` 当作 unknown sentinel。"
- §6 P0-S1 Exact allowed changes 第 6-7 条：同时要求 `budget_state=None` 和 `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 断言。
- §6 P0-S1 Expected assertions 第 3-4 条："`budget_state=None` 是合法 unknown。`budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 这类真实 snapshot 合法。`ContextBudgetSnapshot(0, 0, 0)` 不得作为 unknown sentinel，但本 P0 不要求 dataclass 类型级禁止零值。"
- §7 Expected failure paths 第 3 条："如果 contract tests 只覆盖 `None`，没有覆盖真实 `ContextBudgetSnapshot(1000, 500, 1500)`，P0-S1 不得完成。"

结论：两条合法路径均已显式覆盖，零值类型级禁用已被明确排除，contract tests 不会误把 `int 三元组` 变成类型级非法。

---

### A6 — runner_events.py docstring 目检已纳入 P0-S2

**status: fixed**

controller 要求：将 `dayu/engine/contracts/runner_events.py` 作为 P0-S2 可选检查文件；若无需修改，implementation artifact 记录 `checked, no change needed`。

revised plan 验证：

- §3.2 条件候选中 `dayu/engine/contracts/runner_events.py` 条目存在，措辞与 A6 要求一致。
- §6 P0-S2 Allowed files 包含 `dayu/engine/contracts/runner_events.py`，并注明"仅检查 docstring 是否仍暗示 Engine budget governance；若无需修改，implementation artifact 记录 `checked, no change needed`。"
- §6 P0-S2 Exact allowed changes 第 4 条："检查 `dayu/engine/contracts/runner_events.py` 中 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 等相关 docstring。若没有旧 `0/0/0`、Engine budget governance 或 Engine compact/retry 暗示，不修改该文件，并在 implementation artifact 记录 `checked, no change needed`。"
- §6 P0-S2 Expected assertions 第 3 条："如未修改，implementation artifact 写明 `checked, no change needed`。"

结论：runner_events.py 已纳入 P0-S2 必检文件（非条件候选），且 artifact 记录要求明确。

---

### A7 — dayu/README.md 操作是精化已有术语，不是机械追加，不把未来 Phase 10 写成已完成

**status: fixed**

controller 要求：将 `dayu/README.md` 操作从 "补充" 改为 "精化已有 Context Governance 术语条目"；只说明当前边界。

revised plan 验证：

- §3.3 文档候选中 `dayu/README.md` 条目："应精化已有 Context Governance 术语条目，加入 budget unknown 边界。不要机械追加重复段落，不要把未来 Phase 10 写成已完成。"
- §6 P0-S2 Exact allowed changes 第 5 条："精化 `dayu/README.md` 已有 Context Governance 术语条目：只说明当前边界，即 Engine reactive event 在 provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator / policy；不得机械追加重复段落，不得写成 Phase 10 已完成。"
- §8 Documentation Update Decision 中 `dayu/README.md`："只精化已有 Context Governance 术语条目，避免冗余，不把未来 Phase 10 写成已完成。"

结论：全文档中 "补充" 已替换为 "精化"，"不得机械追加" 和 "不把 Phase 10 写成已完成" 约束一致。

---

## Scope Boundary Verification

revised plan §2 Non-Goals And Scope Boundary 未改动，以下硬约束仍然成立：

| 约束项 | 验证 |
| --- | --- |
| 不实现 Host Context Governance | §2 明确 non-goal |
| 不修改 Host implementation code | §2 明确 non-goal |
| 不实现 compact / retry / tokenizer / policy | §2 明确 non-goal |
| 不把 proactive context governance 放进 Engine | §2 明确 non-goal |
| 不新增兼容 wrapper / re-export | §2 明确 non-goal |
| 不把诊断事实塞进 metadata | §2 明确 non-goal |
| 不改变 EngineEvent wire value | §2 明确 non-goal |

结论：revised plan 未引入任何 scope 膨胀。

---

## Residual Risk Destination Verification

| 风险 | destination | 悬空? |
| --- | --- | --- |
| Engine overflow budget unknown 已修复 | `docs/host/implementation-control.md` 追踪区 | 否 |
| Host reactive ingest validation 对 `budget_state=None` | Phase 5（ingest validation） | 否 |
| Host Context Governance semantic interpretation | Phase 10 | 否 |
| Host estimator / policy / compact artifact | Phase 10 | 否 |
| Provider-specific tokenizer adapter | Host later capability | 否 |
| `reason: str` 自由字符串 | Phase 5 / Phase 10 ingest mapping | 否 |
| `ContextBudgetSnapshot` 导出保留 | P0-S2 docs sync | 否 |
| P0 closeout 回写 Phase 5/10 责任切分 | `docs/host/implementation-control.md` 追踪区 | 否 |

结论：所有 residual risk 均有明确 destination，无悬空项。

---

## New Blocker Check

未发现新 blocker。revised plan 未引入新的公共类型、新的 Host 依赖、新的 Engine 职责膨胀或新的测试缺口。

---

## Artifact Path

`docs/reviews/gateflow-plan-re-review-host-p0-engine-context-compaction-mimo-20260513.md`
