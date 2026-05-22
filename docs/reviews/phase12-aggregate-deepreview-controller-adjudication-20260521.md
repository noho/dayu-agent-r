# Phase 12 Aggregate Deepreview Controller Adjudication

## Verdict

- MiMo aggregate deepreview：PASS，blocking count = 0。
- DS aggregate deepreview：PASS，blocking count = 0。
- Controller 裁决：Phase 12 整体设计边界成立，但接受 DS P12-AGG-M1 为当前 aggregate fix；修复后需要双路 aggregate re-review。

## Accepted Current Fix

### P12-AGG-F1: extract duplicated runtime digest helpers

来源：DS P12-AGG-M1。

裁决：接受为当前 aggregate fix。

理由：`tools_discovery.py` 与 `scene_prepare.py` 均实现 canonical JSON digest 与 JSON value normalization。当前行为正确、测试通过，但这是同一 runtime 层中立语义的重复实现，违反项目“重复逻辑必须抽取”的编码硬约束。最佳修复是在 `dayu.runtime` 内新增私有层中立 helper，由两个组件共享，不改变 public API、digest 算法或 Host 接口。

修复边界：

- 允许修改 `dayu/runtime/_digest.py`、`dayu/runtime/tools_discovery.py`、`dayu/runtime/scene_prepare.py` 与 focused tests。
- 不修改 Host public interface、Engine、Service、UI、Fins、ConfigLoader schema、Scene manifest schema 或 ToolsDiscovery public behavior。
- 不改变 existing content digest output；现有 digest stability tests 必须继续通过。

## Non-Blocking / Deferred

- MiMo M1：`dayu/runtime/README.md` 缺失。当前项目 README 触发规则未定义 runtime 包 README 固定职责；Phase 12 稳定事实已同步到 `dayu/README.md`、`dayu/config/README.md` 与 `tests/README.md`。裁决为 deferred documentation hardening，不阻塞 ready-to-open-draft-PR。
- MiMo L1：`ToolBundleSourceRef` dedicated behavioral tests 不足。当前 contracts package export、import boundary 与 pyright 已覆盖；可作为后续 contracts hardening，不阻塞当前 aggregate gate。
- MiMo L2：real scene asset migration test 依赖真实 manifest 文件。该测试正是 Slice 5 验收目标，不阻塞。
- DS low / residual observations：`SERVICE_COMPOSITION` 不在 discovery config、真实 Service wiring 未覆盖、workspace real path overlay 未集成测试，均符合 Phase 12 non-goals 或后续 Service owner。

## Required Re-Review

P12-AGG-F1 修复完成并通过 controller validation 后，需 MiMo 与 DS 做 aggregate re-review，确认 digest helper 抽取未改变行为且无新增 blocker。
