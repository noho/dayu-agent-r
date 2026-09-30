# upload_material 第一轮校准：UM-O24 用户裁决

登记日期：2026-09-28。状态：**用户已同意裁决建议，后由已接受 UM-O25 限定未来多文件准入；正式 oracle/scenario 尚未更新**。本项记录真正不同文件主名的多文件上传、计数和文档 ID 对照；没有新增独立修复项。UM-O23-F01 的同主名派生碰撞与 UM-O25-F01 的主文件选择均已接受、未实施。

## 冻结证据与运行

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对的冻结 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

三次均运行冻结 `.venv/bin/dayu-cli upload_material --ticker AAPL --forms MATERIAL_OTHER --files <两个文件> --company-name 'Apple Inc.'`，cwd 为冻结 run 的 `repo`，stdin=`DEVNULL`，分别使用 CI-owned fresh `--base`；未借用已有 document。具体差异：

| 场景 | 关键 argv | 独立 workspace | 输出 document ID |
| --- | --- | --- | --- |
| UM-S23 | `--material-name 'True Distinct Debug' --files probe.txt tencent-ai-panel.md --debug --log-file ...` | `workspaces/supplement2/distinct-debug` | `mat_d5d85a64446cbd37477cfcaa286fe4381ff71759` |
| UM-S24 | `--material-name 'Distinct Order' --files probe.txt tencent-ai-panel.md` | `workspaces/supplement2/order-forward` | `mat_e24264cc1db2c612a85b99baf8153dcdc663293b` |
| UM-S25 | `--material-name 'Distinct Order' --files tencent-ai-panel.md probe.txt` | `workspaces/supplement2/order-reverse` | `mat_e24264cc1db2c612a85b99baf8153dcdc663293b` |

三个 `command.json` 可逐项核对 exact argv、cwd、workspace、环境和 stdin。各自 `result.json` 记录 exit 0、success、未超时、残留进程 0、evidence_status=sufficient；`screen.txt` 均显示 upload.completed、status=ok、`requested_files=2`、`stored_files=2`，stderr 为空。每个 `filesystem-diff.json` 显示新发布的 material document、`.identity.json`、`meta.json`、两个 original blob、两个 Docling JSON blob 和 `material_manifest.json`，无删除/修改。三个 `key-json-artifacts.json` 的 source meta 均为 `ingest_complete=true`、`document_version=v1`、`files` 共有 4 条，其中 `source=original` 两条、`source=docling` 两条，文件 SHA-256 与文件系统 diff 一致；manifest 的 document ID、version、source fingerprint 与 source meta 一致。此处的 `stored_files=2` 计**输入原件数**，不是物理资产总数 4。

S24/S25 只反转同一组文件的 argv 顺序，material name/form/period 与输入字节相同；二者 document ID、internal document ID、source fingerprint（`5d48099df0d1bd5404344073117f2422ca3db375fcd1cdec09ab8ca746a8da1d`）均相同，4 个文件的 name/source/sha256 集合也相同。二者 `primary_document` 分别为 `probe_docling.json` 与 `tencent-ai-panel_docling.json`，**此差异只作为 UM-O25 的待裁决证据，不在 UM-O24 接受顺序决定 primary 的规则**。S23 使用不同 material name，产生不同 document ID；不能把 S23 与 S24/S25 当成同一 identity 的稳定性复验。

三个 `result.json` 均显示 SQLite database_count=0；Host/EventLog/Trace/Memory/job roots 被查询但不存在。这些 direct CLI 运行不依赖这些 durable 组件；不能据此推断其他入口均不写入。

直接证据：

- `evidence/supplement2/UM-S23-multi-true-distinct-stems-debug/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/supplement2/UM-S24-distinct-order-forward/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/supplement2/UM-S25-distinct-order-reverse/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`、`key-json-artifacts.json`

## 代码边界与动机

`dayu/fins/pipelines/docling_upload_service.py:_build_original_assets` 为 material 产生 original，`_build_pending_assets` 对 converter inputs 各产生一个 Docling asset；`_apply_prepared_upsert` 写 blob/file entries/source meta。`build_material_ids` 基于规范化 form type、material name、可选 fiscal year/period 生成稳定 ID，不取文件 argv 顺序；`_build_upload_source_fingerprint` 对 material original assets 按 name 排序后计算指纹。这些是代码层的现有规则，冻结 CLI 证据只直接确认 S24/S25 这组输入的稳定结果；不把函数实现细节或少量样本外推成全部不同文件集合同 ID、所有变体顺序无关。

业务动机成立：项目公开允许多文件 material 上传，必须对每个支持的原件执行 Docling 转换并发布可追溯的原件/派生件。S23～S25 是真正不同文件主名、无身份碰撞的正样本，填补 F20/F23/F24 错标为“不同 stem”后的证据缺口。转换内容的语义准确性由 Docling 上游负责，本项只确认请求被处理、派生文件持久化和元数据对应。

## Accepted 行为

接受 S23～S25 直接证明的转换与发布能力：两个不同主名且可转换的文件能够同批转换，已发布样本的 CLI 计数为 requested=stored=2，source meta/manifest 完整包含两个原件和两个 Docling JSON；同一 material 业务身份、同一文件集合仅反转 argv 顺序时，document ID 稳定。S24/S25 的源指纹相同是冻结观察；按已接受 UM-O25-F01，未来多文件请求须显式指定主原件，只有指定同一主原件时才要求指纹在输入逆序后保持一致，指定不同主原件应得到不同 role-aware 指纹。原 S23～S25 未带 selector 的成功不能成为修复后的正向 oracle，须以带合法 selector 的新隔离补跑替代。接受计数与角色关系，不把当前 `<stem>_docling.json` 字符串固化为公有命名契约；UM-O23-F01 的统一命名函数实施后可以改变具体派生存储名，但元数据/manifest 仍须准确引用。首文件即 primary 不获接受。

本项无独立修复登记：已观察到双文件转换与发布能力，准入缺陷归 UM-O25-F01。后续正式 oracle/scenario 应引用这三次 raw evidence 作为历史观察，并以带合法 selector 的新证据确立正向用例；本裁决不改动冻结 evidence、正式 registry/readiness 或产品实现。
