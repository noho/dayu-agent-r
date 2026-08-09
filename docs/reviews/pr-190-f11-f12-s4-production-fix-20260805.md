# PR 190 F11/F12 S4.1 Production Fix Implementation Artifact

## Gate

- Work unit：PR 190 F11/F12 interactive memory v3。
- Slice：`S4.1`，修复 accepted production blocker `S4-001`。
- Gate：implementation complete；next entry point 为 code review。
- Baseline：`c824ea9038ecb4084621117c6806764cd63e9a20`。
- Artifact path：`docs/reviews/pr-190-f11-f12-s4-production-fix-20260805.md`。

## Goal 与边界

目标是让 fallback selection 与 durable replay 从同一个 current-input material block
construction / normalization / digest 真源派生，并覆盖连续空白、空行与换行输入。修复还必须保证
reactive recovery 的 protected-recent selection 不由 RunInput 或 Memory 重新猜测 block identity。

本 slice 不改变 fallback policy、caps、terminal permit、Run / Attempt state machine、schema、Memory、
harness、renderer、oracle/scenario、旧 review/evidence 或真实 provider evidence。没有 stage、commit、push。

## First-principles judgment 与 exact owner

`S4-001` 成立且是 production blocker。基线上的 deterministic 反例直接得到：

1. proactive 两次 `quality_check_rejected` 后，selection 使用 raw current-input text 生成 digest，
   replay 经 `run_input_material_block` 折叠空白后生成另一个 digest，最终抛出
   `HostDurableError: fallback selected material view digest mismatch`；
2. reactive protected-recent fallback 的 selection 使用 EventLog-backed block ids，replay 却让
   RunInput consumer 从 Memory 视图重建不同 block ids，最终抛出
   `HostDurableError: fallback selected block id is missing from material view`。

语义 owner 判定如下：

- `dayu.host.compact_material.run_input_material_block` 唯一拥有 material 文本规范化、
  `size_units` 与 `content_digest` 派生；
- `dayu.host.context_fallback` 拥有 durable fallback window 的读取与 replay material view；
- `dayu.host.compact_pipeline._fallback_material_blocks` 是 selection 的直接上游 producer，原实现绕过
  material owner；
- `dayu.host.run_input._selected_material_render_view` 只是严格 consumer/validator，不是修复 owner。

因此没有在 RunInput、Memory、harness、renderer 或 fixture 添加 fallback、特例或 loose parsing。

## Implementation

### Production

- `dayu/host/context_fallback.py`
  - 将 fallback current-input anchor 收口到内部
    `_fallback_current_input_material_block`，统一委托 `run_input_material_block`；
  - proactive 与 reactive durable replay 都从同一 EventLog-backed pre-dispatch material view 重建，
    保留 selection 的 block id、source ref、protected-recent group 与 normalized digest；
  - 非 proactive/reactive trigger 继续 fail closed；没有扩张 `__all__` 或 package public interface。
- `dayu/host/compact_pipeline.py`
  - `_fallback_material_blocks` 删除 raw `RunInputMaterialBlock` 手工构造，改用同一个 fallback
    current-input helper；selection 与 replay 因此共用 construction、normalization 与 digest owner。

### Owner tests

- `tests/host/test_dispatch_scheduler.py`
  - proactive exhausted fallback：输入含连续空白与空行，两个 proposal 均为
    `quality_check_rejected`，只提交一个 `CONTEXT_COMPACTION_FAILED`；断言 current-only bounded
    selection、normalized selected-view digest、fallback manifest ref、`DISPATCH_FALLBACK` sizing stage、
    单一 ordinary Attempt、proactive terminal projection cleanup、唯一 `RUN_SUCCEEDED`、无 `RUN_LOST`
    且 scheduler active task 清空；
  - reactive recovery protected-recent：current input 与 recent raw material 均含可折叠空白/换行，
    断言 EventLog-backed selected ids、normalized selected-view digest、protected recent replay、recovery
    manifest fallback ref、source Attempt failed、recovery Attempt succeeded、Run succeeded 与 task cleanup；
  - `_seed_current_run` 仅增加通用 `display_text` 输入，用于构造真实 owner counterexample；没有为
    fallback 写 fixture 补偿。

## Validation

- 基线 red proof：新增两条 owner tests 在生产修复前均失败，分别得到
  `fallback selected material view digest mismatch` 与
  `fallback selected block id is missing from material view`。
- 定向 owner tests：`2 passed`。
- 受影响 Host tests：
  `tests/host/test_compact_pipeline.py`、`test_run_input_builder.py`、
  `test_engine_ingest_mapping.py`、`test_recovery_dispatch.py`、
  `test_public_compact_smoke.py`、`test_dispatch_scheduler.py`：`409 passed, 1 skipped`。
- 单文件 branch coverage：
  - `dayu/host/compact_pipeline.py`：`90%`；
  - `dayu/host/context_fallback.py`：`87%`；
  - 合计：`88%`。
- 全量 Host tests：`2423 passed, 1 skipped, 6 deselected`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

## README decision

- 已先读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。本修复只恢复 README 已承诺的
  Host-owned fallback/recovery 同源与 fail-closed 行为，没有新增稳定接口、状态机、事件或扩展点，
  因此不更新。
- 已先读取 `tests/README.md` 的维护边界。测试仍属于既有 Host Context Governance / dispatch /
  reactive recovery 层级，没有新增测试层级或运行方式，因此不更新。
- 根 README 与 `dayu/README.md` 的用户工作流、命令参数、输出位置和分层关系均未变化，不触发更新。

## Residual risks 与 uncovered areas

- `fixed in current slice`：raw-vs-normalized current-input digest mismatch；reactive protected-recent
  EventLog block identity replay mismatch；模块公开导出边界误扩张已在全量 Host 首轮发现并纠正。
- `covered by later approved slice`：真实 Mimo→DeepSeek mandatory evidence 必须在本 production fix 双 review
  通过后写入全新 evidence root；旧 S4 bundle 继续保持 immutable / superseded partial evidence。
- 没有未分类 residual risk；没有需要新 issue 或用户裁决的实现问题。

## Completion status

`READY_FOR_CODE_REVIEW`。当前工作树只包含正确 Host owner、直接 owner tests 与本独立 artifact；下一步按
Gateflow 使用 `deepreview` 执行 code review，并按用户要求停在 code review，不进入 fix、re-review、commit、
push 或真实 provider 重跑。
