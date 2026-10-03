# upload_material 第一轮校准：UM-O34 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户明确以 manifest 文档条目作为上传/下载成功的必要条件：**已发布 manifest 没有该文档条目，就不能认定该文档成功上传或下载**。本项同时保留失败或取消时公司事实与材料文档持久化边界的观察，并纠正冻结 observed report 的过宽概括 `UM-O34-E01`。未发现独立产品修复项；UM-O07/O21/O23/O30/O31 已有相关但各自更窄的裁决。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

下表均为冻结 `.venv/bin/dayu-cli upload_material`、cwd 为 run 下 `repo`、stdin=`DEVNULL`、各自独立 fresh CI-owned `--base`；每个原始 `command.json` 记录绝对 argv/环境。文件差异、key JSON 与 screen 为本次裁决的直接来源。

| 场景与输入 | 终态 | 独立 workspace 的文件观察 |
| --- | --- | --- |
| UM-F19：`--files inputs/probe.txt inputs/corrupt.docx` | exit 1，`content/docling_converter_execution`，requested=2/stored=0。 | 新建 15 项：`.dayu` 锁/目录、AAPL 公司 identity/meta 与空 `filings/materials/processed`；无文档目录、原件、Docling JSON、document meta 或 material manifest。 |
| UM-S19：`--files inputs/probe.txt inputs/probe.md --debug --log-file ...` | exit 1，`runtime/unexpected_runtime`，requested=2/stored=0；两个 basename 的 stem 同为 `probe`，不是“真正不同 stem”对照。 | 同样新建公司事实和脚手架 15 项，无材料文档 publication；debug 日志记录两次转换及后续 batch 回滚，但未给出精确异常，不据此断定哪条校验抛错。 |
| UM-L02：`--files inputs/msft-outlook.pptx`，`upload.started` 后 SIGINT | exit 130，屏幕给出取消请求与 cancelled 终态。 | 同样仅留下公司事实和脚手架 15 项，无文档 publication。 |
| UM-L04：同类 PPTX，在 `upload.started` 后进程组 SIGKILL | 采集器 returncode `-9`，无业务终态。 | 同样仅留下公司事实和脚手架 15 项，无文档 publication；这是强杀在提交之前的单一切点，不是 CLI 清理或所有 crash 时机的保证。 |
| UM-A23：显式 `--document-id mat_0000000000000000000000000000000000000000` 与 owner 生成身份不匹配 | exit 1，公开错误仍笼统（已在 UM-O07 登记修复）。 | **filesystem diff 完全为空，key JSON 为空；公司 identity/meta 也没有创建。** 此例发生在公司提交之前。 |

五次均无超时、无残留进程，workspace 内 SQLite 为 0，Host/Trace/Memory/runtime/旧 job locator 均 queried-but-absent（UM-O28 direct CLI 边界）。F19/S19/L02/L04 的快照中 `.dayu/repo_batches`、`.dayu/repo_backups` 为目录而无残留条目；L04 在文档 batch 提交前被强杀，不能用它证明提交中途 crash cleanup。A23 的屏幕仍显示 `upload.preparing`/`upload.started` 后才失败，不能把“文件零变化”误说成“CLI 在进度事件前拒绝”；这条错误时序的修复归 UM-O07-F02。

直接证据：

