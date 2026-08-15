# UF-FIX06 Slice 3 code fix

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3（让 Service 与 workflows 消费 typed roles）
- Gate：code fix
- 日期：2026-08-15
- 基线：`affa665b0592aec54564d31b0cfeb4055dd7bd8a`
- 分支：`codex/upload-filing-oracle`
- 输入裁决：`docs/reviews/uf-fix06-slice3-code-review-adjudication-20260815.md`
- 状态：`FIX COMPLETE / RE-REVIEW PENDING`
- 下一入口：Slice 3 code re-review
- Commit：未创建；用户明确禁止 commit

## Scope 与 owner 判断

- 两路 review 均为 PASS，Controller 将 DS F1-F5 收敛为 accepted A1-A5；五项均有直接代码证据，动机成立。
- failure kind/code 一致性的唯一 owner 是 `FinsUploadFailureReason` 与其 closed mapping；parser 只是同源入口，
  因此校验落在 reason owner，而非 workflow consumer 或测试 fixture。
- prepare 阶段 partial conversion 的丢弃与零 publication 是 `DoclingUploadService` 的 lifecycle contract；测试在
  Service owner 观察 batch/source/blob，并在 SEC workflow 验证 public failure 投影。
- 严格未扩展 material empty、delete+files、collision、显式 primary 或 batch association；README 旧引用留 Slice 4。
- 三份 review artifacts 保持只读；未修改 README、registry、oracle/scenario、design document 或冻结 evidence。

## Accepted findings 处置

| ID | 状态 | 修复与证据 |
|---|---|---|
| A1 | 已修复 | failure reason kind 文档补齐 `usage`，保持 closed enum 说明完整。 |
| A2 | 已修复 | `_build_pending_assets` 分别记录 cancellation、filing wrapped failure、material typed failure 与 invariant failure。 |
| A3 | 已修复 | 两文件 material 在第二项转换前取消；断言首项已调用但最终 cancelled、空 events、零 stored、零 batch/source/blob。 |
| A4 | 已修复 | `[ok.pdf, corrupt.docx]` 在第二项抛 typed failure；Service 保留异常 identity，SEC 投影 content failure 且不发布 material source。 |
| A5 | 已修复 | reason direct construction 校验 enum 具体类型与唯一 kind/code mapping；分组显式验证 kind 完整及 code 互斥/完整，parser 复用同一 mapping。 |

## 验证结果

- 新增反例聚焦：`84 passed, 3 warnings`。
- Slice 3 focused matrix：`1235 passed, 1 skipped, 3 warnings`。
- Coverage matrix（focused 加既有 CN download tests）：`1338 passed, 1 skipped, 3 warnings`；11 个计划
  production files 分别为 99%、86%、91%、92%、94%、89%、95%、92%、96%、95%、93%，总计 92%。
- Changed-file Pyright：`0 errors, 0 warnings, 0 informations`。
- Black、Ruff、`git diff --check`：通过。
- skip 是需显式启用的真实 Docling integration；warnings 是三条既有 edgar deprecation warning。
- 未运行 UF-PF06、UF-PF12。

Coverage 首次尝试把模块列表传给 `coverage --source`，触发本地 NumPy C extension collection-time 重复加载；
同一 focused suite 在其前已通过。改为不预导入模块、仅 report 阶段筛选文件后，完整 coverage matrix 正常通过，
因此该次失败属于 coverage invocation 问题，不是产品或测试失败。

## Docs decision

README 不修改：用户明确要求旧引用留 Slice 4，且本 fix 未改变 Slice 3 已批准的最终用户文档边界。

## Residual risks

- Assigned elsewhere：material empty、delete+files 历史项、UF-FIX07 collision/显式 primary/batch association。
- Covered later：README 旧引用由 Slice 4 处理；真实格式矩阵由 UF-PF06/UF-PF12 owner 处理，本轮按约束未运行。
- Accepted：默认跳过的真实 Docling integration 仍需显式环境开关。
- Unclassified：无。

## Completion signal

accepted A1-A5 已全部修复并以 owner-level 反例锁定；没有命中 stop condition。下一入口是 Slice 3 code
re-review，本轮不 commit、不修改 review artifacts、不进入后续 Slice。
