# upload_material 第一轮校准：UM-O09 用户裁决

登记日期：2026-09-16。裁决来源：本轮会话中用户对 UM-O09 的逐项讨论，最终明确回复“同意建议”并指定合法财年域为 1800–2100。本文件登记该项最终裁决，不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-S03 | `evidence/supplement/UM-S03-negative-fiscal-year-isolated` | `--fiscal-year -1`：exit 0；`fiscal_year: -1` 原样持久化。 |
| UM-S04 | `evidence/supplement/UM-S04-zero-fiscal-year-isolated` | `--fiscal-year 0`：exit 0；`fiscal_year: 0` 原样持久化。 |
| UM-S05 | `evidence/supplement/UM-S05-large-fiscal-year-isolated` | `--fiscal-year 10000`：exit 0；`fiscal_year: 10000` 原样持久化。 |

三场景分别声明 `supersedes-harness:UM-043/044/045`；除 material-name 与 fiscal-year 外其余输入一致，stable ID 差异不能单独归因 fiscal_year。fiscal_year 参与身份生成是 owner 代码事实（`dayu/fins/pipelines/docling_upload_service.py:1947` seed 构造含 `fiscal_year`），不作为 CLI 证据声明。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

本项无新增 accepted 行为；`-1`、`0`、`10000` 原样持久化并参与身份生成的行为不被接受。

## 已裁决修复项

### UM-O09-F01：fiscal_year 合法域校验

状态：用户接受修复方向，尚未实施。

动机：财年是财报身份的一部分，负、0 与远超当前年份的值不是任何真实财年；非法值原样进入持久化 meta 并参与 stable identity seed，会使错误身份永久固化。

语义 owner：`dayu/fins/pipelines/docling_upload_service.py` 的 material identity builder/validator（与 UM-O07-F02 同一 owner），校验必须在生成身份前完成。

修复要求：

- 由身份/元数据 owner 定义合法财年域为 1800–2100（用户裁决值，含端点），拒绝负、0 与超出该域的整数。
- 在生成身份前校验非法值并拒绝，保持零持久化副作用，遵循 UM-O07-F02 的“尽可能在开始上传生命周期前完成校验、零副作用”原则。
- 不固化具体错误文案为 contract；CLI 已保证 int 解析，非整数输入属 UM-O02 已接受的 parser 基线，不在本项范围。

## 待补跑与 scenario 处置

- S03～S05 保留为发现证据，不转为长期 accepted scenarios；原 UM-043/044/045 被对应补跑取代。
- 修复获授权并完成后，真实 CLI 补跑：`-1`/`0`/`10000` 被拒绝且零持久化副作用；域内合法值（如 2024）正常上传并持久化。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O09 的原始建议。原始运行事实保持不变；冻结报告中的 pending 状态属于当时快照，当前 UM-O09 的用户裁决以本文件为准。

本次仅登记 UM-O09，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
