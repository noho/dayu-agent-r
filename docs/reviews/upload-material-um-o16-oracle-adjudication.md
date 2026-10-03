# upload_material 第一轮校准：UM-O16 用户裁决

登记日期：2026-09-28。裁决来源：本轮会话中用户对 action/files 封闭输入规则及 `UM-O16-F01` 明确回复“同意你的裁决建议。下一项。”本文件登记最终裁决与修复方向，不代表产品修复已获执行授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。所有场景由真实 CLI 在隔离 CI-owned workspace 执行，cwd 为 run 下 `repo`、stdin 为 `DEVNULL`；各目录有 command/result、双流、screen、文件系统前后快照与 diff、key JSON artifacts、durable/SQLite/process 查询。

| 场景 | 原始证据目录 | 直接观察与证据用途 |
| --- | --- | --- |
| UM-053～055 | `evidence/static/UM-053-auto-without-files`、`UM-054-create-without-files`、`UM-055-update-without-files` | fresh workspace 省略 `--files`，均 exit 1、`unexpected_runtime`，无文件系统变化；但缺公司元数据/既有目标等前置条件不能排除，不能单独归因文件缺失。 |
| UM-056 | `evidence/static/UM-056-delete-with-files` | fresh workspace 的 delete 带 `probe.txt`，exit 1、`storage_io`，创建 ticker identity 等文件；因目标不存在，不能证明带文件已被拒绝。 |
| UM-S12 | `evidence/supplement/UM-S12-no-files-baseline` | fresh workspace 以 `auto` 和 `probe.txt` 成功发布材料，为 S13～S15 建立有效既有目标。 |
| UM-S13～S15 | `evidence/supplement/UM-S13-auto-without-files-existing`、`UM-S14-create-without-files-existing`、`UM-S15-update-without-files-existing` | 在 S12 的有效既有目标上分别执行 auto/create/update 并省略 `--files`，均 exit 1、`unexpected_runtime`，先显示 `upload.started`，文件系统无变化。三次分别声明 `supersedes-harness:UM-053/054/055`。 |
| UM-S16 | `evidence/supplement/UM-S16-delete-with-files-baseline` | fresh workspace 用 `probe.txt` 成功发布材料，为 S17 建立有效既有目标。 |
| UM-S17 | `evidence/supplement/UM-S17-delete-with-files-existing` | 在 S16 的有效目标上执行 `--action delete --files inputs/probe-v2.txt`，exit 0、status=deleted、`requested_files=1`、`stored_files=0`；仅 meta/manifest 两项改动为 tombstone，仍保留原 `probe.txt`/Docling 资产与 source fingerprint，未存储或转换传入的 `probe-v2.txt`。声明 `supersedes-harness:UM-056`。 |

S12/S16 均 exit 0，验证后续补跑的业务前置状态。S13～S15 的三次失败和 S17 的成功均无超时、信号或残留进程，stderr/屏幕与文件系统记录一致；workspace 内 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均 queried-but-absent。冻结 `UM-001-help` 声明 auto/create/update 至少一个文件、delete 不得提供文件；help 是公开声明，不替代上述 CLI 行为证据。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. action/files 的封闭输入规则：auto/create/update 要求至少一个文件；delete 要求零文件。
2. 非法组合应在上传生命周期及公司/材料业务持久化前作为字段/动作明确的 typed usage 错误拒绝，不以 `unexpected_runtime`、`storage_io` 或静默忽略输入表示。S17 当前“带文件却成功删除并报告 requested_files=1”的行为不被接受。
3. 无文件组合的校验优先级应稳定，不因目标状态不同而被其它错误遮蔽；不固化具体文案或未经补跑确认的 exit code。

## 已裁决修复项

### UM-O16-F01：action/files 组合的共享前置输入校验

状态：**用户接受修复方向，尚未实施**。

动机：无文件 upsert 经过上传开始后被 `FinsUploadMaterialFiles.from_upsert_paths` 的 `ValueError` 归为通用 runtime；带文件 delete 在 material workflow 中无条件构造空的 `for_delete` selection，原始文件参数被忽略并产生成功删除。S13～S17 把文件组合问题从 fresh 目标缺失等混杂前置条件中隔离出来。

语义 owner：Fins material 请求的 action/files admission contract，与 `dayu/fins/upload_format_contract.py:FinsUploadMaterialFiles` 的 typed selection 保持同源。应在所有入口共用的 material 输入边界根据显式动作及文件 tuple 判定合法组合，再由 CLI/tool 投影同一 typed usage 原因。当前 SEC material workflow 在 `dayu/fins/pipelines/sec_upload_workflow.py` 对 delete 丢弃原始文件 tuple，是 S17 静默忽略的直接代码原因；只改 CLI parser 或该市场 workflow 会使非 CLI/CN/HK 路径分叉。

修复要求：auto/create/update 无文件时、delete 带任何文件时，都在上传开始与公司/材料业务持久化前拒绝；错误指出动作和文件组合，不能转换、忽略或悄悄删除所传文件；规范化结果、CLI summary 与持久化事实应一致。与 UM-O15 的 target-missing 前置校验协调顺序，使非法文件组合不被缺目标错误遮蔽；不对 argparse 已处理的 `--files` 后缺参数值建立兼容分支。

## 待补跑与 scenario 处置

UM-053～056 为混杂前置条件的发现证据，不单独支持 action/files 的接受结论；S13～S15 与 S17 为缺陷发现证据，不转为接受当前错误/静默删除的长期 scenarios。S12/S16 仅为有效状态基线。修复获单独授权并完成后，真实 CLI 在 fresh 与已有目标上补跑三种无文件动作、delete 带文件、合法带文件 upsert 与合法无文件 delete，核对 screen/双流/exit、文件系统、公司/材料 meta/manifest、durable/SQLite/process；还应验证非 CLI material 入口复用同一 contract。

## 裁决替代关系

本裁决替代冻结 observed report UM-O16 的 pending 建议，以 S12～S17 的有效前置状态确定封闭输入规则，不把 UM-056 的 `storage_io` 错误归因于文件组合。原始 evidence 不改写；UM-O15 的 missing target 和 UM-O13 的合法 delete 语义分别保持独立。本次不修改正式 registry/readiness，也不将 upload_material 加入 readiness scope。
