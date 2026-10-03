# upload_material 第一轮校准：UM-O18 用户裁决

裁决日期：2026-09-28。用户对保留并实现 material `--amended` 语义及修复候选 `UM-O18-F01` 明确回复“同意你的裁决建议。下一项。”本文件登记 accepted 行为和已裁决修复方向；产品实现仍未获单独授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。A16/A17 在同一 CI-owned workspace `workspaces/identity/amended` 中顺序调用真实 CLI，cwd 为该 run 的 `repo`，stdin 为 `DEVNULL`。各原始目录均有 command/result、双流、screen、文件系统前后快照与 diff、key JSON artifacts、durable/SQLite/process 查询。

| 场景 | 原始证据目录 | 直接观察 |
| --- | --- | --- |
| UM-A16 | `evidence/actions/UM-A16-amended-baseline` | `--ticker AAPL --action auto --forms MATERIAL_OTHER --material-name "Amended Identity" --files inputs/probe.txt --company-name "Apple Inc."`，未传 `--amended`；exit 0，ID `mat_be36ccd60de3b4d561068025a9489141db93fe53`，source meta 和 material manifest 为 `v1`，source meta 不含 `amended`。 |
| UM-A17 | `evidence/actions/UM-A17-amended-same-fields` | 同一 workspace、同一 ticker/form/name，改用 `inputs/probe-v2.txt` 并传 `--amended`；exit 0，ID 不变，source meta 和 manifest 为 `v2`，source meta 仍不含 `amended`。旧 original/Docling JSON 被移除，新文件写入同一 material 目录。 |

A16/A17 的 stderr 均为空、无超时、无残留进程；workspace 内 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均 queried-but-absent。冻结源码/当前代码核对显示：CLI 公开 `--amended` 并写入 `FinsUploadMaterialRequest`；material workflow 的调用签名、上传 meta、事件和结果均未接收或投影它。source fingerprint 的内容变化会使 `document_version` 递增，因此 A17 的版本变化不能单独归因于 `--amended`。A16/A17 同时改变输入文件和 amended 标记，没有构成该标记的因果对照实验。不能据此推断同内容切换该标记的真实 CLI 行为。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

保留 material 公开 `--amended`，定义为**当前发布材料是否为修订材料**的布尔业务事实。成功发布后，该事实应在 source meta 中持久化，并由同一事实投影到 material manifest 和存在该字段的事件/结果。`amended` 不参与 material 稳定 ID；同一材料新内容沿用 ID，而 `document_version` 仍由内容/发布版本规则负责，不能把版本递增解释成 amended 标记生效。A16/A17 可支持稳定 ID 与不同内容导致的版本替换这一窄观察；A17 当前“传 `--amended` 却未持久化”的行为不予接受。当前证据不足以规定首次上传带 `--amended`、同内容只改标记、删除与恢复时该标记的完整状态机，须在实现前明确 owner 级规则并补证。

未采用移除公开参数的替代方案。现有 CLI help 已承诺“标记为修订文件”，且 material 修订有独立业务含义。

## 已裁决修复项

### UM-O18-F01：material amended 的单一发布事实

状态：**修复方向已接受，尚未实施**。

动机：material 请求和可能的 job 摘要带有 `amended`，但市场 workflow 不向发布 owner 传递它，source meta/manifest 与用户可见结果缺失；请求意图与持久化材料事实脱节。`v2` 是内容变更的结果，无法替代 amended 事实。

语义 owner：Fins material 请求校验与发布准备边界产生、验证 amended 事实；source meta 是当前发布材料的持久化真源；material manifest 和相关事件/结果从该事实投影。CLI/Service/tool/batch plan 仅负责传递，不各自推导；storage 仓储负责按已定义 schema 原子持久化和投影，不能从版本号、文件名或用户输入历史反推 amended。

修复要求：定义 `amended` 与 material 身份、内容版本相互独立的规则；将请求布尔值从所有 material 入口送到共同发布 owner，写入 source meta，并从 source meta 统一投影到 manifest 和相关结果/事件；现有 A17 预期为 `amended=true`、稳定 ID 不变、内容版本 `v2`，A16 为 `amended=false`、`v1`。不能只在 CLI 输出中展示正确，也不能只在 job 摘要中保留请求值。对同内容只改 amended 标记、跳过上传、首次发布、删除/恢复的 owner 级状态转换和用户可见结果，需要在实施方案中先定义并用测试和真实 CLI 补跑验证；避免被内容指纹去重吞掉元数据变更。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。A16/A17 的成功、稳定身份、文件替换和 `v1→v2` 保留为观测；A17 的 amended 缺失只作为缺陷证据，不转 accepted scenario。若修复获单独授权，至少使用隔离 workspace 做真实 CLI 对照：同输入内容分别带/不带 `--amended`，内容改变但不带 `--amended`，再核对 screen/exit、source meta、material manifest、身份、版本及跨命令读取；所有原始证据和补跑 lineage 分开保存。LLM tool 与 batch plan 作为非 CLI 输入边界另行验证。

## 裁决替代关系

本裁决取代冻结 observed report UM-O18 的 pending 建议，明确不能把 A17 版本递增当作 amended 标记的因果证据。原始 evidence 不改写；正式 registry/readiness 待后续统一登记。

## 2026-09-29 补充用户裁决：同内容与 overwrite

同字节材料只切换 `amended` 时，未指定 `--overwrite` 走仅更新元数据、保留内容版本；指定 `--overwrite` 则强制重新转换并发布，即使字节未变，版本仍按现有指纹规则保持。`amended` 与内容版本是两个独立事实；发布结果、source meta 与 manifest 必须同源。该决定已在 O18 独立 plan adjudication 的 PR2-F3 和主修复队列登记，待 O12/O14/O15 集成后按八格计划实施与真实 CLI 验证；冻结 A16/A17 不据此改写。
