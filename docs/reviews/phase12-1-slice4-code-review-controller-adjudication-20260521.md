# Phase 12.1 Slice 4 Code Review Controller Adjudication

## Scope

- Work unit: Phase 12.1 runtime assembly schema / public contract correction follow-up。
- Gate: Slice 4 code review adjudication。
- Implementation artifact: `docs/reviews/phase12-1-slice4-implementation-codex-20260521.md`。
- Review artifacts:
  - `docs/reviews/phase12-1-slice4-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-1-slice4-code-review-ds-20260521.md`

## Verdict

Slice 4 进入当前 fix pass。

## Review Summary

AgentMiMo verdict 为 PASS，blocking finding count = 0。

AgentDS verdict 为 PASS，blocking finding count = 0，并提出 2 个 residual risks：

- provider extension helper 中 `_parse_openai_reasoning` / `_parse_mimo_thinking` 未统一通过 `_wrap_contract_error` 构造 Engine contract。
- `dayu.runtime.assembly` 的 `_FALLBACK_MODES` 与 `SceneAgentFallbackMode` 枚举值重复维护。

## Findings Adjudication

### P12.1-S4-F1: provider extension contract error wrapping 不一致

- Decision: accepted-current-fix。
- Reasoning: 当前两个 dataclass 暂无 `__post_init__`，所以不是现有行为 bug；但 provider extension helper 的稳定语义是“Engine contract 拒绝的字段组合统一转换为 `ProviderExtensionConfigError`”。保持所有 typed contract 构造路径都走 `_wrap_contract_error` 是更稳妥的 fail-closed 设计，避免未来 contract 增加校验时漏出裸 `ValueError`。
- Required fix: `_parse_openai_reasoning` 与 `_parse_mimo_thinking` 也通过 `_wrap_contract_error` 返回。

### P12.1-S4-F2: fallback mode 双真源

- Decision: accepted-current-fix。
- Reasoning: Slice 4 的职责是提供 Service 组装所需的 runtime-neutral typed merge helper。`fallback_mode` 已由 `SceneAgentFallbackMode` 枚举表达闭合集合，`assembly.py` 再手写同值 frozenset 会制造同一契约的双真源。当前最佳实践是从枚举派生 runtime merge 的允许值。
- Required fix: 将 `_FALLBACK_MODES` 改为从 `SceneAgentFallbackMode` 派生，保持 code default / execution profile / run override 与 scene enum 同源。

## Deferred Items

- Service composition helper 延后到 Slice 5 / 后续真实 Service composition root。
- Provider DSL helper 未来新增 union 成员时同步扩展 dispatch / README / tests，作为长期维护责任，不阻塞当前 slice。

## Controller Decision

基于 `docs/host/design.md` 的分层边界和 Phase 12.1 plan，Slice 4 主实现方向正确且无 blocking defect。两个 accepted findings 都是窄范围一致性修复，不改变 public behavior，却能降低 future drift，因此进入当前 fix pass，修复后 re-review。
