# upload_material 第一轮校准：UM-O08 用户裁决

登记日期：2026-09-16。裁决来源：本轮会话中用户对 UM-O08 的逐项讨论，最终明确回复“同意建议”。本文件登记该项最终裁决，不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-037 | `evidence/static/UM-037-document-id-empty` | 显式空 document_id：exit 2；stderr 为字段级拒绝；文件系统零副作用。 |
| UM-S02 | `evidence/supplement/UM-S02-empty-internal-id-isolated` | 显式空 internal_document_id：exit 0；空串被当作未提供，真实上传完成并持久化 owner 生成的身份。 |

两场景 action、workspace、文件输入与被测参数均不同，不构成变量一致的配对实验；UM-S02 声明 `supersedes-harness:UM-041`。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 公开 `--document-id` 显式空值在 CLI 输入边界被拒绝（exit 2，`--document-id must not contain empty item`），保持零持久化副作用。
2. 不把“显式空 internal_document_id 被当作未提供并成功上传”登记为 accepted scenario。

## 修复关联

原建议“两个显式 ID 参数共享空值规则”已因 UM-O07 批准移除 material 公开 internal_document_id 输入而失去前提。空内部 ID 的“空串视作未提供”问题并入 `UM-O07-F01`（移除 material internal_document_id 公开输入），不建立保留该参数并补空值校验的独立修复项。

## 待补跑与 scenario 处置

- 补跑并入 UM-O07 裁决的待补跑清单：修复获授权并完成后，旧参数传空/非空均被作为未知参数拒绝且零副作用；省略内部 ID 的正常上传与跨命令消费正常。
- UM-037 与 UM-S02 均保留为冗余 public surface 的发现证据，不转为长期 accepted scenarios。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O08 的原始建议。原始运行事实保持不变；冻结报告中的 pending 状态属于当时快照，当前 UM-O08 的用户裁决以本文件为准。

本次仅登记 UM-O08，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
