# upload_material 第一轮校准：UM-O22 用户裁决

登记日期：2026-09-28。状态：**用户已同意裁决建议，修复未实施**。`UM-O22-F01` 已登记为待实施修复项；本裁决不表示产品实现、正式 oracle/scenario 或 registry/readiness 已更新。

## 证据与追溯

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。`inputs/input-manifest.json` 记录 `empty.txt` 为 0 字节（空内容 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`）。F16 与 S18 在不同 CI-owned fresh workspace 运行真实 CLI，cwd 均为 run 下 `repo`，stdin 为 `DEVNULL`；S18 另传 `--debug --log-file`。逐项核对 command/result、双流、screen、文件系统 diff、key JSON、durable/SQLite/process；S18 另核 `captured-debug.log`。

| 场景 | 输入与结果 | 直接观察 |
| --- | --- | --- |
| UM-F16-empty-txt | `--files inputs/empty.txt`；exit 1、requested=1/stored=0 | `failure_kind=runtime`、`failure_code=unexpected_runtime`，提示“上传执行失败，请检查运行日志后重试”。 |
| UM-S18-empty-txt-debug | 同一 0 字节文件，加 `--debug --log-file`；exit 1、requested=1/stored=0 | 同样映射为 `runtime/unexpected_runtime`；采集的 debug log 只记录外层 direct event/terminal 映射，没有空文件的具体根因。 |

两次均无 material original、Docling JSON、source meta 或 material manifest publication；只新增 `.dayu` 锁/目录与 `portfolio/AAPL` 公司 identity/meta 和空目录，无超时、无残留进程。SQLite 与 Host/EventLog/Trace/Memory/job 查询为 queried-but-absent。公司元数据副作用另见 UM-O34，不能用“未发布材料”替代“零工作区副作用”。

直接源码链：`dayu/fins/pipelines/docling_upload_service.py:_build_original_assets` 读入原始字节后，只在 `SourceKind.FILING` 且 `raw_data == b""` 时用共享 `fins_upload_empty_input_failure` 生成 `content/empty_input_file` 与安全文件标签；material 的空字节继续传入 `dayu/fins/pipelines/docling_process_converter.py:_validate_conversion_request`，由通用参数校验抛 `ValueError("input_bytes must not be empty")`。SEC/CN material workflow 的外层 `except Exception` 调用 `fins_upload_failure_from_exception`，该 resolver 未识别 `ValueError` 为可行动空内容，故返回 `runtime/unexpected_runtime`。S18 的 debug log 未展示这条内部异常，因此真实 CLI 证据证明对外投影错误；源码/输入字节的直接链路定位了根因，不把缺少日志堆栈当作根因证据。

登记时核对的 SHA-256：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`
- `evidence-manifest.json`：`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`

## Accepted 行为

接受 0 字节 material 文件不被发布、命令失败且 `stored_files=0`；不接受其当前 `runtime/unexpected_runtime` 分类与“查看日志重试”的错误建议。零字节是输入内容的可判定问题，应由共享 Fins 原始字节准入边界在进入 Docling 前产生已有 `content/empty_input_file` typed 失败、安全文件标签和“提供非空文件”的可行动提示；在屏幕、事件、结果和可能的 durable failure 摘要中保持同一原因。这个决定不要求项目解释 Docling 的抽取质量，也不另建与 filing 不一致的 material 空文件错误码。

## 已裁决修复项

### UM-O22-F01：material 空字节复用共享 typed content 失败

状态：**用户已接受，尚未实施**。

动机：同一原始字节事实在 filing 上传路径已被识别为 `empty_input_file`，material 路径却越过该校验并被转换器参数校验抛出的 `ValueError` 降格为未知 runtime；输入错误原因与用户提示均失真。

语义 owner：`DoclingUploadService._build_original_assets` 是读取原件并知道当前文件名的共同准入边界，应对 filing/material 同一 0 字节事实复用 `fins_upload_empty_input_failure` 和 `canonicalize_fins_public_file_label`。`dayu.fins.upload_failure` 的 typed failure resolver 应原样保留 owner 已产生的 `FinsUploadFailureError.failure`；市场 workflow、CLI/Service/tool 只能投影，不得从异常字符串、文件大小重算或用下游特例纠正。

修复要求：在 Fins 原始字节准入处统一拒绝 0 字节 filing/material，并在共享错误投影中保留已有 `content/empty_input_file`、安全 `file_label`、bounded 文案及重试建议；不得把 `ValueError` 的内部英文文本直接泄漏给用户。与已裁决 UM-O21-F01 的 material 文件标签链路合并设计，避免两套 typed failure 传播方式。owner 级测试覆盖 material 单文件/多文件中的 0 字节、filing 既有行为和正确文件标签，确认无 material 部分发布；隔离真实 CLI 补跑普通/debug 入口，核对 screen、result、产物、process 和必要的 operator 诊断。公司 metadata 提前写入归 UM-O34，不在本项用局部补偿处理。

## 待补跑与 scenario 处置

当前不新增正式 oracle/scenario。F16/S18 的失败、零材料发布与无残留进程为观察事实；当前 runtime 分类不转 accepted scenario。若修复获单独授权，补跑证据进入新的隔离 lineage，不改写 F16/S18 原始记录，并验证 content reason 与标签在普通/debug 输出一致。

## 裁决替代关系

本裁决细化冻结 observed report UM-O22 的 pending 修复建议，直接定位 filing-only 空字节准入与 material typed failure 投影断裂；原始 evidence 不改写，正式 registry/readiness 不修改。
