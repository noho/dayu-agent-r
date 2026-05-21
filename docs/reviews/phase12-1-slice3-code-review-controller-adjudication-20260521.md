# Phase 12.1 Slice 3 Code Review Controller Adjudication

## Scope

- Work unit: Phase 12.1 runtime assembly schema / public contract correction follow-up。
- Gate: Slice 3 code review adjudication。
- Implementation artifact: `docs/reviews/phase12-1-slice3-implementation-codex-20260521.md`。
- Review artifacts:
  - `docs/reviews/phase12-1-slice3-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-1-slice3-code-review-ds-20260521.md`

## Verdict

Slice 3 进入当前 fix pass。

## Review Summary

AgentMiMo verdict 为 PASS，blocking finding count = 0。

AgentDS verdict 为 PASS，blocking finding count = 0，并提出 1 个 low finding：

- `dayu/runtime/scene_prepare.py::_require_scene_id` 对非法 scene id 格式抛出 `ValueError`，而非模块统一的 `ScenePrepareError`。

## Findings Adjudication

### P12.1-S3-F1: `_require_scene_id` 异常类型不一致

- Decision: accepted-current-fix。
- Reasoning: `ScenePrepareError` 是 scene manifest 解析、校验或装配失败的结构化错误契约。非法 scene id 可来自 request、manifest `scene` 字段或 `extends` parent id，属于 ScenePrepare schema validation 失败。当前抛出父类 `ValueError` 会让只捕获 `ScenePrepareError` 的 Service / tests 漏掉结构化错误，虽低概率但与本 Slice 的 fail-fast typed schema 目标不一致。
- Required fix: 将 `_require_scene_id` 的非法格式分支改为抛 `ScenePrepareError`，并补三条 focused tests：request scene id、manifest scene 字段、extends parent id 非法格式均抛 `ScenePrepareError`。

## Deferred / No-action Items

- 子 manifest 是否能放宽父级 required context slot：deferred observation。当前设计未要求子级放宽父级 required slot，且所有包内 manifest 平铺；后续若需要该语义，先进入设计讨论。
- `smoke_host_public_multiturn` 尚未被 smoke 脚本消费：deferred to Slice 5。
- `PreparedSceneInputs.model_hints` 可为空后的 baseline 映射：deferred to Slice 4 / Slice 5 assembly helper。

## Controller Decision

基于 `docs/host/design.md` 的设计目标和第一性原理，本 Slice 的主实现方向正确，但结构化错误契约必须同源。当前最佳实践是接受 P12.1-S3-F1 为窄 fix，修复并 re-review 后再创建 accepted local commit。