- `evidence/formats/UM-F19-valid-plus-corrupt-atomic/command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/supplement/UM-S19-multi-distinct-debug/command.json`、`result.json`、`screen.txt`、`captured-debug.log`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/lifecycle/UM-L02-docling-sigint/command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/lifecycle/UM-L04-docling-sigkill/command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/actions/UM-A23-mismatched-document-id/command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`

## 语义 owner、证据纠错与待裁决建议

冻结 US material workflow `dayu/fins/pipelines/sec_upload_workflow.py:472-562` 在验证稳定 material ID 后，先以独立 `company_batch` 提交有效公司 identity/meta，再准备/转换材料，随后另开 document batch 提交 source；CN/HK workflow 同样有 company batch 与 document batch 两段。Fins storage 是各 batch 的持久化及原子提交 owner，CLI/Service 不应在后续材料失败后删除公司来模拟跨事务回滚。公司名称和 ticker 是可独立复用的公司事实；在合法公司信息已经提交、随后输入内容失败或任务被取消时保留该事实，符合分层所有权。若用户希望整条命令原子性，应在 Fins workflow/storage 交易设计处重新裁决，不能用 CLI 清理补丁实现。

`UM-O34-E01` 证据纠错：冻结 observed report 写“所有失败……进入 upload 之后会持久化公司 identity/meta”，A23 实际在已有 `upload.started` 输出后 **零文件变化**。因此不能用 CLI 进度阶段推断公司 commit 已发生；正确范围是 F19/S19/L02/L04 这四个**已完成公司 batch、未完成文档 publication**的已测切点会留公司事实，A23 身份拒绝不会。本纠错不改写冻结文件字节，也不新增产品修复项。

## 用户要求的代码顺序核对

本次逐段核对冻结 `repo` 与当前工作树的 `docling_upload_service.py`、`sec_upload_workflow.py`，对应文件 SHA-256 相同。两处 material workflow（US 的 `sec_upload_workflow.py:495-568`，CN/HK 的 `cn_pipeline.py:1139-1184`）均先读取现存 document state、提交独立的 company batch，再调用 `prepare_upload`。因此生成 Docling 之前，公司 identity/meta 就可能已经 durable；不能把“文档成功才算上传成功”理解为“此前没有公司副作用”。

- 对需要新建或更新的材料文档，`DoclingUploadService.prepare_upload` 先构建全部原件与 Docling 派生资产，之后才返回待发布计划（`docling_upload_service.py:469-550`）。一份 material 文档可含多个原件；这是全部所选文件转换完后，为**一个**文档写 source meta 和 manifest 条目，不是每个文件独立登记一次 manifest。
- `publish_prepared_upload` 在 document batch 的 staging 中先写资产，`_create_source_document` 再写 source meta 与 material manifest（`docling_upload_service.py:721-775`；`_fs_source_document_core.py:1796-1807`）。`commit_batch` 校验 staged source/meta/manifest 后发布；US/CN/HK workflow 均等 `commit_prepared_upload_batch` 返回后才生成 `status=ok` 的 completed/success 结果。因此 **manifest 仅写进暂存区不等于成功，提交正常返回才报告成功**。冻结证据未命中 commit 中途或 post-commit 释放锁异常；代码允许 durable commit 后的释放异常继续向上抛出，不能反向断言“凡 CLI 失败都没有 manifest”。
- 非 `--overwrite` 的逻辑**不等到 Docling 或 manifest 后才检查**：`evaluate_upload_overwrite_precondition` 与 `_can_skip_upload` 在 `_build_pending_assets` 转换前运行（`docling_upload_service.py:455-507`）。现存相同 fingerprint 的 material `auto` 在此直接返回 `skipped`，不重新转换也不重写 manifest；现存不同内容的 `auto` 解析为 `update`，通过转换后替换。显式 material `create` 命中既有 active 目标且未指定 `--overwrite` 时，当前计算了 `CREATE_TARGET_EXISTS` 却只对 filing 执行拒绝，已由 `UM-O14-F01` 裁决为待修复。不能把该现状写成正确的“非 overwrite 必须等登记成功”的统一规则。

`UM-O14-F01` 仍负责 material 显式 create 的前置冲突语义；若正式 oracle 要覆盖 commit 后异常导致 CLI 失败但文件已发布的分支，须另设计隔离故障注入并保存真实 CLI 证据。

## Accepted 行为与范围

用户裁决的文档成功必要条件是**权威已发布 source manifest 中存在该文档条目**，且该条目对应已发布文档事实；只写入 staging manifest、只生成 Docling、只创建公司 identity/meta 或只输出 `upload.started`，均不代表该文档上传/下载成功。F19/S19/L02/L04 没有 material manifest 条目，因此这些材料文档没有成功上传；已留下的合法公司事实属于独立上游提交，不把失败材料伪装成成功，也无需在 CLI 下游为材料失败反向删除公司。A23 身份不匹配时公司与文档均零业务持久化，UM-O07-F02 仍负责把拒绝前移。

这是“**缺少条目 ⇒ 文档未成功**”的必要条件，不擅自写成“有条目 ⇒ CLI 必然报告成功”：提交后异常的代码分支尚未由冻结真实 CLI 覆盖。用户同时明确提及下载，正式跨命令成功语义应使用各自 source manifest 的权威已发布条目；本轮原始证据和正式 scenario 只覆盖 `upload_material`，不据此改写已闭环 download oracle。正式 UM-O34 scenario 应按前置阶段同时核对 CLI 终态、公司事实、source 文件/meta 与 material manifest，不承诺所有失败必定创建公司，也不宣称任意 commit 中途崩溃已验证。已有 UM-O21/O23 的文档无部分发布裁决继续有效；本项不新增独立修复。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。
