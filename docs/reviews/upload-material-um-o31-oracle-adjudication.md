# upload_material 第一轮校准：UM-O31 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户接受这个进程组 SIGKILL 切点及同 workspace 重试的限定裁决。SIGKILL 无协作式退出机会，不能沿用 UM-O30 的 SIGINT 优雅收尾语义；本次未发现独立产品修复项。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

L04/L05 均从冻结 `.venv/bin/dayu-cli upload_material` 运行，cwd 为 run 下 `repo`，stdin=`DEVNULL`；两次 argv 完全相同：`--base workspaces/lifecycle/docling-sigkill --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Docling Kill' --files inputs/msft-outlook.pptx --company-name 'Apple Inc.'`。L04 的 workspace 起初为空，L05 紧接 L04 使用原 workspace。采集器用 `start_new_session=True` 启动命令，以其 PID 为进程组 ID，在实际运行约 3.100 秒时调用 `os.killpg(..., SIGKILL)`；这是**对 CLI 和同组子进程的外部强杀**，不是只杀 CLI 主进程，也不是 CLI 自发取消。采集器源码位置：`workspace/tmp/upload_material_calibration.py:670-712`。

| 场景 | 终端与进程 | 文件状态 |
| --- | --- | --- |
| UM-L04 kill | 已输出 `upload.preparing`、`upload.started`；信号前进程树采样有 CLI 与两个子进程。采集器记录 `signal=9`、Python subprocess returncode `-9`，stderr 空，没有 `completed`、`succeeded` 或 `cancelled` terminal；未超时。500ms 后残留进程数为 0，但这与采集器杀整个进程组有关，不能归功于产品清理逻辑。 | fresh workspace 新建 15 项：`.dayu` 锁/目录和 `portfolio/AAPL` 公司 identity/meta/空目录；没有材料文档目录、原件、Docling JSON、文档 meta 或 material manifest；无 modified/deleted。 |
| UM-L05 retry | 同 workspace、同 argv、无信号；exit 0，stdout 输出 `upload.completed`、`Fins succeeded`、summary `status="ok" requested_files="1" stored_files="1"`，stderr 空；无超时和残留进程。 | L05 before snapshot 与 L04 after snapshot 完全一致。新增文档 identity/meta、原件、Docling JSON 和 material manifest 共 6 项，无 modified/deleted；已存在的公司 identity/meta 的 SHA-256 不变。 |

L04/L05 各自的 workspace SQLite 查询均为 0，六种 Host/Trace/Memory/runtime/旧 job locator 均 queried-but-absent；这些属于 UM-O28 的 direct CLI 边界。本次只证明 **L04 所处的 publication 之前切点** 没有留下已发布材料，且此状态下原样重跑成功；未命中极短的 storage commit 窗口，不能证明任意时点强杀都无半发布或只杀父进程也无孤儿 worker。L05 的成功不证明执行了专门 recovery 分支；它也可能只是从未发布的业务状态正常开始。

直接证据：

- `evidence/lifecycle/UM-L04-docling-sigkill/command.json`、`result.json`、`screen.txt`、`process-tree.json`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`
- `evidence/lifecycle/UM-L05-retry-after-sigkill/command.json`、`result.json`、`screen.txt`、`process-tree.json`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`

## 语义 owner 与 Accepted 行为

SIGKILL 的进程终止由 OS/外部采集器触发，CLI 无权发出取消终态或运行 cleanup。重启时 source 是否完整、能否继续上传，由 Fins storage 的 publication/recovery 边界和上传 service 读取已发布状态决定；不能拿采集器的进程组 kill/no-residual 证明产品能清理单独被杀父进程留下的 worker。公司事实先行持久化是否符合整命令原子性留待 UM-O34。

接受**这个进程组强杀切点的实测 crash/retry 行为**：外部强杀得到 `-9` 且没有业务终态，材料未发布、公司事实与工作区脚手架保留；同 workspace、同 argv 的下一次命令成功发布材料。把“500ms 后无残留”只登记为**进程组采集条件下的观察**，不作为 CLI 自主清理保证。正式 scenario 必须带 `start_new_session`/`killpg` 方法、实际信号时间、双流/returncode、文件快照衔接和重试结果；若要承诺任意 kill 时机或只杀父进程的行为，需另行隔离补跑。当前证据不支持独立产品修复。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。
