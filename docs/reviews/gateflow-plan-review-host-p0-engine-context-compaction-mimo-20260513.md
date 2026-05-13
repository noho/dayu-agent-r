# Gateflow Plan Review: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置

- review gate: plan review
- reviewer: AgentMiMo
- review date: 2026-05-13
- reviewed plan: `docs/host/phase0-engine-context-compaction-plan.md`
- design truth sources checked against:
  - `docs/host/design.md` §25 / §25.1 Context Governance
  - `docs/host/implementation-control.md` Phase 0 and 追踪区
  - `docs/engine/design.md` §15 Context Compaction
  - `dayu/engine/README.md`
  - `dayu/engine/contracts/engine_events.py` (current code)
  - `dayu/engine/contracts/agent_run.py` (current code)
  - `dayu/engine/agent.py` (current overflow branch)
  - `tests/engine/test_engine_event_contract.py` (current tests)
  - `tests/engine/test_agent_phase2.py` (current tests)
  - `tests/engine/runners/openai/test_http_error_event.py` (current tests)
  - `tests/engine/runners/openai/test_context_overflow_classifier.py` (current tests)

## Reviewer Conclusion

**PASS — 无 blocker。plan 可直接进入 user confirmation。**

plan 正确识别了真实存在的公共契约语义问题（`0/0/0` sentinel 误导），严重性判断准确（阻塞 Phase 10，不阻塞 Phase 1-9），scope 不夹带 Host implementation，slices 足够小且 file ownership 清楚。optional `None` 表达 unknown 是最小、可维护、可测试的契约变更，与现有 `provider_request_id: str | None` 风格一致。

## Findings

### 001-未修复-[低]-Reason 字符串自由度留给后续 phase

**location**: plan §4.2, §10 Non-Blocking Risks #1

**evidence**:

- plan §4.2 明确保留 `reason: str`，不在 P0 引入 reason enum。
- plan §10 Non-Blocking Risks #1 已记录 `reason: str` 自由字符串的风险：Host ingest 若用自由字符串匹配，仍需自身 typed mapping。
- 归属已明确：P0 plan review 裁决；若非 blocker，则 Host Phase 5 / Phase 10 ingest mapping 处理。
- 当前 `RunFailedData.error_code` 也是 `str`，与 `ContextCompactionRequestedData.reason` 风格一致。

**assessment**: 这不是 P0 blocker。当前 Engine 代码中 `reason` 已有私有常量 `_ERROR_CONTEXT_COMPACTION_REQUIRED` 和 `_CONTEXT_COMPACTION_REQUIRED_MESSAGE`，string 契约已稳定。Phase 10 ingest mapping 需要自行 typed mapping 是已知 deferred item，destination 清楚。

**controller decision status**: pending-controller-decision

---

### 002-已修复-[低]-P0-S2 文档补强指令可以更精确

**location**: plan §6 Slice P0-S2 Exact allowed changes, `dayu/engine/README.md` 和 `dayu/README.md` 条目

**evidence**:

- plan 对 `docs/engine/design.md` §15 的修改指令具体：删除 `ContextBudgetSnapshot(0,0,0)` 占位说明，改为 `budget_state=None` / unknown。
- 但对 `dayu/engine/README.md` 的指令是"事件流 / 关键机制处补强：上下文长度超限会提升为 `context_compaction_requested`，该事件的 `budget_state` 在 provider overflow 路径为 `None`"。
- 当前 `dayu/engine/README.md` 已在事件流表格和关键机制段落中描述了 `context_compaction_requested`，但没有提及 `budget_state` 语义。
- `dayu/README.md` 的指令是"Context Governance 术语处补充：Engine reactive event 不携带真实 Host budget；Host 使用自身 estimator / policy"。当前 `dayu/README.md` 已说明 Engine emit 是 reactive fallback，但未提及 budget unknown 语义。

**assessment**: 指令意图清楚，implementation agent 可以根据"补强"指令自行判断具体改哪些行。这不是 blocker，但 P0-S2 完成后 reviewer 应验证旧 sentinel 语义已被完全替换。plan §6 已有 sentinel 搜索作为 completion signal，可以覆盖。

**controller decision status**: pending-controller-decision

---

### 003-已修复-[低]-条件候选 test_http_error_event.py 在验证命令中未显式覆盖

**location**: plan §3.2 条件候选, §7 Tests And Validation Commands

**evidence**:

- plan §3.2 将 `tests/engine/runners/openai/test_http_error_event.py` 列为条件候选："若当前没有 Runner 级 HTTP 400 context overflow 事件流测试，应补一个回归测试"。
- 当前 `test_http_error_event.py` 覆盖 429、500、400(普通 client error)、网络错误、超时等，但没有专门的 context overflow (400 + context_length_exceeded body) 测试。
- `test_context_overflow_classifier.py` 覆盖 `detect_context_overflow` 函数级分类，但不覆盖完整 Runner call → HTTP error → RunnerEvent 产出路径。
- plan §7 验证命令包含 `test_context_overflow_classifier.py`，但不包含 `test_http_error_event.py` 的 context overflow 测试。
- plan §7 Expected failure paths 有一条："如果 Runner context overflow 被误归为普通 `CLIENT_ERROR`，Runner classifier / HTTP overflow 测试应失败"，但这依赖 classifier 测试，不依赖完整 Runner HTTP error 事件流测试。

**assessment**: 当前 `test_http_error_event.py` 没有 context overflow 专用测试，而 classifier 测试只覆盖 `detect_context_overflow` 函数级分类。P0-S1 的 Exact allowed changes 已允许在 `test_http_error_event.py` 中补 Runner overflow 回归测试。这不是 blocker，但 implementation agent 应在 P0-S1 实施时评估是否需要补这个回归测试（按 plan §3.2 的条件判断）。

**controller decision status**: pending-controller-decision

---

### 004-已修复-[低]-P0-S1 completion signal 未显式覆盖 pyright 验证

**location**: plan §6 Slice P0-S1 Completion signal

**evidence**:

- P0-S1 Completion signal 有两条：slice tests 通过 + sentinel 搜索不命中。
- plan §7 已列出 `pyright` 验证命令。
- plan §9 Stop conditions 有一条："pyright 报错涉及更大公共契约设计，且无法在本 P0 文件边界内最小修复"。
- 但 P0-S1 的 Completion signal 本身没有把 pyright 作为显式条件。

**assessment**: 这不是 blocker。plan §7 已列出 pyright 命令，implementation agent 必须运行。P0-S1 完成时应同时满足 pyright 通过。Completion signal 可以更显式地包含 pyright，但当前 plan 的验证要求已覆盖。

**controller decision status**: pending-controller-decision

---

## Open Questions

无 blocking open questions。

## Residual Risk

| risk | destination | status |
| --- | --- | --- |
| `reason: str` 自由字符串 → Host ingest 需 typed mapping | Phase 5 / Phase 10 ingest mapping | deferred, destination clear |
| `ContextBudgetSnapshot` 导出保留但 provider overflow 不再生产 | P0-S2 docs sync | deferred to implementation |
| Host canonical compact event payload 需 budget snapshot refs | Phase 10 Context Governance | deferred, destination clear |
| Host reactive ingest mapping 对 `budget_state=None` 处理 | Phase 5 dispatch / Phase 10 | deferred, destination clear |

所有 residual risk 均有明确 destination，无悬空项。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-mimo-20260513.md`
