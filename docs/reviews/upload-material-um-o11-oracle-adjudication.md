# upload_material 第一轮校准：UM-O11 用户裁决

登记日期：2026-09-25。裁决来源：本轮会话中用户对 UM-O11 的逐项呈报明确回复“同意建议。下一个”。本文件登记该项最终裁决与修复要求，不代表产品修复已获执行授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。原始真实 CLI 的 validation commit 为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`；不以该运行证明当前 HEAD 行为。

| 场景 | 原始证据目录 | 已观察结果 |
| --- | --- | --- |
| UM-A18 | `evidence/actions/UM-A18-invalid-date-publication` | 同时输入 `--filing-date 2025-02-30`、`--report-date nonsense`：exit 0；两个原始字符串进入材料 meta 与 manifest。 |
| UM-S09 | `evidence/supplement/UM-S09-empty-filing-date-isolated` | 输入 `--filing-date ""`：exit 0；材料 meta 与 manifest 的 `filing_date` 为 `null`。 |
| UM-S10 | `evidence/supplement/UM-S10-invalid-filing-date-isolated` | 单独输入 `--filing-date 2025-02-30`：exit 0；原始字符串进入材料 meta 与 manifest。 |
| UM-S11 | `evidence/supplement/UM-S11-invalid-report-date-isolated` | 单独输入 `--report-date not-a-date`：exit 0；原始字符串进入材料 meta 与 manifest。 |

四次使用独立 CI-owned workspace、同一 `inputs/probe.txt`，均报告 upload completed / succeeded，发布材料且 `ingest_complete=true`；每次新增 21 个文件系统条目、stderr 为空、残留进程为 0。workspace 范围的 SQLite、Host EventLog、Trace、Memory 与旧 ingestion job 均为 queried-but-absent。S09～S11 分别声明 `supersedes-harness:UM-049/050/051`。各场景同时改变了材料名称和 workspace，不能通过稳定 ID 差异推断日期参与身份生成。本组未单独测试显式空 `report_date` 或合法日期对照。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 公开 `--filing-date` 显式空字符串经当前 CLI 输入边界成为 `null`，上传可完成，材料 meta 与 manifest 均投影 `null`。
2. 不把非法日期字符串原样持久化、成功退出或该错误情况下的进度输出登记为 accepted 行为。空 `report_date` 未获本组证据支持，不由本裁决推广。

## 已裁决修复项

### UM-O11-F01：material 上传日期合法性前置校验

状态：用户接受修复方向，尚未实施；本裁决不构成产品修复授权。

动机：`2025-02-30` 不是存在的公历日期，`nonsense` / `not-a-date` 也不符合日期格式；当前输入作为日期事实同时进入 source meta 与 material manifest，使错误业务事实持久化并可被后续消费者读取。

语义 owner：日期格式和日历存在性规则由 `dayu/fins/domain/filing_semantics.py` 的 `parse_iso_calendar_date` 统一定义。material 上传请求的 Fins 前置校验边界负责在发布前承诺两个日期字段为合法的可选日期；不同市场的上传流程、CLI、tool、仓储和 manifest 不能各自建立日期规则或事后补救。现有 filing 上传请求在 `dayu/fins/ingestion_runtime.py` 已复用该日期真源；material 路径缺少对应校验。具体实现边界需在修复任务中按 US/CN/HK 共用输入链确认，且必须早于公司与文档持久化。仅在 `docling_upload_service` 后段校验不足以保证该要求。

修复要求：

- 对 material `filing_date`、`report_date` 的非空输入复用严格 `YYYY-MM-DD` 与真实公历日期校验；保留已接受的显式空 `filing_date` 转 `null`。
- 非法值以字段明确的 typed 输入错误拒绝；不固化当前错误文案或未经观察的具体 exit code。
- 校验先于上传生命周期的持久化步骤，失败时公司与文档均无持久化副作用，且不能写入 source meta 或 material manifest。
- 从同一通过校验的日期事实投影结果、元数据与 manifest；避免仅在 CLI、单一市场流程或仓储层做局部补偿。

## 待补跑与 scenario 处置

- UM-S09 可作为显式空 `filing_date` 转 `null` 的 accepted scenario 证据基础。UM-A18、UM-S10、UM-S11 仅保留为缺陷发现证据，不转为长期 accepted scenarios。
- 修复获单独执行授权并完成后，用真实 CLI 在隔离 CI workspace 补跑：非法 filing 日期、非法 report 日期分别 typed 拒绝并确认公司与文档零持久化副作用；合法日期对照正常上传且 meta/manifest 一致；显式空 `filing_date` 继续转 `null`。
- 若将显式空 `report_date` 纳入正式 contract，须另取真实 CLI 证据并逐项裁决，不能从 S09 类推。

## 裁决替代关系

本裁决替代冻结 observed report 中 UM-O11 的原始 pending 建议，并细化为已测空值行为、日期修复及待补跑。原始运行事实与 evidence 原字节保持不变；冻结报告的 pending 状态属于当时快照。

本次仅登记 UM-O11，不改写已闭环命令的 accepted oracle，不新增正式 accepted scenarios，也不将 upload_material 加入 readiness scope。产品修复尚未执行。
