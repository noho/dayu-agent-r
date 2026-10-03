# upload_material 第一轮校准：UM-O14 用户裁决

登记日期：2026-09-28。裁决来源：本轮会话中用户对 UM-O14 的严格 `create` 冲突语义及 `UM-O14-F01` 明确回复“同意你的裁决建议。下一项。”本文件登记最终裁决与修复方向，不代表产品修复已获执行授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。以下运行使用同一 CI-owned workspace `workspaces/actions/main`、ticker AAPL、form `MATERIAL_OTHER`、material name `Calibration Deck` 及稳定 document ID `mat_e7e5eeabf0469cf3759d482b8f58a2c1b0f8f8ce`。原始 command/result/screen/filesystem-diff/key-json-artifacts 位于各目录。

| 场景 | 原始证据目录 | 直接观察 |
| --- | --- | --- |
| UM-A03 | `evidence/actions/UM-A03-auto-changed-update` | 用 `probe-v2.txt` 的 auto 上传后，现存材料为 v2，source fingerprint 为 `afc63eb1d5726ff63850ab80342d227363c9dff92abd996187d6bc20dd07b3b6`。 |
| UM-A04 | `evidence/actions/UM-A04-create-existing` | 在 A03 的 v2 状态，对同一 identity、同一个 `probe-v2.txt` 执行 `--action create`，未提供 `--overwrite`：exit 0、status=skipped、stored_files=0；文件系统无变化，meta/manifest 保持 v2 与相同 fingerprint。 |
| UM-A05 | `evidence/actions/UM-A05-create-existing-overwrite` | 在 A04 的 v2 状态，用内容不同的 `probe.txt` 执行 `--action create --overwrite`：exit 0、status=ok、stored_files=1；同 ID 版本升至 v3，fingerprint 变为 `1874a0212bad3c52f3ec53066a269335e670f108571ae0f234c3b21b3ce72bc1`；文件系统 2 创建、2 修改、2 删除。 |

三次 stderr 为空、无超时或残留进程；workspace 内 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均 queried-but-absent。`inputs/input-manifest.json` 记录 `probe-v2.txt`（44 字节）与 `probe.txt`（36 字节）输入 SHA-256 不同。冻结 observed report 将 A04 描述为“既有不同内容上 create”，与 A03/A04 的 exact argv 和持久化 fingerprint 不符；本底稿以原始证据纠正为“既有相同内容上 create”。无覆盖的分支是**已有材料、不同内容、显式 create 且没有 overwrite**。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 显式 `create` 用于创建新的 active identity；已有 active identity 且未指定 `--overwrite` 时，无论内容相同或不同都应明确拒绝为 typed target-exists/conflict，保持零公司与文档业务持久化副作用。A04 的相同内容 skip 不被接受。
2. 相同内容重试/跳过由 UM-O13 已接受的 `auto` 承担；显式 `update` 表达修改已有目标。
3. `create --overwrite` 可对已有目标明确替换：A05 证明在所测不同内容输入下保留稳定 ID，内容升版且 meta/manifest 一致。不固化固定文案、固定 ID 或 A04 的延迟 skip 时序。
4. 已删除 tombstone 上的显式 `create` 未经本组覆盖，本项不推断其语义。

## 已裁决修复项

### UM-O14-F01：material create 的 target-exists 前置拒绝

状态：**用户接受修复方向，尚未实施**。

动机：A04 中显式 `create` 命中 active 既有目标却返回 `skipped`，使 create 与已接受的 auto 相同内容路径在用户可见语义上重合。冻结代码的共享 `evaluate_upload_overwrite_precondition` 已在“create + 既有目标 + 无 overwrite”时产生 `CREATE_TARGET_EXISTS`，但上传服务仅对 filing 执行该拒绝，material 继续进入相同指纹 skip。这是代码侧直接成因，不依赖对未测“不同内容无 overwrite”分支的推断。

语义 owner：Fins 上传动作/既有 source 状态的 shared precondition `dayu/fins/pipelines/docling_upload_service.py:evaluate_upload_overwrite_precondition`；material 请求的状态感知前置校验须在读取权威 published source state 后复用该结果，并在 `upload.started`、公司提交和转换前拒绝。仓储 publication 边界仍需保证并发条件下不能覆盖非授权目标。CLI 仅投影 typed 错误，不能独立维护另一套 create 规则。

修复要求：对 active 已有目标且无 `--overwrite` 的显式 material create 返回动作明确的 typed conflict；相同内容也不 skip；`--overwrite` 允许明确替换，并保持同一稳定 ID、内容版本与 meta/manifest 一致；拒绝前不产生公司或文档业务持久化。不得把 A04 误标为不同内容证据，亦不得用 CLI 或单一市场入口的局部判断替代共享 owner。

## 待补跑与 scenario 处置

UM-A04 仅保留为相同内容 create 错误 skip 的发现证据，不转为长期 accepted scenario。UM-A05 可作为明确覆盖成功行为的 scenario 证据基础。先在隔离 CI workspace 最小补跑“已有 active 目标、不同内容、create、无 overwrite”，纠正首轮覆盖缺口并记录完整原始 CLI 证据；A04 不能替代它。修复获单独授权并完成后，还应补跑相同内容 create 拒绝、不同内容 create 拒绝、`create --overwrite` 替换、fresh create 成功，以及必要的 tombstone/并发边界。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O14 的 pending 建议，纠正其对 A04 前置内容的误标，并确定严格 create 冲突语义。原始 evidence 保持不变；UM-O13 对 A05 v3 的使用仅为动作链上下文。本次不修改正式 registry/readiness，也不将 upload_material 加入 readiness scope。
