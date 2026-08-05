# PR 190 F11/F12 S4.1 Production Review Fix Artifact

## Gate

- Work unit：PR 190 F11/F12 interactive memory v3。
- Slice：`S4.1` production code review accepted findings fix。
- Gate：fix complete；next entry point 为 re-review。
- Baseline：`c824ea9038ecb4084621117c6806764cd63e9a20`。
- 执行时间：`2026-08-05 22:20:33 CST`。
- Artifact path：`docs/reviews/pr-190-f11-f12-s4-production-review-fix-20260805.md`。

## Scope 与 owner judgment

本 gate 只执行 controller adjudication 接受的两个修改：消除
`compact_pipeline -> context_fallback` 私有 helper 依赖，以及修正
`ActiveRecentWindowFallback.material_blocks` 的过期 docstring。

直接代码证据证明 finding 成立但属于模块封装问题，不是新的 correctness blocker：selection 与 replay
在修复前已经通过同一个内部 helper 委托
`dayu.host.compact_material.run_input_material_block`。真正拥有文本 normalization、`size_units` 与
`content_digest` 派生语义的 owner 始终是 `run_input_material_block`；两个 fallback producer 只拥有
fallback-specific 的 block id、section、kind、canonical source refs 与 EventLog sequence 输入。

因此采用 adjudication 首选的最小方案：两个 producer 分别直接调用现有 owner。没有新增公共导出、
compatibility wrapper / re-export、新模块或第三个共享 helper，也没有恢复 raw digest 手工构造。

## Fix

### Accepted finding 1：跨模块私有 helper import

- `dayu/host/compact_pipeline.py`
  - 删除对 `context_fallback._fallback_current_input_material_block` 的跨模块私有依赖；
  - `_fallback_material_blocks` 直接调用 `compact_material.run_input_material_block`，显式传入
    `current:<event-ref>`、current-input section/kind、source ref 与 input EventLog sequence。
- `dayu/host/context_fallback.py`
  - `_fallback_material_blocks_for_window` 直接调用同一个 `run_input_material_block` owner；
  - 删除无独立语义的 `_fallback_current_input_material_block` 私有薄 helper；
  - 全仓搜索确认该私有符号已无定义或引用。
- `tests/host/test_compact_pipeline.py`
  - 在现有 pure fallback decision owner test 中注入含连续空白与空行的同一 source snapshot；
  - 直接断言 selection current block 与 `run_input_material_block` expected dataclass 完全相等，覆盖
    block id、section、kind、normalized text、`size_units`、`content_digest`、canonical source refs、
    EventLog sequence 及 dataclass 其余默认字段；
  - 未新增 durable fixture。两条既有 dispatch owner regressions 继续验证 window 与 EventLog replay 的
    exact digest / id / source、manifest、Attempt / Run terminal 与 cleanup。

Fix status：`已修复`；独立 re-review 尚未执行。

### Accepted finding 2：`material_blocks` docstring 过期

- `dayu/host/context_fallback.py`
  - 将“仅 proactive provider 填充”修正为 valid proactive/reactive durable loader 均从
    EventLog-backed source 重建并填充；
  - 未修改 dataclass 类型、schema 或 loader state transition。

Fix status：`已修复`；独立 re-review 尚未执行。

## Adjudication-preserved non-goals

- MiMo `002` 保持 `rejected-with-reason`：selection 使用 frozen source snapshot，durable replay 从 canonical
  EventLog 重建是生命周期要求，不是第二 owner；本 gate 不改变。
- MiMo `003` 保持 `rejected-with-reason`：deterministic rejecting compactor 验证 Host fallback state machine；
  本 gate 不替换为真实 provider 测试。
- RunInput `material_blocks is None` consumer branches 不改，不把 optional contract 机械迁移为 required。
- 未修改 harness、oracle、scenario、evidence、MiMo/DS reviewer artifacts 或 controller adjudication。
- 未 stage、commit、push，也未执行 provider evidence 重跑。

## Validation

- Pure owner test 与两条指定回归：`3 passed`。
  - `test_fallback_decision_input_dispatch_and_fail_closed`
  - `test_proactive_exhausted_fallback_normalizes_current_input_for_replay`
  - `test_reactive_compact_failure_fallback_dispatch_uses_failed_view`
- 受影响 Host tests：`409 passed, 1 skipped`。
- 全量 Host tests：`2423 passed, 1 skipped, 6 deselected`。
- Branch coverage：
  - `dayu/host/compact_pipeline.py`：`90%`；
  - `dayu/host/context_fallback.py`：`87%`；
  - 合计：`88%`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

## README decision

- 已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。本 gate 只收紧内部 owner 调用边界并
  修正文档字符串，没有新增稳定接口、状态机、事件、schema 或扩展点，因此不更新。
- 已读取 `tests/README.md` 的维护边界。pure owner assertion 与既有 dispatch regressions 仍属于现有
  Context Governance / compact pipeline / fallback recovery 测试层级，没有新增测试层级或运行方式，因此不更新。
- 根 README 与 `dayu/README.md` 的用户工作流及分层关系未变化，不触发更新。

## Residual risks 与 uncovered areas

- `fixed in current slice`：`compact_pipeline` 跨模块私有 helper import；过期 `material_blocks` docstring。
- `assigned to later work unit`：RunInput / ContextFallback contract 仍允许注入式
  `material_blocks is None` 分支。按 adjudication，本 slice 不扩大；若 aggregate deepreview 找到真实 production
  可达反例，由 RunInput / ContextFallback contract owner 升级处理。
- `covered by later approved slice`：Mimo-first、DeepSeek-only-fallback 的真实 provider evidence 必须在本
  review loop 通过后使用 fresh evidence root 重跑；旧 bundle 继续保持 immutable / superseded partial evidence。
- 没有未分类 residual risk 或 blocking open question。

## Completion status

`READY_FOR_RE_REVIEW`。当前 fix evidence 已完整；下一 Gate Order entry 是由 AgentMiMo 与 AgentDS 对接受项执行
两路独立 re-review，再由 controller 裁决最终 finding 状态。按用户要求，本 gate 停在 re-review，不进入 accepted
PR review commit、stage、push 或后续 gate。
