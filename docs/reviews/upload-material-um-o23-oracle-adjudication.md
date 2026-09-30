# upload_material 第一轮校准：UM-O23 用户裁决

登记日期：2026-09-28。状态：**用户已接受裁决建议及统一文件名映射函数的补充要求，修复未实施**。`UM-O23-F01` 已登记为待实施修复项；产品代码、正式 oracle/scenario 与 registry/readiness 均未更新。本项只处理 material 上传的资产名碰撞；真正不同 stem 的多文件成功及 primary 顺序分别留给 UM-O24、UM-O25。

## 运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。三个冻结总文件的 SHA-256 依次为 `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`（observed-behavior.md）、`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`（observed-behavior.json）、`fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`（evidence-manifest.json）。

| 场景 | `--files` 关键输入 | 观察 |
| --- | --- | --- |
| UM-F20、UM-S19 debug | `inputs/probe.txt inputs/probe.md` | 两个不同 basename、相同 `probe` stem；exit 1、`requested_files=2/stored_files=0`、`runtime/unexpected_runtime`。S19 日志有两个 Docling child 完成及 commit_batch 回滚。F20 的“distinct stems”标签错误。 |
| UM-F21、UM-S20 debug | `inputs/same-a/deck.txt inputs/same-b/deck.txt` | 两个不同路径、相同 basename/stem；同样双转换后回滚、exit 1、stored 0。不能单靠此场景隔离原件 basename 与派生名冲突。 |
| UM-F22 | `inputs/same-stem/deck.txt inputs/same-stem/deck.md` | 同 stem 不同后缀；exit 1、stored 0、`runtime/unexpected_runtime`；`filesystem-diff.json` 无 document/meta/manifest 发布。 |
| UM-F23、UM-F24 | `probe.txt probe.md` 及逆序 | 两个顺序都失败、stored 0；标签中的 distinct/order 结论受相同 stem 碰撞污染。 |
| UM-S23～S25（对照） | `probe.txt tencent-ai-panel.md` 及顺序对照 | 真正不同 stem；exit 0、requested=stored=2，source 下可见两个 original 与两个 Docling JSON。仅用作本项“多文件不是普遍失败”的对照；完整成功/ID 裁决归 UM-O24。 |

以上命令均为真实 `dayu-cli upload_material --ticker AAPL --forms MATERIAL_OTHER --material-name ... --files ... --company-name 'Apple Inc.'`，cwd 为冻结 run 的 `repo`，各自使用 CI-owned fresh `--base`，stdin 为 `DEVNULL`；S19/S20 另加 `--debug --log-file`。每场景的 `command.json` 给出精确 argv、workspace 和环境，`result.json` 给出 exit、timeout、进程、SQLite 与 durable 查询。失败场景均无超时或残留进程；仅有锁文件、公司 identity/meta 及空目录等准备副作用，material document、source meta/manifest 均未发布。Host/EventLog/Trace/Memory/job 查询为 queried-but-absent；SQLite count 为 0。公司提前写入另归 UM-O34，不在此项裁决。

直接证据路径：

- `evidence/formats/UM-F20-multi-distinct-stems/command.json`、`screen.txt`、`result.json`
- `evidence/formats/UM-F21-duplicate-basename/command.json`、`screen.txt`
- `evidence/formats/UM-F22-same-stem-different-suffix/command.json`、`screen.txt`、`filesystem-diff.json`、`result.json`
- `evidence/formats/UM-F23-reversed-order-a/command.json` 与 `evidence/formats/UM-F24-reversed-order-b/command.json`、各自 `screen.txt`
- `evidence/supplement/UM-S19-multi-distinct-debug/captured-debug.log`、`screen.txt`、`filesystem-diff.json`
- `evidence/supplement/UM-S20-duplicate-basename-debug/captured-debug.log`、`screen.txt`
- `evidence/supplement2/UM-S23-multi-true-distinct-stems-debug/screen.txt`、`result.json`；`evidence/supplement2/UM-S24-distinct-order-forward/result.json`、`evidence/supplement2/UM-S25-distinct-order-reverse/result.json`

## 根因边界

