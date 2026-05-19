# Phase 10.5 Plan Review Controller Adjudication

## Gate

当前 gate：P10.5 plan review adjudication。

## Inputs

- Plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- MiMo review: `docs/reviews/phase10-5-plan-review-mimo-20260518.md`
- DS review: `docs/reviews/phase10-5-plan-review-ds-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- P10.5 scope input: `docs/host/post-p10.md`

## Verdict

两份 review 均为 PASS，blocking count = 0。Plan 已满足 P10.5 implementation-ready 的主体要求：普通本地多轮
Host public contract、`open_host(options)`、session-level live event stream、terminal `HostEvent` final answer
view、per-run override、tool selector、WAITING resume、steer / retry / replay、S1-S5 smoke success signal 和
residual owner 均已落到 slice / tests / owner。

总控裁决：不直接进入 implementation。DS 提出的 N1-N5 / C1-C3 与 MiMo 的 F5-F7 都属于低成本 plan hardening，
可降低 implementation agent 在 Slice 1-2 重新设计或误分配 ownership 的概率。基于 `docs/host/design.md` 的设计目标和第一性原理，
这些澄清应在 plan fix gate 中收口，而不是留给 implementation agent 自行解释。

## Accepted For Plan Fix

### A1. Slice dependency and Slice 2 request-shape boundary

来源：DS N1、DS C3、MiMo F7。

裁决：accepted for plan fix。

理由：P10.5 plan 必须让 implementation agent 无需重新设计 sequencing；明确 Slice 1 -> Slice 2 -> {Slice 3, Slice 4}
-> Slice 5 -> Slice 6，以及 Slice 2 可用当前 request shape 验证 runtime wakeup、Slice 3 再迁移 request contract，可避免 Slice 2
提前做 Slice 3 / Slice 5 work。

### A2. Public handle session/read wrappers ownership

来源：DS N2。

裁决：accepted for plan fix。

理由：`ensure_session` / `create_session` / `get_session` / `get_run` 是 design truth 中普通 Service minimum interface 的一部分。
它们必须明确归属 Slice 2 的 public async handle delegation，不能只隐含在 command handle wiring 中。

### A3. HostEventStream disposition

来源：DS N3、MiMo F5。

裁决：accepted for plan fix。

理由：P10.5 的设计目标要求普通 Service 只理解 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`。现有
`HostEventStream` 若仍在 public export 中，会削弱 public contract freeze；plan 必须明确 Slice 4 处理方式。

### A4. Compactor baseline None semantics and field mapping

来源：DS N4、DS N5、DS C1、MiMo F3。

裁决：accepted for plan fix。

理由：memory catch-up / compact 是 P10.5 查漏补缺范围。`compactor_baseline=None` 的 fail-closed 语义、Slice 2 对
`OpenHostOptions.compactor_baseline` 到内部 compactor fields 的映射、以及 S4 owner 包含 Slice 2 wiring，必须明确，避免
implementation agent 自行决定预算压力行为或 compactor adapter 放置。

### A5. HostToolingOptions shape note

来源：DS C2。

裁决：accepted for plan fix。

理由：per-run `tool_names` 与 ToolRuntime policy 是 Host / ToolRuntime governance 的核心边界。Plan 可复用现有
`HostToolingOptions`，但必须说明如果现有类型缺少 ToolRuntime policy typed fields，Slice 1 负责补齐 typed fields，而不是改用
extra payload 或 service locator。

## Accepted As Implementation Checklist / Residual, No Plan Fix Required

### C1. Smoke tests concentrated in Slice 6

来源：MiMo F1。

裁决：accepted as implementation checklist。

理由：端到端 smoke 依赖 Slice 1-5 的 contract 就位，集中在 Slice 6 符合分层验证。Plan 已允许 Slice 6 做 narrow
`dayu/host` fixes if smoke exposes Slice 1-5 public-path bugs。

### C2. post-p10 gap explicit mapping table

来源：MiMo F2。

裁决：accepted as optional implementation checklist, not plan fix。

理由：Plan 已通过 coverage table、readiness closure 与 slices 覆盖 `post-p10.md` 的 gap；显式 G-map 是 review ergonomics，
不是 implementation-readiness 的必要条件。

### C3. HostClosedError inheritance

来源：MiMo F4。

裁决：accepted as Slice 1 implementation decision within plan boundary。

理由：Plan 已固定不把 handle closed 映射为 command-level `INVALID_STATE`，并设置新增 error code 的 Controller stop condition。
第一版可按 plan 推荐选择 standalone `HostClosedError(Exception)`，不阻塞 plan。

### C4. Effective config observable surface

来源：MiMo F6。

裁决：accepted as Slice 3 implementation decision within plan boundary。

理由：Plan 已允许 Run / Attempt snapshot、source refs 或 diagnostic refs 作为 effective config freeze 的可解释面。只要不读内部 durable
truth 来证明 Service-facing correctness，具体测试断言面可由 Slice 3 根据现有代码选择。

## Plan Fix Requirements

Planning specialist 只允许修改 `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`，不得修改源码、tests、
README、总控文档或 review artifacts。修复完成后必须报告：

- 修改了哪些 sections；
- A1-A5 如何逐条收口；
- 是否产生新的 Blocking Questions For Controller；
- artifact path。

## Next Gate

进入 P10.5 plan fix。Fix 后派发 P10.5 plan re-review。
