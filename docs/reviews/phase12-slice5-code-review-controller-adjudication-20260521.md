# Phase 12 Slice 5 Code Review Controller Adjudication

## Verdict

- MiMo review：PASS，blocking count = 0。
- DS review：标记 BLOCKED，但 artifact 明确写明 blocking finding count = 0；其中 F1 / F2 属于 scene asset 语义质量问题。
- Controller 裁决：进入 Slice 5 窄 fix。接受 DS F1 / F2 为当前修复项；MiMo PASS 与 DS 其它 findings 不阻塞。

## Accepted Current Fixes

### P12-S5-F1: required context slots must be consumed by migrated fragments

裁决：接受为当前 fix。

理由：Phase 12 设计已确认 ScenePrepare 解释 scene manifest、接收 Service 提供的 context slot values，并输出已装配 system messages。当前 migrated assets 中 13 个 manifest 声明 required context slots，但所有 fragments 都没有 `{{slot_name}}` placeholder，导致 required context 被校验却不进入 system messages。基于 design_doc 的 ScenePrepare 目标，最佳实践不是保留误导性 required contract，而是在现有直接引用 prompt fragment 中做最小占位符接线。

修复边界：只修改迁移后的 prompt assets 与迁移测试；不新增 workflow / task prompt，不修改 ScenePrepare runtime 逻辑，不修改 Host public interface。

### P12-S5-F2: remove legacy conditional prompt markers from visible system messages

裁决：接受为当前 fix。

理由：`<when_tag>` / `<when_tool>` 是旧项目的条件模板标记，ScenePrepare v1 不解释它们，Service 也不应二次解释 fragments。若原样进入 system messages，会把旧模板控制语法暴露给模型。基于 design_doc 的“ScenePrepare 拥有 manifest 解释权、Service 不重拼 prompt”边界，最佳实践是在迁移资产中清理这些旧标记。

修复边界：只清理迁移后的 `base/tools.md` 可见模板标记；不得为旧条件模板引入新的 ScenePrepare processor。

## Accepted As Residual / Non-Blocking

- DS F3：真实 assets 当前不使用 `extends`，但 unit tests 已覆盖继承语义；后续新增继承 scene 时再加真实资产集成测试。
- DS F4 / MiMo N1：`capability_tags` 当前只保守映射 scene id，符合 Slice 5 迁移边界。
- DS F5：迁移测试 happy path 覆盖真实 assets，错误路径已由 `test_scene_prepare.py` 覆盖。
- DS F6：`conversation_compaction` model hint 是否使用 thinking profile 属 Service / execution profile mapping 后续 owner。
- `allowed_names` 删除与 raw runtime patch 不映射：符合设计，后续若仍需模型 allow-list 或运行预算，应在 ConfigLoader / Service typed mapping 中显式设计。

## Required Re-Review

修复完成后需要 MiMo 与 DS 对 P12-S5-F1 / P12-S5-F2 做 re-review，并确认没有新增 blocker。
