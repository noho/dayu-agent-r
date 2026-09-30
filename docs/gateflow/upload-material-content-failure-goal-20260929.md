# UM-O21-F01 + UM-O22-F01：material 内容失败原因与文件标签同源 goal confirmation

- Gate：goal confirmation pass；两个已接受修复标签合成一个 typed content failure work unit，分别验收。隔离工作区 `/private/tmp/dayu-upload-content`，分支 `codex/upload-material-content`，基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，创建时干净。
- 用户逐项接受 `docs/reviews/upload-material-um-o21-oracle-adjudication.md` 与 `upload-material-um-o22-oracle-adjudication.md` 的修复方向，并授权闭环代码汇入 PR #197，用户手工 merge。冻结 F16–F19/S18 仅是旧 validation commit 观察；以下根因以本 HEAD 的逻辑/数据同源代码核对。

## 动机与直接证据

`DoclingUploadService._build_original_assets` 已在读取 filing 原始字节后，对 `b""` 生成 `FinsUploadFailureError(fins_upload_empty_input_failure(file_label))`，material 分支却跳过，随后转换器输入校验抛普通 `ValueError`，外层被映为 `runtime/unexpected_runtime`。同一个原始字节事实必须在共同读取 owner 处产生相同 typed content failure。

`DoclingUploadService._build_pending_assets` 对 filing `DoclingConversionError` 在知道当前 `file_path.name` 的位置生成安全 file label 和 typed failure，material 则原样重抛；SEC/CN material workflow 的 catch 用 `file_label=None` 投影，已丢失当前文件身份。显示层或调用顺序不能恢复它。两项同属 Docling service 的输入/逐文件转换 owner 到共享 `FinsUploadFailureReason` 的传播链，合并实施避免两个局部 wrapper 漂移。

严重性限于错误原因和用户定位：旧冻结证据的 0 字节与损坏 PDF/DOCX 均未发布材料文档；F19 双文件 stored=0。不能由这些例子推断公司元数据零副作用、任意 commit 故障全事务原子性或 Docling 抽取准确率。

## 目标与成功信号

1. filing/material 的原件 `b""` 在共享原始字节准入边界、进入 Docling 前产生同一个 `content/empty_input_file` typed failure、安全有界 `file_label` 与提供非空文件的可行动提示。单文件及多文件中空输入都指出实际当前文件，材料无部分发布，`stored_files=0`。
2. material 的 `DoclingConversionError` 在逐文件转换 owner 处携带当前原件的 canonical public file label，同时保留现有 `content/docling_converter_execution` 类别、code、用户可修正文案与材料文档无部分发布。双文件有效+损坏输入指向损坏文件；filing 原有行为保持。
3. SEC/CN/HK workflow、CLI、direct result/事件、tool 与任何 durable failure 摘要只投影同一个 typed reason；不得从列表顺序、异常字符串、绝对路径、日志或下游展示重算。owner 级和真实隔离 CLI 测试覆盖 F16–F19/S18 的新 lineage，普通/debug 均核对 safe label、kind/code、requested/stored、文件/meta/manifest、进程；冻结证据不改写。

## 范围与非目标

- 修复点位于 `DoclingUploadService` 的读字节与转换 catch，以及其直接 typed failure resolver/市场 workflow 投影边界。不得为 material 引入与 filing 不同的新空文件 code，不把内部英文 `ValueError` 暴露用户，不让 adapter 在展示阶段猜文件。
- 不修改 Docling 的抽取算法、准确性评价、格式 capability 或上游包；真正有效内容的抽取质量只可报给 Docling。材料文档层无部分发布是本项验收边界；公司 identity/meta 提前持久化归 UM-O34。O04/O23 的资产名规划也修改同一 Docling service，最终集成须串行审查文件身份与 label 真源，不让两个工作区的独立 diff 相互覆盖。
- 如果当前 typed failure resolver 在 material workflow 仍丢失 owner label，plan 必须沿实际 catch 链修到同一事实；若需要新增公开 schema 或改变已有 content 分类，停止并重新确认目标。

下一 gate：gpt-6-sol 给出最小 plan；Kimi/MiMo 独立并行 plan review 后才能实施。全部闭环代码进现有 PR #197。
