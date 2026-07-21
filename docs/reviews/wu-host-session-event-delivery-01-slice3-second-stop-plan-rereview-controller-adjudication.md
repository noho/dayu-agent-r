# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Second Stop Plan Re-Review Controller Adjudication

## Scope

- Gate: `plan-review-slice-3-amendment-r2`
- Base: accepted first Slice 3 plan amendment commit `6c1cf62a`
- AgentCodex R2 plan-fix: `docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-plan-fix-codex.md`
- AgentMiMo `$planreview`: `docs/reviews/plan-review-20260722-000527.md`
- AgentDS `$planreview`: `docs/reviews/plan-review-20260722-000355.md`

两路 reviewer独立并行，只审查R2 working-tree plan diff，不审查partial implementation或对方artifact。AgentMiMo起初读取了错误的commit-range diff；Controller纠正后，它实际读取 `git diff -- <plan>` 并基于R2 hunks重新完成审查，最终artifact可计入gate。

## Review conclusions

- AgentMiMo: `PASS`，0 material finding，0 blocking open question，2项低风险test-level residual。
- AgentDS: `PASS`，2项低严重度finding，2个非阻塞open question；均有现有stop backstop。

两路一致确认：

1. `tests/host/test_watch_session_events.py` 是该dual-opener instrumentation的必要且唯一owner文件。
2. opener A本地hook可合法推进；正确cross-opener证据必须落在C instance-local watermark/hook、watcher pending与reconcile/page-read barrier。
3. S2 shared DB/fence/multipage/A-terminal-before-B/timeout/cleanup断言全部保留。
4. 目标case、整文件、`tests/host -q`、完整pyright/diff/scans验证闭集充分。
5. 未授权production、其它test、fixture或support file。

## Findings adjudication

### DS-F1 helper class修改授权边界

Decision: `accepted-as-implementation-dispatch-constraint; no-plan-fix`。

恢复implementation时，授权范围明确包括目标test method的setup、barrier instrumentation、局部断言，以及只被该test使用的 `_TerminalWatermarkHookCallCounter`；只可为C instance-local观测更新其实现/docstring。不得改变 `_ControlledSessionEventReconciliationWaiter`、`_ReconciliationWaiterFactory`、`_SessionEventPageReadSpy` 的共享行为语义。Plan的“barrier instrumentation与对应局部断言”加Controller裁决已足够，不再扩写plan。

### DS-F2 C-side最小正向断言闭集

Decision: `accepted-as-implementation-dispatch-constraint; no-plan-fix`。

目标test必须至少证明：

1. A local hook至少发生一次或A watermark前进，证明A coordinator正常工作。
2. C `committed_terminal_event_sequence_high_watermark(session_id)`保持0/动作前值。
3. C local hook未被A调用。
4. A terminal后、C reconcile clock推进前，C watcher保持pending且`page_read_spy`无新cursor。
5. 后续原S2 multipage catch-up、A terminal before B、timeout/cleanup断言保持。

只删除全局`call_count == 0`而不建立上述证据不得通过implementation gate。

### OQ1 instance-level vs class-level mock

Decision: `closed-by-owner-boundary`。

不得继续使用跨A/C的class-level zero-call mock作为barrier。实现应使用instance-local instrumentation，或直接比较A/C各自owner state；精确test写法由AgentCodex选择，但必须满足上述闭集。

### OQ2 第二个dual-opener test

Decision: `closed-by-full-file-and-affected-validation`。

R2授权不修改第二个test；完整test file与`tests/host -q`均为必过gate。若第二个test也暴露新语义冲突，必须再次stop，不可在当前授权内修改。

## Gate decision

Decision: `accepted-plan-amendment-r2`。

- Material findings: 0。
- Blocking open questions: `None`。
- Controller只stage/commit R2 plan/stop/review/control artifacts，partial S3 code/tests保持unstaged。
- Accepted commit后恢复AgentCodex；上述implementation constraints是强制派发条件。
