# upload_material 第一轮校准：UM-O10 用户裁决

登记日期：2026-09-23。裁决来源：本轮会话中用户对 UM-O10 的逐项讨论，最终明确回复“同意”，接受修复项 `UM-O10-F01` 及值域 `FY/H1/Q1/Q2/Q3/Q4`（复用 filing 域 canonical 语义）。本文件登记该项最终裁决，不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-A15 | `evidence/actions/UM-A15-period-case-space-normalization` | `--fiscal-period " q1 "`：exit 0；持久化 `fiscal_period: "Q1"`。 |
| UM-S06 | `evidence/supplement/UM-S06-empty-fiscal-period-isolated` | `--fiscal-period ""`：exit 0；持久化 `fiscal_period: null`。 |
| UM-S07 | `evidence/supplement/UM-S07-overlong-fiscal-period-isolated` | `--fiscal-period` 241 个 `P` 字符：exit 0；241 字符原样持久化。 |
| UM-S08 | `evidence/supplement/UM-S08-arbitrary-fiscal-period-isolated` | `--fiscal-period nonsense`：exit 0；持久化 `fiscal_period: "NONSENSE"`。 |

四场景均完成 publication（21 个新文件），manifest 不投影 fiscal_period。S06～S08 分别声明 `supersedes-harness:UM-046/047/048`。period 参与稳定身份是 owner 代码事实（`dayu/fins/pipelines/docling_upload_service.py:1947` identity seed 含 `fiscal_period`），不作为 CLI 证据声明。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. fiscal period 的规范化行为：trim 首尾空白、转大写；规范化后为空的输入转为 `null`（等同未提供）。
2. 该规范化与 filing 域既有 `normalize_fiscal_period`（`dayu/fins/domain/filing_semantics.py:300`）的前半段一致，可作为 accepted 行为登记。

不接受的行为：任意非枚举值与超长值原样持久化并参与身份生成（S07/S08 的观察），不登记为 accepted scenario。

## 已裁决修复项

### UM-O10-F01：fiscal period 值域校验（长度被枚举吸收）

状态：用户接受修复方向，尚未实施。

动机：period 参与稳定身份，`nonsense`、241 字符这类值原样固化进身份 seed 与持久化 meta，会使错误身份永久存在。

语义 owner：`dayu/fins/pipelines/docling_upload_service.py` 的 material identity builder/validator（与 UM-O07-F02、UM-O09-F01 同一 owner）。仓库已有 filing 域 canonical 语义：`dayu/fins/domain/filing_semantics.py:39` 定义 `FiscalPeriod = FY/H1/Q1/Q2/Q3/Q4`，`normalize_fiscal_period` 实现 trim/uppercase/空转 None 加非枚举值 `ValueError`；material 上传路径的 `_normalize_optional_upload_fiscal_period`（`docling_upload_service.py:2027`）未复用它，是本问题的直接成因。

修复要求：

- material 上传路径复用 filing 域 canonical 语义（`FISCAL_PERIODS`/`normalize_fiscal_period`，或经用户确认的 material 专属域），在生成身份前拒绝非域值。
- 用户裁决的值域：`FY/H1/Q1/Q2/Q3/Q4`。
- canonical 域只有 2 字符枚举，长度问题被枚举吸收，不设独立长度上限（区别于 UM-O06 自由文本场景）。
- 校验发生在生成身份前，失败保持零持久化副作用；不固化具体错误文案为 contract。
- 与 UM-O17（form/period 规范化同源）直接关联；若 UM-O17 裁决细化同一 canonical 投影，须显式关联本项，避免重复或矛盾修复。

## 待补跑与 scenario 处置

- A15、S06 的规范化行为可作为 accepted scenario 的证据基础；S07/S08 仅保留为发现证据，不转为长期 accepted scenarios；原 UM-046/047/048 被对应补跑取代。
- 修复获授权并完成后，真实 CLI 补跑：`nonsense`、241 字符被 typed 拒绝且零持久化副作用；` q1 `、空值、域内值（如 `Q1`）保持现有规范化行为并正常上传。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O10 的原始建议（原建议为“接受规范化；任意值和无界长度登记修复”）。长度修复要求经裁决细化为被值域枚举吸收，不另设长度上限。原始运行事实保持不变；冻结报告中的 pending 状态属于当时快照，当前 UM-O10 的用户裁决以本文件为准。

本次仅登记 UM-O10，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
