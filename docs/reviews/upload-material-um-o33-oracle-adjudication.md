# upload_material 第一轮校准：UM-O33 用户裁决

登记日期：2026-09-28。状态：**用户已接受修复方向，正式 oracle/scenario 尚未更新**。本项登记同一 `auto` material identity 的双进程并发异常及修复项 `UM-O33-F01`；修复尚未实施，也未获实施授权。已接受的 UM-O13 顺序相同输入 `auto` 幂等跳过，与本项并发同输入的预期相互关联；UM-O32 不同 identity 并发成功不替代本项证据。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

UM-L06A/B 在 fresh `--base workspaces/concurrency/same-document` 中以完全相同 argv 同步启动：冻结 `.venv/bin/dayu-cli upload_material --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Concurrent Same' --files inputs/probe.txt --company-name 'Apple Inc.'`（`--base` 与输入文件在实际 `command.json` 中为绝对路径）；cwd 为 run 下 `repo`，stdin=`DEVNULL`。采集器在 before snapshot 后设双线程启动屏障、在两个进程结束后设 after snapshot 屏障；两进程记录启动时刻相差 65 微秒。`UM-L06-pair-index.json` 的 `synchronized_start`、`synchronized_after_snapshot` 均为 true，因此成员的 filesystem diff 都是同一共享 workspace 的 pair 最终差异，不能把全部新建文件归因给其中一个进程。

| 成员 | 双流/exit | 共享工作区终态 |
| --- | --- | --- |
| UM-L06A | exit 1；stdout 到 `upload.completed_with_failures`；stderr 为 `Fins failure ... status="failure"`，summary `status="failed" requested_files="1" stored_files="0" failure_kind="storage" failure_code="storage_io" failure_message="上传产物读写失败，请稍后重试"`。没有 skip 或 typed identity conflict。 | L06A/B 的同步最终快照均有 21 项新建、无 modified/deleted；这一行不表示 L06A 写出了文档。 |
| UM-L06B | exit 0；stdout 到 `upload.completed`、`Fins succeeded`，summary `status="ok" requested_files="1" stored_files="1"`；stderr 空。 | 最终只有一份 active 文档 `mat_8cb632e4d3f818fbf9dcd03d28e91822661f6c2e`，版本 v1、fingerprint `1874a0212bad3c52f3ec53066a269335e670f108571ae0f234c3b21b3ce72bc1`；document meta 含 `probe.txt` 原件和 `probe_docling.json`，manifest 恰有该文档一项。 |

两次均未超时、无残留进程；CI-owned workspace SQLite 查询为 0，Host/Trace/Memory/runtime/旧 job locator 均 queried-but-absent（UM-O28 边界）。最终文件没有观察到双份或半份 publication，但一方以通用 storage I/O 失败，与已接受的顺序相同输入 `auto` skip 语义不一致。

直接证据：

- `evidence/concurrency/UM-L06-pair-index.json`
- `evidence/concurrency/UM-L06A-concurrent-same-document/command.json`、`result.json`、`screen.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`、`process-tree.json`
- `evidence/concurrency/UM-L06B-concurrent-same-document/command.json`、`result.json`、`screen.txt`、`filesystem-before.json`、`filesystem-after.json`、`filesystem-diff.json`、`key-json-artifacts.json`、`process-tree.json`
- 顺序相同输入 `auto` skip 的已接受证据：`evidence/actions/UM-A02-auto-identical-repeat/`

## 语义 owner、证据边界与 Accepted 行为

业务上的相同 material identity、`auto` 动作和 source fingerprint，由 Fins 上传 service 决定；对该 identity 的已发布 source state、batch 提交与跨进程串行化由 `dayu.fins.storage` 拥有。冻结代码 `dayu/fins/pipelines/sec_upload_workflow.py:495-500, 537-565` 在准备/转换前读取 `previous_meta`，随后分公司 batch 和文档 batch 提交；`dayu/fins/pipelines/docling_upload_service.py:479-493` 只基于读取到的旧 meta 判断 material identical skip。冻结 storage 的 `begin_batch` 和 `commit_batch` 已有 ticker writer/publication guards，因而不能未经异常证据便断言“缺少锁”是根因。L06 原始屏幕只给出通用 `storage_io`；未采集足以定位具体抛错位置的 debug log/底层异常。上述代码证明存在跨阶段 state 读取与提交边界，**不证明** L06A 的具体异常就是旧快照、锁获取或目录替换之一。

用户接受的裁决：同一 fresh workspace、完全相同 `auto` identity 和文件输入在并发竞争时，权威 state/publication 边界应线性化为**一方创建成功，另一方在确认已发布 identity、fingerprint 和完整性相同后返回幂等 skipped**，最终只有一份完整文档，且 skip 不重写 source meta/manifest。若权威状态已改变但无法证明相同，必须返回与真实冲突相符的 typed 结果；真正的存储 I/O 故障仍应保留 storage failure，不能把所有 `storage_io` 在 CLI 端改写为 skipped。L06A 的通用 `storage_io` 不登记为 accepted oracle。

### UM-O33-F01：同一 auto identity 并发重试的权威状态裁决

状态：**用户接受修复方向；未实施**。

动机：同一 `auto` 请求顺序重试已接受为幂等 skip；L06 并发重试却有一方收到通用存储故障，增加无意义的用户重试和错误诊断。最终文档虽完整，终态语义仍有缺陷。

修复边界：先在隔离 CI workspace 用同一同步并发命令补采错误方的 debug log/底层异常，并核对当前待修 commit，确认准确抛错点和是否仍可复现；再在 Fins 上传状态机与 `dayu.fins.storage` publication owner 的直接边界解决 state 读取、版本再验证和提交后的幂等裁决。不得在 CLI、输出层或 generic `storage_io` 映射处按消息猜测并发并改写结果；不得以无条件重试遮蔽真正 I/O 错误。实现时应覆盖同输入 success+skip、不同输入竞争的有类型结果、顺序 `auto` 已接受语义和 UM-O32 不同 identity 并发共存。

## 待补跑与 scenario 处置

2026-09-29 当前 HEAD 新补证：`docs/gateflow/upload-material-o33-e01-evidence-20260929.md` 在两个 fresh 隔离根复现一成一败；第二组 workflow 捕获边界临时诊断的真实 traceback 指向 stale `auto`→`create` 后，另一进程先发布，仓储 `_fs_source_document_core.py:1749` 抛 `FileExistsError(文档已存在)` 并被泛投影 `storage_io`。这解释本 HEAD 的本次失败，**不反推冻结 UM-L06 原始异常必为同一原因**。原始证据/无效诊断 pilot、哈希和依赖顺序见新 artifact；修复方向及正式 scenario 门槛不变。

UM-L06A/B 作为缺陷发现和最终一份完整文档的证据保存；失败方 `storage_io` 不转 accepted scenario。先补采真实 CLI 的 owner 错误诊断以定位根因；修复获单独授权并实施后，用同步真实双进程重跑，核对各自 exit/summary、最终 meta/manifest、文件 diff、无残留进程及重复多轮下的结果。当前不修改正式 registry/readiness、冻结 evidence 或产品代码。