当前 `dayu/fins/pipelines/docling_upload_service.py` 的 material original 资产名为 `file_path.name`，derived 资产名为 `file_path.stem + "_docling.json"`。因此 `deck.txt` 与 `deck.md` 的两个原件名不同，派生名却都精确等于 `deck_docling.json`；`probe.txt`/`probe.md` 同理。`dayu/fins/pipelines/docling_upload_service.py:_apply_prepared_upsert` 逐资产用该名字写 blob 和 file entry；`dayu/fins/storage/_fs_storage_infra.py:commit_batch` 在 publication 前检查完整 staged source，失败就回滚。S19/S20 日志直接证明两个 Docling 子进程都完成、随后 commit 回滚；日志不打印内部校验异常，**不能**仅据日志断言具体是哪条仓储校验抛错。命名函数的重复输出与仓储完整性合同构成直接的设计冲突，足以把问题定位于上传资产身份规划；具体 commit 异常须在后续隔离诊断中补证。

业务动机成立：`deck.txt` 与 `deck.md` 是两个不同、支持 Docling 的输入，文件名不同且均能单独转换；以 stem 截断身份导致整次多文件上传失败，且错误被降格为不可操作的 `unexpected_runtime`。这不属于 Docling 抽取内容准确性问题，也不是应由仓储放宽唯一性或 CLI 在回滚后重命名的情形。

## Accepted 行为与修复方向

接受“发生身份冲突时，不发布半个 material document，`stored_files=0`”这部分失败原子性观察；不接受当前“不同 basename、相同 stem 必须失败”和 `runtime/unexpected_runtime` 行为。接受**使不同 basename 的同 stem 文件可共同上传**：在 Fins 资产身份 owner 处，基于完整 original storage identity 生成稳定、互不冲突的 derived identity，且在 Docling 启动前规划并验证同一文档全部 original 与 derived 的名字全局唯一。原件名与另一个派生名也可能碰撞，故只把 stem 改为 basename 而不检查完整集合仍不足够。原件 basename 完全相同或同一路径重复，仍按已接受 UM-O04-F01 在转换前 typed 拒绝；不从不同父目录路径悄悄推断或覆盖同名原件。真正不同 stem 的普通多文件继续按既有路径转换全部输入。

### UM-O23-F01：material 派生资产身份消除同 stem 碰撞

状态：**用户已接受，尚未实施**。此项是 UM-O04-F01 的身份规划细化，不是第二套数量或重复输入校验。UM-O04-F01 中“同 stem 派生冲突前置拒绝”的范围已收窄为“规划后的真实资产名冲突前置拒绝”；同 stem、不同 basename 在完成无冲突规划后应可成功。

语义 owner：`DoclingUploadService` 的 selection/asset identity planning 边界负责 original/derived 的一一对应、名字唯一性和 primary 引用；storage 的 complete-source 校验只防止非法发布，CLI/Service 只投影 typed 结果。设置一个共同的、负责“原件 storage 文件名 → Docling storage 文件名”的 owner 函数，供 filing/material 的派生身份规划复用；source kind 需要不同命名规则时由此函数显式处理，不在调用点各自拼接。派生身份必须从完整 original storage identity 生成，不能从截断 stem 或转换结果/持久化文件反推；具体编码与命名空间由实现设计，但须为合法单文件名、确定性、不会覆盖原件，并处理与另一原件或派生名相撞的剩余情况。

修复要求：转换前经统一函数一次规划全部原件与 Docling 派生身份并校验唯一；后续转换、blob 写入、file entries、primary 和 manifest 只消费同一次规划结果，不再各自重新计算名字。支持 `probe.txt+probe.md`、`deck.txt+deck.md` 成功发布两个 original、两个 Docling JSON；无法唯一规划的输入在转换前给 typed、可行动失败与安全文件标签，不以 commit_batch 的通用 runtime 错误代替。与 UM-O04-F01 合并实现重复 path/basename、超限输入的前置校验；不得在存储、错误展示或测试 fixture 做局部兼容。owner contract 测试覆盖统一函数对 filing/material 的映射与一一对应、同 stem 不同后缀、同 basename 不同路径、重复路径、原件名与拟派生名交叉碰撞、输入逆序与正常不同 stem。独立真实 CLI 补跑同 stem 成功/真实冲突失败，核对输出、文件、meta/manifest、无残留进程及明确内部错误诊断。

## 冻结证据与后续处置

F20/F23/F24 的错误标签作为采集历史保留，不能作为“真正不同 stem 失败”或顺序语义 oracle；S23～S25 是其不同 stem 对照的 supersede lineage。F21/S20 同时触发原件 basename 与 derived stem 冲突，不能用来证明任一冲突可单独解释全部失败。F22 和 F20/S19 可隔离派生名冲突。当前不新增正式 oracle/scenario，也不修改原始 evidence、正式 registry/readiness。修复方向已接受，产品实施仍需独立授权与新隔离 lineage 的补跑。
