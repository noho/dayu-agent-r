# upload_material 第一轮校准：UM-O21 用户裁决

裁决日期：2026-09-28。用户对材料文档层无部分发布、损坏内容 typed failure 以及修复项 `UM-O21-F01` 明确回复“同意你的裁决建议。下一项。”本文件登记 accepted 行为和已裁决修复方向；产品实现仍未获单独授权，也不代表 upload_material 全量 calibration 或 readiness 已闭环。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。逐项核对 F17～F19 的 `command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`、durable/SQLite/process 查询。均为真实 CLI 在独立 fresh CI-owned workspace 中运行，cwd 为 run 的 `repo`、stdin 为 `DEVNULL`、无超时和残留进程。

| 场景 | exact 输入 | 直接观察 |
| --- | --- | --- |
| UM-F17-corrupt-pdf | `corrupt.pdf`，9 字节文本 `not a pdf` | exit 1；`failure_kind=content`、`failure_code=docling_converter_execution`、requested=1/stored=0；无 material publication。 |
| UM-F18-corrupt-docx | `corrupt.docx`，18 字节文本 `not a zip document` | 同样 exit 1、typed content failure、requested=1/stored=0；无 material publication。 |
| UM-F19-valid-plus-corrupt-atomic | 按顺序传 `probe.txt`、`corrupt.docx` | exit 1、同样 typed content failure，requested=2/stored=0；没有任一 original/Docling JSON、source meta 或 material manifest publication。 |

三次文件系统 diff 均只新增 `.dayu` 锁/目录和 `portfolio/AAPL` 公司 identity/meta 与空的 `filings`、`materials`、`processed` 目录；`key-json-artifacts.json` 仅包含公司 identity/meta。SQLite 与 Host/EventLog/Trace/Memory/job 为 queried-but-absent。故本项直接证明**材料文档无部分发布**，不证明工作区零副作用，也不证明所有 commit 中途故障的事务原子性；公司元数据提前持久化归 UM-O34 独立裁决。F19 第一份 `probe.txt` 作为单文件曾在 UM-F15 成功转换，但 F19 的屏幕未单独证明第一份在本次运行中完成转换，只证明它被作为第一输入传入且整个材料未发布。

三次普通 stderr 都没有失败文件的 `file=` 标签，F19 尤其无法从错误本身辨认第二份 `corrupt.docx`。源码 owner 调查与该结果同源：`dayu/fins/pipelines/docling_upload_service.py:_build_pending_assets` 在 material 转换出 `DoclingConversionError` 时原样抛出；filing 分支则在知道当前文件的边界构造 canonical public file label 和 typed failure。SEC/CN material workflow 的外层 catch 统一以 `file_label=None` 映射异常，因此文件身份在离开转换 owner 后丢失。不能在 CLI、Service、日志或事件投影处根据输入顺序反推。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

接受：无法转换的 PDF/DOCX 材料返回稳定 typed content failure，而不发布该材料；多文件材料中任一转换失败，本次材料整体失败、stored originals 为 0，不能把此前输入或其 Docling JSON 单独发布。这个承诺限定于**材料文档发布边界**；公司 identity/meta 的提前写入另由 UM-O34 判断。F17/F18/F19 支撑当前失败分类、零材料发布和双文件 fail-closed 行为；不把“任意转换失败都绝无其他工作区副作用”或“commit 中途任意故障都已验证”写入 oracle。

**不接受** material 转换失败时丢失出错文件标签的当前表现。至少在双文件失败中，用户无法定位需要替换的输入文件；项目的 converter failure owner 已知道精确当前文件并有共享 canonical public label 能力，缺失标签属于产品错误投影问题，而非 Docling 抽取质量问题。

## 已裁决修复项

### UM-O21-F01：material 转换失败保留 owner 产生的安全文件标签

状态：**修复方向已接受，尚未实施**。

动机：F19 的 typed failure 保留 kind/code，却丢失当前文件身份；多文件用户只能猜测哪份文件失败。仓储和 CLI 不具备还原该语义的合法依据。

语义 owner：`DoclingUploadService` 的逐文件转换边界在捕获 `DoclingConversionError` 时知道 exact original basename；在此处用共享 `canonicalize_fins_public_file_label` 生成安全标签，并通过共享 `FinsUploadFailureReason`/typed exception 向 SEC/CN material workflow 传递。workflow 只投影该 owner 事实；不从列表位置、异常字符串、绝对路径或下游事件重算。

修复要求：material 分支与 filing 同样在当前文件转换失败处附带 bounded `file_label`，保持既有 `content/docling_converter_execution` 分类和零材料发布行为；screen、事件、result 和任何 durable failure 摘要均使用同一个 typed reason。F17/F18 单文件和 F19 双文件补断言失败标签，尤其 F19 应指向 `corrupt.docx`；安全文件名、绝对路径不泄漏及 CN/HK/US 各流程共用 owner 边界须验证。不得只给 CLI 加文件名，也不得据“第二个文件”做位置特例。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。F17/F18 的 typed content failure 与无材料发布、F19 的 requested=2/stored=0 和无部分材料发布可作 accepted scenario 候选；当前缺失文件标签不转为 accepted 行为。若 `UM-O21-F01` 获单独实施授权，测试 owner 级 typed failure，并在隔离 workspace 真实 CLI 补跑单/双文件，核对屏幕、result、文件系统、durable/process 与安全标签。公司 metadata 副作用保留给 UM-O34，不能被本项的“原子性”措辞掩盖。

## 裁决替代关系

本裁决取代冻结 observed report UM-O21 的整体接受建议：把“batch 原子性”收窄为材料文档层的无部分发布，并将 material 失败文件标签缺失登记为 `UM-O21-F01`。原始 evidence 不改写；正式 registry/readiness 待后续统一登记。
