# upload_material 第一轮校准：UM-O13 用户裁决

登记日期：2026-09-28。裁决来源：本轮会话中用户对 UM-O13 的核心动作链及修复候选 UM-O13-F01 明确回复“同你你建议的裁决。下一条。”本文件由待裁决底稿更新为最终裁决；不代表产品修复已获执行授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。同一 CI-owned workspace `workspaces/actions/main` 中使用 `MATERIAL_OTHER`、`Calibration Deck` 及稳定 document ID `mat_e7e5eeabf0469cf3759d482b8f58a2c1b0f8f8ce`。原始命令、结果、屏幕、文件系统前后快照与 diff、key JSON artifacts 均位于下表目录。

| 场景 | 原始证据目录 | 观察概要 |
| --- | --- | --- |
| UM-A01 | `evidence/actions/UM-A01-auto-fresh-create` | fresh auto 用 `probe.txt` 创建 v1。 |
| UM-A02 | `evidence/actions/UM-A02-auto-identical-repeat` | 相同输入 auto 返回 skipped，文件系统无变化。 |
| UM-A03 | `evidence/actions/UM-A03-auto-changed-update` | 换 `probe-v2.txt` 后 auto 更新同 ID 至 v2。 |
| UM-A04/A05 | `evidence/actions/UM-A04-create-existing`、`evidence/actions/UM-A05-create-existing-overwrite` | 中间状态上下文：A05 的 create --overwrite 以 `probe.txt` 将文档升至 v3；create 的正确语义留待 UM-O14 裁决。 |
| UM-A06 | `evidence/actions/UM-A06-update-existing-identical` | 在 A05 的 v3 基础上，显式 update 相同 `probe.txt` 返回 skipped，文件系统无变化。 |
| UM-A07 | `evidence/actions/UM-A07-delete-existing` | delete 后 meta/manifest 写入 `is_deleted=true`、`deleted_at=2026-08-18T09:00:15+00:00`，版本保持 v3，原资产仍在。 |
| UM-A08 | `evidence/actions/UM-A08-delete-already-deleted` | 再次 delete 返回 deleted，但 meta/manifest 均重写，`deleted_at` 改为 `2026-08-18T09:00:17+00:00`，`updated_at` 亦改变，版本仍为 v3。 |
| UM-A09 | `evidence/actions/UM-A09-auto-after-delete` | 用原 `probe.txt` 执行 auto，原 ID 清除 tombstone 并恢复，版本保持 v3；仅 meta/manifest 改动。 |

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 在已测 fresh 状态，`auto` 创建材料 v1；相同输入再次 `auto` 返回 skipped 且业务文件无变化；不同内容的 `auto` 更新同一稳定 ID 并使内容版本从 v1 到 v2。
2. A05 已将内容换回 `probe.txt` 并升至 v3；在此状态下，A06 显式 `update` 相同内容返回 skipped，业务文件无变化。v3 不归因于 A06。A04/A05 的 `create`/`--overwrite` 正确语义仍归 UM-O14 独立裁决。
3. 对现存材料首次 `delete` 产生逻辑 tombstone，版本保持 v3，原资产保留；已删除时再次 `delete` 可以成功返回已删除状态，但持久化状态应幂等，当前 A08 改写时间的行为不被接受。
4. 在已测同内容输入下，删除后的 `auto` 恢复原文档 ID，清除 tombstone，版本保持 v3。该结论不外推至不同内容或并发恢复。

## 已裁决修复项

### UM-O13-F01：重复 delete 不改写既有 tombstone 时间

状态：**用户接受修复方向，尚未实施**。

动机：A08 在已有 `is_deleted=true` 的状态再次执行 delete，仍返回 `deleted`，却把 `deleted_at` 从 A07 首次删除时间改为本次调用时间，同时改写 meta 与 manifest。若 `deleted_at` 表达状态转入已删除的时间，这会丢失原始删除事实，也不满足重复请求的持久化幂等。

语义 owner：`dayu/fins/storage/_fs_source_document_core.py` 的 source-document 删除状态转换负责产生并写入 canonical `is_deleted/deleted_at/updated_at`；上传动作状态机须以这一 owner 的状态结果投影 CLI。冻结 commit 的 `_toggle_source_deleted` 对每次 `deleted=True` 均调用当前时间，是直接代码解释。修复应在 owner 边界维护状态转换语义，避免仅在 CLI 或 manifest 输出做补偿。

修复要求：已删除状态再次 delete 应保留当前 tombstone 周期首次进入已删除状态时的 `deleted_at` 与业务元数据字节，不重新发布 tombstone；CLI 可继续报告已删除。恢复后再次删除是新的状态转换，应产生新的 `deleted_at`。meta 与 manifest 必须投影同一真源；不以固定输出文案作为 contract。共享 source-document 状态 owner 的更改须核对 filing 等其它消费者，不静默改写其已冻结 oracle。

## 待补跑与 scenario 处置

UM-A01/A02/A03/A06/A07/A09 可作为上述 accepted 行为的 scenario 证据基础；UM-A08 仅保留为非幂等 tombstone 的缺陷发现证据，不将改写 `deleted_at` 登记为 accepted scenario。修复获单独授权并完成后须用真实 CLI 补跑首次删除、重复删除、恢复与再次删除，核对 `deleted_at`、版本、meta/manifest、文件差异及 CLI 投影。现有冻结证据不能证明不同内容的删除后恢复或并发重复删除行为。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O13 的整体接受建议：接受有证据支撑的动作链，同时排除 A08 的 tombstone 时间改写并登记 UM-O13-F01。原始 evidence 保持不变；不影响 UM-O14 的独立 create/overwrite 裁决。本次不新增正式 registry 条目，也不将 upload_material 加入 readiness scope。
