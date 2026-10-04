# upload_material 第一轮校准：UM-O30 用户裁决

登记日期：2026-09-28。状态：**用户已裁决，正式 oracle/scenario 尚未更新**。用户明确裁决：**SIGINT 的语义是优雅地退出，能优雅地退出即可**。本项保留冻结 direct CLI 的两处 SIGINT 切点和同 workspace 重试作为观察证据；不预判 UM-O31 的 SIGKILL、UM-O34 的公司/文档整命令原子性，也不把本次文件快照外推到所有取消时机。当前未发现独立修复项。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

三次均从冻结 `.venv/bin/dayu-cli upload_material` 运行，cwd 为 run 下 `repo`，stdin=`DEVNULL`，文件是 `inputs/msft-outlook.pptx`，`--ticker AAPL --action auto --forms MATERIAL_OTHER --company-name 'Apple Inc.'`。L01 以独立 fresh `--base workspaces/lifecycle/early-sigint` 和 `--material-name 'Early Cancel'` 运行；L02/L03 使用同一个起初为空的 `--base workspaces/lifecycle/docling-sigint` 和 `--material-name 'Docling Cancel'`，重试 argv 完全一致。三次未超时；各自 workspace SQLite 查询为 0，六种 Host/Trace/Memory/runtime/旧 job locator 均 queried-but-absent（这些归 UM-O28 边界）。

| 场景 | 信号与屏幕/exit | 文件和进程观察 |
| --- | --- | --- |
| UM-L01 very early | 计划延迟 50ms，实际进程启动后约 **225.542ms** 发送 SIGINT；exit 130，stdout/stderr 均空。不能把计划延迟当作实测时间。 | fresh workspace 前后均 0 项、diff 为空；过程采样仅 CLI 进程，退出后 500ms 残留 0。只证明此切点没有产生文件。 |
| UM-L02 active | `upload.preparing`、`upload.started` 已输出；启动后约 **3.103s** 发送 SIGINT；stderr 为 `Fins operation cancel requested.` 和 `Fins cancelled: ... status="cancelled"`；exit 130，无 completed/succeeded。信号时采样见 CLI 与两个子进程，但仅凭采样不能精确确定 Docling 内部子阶段。 | fresh workspace 新建 15 项，包括 `.dayu` 锁/目录、`portfolio/AAPL/.identity.json`、`portfolio/AAPL/meta.json` 和空的材料/处理目录；无材料文档目录、原件、Docling JSON、文档 meta 或 material manifest。无 deleted/modified；退出后 500ms 残留 0。 |
| UM-L03 retry | L02 后同 workspace、同 argv，不发送信号；exit 0，stdout 有 `upload.completed`、`Fins succeeded`、summary `status="ok" requested_files="1" stored_files="1"`，stderr 空。 | L03 before snapshot 与 L02 after snapshot 完全一致；新建文档 identity/meta、原件、Docling JSON、material manifest 共 6 项，无 modified/deleted；既有公司 meta 的 SHA-256 保持一致。退出后 500ms 残留 0。 |

直接证据：

- `evidence/lifecycle/UM-L01-very-early-sigint/command.json`、`result.json`、`screen.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`process-tree.json`
- `evidence/lifecycle/UM-L02-docling-sigint/command.json`、`result.json`、`screen.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`、`process-tree.json`
- `evidence/lifecycle/UM-L03-retry-after-sigint/command.json`、`result.json`、`screen.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`、`process-tree.json`

## 语义 owner 与 Accepted 行为

冻结代码中 `dayu/cli/commands/fins.py` 的 direct stream SIGINT 观察器负责把运行中信号转成取消请求与 CLI 终态；`dayu/fins/pipelines/docling_upload_service.py` 的准备、取消 checkpoint 与 batch 提交边界负责文档发布；Fins storage 是 source 文件与元数据的持久化 owner。CLI 的 exit 130 和用户可见消息与文件事实在这三次运行中一致。L02 公司事实先于材料文档持久化，不能称为“整条命令零副作用”；公司事实是否应回滚留待 UM-O34 单独裁决。

接受的公共语义是：**SIGINT 请求运行中的 direct CLI 操作优雅收尾并退出**，不挂起、不留下本次运行的残留子进程，也不把已取消的操作报告为成功。L01 的无输出 exit 130、L02 的取消请求/取消终态 exit 130 与无残留进程，均符合这个裁决；早于 direct stream 的信号不必强行补打业务取消消息。L02 未发布材料文档而留下公司元数据和工作区脚手架、L03 随后成功重试，是这两个切点的实测事实，**不是** SIGINT 必须零文件变化、所有时机必须回滚公司状态或必须产生完全相同文件快照的规范。文档 publication 的一致性仍由 Fins storage 的提交边界保证，不能仅从本次运行宣称所有信号时机均已验证。当前没有直接证据支持新增独立修复；正式 scenario 应检验信号后的有界退出、取消/成功终态区分与进程清理，并保留实际信号时间、双流/exit、before/after/diff 和重试快照作为证据。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。
