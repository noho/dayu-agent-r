# Phase 12.1 Slice 3 Re-review Controller Adjudication

## Scope

- Work unit: Phase 12.1 runtime assembly schema / public contract correction follow-up。
- Gate: Slice 3 re-review adjudication。
- Implementation artifact: `docs/reviews/phase12-1-slice3-implementation-codex-20260521.md`。
- Code review adjudication: `docs/reviews/phase12-1-slice3-code-review-controller-adjudication-20260521.md`。
- Re-review artifacts:
  - `docs/reviews/phase12-1-slice3-rereview-mimo-20260521.md`
  - `docs/reviews/phase12-1-slice3-rereview-ds-20260521.md`

## Verdict

Slice 3 accepted. 进入 accepted local commit。

## Fixed Finding Verification

P12.1-S3-F1 已修复：

- `_require_scene_id` 非法格式分支现在抛 `ScenePrepareError`。
- 已补三条 focused tests，分别覆盖 request scene id、manifest `scene` 字段、`extends` parent id 非法格式。
- 两份 re-review 均 PASS，确认无新增 blocker。

## Controller Validation

Controller 本地复跑通过：

- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q`：41 passed。
- `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`：10 passed。
- `python -m pyright dayu/runtime tests/runtime`：0 errors。
- `git diff --check`：clean。

## Deferred Items

- `PreparedSceneInputs.model_hints` 为空时映射到 execution profile baseline：deferred to Slice 4 / Slice 5。
- `utils/smoke_host_public_multiturn.py` 接入普通 `smoke_host_public_multiturn` scene：deferred to Slice 5。
- 子 manifest 是否可放宽父级 required context slot：deferred design observation；当前所有包内 manifest 平铺，不阻塞本 slice。

## Controller Decision

基于 `docs/host/design.md` 的设计目标，Slice 3 已完成 scene-only schema、typed scene output、包内 scene asset 迁移和 dedicated smoke scene asset 的可验证闭环。accepted finding 已由 re-review 确认收口，因此当前最佳实践是接受本 slice，创建 accepted local commit，并进入 Slice 4 implementation。
