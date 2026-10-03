# upload_material 第一轮校准：UM-O15 用户裁决

登记日期：2026-09-28。裁决来源：本轮会话中用户对 UM-O15 的 typed target-missing、零业务持久化及 `UM-O15-F01` 明确回复“同意你的裁决建议。下一项。”本文件登记最终裁决与修复方向，不代表产品修复已获执行授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。三次均由真实 CLI 在独立 fresh CI-owned workspace 执行，cwd 为 run 下 `repo`，stdin 为 `DEVNULL`。各目录包含 exact command/result、双流、screen、文件系统前后快照与 diff、key JSON artifacts、durable/SQLite/process 查询。

| 场景 | 原始证据目录 | 直接观察 |
| --- | --- | --- |
| UM-A11 | `evidence/actions/UM-A11-update-missing` | `--action update --ticker AAPL --material-name "Missing Target" --files inputs/probe.txt --company-name "Apple Inc."`：exit 1，`failure_kind=storage`、`failure_code=storage_io`、`stored_files=0`；无材料发布，却创建 `portfolio/AAPL/.identity.json` 与 `portfolio/AAPL/meta.json` 等共 15 个条目。 |
| UM-A12 | `evidence/actions/UM-A12-update-missing-overwrite` | A11 相同业务输入另用 fresh workspace 并加 `--overwrite`：exit 1，同一 `storage_io`，无材料发布；同样创建公司 identity/meta 等共 15 个条目。 |
| UM-A13 | `evidence/actions/UM-A13-delete-never-existed` | `--action delete --ticker AAPL --material-name "Never Existed"`，无文件，fresh workspace：exit 1，同一 `storage_io`，无材料发布；创建 `portfolio/AAPL/.identity.json` 等共 14 个条目，未创建公司 meta。 |

三次 stdout 均先显示 `upload.started` 再显示 `upload.completed_with_failures`；stderr 给出“上传产物读写失败，请稍后重试”。均未超时、无信号或残留进程；workspace 内 SQLite、Host EventLog、Trace、Memory、旧 ingestion job 均 queried-but-absent。A11/A12 的公司 meta 内容为 `company_id=AAPL_US`、`company_name=Apple Inc.`；A13 只留下 canonical ticker identity 描述文件。故“未发布 document”不能外推为“零业务持久化副作用”。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

1. 显式 `update` 或 `delete` 指向从未存在的材料时，Fins 应识别为 typed target-missing/源文档不存在输入状态，CLI 给出动作明确的纠正方向。
2. `--overwrite` 不把 missing update 变成 upsert；已删除 tombstone 上的重复 delete 是 UM-O13 已接受的独立状态，不等同从未存在。
3. 拒绝应发生在 `upload.started` 与公司/材料业务持久化前；A11～A13 当前的 `storage_io`、误导性读写重试提示和已创建公司 identity/meta 不被接受。具体固定文案与未经补跑确认的 exit code 不冻结为 contract。

## 已裁决修复项

### UM-O15-F01：material update/delete 目标不存在的状态拒绝与 typed 投影

状态：**用户接受修复方向，尚未实施**。

动机：CLI 参数显式要求修改或删除既有目标，实际 published source 不存在。当前流程先发布公司状态，再由下游 `FileNotFoundError` 进入通用 `OSError` 映射，生成 `storage_io`；调用者被误导为读写故障，失败请求还产生了公司身份事实。

语义 owner：Fins 上传动作与 published source 状态的共享 admission owner，已有 `dayu/fins/pipelines/docling_upload_service.py:evaluate_upload_overwrite_precondition` 对 `update + missing` 返回 `UPDATE_TARGET_MISSING`，filing 请求已在 `dayu/fins/ingestion_runtime.py` 将其映射为 typed usage。material 路径需在公司提交与 `upload.started` 前复用该 owner；`delete + never existed` 也须由同一状态机明确产生 absent-target 结果。存储仓储继续保证并发下的最终存在性，不能把任意 `FileNotFoundError` 字符串或所有 `OSError` 当作状态真源。

修复要求：对 missing update（含 `--overwrite`）与 never-existed delete 前置拒绝并投影动作明确的 typed 原因；公司与材料业务状态零持久化副作用，必要锁或运行期辅助文件须在补跑中单独记录；保持已删除 tombstone 的重复 delete 成功语义（UM-O13）。跨 US/CN/HK material 入口复用同一 precondition/public contract，避免仅修改 SEC workflow 或 CLI。

## 待补跑与 scenario 处置

A11～A13 仅作为缺陷发现证据，不将 `storage_io` 或公司副作用转为 accepted scenarios。修复获单独授权并完成后，真实 CLI 在 fresh 与既有公司 workspace 补跑 update missing、update missing `--overwrite`、delete never existed、delete tombstoned、合法 update/delete，并核对 screen/双流/exit、公司和材料文件差异、meta/manifest、durable/SQLite/process 查询。跨市场与并发 target 消失边界须按共享 owner contract 验证。

## 裁决替代关系

本裁决替代冻结 observed report UM-O15 的 pending 建议，补充其对 A11/A12 公司 meta 及 A13 ticker identity 副作用的遗漏，并登记 UM-O15-F01。原始 evidence 保持不变；UM-O14 已接受的 `--overwrite` 是已有目标明确覆盖，不赋予 missing update upsert 语义。本次不修改正式 registry/readiness，也不将 upload_material 加入 readiness scope。
