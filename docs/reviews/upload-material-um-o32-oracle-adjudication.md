# upload_material 第一轮校准：UM-O32 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户确认这两组不同 identity 双进程并发的行为正确：同 ticker 不同 material 文档、不同 ticker 各一份文档均完整发布。UM-O33 的同一 auto identity 竞争另行裁决；当前未发现独立修复项。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

四次均从冻结 `.venv/bin/dayu-cli upload_material` 启动，cwd 为 run 下 `repo`，stdin=`DEVNULL`，`--action auto --forms MATERIAL_OTHER`。每组从 fresh、独立的 CI-owned `--base` 启动两个 CLI 进程。采集器在各进程的 before snapshot 后以双线程 `start_barrier` 同步启动，在两进程结束后用 `finish_barrier` 同步 after snapshot；pair index 均记录 `synchronized_start=true`、`synchronized_after_snapshot=true`。因此每个成员的 filesystem diff 是**同一 pair 的最终共享工作区差异**，不能把整份 diff 归给该成员独自写入。

| 组别 | 运行输入和并发时间 | 双流、终态与最终持久化 |
| --- | --- | --- |
| UM-L07A/B：同 ticker 不同文档 | 同 `--base workspaces/concurrency/same-ticker`、`--ticker AAPL --company-name 'Apple Inc.'`；A 是 `--material-name 'Concurrent A' --files inputs/probe.txt`，B 是 `--material-name 'Concurrent B' --files inputs/probe-v2.txt`。两进程记录的启动时刻相差 71 微秒，运行区间重叠。 | A/B 各 exit 0、stderr 空、summary `status=ok requested=stored=1`，屏幕分别给出不同 document ID `mat_65ac84318d0b94a23322f220a48f816553501329` / `mat_636b564f58434221208adf89019aac93448f561b`；最终 `portfolio/AAPL/materials/material_manifest.json` 同时列出这两份不同文档，各自 meta 包含对应原件与 Docling JSON，未见其中一方覆盖另一方；两进程残留 0。 |
| UM-L08A/B：不同 ticker | 同 `--base workspaces/concurrency/different-ticker`；A 是 `--ticker AAPL --material-name 'Concurrent AAPL' --files inputs/probe.txt --company-name 'Apple Inc.'`，B 是 `--ticker MSFT --material-name 'Concurrent MSFT' --files inputs/probe-v2.txt --company-name 'Microsoft Corp.'`。记录启动时刻相差 66 微秒，运行区间重叠。 | A/B 各 exit 0、stderr 空、summary `status=ok requested=stored=1`；最终 `portfolio/AAPL/materials/material_manifest.json` 与 `portfolio/MSFT/materials/material_manifest.json` 各列一份本 ticker 文档，对应 meta/原件/Docling JSON 均存在；两进程残留 0。 |

四个结果均未超时；其 CI-owned workspace SQLite 查询为 0，六种 Host/Trace/Memory/runtime/旧 job locator 均 queried-but-absent，这沿用 UM-O28 的 direct CLI 边界。两组最终快照分别有 26、35 项新建，无 modified/deleted；这些计数是**每组共享结果**，不能相加为四个命令的各自写入量。启动同步和双进程运行重叠证明真实竞争输入，但不证明存储提交也并行、不形成吞吐量或公平调度承诺。

直接证据：

- `evidence/concurrency/UM-L07-pair-index.json`，以及 `UM-L07A-concurrent-document-a/`、`UM-L07B-concurrent-document-b/` 下的 `command.json`、`result.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`、`process-tree.json`
- `evidence/concurrency/UM-L08-pair-index.json`，以及 `UM-L08A-concurrent-aapl/`、`UM-L08B-concurrent-msft/` 下的同名逐笔证据
- 采集器同步方式：`workspace/tmp/upload_material_calibration.py:1698-1726`、`:665-666`、`:734-740`

## 语义 owner 与 Accepted 行为

不同 material 文档的身份生成与输入选择由 Fins 上传 service 决定；原件、Docling JSON、document meta 和同 ticker manifest 的一致持久化由 `dayu.fins.storage` 的 source/batch publication 边界负责。CLI 只投影各命令自己的进度与终态。L07 的两份 document ID 与最终 manifest 同时存在，是本项判断未丢失更新的直接依据；不能只依据两个 exit 0 或每个成员相同的共享 filesystem diff。

接受**两组已测不同 identity 并发输入均成功、最终各自文档完整共存**的行为：同 ticker 不同文档不能互相覆盖 manifest 条目，不同 ticker 的 source 分别发布在各自目录。正式 scenario 应断言 pair 同步运行、每成员的 exit/summary/document ID 和 pair 最终 manifest/文档文件；不要求两个 storage commit 同时发生，也不扩展到同一 identity 竞争或所有可能调度。当前证据不支持独立产品修复。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。
