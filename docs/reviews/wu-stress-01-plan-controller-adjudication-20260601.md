# WU-STRESS-01 Plan Review Controller Adjudication

## Gate

plan review

## Reviewed Artifacts

- `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- `docs/reviews/wu-stress-01-plan-review-mimo-20260601.md`
- `docs/reviews/wu-stress-01-plan-review-ds-20260601.md`

## Controller Conclusion

Plan review gate accepted after re-review. Both initial reviewers concluded PASS with no blocking findings; controller accepted the actionable low-severity findings as plan-fix requirements. AgentCodex updated the plan, and both AgentMiMo and AgentDS re-reviewed the result as PASS with zero remaining findings.

## Finding Decisions

### ADJ-01-accepted-failure_boundary 类型必须收窄

来源：AgentMiMo F1。

裁决：accepted。

原因：基于 design_doc 的强 Host governance 目标和 AGENTS.md 强类型约束，stress summary 的 failure boundary 是固定诊断分类，应在 plan 中要求 `Literal` 或等价封闭类型，避免实现阶段产生裸字符串扩散。

要求：更新 plan，把 `failure_boundary: str | None` 改成封闭诊断类型要求。

### ADJ-02-accepted-所有新增 helper/docstring 约束必须显式写入 plan

来源：AgentMiMo F2、AgentDS F4。

裁决：accepted。

原因：WU-STRESS-01 会新增较多测试 helper；若 plan 不显式约束中文 docstring、参数/返回值/异常和 fresh short read diagnostic 语义，实现阶段容易引入弱边界。

要求：更新 plan，要求所有新增模块级函数、class、dataclass 都有完整中文 docstring；lag diagnostic helper 必须声明 fresh short read transaction 与 point-in-time diagnostic 语义。

### ADJ-03-accepted-StressTerminalObservation 必须有消费场景或删除

来源：AgentMiMo F3。

裁决：accepted。

原因：测试 helper 也要避免 god bag / 死设计。该 dataclass 如果服务 terminal duplicate / watch lag 计算，应在 plan 中写明消费路径；否则不得创建。

要求：更新 plan，明确 `StressTerminalObservation` 被 terminal 去重与 lag helper 消费，或要求实现时不创建该类型。

### ADJ-04-accepted-stress worker factory 边界必须具体化

来源：AgentMiMo F4。

裁决：accepted。

原因：已有 `recovery_support.py` worker helper 可以复用；新增 factory 只有在提供 stream exception、clean EOF、handle close count、cancel count 等增量诊断时才合理。

要求：更新 plan，说明新增 stress factory 与既有 recovery helper 的增量职责，并要求优先复用既有 helper。

### ADJ-05-accepted-pytest addopts / CI / marker 验证需要补足

来源：AgentMiMo F5、AgentDS F-01。

裁决：accepted。

原因：默认排除 stress 是当前 WU 的核心交付，但全局 `addopts` 会改变 pytest 默认收集语义；必须在 plan 中要求检查 CI pytest 调用和 marker 注册，避免默认测试入口被静默破坏。

要求：更新 plan，在 Slice 1 validation 加入 CI pytest 命令检查、`pytest --markers` 和默认收集 / deselect 行为验证。

### ADJ-06-accepted-pytest-timeout 可用性需要写清

来源：AgentMiMo F6、AgentDS F-03。

裁决：accepted as clarification。

原因：`pytest-timeout>=2.1.0` 已在 `pyproject.toml` test optional dependency 中存在，但 plan 应要求 implementation 验证 marker 生效，避免 stress 测试失去 timeout 防线。

要求：更新 plan，写明依赖已存在，并在 Slice 1 验证 `pytest --markers` 或显式 timeout marker 可用。

### ADJ-07-accepted-slice 依赖 handoff 需要显式化

来源：AgentMiMo F7。

裁决：accepted。

原因：本 plan 计划五个顺序 slice，后续 slice 依赖 Slice 1 helper 和 Slice 2 crash helper；总控文档要求后续 slice 可依赖的稳定交付物明确。

要求：更新 plan，在每个 slice 写明 prerequisites / stable output。

### ADJ-08-accepted-Slice 4 close cleanup 间接证明链需要具体化

来源：AgentDS F-02。

裁决：accepted。

原因：不得为了测试暴露 scheduler internals；因此间接证明链必须具体、可审查、可执行。

要求：更新 plan，增加伪代码级验证链：close Host 后检查 stress factory handle close / cancel 计数，reopen 后无 spurious recovery，lane immediate acquire 成功，terminal / EventLog counts 不重复。

### ADJ-09-accepted-Slice 3 consumer cancel 验证机制需要具体化

来源：AgentDS F-05。

裁决：accepted。

原因：watch consumer cancel 不写 EventLog、不 cancel Run 是设计真源中的稳定语义；plan 应明确通过 `get_run` 与 EventLog count 前后对比验证。

要求：更新 plan，在 Slice 3 expected assertions 中加入具体验证机制。

## Next Step

进入 implementation gate。Implementation agent must start from Slice 1 in `docs/host/wu-stress-01-host-production-stress-suite-plan.md` and stop on any plan stop condition.

## Re-review Artifacts

- `docs/reviews/wu-stress-01-plan-rereview-mimo-20260601.md`
- `docs/reviews/wu-stress-01-plan-rereview-ds-20260601.md`

## Artifact Path

`docs/reviews/wu-stress-01-plan-controller-adjudication-20260601.md`
