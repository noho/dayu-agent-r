# upload_material 第一轮校准：UM-O07 用户裁决

登记日期：2026-09-15。裁决来源：本轮会话中用户对 UM-O07 的逐项讨论，最终明确回复“同意你的建议”。本文件登记该项最终裁决与修复要求，不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。

原始 CLI 记录位于以下相对目录，保留 exact argv、屏幕输出、退出状态、文件系统 diff 与持久化元数据；汇总底稿为 root 下的 `observed-behavior.json` 与 `observed-behavior.md`（UM-O07）。本裁决从该汇总及本轮 owner 调查形成，冻结证据不作改写。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-A22 | `evidence/actions/UM-A22-exact-document-id` | 精确 document_id：exit 0；元数据和 manifest 中两个 ID 一致。 |
| UM-A23 | `evidence/actions/UM-A23-mismatched-document-id` | 不匹配 document_id：exit 1；无 publication；对外为笼统参数错误。 |
| UM-A24 | `evidence/actions/UM-A24-exact-internal-document-id` | 精确 internal_document_id：exit 0；两个持久化 ID 相同。 |
| UM-A25 | `evidence/actions/UM-A25-mismatched-internal-document-id` | 不匹配 internal_document_id：exit 1；无 publication。 |

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. Material 身份由唯一 owner 根据规范化 form、material name 和适用 fiscal 字段确定性生成。
2. 持久化 internal_document_id 由 owner 生成，当前与稳定 document_id 一致。字段保留不构成允许调用者输入该字段的理由。
3. 保留公开 document_id 作为稳定身份的一致性断言；显式值不能覆盖 owner 生成的身份。不匹配时应拒绝，且无持久化副作用。
4. 成功结果中同一身份在事件、元数据和 manifest 的投影应一致。

具体摘要算法、固定摘要字面值、笼统错误文案以及先发出 upload.started 再拒绝非法身份的时序，不作为 accepted contract。

## 已裁决修复项

### UM-O07-F01：移除 material 的公开 internal_document_id 输入

状态：用户接受修复方向，尚未实施。

动机：`build_material_ids` 返回同一个值作为两个 ID；显式 internal_document_id 仅重复校验，不能接受独立的外部来源编号。当前 tool schema 将其描述为可提供的精确源文件 ID，与实际能力不符。

语义 owner：`dayu/fins/pipelines/docling_upload_service.py` 的 material identity builder/validator。输入传播路径为 CLI 或 upload tool → material request/Service → runtime → SEC/CN/HK material workflow → identity owner → repository。

修复要求：

- 移除 `dayu-cli upload_material --internal-document-id` 与对应用户输入透传。
- 同步移除 LLM upload tool 的 material `internal_document_id` 输入能力，以及 material 用户请求链路的冗余输入字段，避免仅在单一入口隐藏。
- 底层统一源文档模型仍保留 internal_document_id，由 material owner 产生；filing 领域独立来源身份语义不在本项修改范围。
- 不保留隐藏参数、废弃别名或兼容 wrapper。
- 保留公开 document_id 的一致性断言能力。

### UM-O07-F02：公开 document_id 不匹配的错误投影与校验边界

状态：用户接受修复方向，尚未实施。

由身份 owner 或其直接上游输入校验边界识别不匹配，向调用者给出可操作的字段级错误；尽可能在开始上传生命周期前完成校验，并保持零持久化副作用。不得固化当前笼统错误和延迟校验时序。

原建议将此问题与 UM-O08 的身份输入边界合并处理。UM-O08 尚未逐项裁决；本项移除 internal_document_id 输入的决定已使“两个公开 ID 参数共享空值规则”的原建议失去前提，后续裁决应据此调整，不能登记为保留该参数的要求。

## 待补跑与 scenario 处置

- UM-A22/UM-A23 支持上述 document_id 一致性与失败原子性的接受结论；后续正式 scenario 登记应排除当前笼统错误文案和延迟校验时序。
- UM-A24/UM-A25 仅保留为冗余 public surface 的发现证据，不转为长期 accepted scenarios。
- 修复获授权并完成后，真实 CLI 补跑：help 不再展示该参数；旧参数输入被拒绝且无副作用；省略内部 ID 的上传及跨命令消费正常；document_id 正确/错误断言与持久化一致性正常。
- LLM tool schema 和非 CLI material 输入边界的移除需另行验证；不得用此类静态检查或测试替代 CLI 补跑证据。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O07 的初始“接受两个显式 ID 一致性断言”建议，以及会话中对该参数公开暴露的初始接受建议。原始运行事实保持不变；冻结报告中的 pending 状态属于当时快照，当前 UM-O07 的用户裁决以本文件为准。

本次仅登记 UM-O07，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
