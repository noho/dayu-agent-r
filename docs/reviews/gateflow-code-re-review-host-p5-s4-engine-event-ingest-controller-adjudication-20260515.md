# Host P5-S4 EngineEvent Ingest Controller 裁决

## Gate

- Work unit: Host Phase 5 RunInputBuilder local dispatch
- Slice: P5-S4 EngineEvent Ingest Mapping And Terminal Closeout
- Role: controller adjudication
- Design source: `docs/host/design.md` §13.4 / §17 / §22
- Approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S4, §3.1, §3.5, §3.6

## 输入

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s4-engine-event-ingest-20260515.md`
- MiMo code review: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`
- DS code review: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-ds-20260515.md`
- Fix artifact: `docs/reviews/gateflow-fix-host-p5-s4-engine-event-ingest-20260515.md`
- MiMo code re-review: `docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`
- DS code re-review: `docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-ds-20260515.md`

## 裁决

接受 P5-S4 slice，允许进入 accepted slice commit。MiMo 原始 review 提出 1 个 blocking finding；该 finding 已修复并由 MiMo、DS re-review 确认 fixed，无新增 blocking。

## Scope Expansion

`dayu/host/durable/state.py` 不在 P5-S4 原始 allowed files 内，但本次扩展被接受。

裁决理由：

- 新增的 `cancel_cancelling_run_row` 与 `cancel_running_attempt_row` 是 durable state row CAS helper，属于 `state.py` 既有 ownership。
- 将这两段 SQL 写入 `run_transition.py` 会绕过 `RunMutationResult` / `AttemptMutationResult` 的 typed CAS 分类，是更差的分层方案。
- 扩展后的 `state.py` diff 只包含两个功能 helper，无无关格式 churn。

## Finding 裁决

- MiMo B1: duplicate terminal replay 不触发 queue promotion wakeup。Accepted blocking，已修复。`EngineEventIngestor` 现在通过 `_with_terminal_promotion_retry` 对 `terminal_closeout=True` 且 status 为 `ACCEPTED` 或 `DUPLICATE` 的结果统一调用 `wake_queue_promotion`，并返回 `promotion_triggered=True`。回归测试覆盖 duplicate `final_answer` 与 duplicate clean EOF。
- MiMo B2 / DS NB-3: `run_suspended`、`tool_awaiting`、`provider_protocol_error` 路径缺少显式测试。Accepted nonblocking。当前代码路径由已有 unsupported recovery / diagnostic + closeout 机制覆盖；后续 P5-S6 或测试 hardening 可补更细分覆盖。
- MiMo B3: preview event 路径缺少测试。Accepted nonblocking。当前 preview 不改状态；后续测试 hardening 可补至少一个 preview event。
- MiMo B4 / DS NB-2: terminal-late / run_cancelled without active cancel rejection 缺少显式测试。Accepted nonblocking。已有 stale execution rejection 覆盖不污染 canonical facts 的核心机制；后续测试 hardening 可补目标负例。
- DS NB-1: 测试 helper 重复。Accepted low。当前不引入测试 helper 重构，避免扩大 slice。
- DS re-review minor: `_close_active_cancel` 内部返回的 `promotion_triggered=False` 是外层 wrapper 覆盖前的哑值。Accepted low，不影响语义。

## 验证

Controller 与 reviewers 均验证通过：

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q`: 10 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`: 0 errors。
- `git diff --check`: passed。

## 后续 owner

- P5-S5: active cancel propagation 到 LocalProxy / worker handle，以及 public `cancel_run` / `cancel_session_runs` active worker 子集。
- P5-S6: dispatch scheduler worker stream 与 `EngineEventIngestor` 的端到端集成、README 终态同步和更宽集成验证。
- 后续测试 hardening: preview、unsupported waiting、provider protocol error、terminal-late、run_cancelled without active cancel 的显式负例覆盖。
