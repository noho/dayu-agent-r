# upload_material 第一轮校准：UM-O17 用户裁决

裁决日期：2026-09-28。用户明确回复“同意你的裁决建议，处理form类别的代码做成一个函数，其它地方调用，防止逻辑漂移。下一项。”本文件登记 accepted 行为和已裁决修复方向；产品实现仍未获单独授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。A14/A15 均由真实 CLI 在各自独立的 CI-owned fresh workspace 中运行，cwd 为 run 下 `repo`，stdin 为 `DEVNULL`，输入文件为 `inputs/probe.txt`。每个目录均有 exact command/result、双流、screen、文件系统前后快照与 diff、key JSON artifacts、durable/SQLite/process 查询。

| 场景 | 原始证据目录 | 直接观察 |
| --- | --- | --- |
| UM-A14 | `evidence/actions/UM-A14-form-case-space-normalization` | `--forms " material_other " --material-name "Normalize Form"`：exit 0，发布 21 个新条目；source meta 与 material manifest 均持久化 `form_type="material_other"`，document/internal ID 为 `mat_294e14256d78c8df2897693749d9be85160d42cd`。 |
| UM-A15 | `evidence/actions/UM-A15-period-case-space-normalization` | `--forms MATERIAL_OTHER --material-name "Normalize Period" --fiscal-year 2025 --fiscal-period " q1 "`：exit 0，发布 21 个新条目；source meta 中 `form_type="MATERIAL_OTHER"`、`fiscal_period="Q1"`，manifest 的 form 亦为 `MATERIAL_OTHER`；manifest 不投影 fiscal_period。document/internal ID 为 `mat_bc6d383d5355c57bd36142de4dc93a752c23e553`。 |

两次 stderr 为空、无超时、无残留进程；workspace 内 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均 queried-but-absent。冻结源码 `dayu/fins/pipelines/docling_upload_service.py:build_material_ids` 对 form 做 trim/uppercase 后进入 identity seed。将 `MATERIAL_OTHER|Normalize Form` 按其 SHA-1 规则计算，得到 A14 所观察的 ID；原小写 form seed 得到不同值。这是代码与数据同源的 identity 解释，不把单次 A14 运行误当作两种输入的 CLI 配对实验。A15 的 `Q1` 规范化与 UM-O10 已接受行为一致。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

接受 material form type 作为类别代码的 trim/uppercase 规范化，并要求同一 canonical form 事实同时用于稳定身份、source meta、material manifest 及对外事件/结果中存在该字段的投影。A14 当前身份按 `MATERIAL_OTHER` 生成而持久化 `material_other` 的分叉不予接受；不在本项凭两个成功场景设定新的 form 枚举或长度限制。A15 的财期 trim/uppercase 与允许域继续按已裁决的 UM-O10 处理，不登记一套新的 period 规则或重复修复。

## 已裁决修复项

### UM-O17-F01：material form 的 canonical 值统一投影

状态：**修复方向已接受，尚未实施**。

动机：身份生成器局部规范化 `form_type`，US/CN/HK material workflow 则把原始或仅 trim 后的 form 继续投影给上传结果与 publication meta。A14 的 ID 与持久化字段因此对同一类别表达不同事实，后续读取、匹配和证据引用可能发生语义偏移。

语义 owner：`dayu/fins/pipelines/docling_upload_service.py` 的 material identity builder/validator 及其直接上游 Fins material 请求校验边界，应唯一产生并承诺 canonical form 值；身份、事件、source meta 与 manifest 都从这一值派生。不能在仓储、展示层、单个市场流程或消费者处各自 upper/重算。`fiscal_period` 的 canonical 值与枚举校验已归 UM-O10-F01，实施时应复用其唯一来源，不在本项另设 period owner。

修复要求：在 Fins material 语义 owner 处提供**一个共享的 form 类别规范化函数**，集中执行有效值的 trim/uppercase；身份生成、各市场工作流、上传结果、事件和持久化投影均调用或使用该函数产生的同一 canonical 值，禁止各处复制规范化逻辑，防止逻辑漂移。A14 输入应继续正常上传，身份保持 canonical seed 语义，meta/manifest 改为 `MATERIAL_OTHER`。原值不作为第二套持久化业务事实；不引入兼容 alias 或 downstream fallback。与 UM-O07 稳定身份、UM-O10 period 值域、UM-O05 form 必填边界明确协同。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。A14 保留为 form 投影分叉的缺陷发现证据，当前小写持久化不转为 accepted scenario；A15 已是 UM-O10 规范化行为的证据基础，不在本项重复登记。若修复获单独授权并完成，真实 CLI 在隔离 workspace 补跑 `" material_other "` 与 `MATERIAL_OTHER`，核对 canonical 身份、meta/manifest、事件/summary 及跨命令读取一致；财期 `" q1 "` 与域内/域外输入依 UM-O10-F01 的清单验证。两次独立输入的身份等价性需有真实 CLI 配对证据，不以单次 SHA-1 推算替代。

## 裁决替代关系

本裁决取代冻结 observed report UM-O17 的 pending 建议，明确 form 为本项新增修复、period 复用 UM-O10-F01，不重复登记同一语义。原始 evidence 不改写；正式 registry/readiness 待后续统一登记。
