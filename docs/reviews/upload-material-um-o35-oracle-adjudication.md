# upload_material 第一轮校准：UM-O35 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。本项只评估冻结运行的进程结果与取证完整性；不以汇总数字证明产品正确、超时处理正确或 readiness 已成立。本项没有独立产品修复项。

## 运行了什么

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。原矩阵 135 次、补跑 22 次、标签修正补跑 3 次，共 160 个真实 `.venv/bin/dayu-cli upload_material` 进程结果。各场景的 `command.json` 给出绝对 argv、run 下 `repo` cwd、`DEVNULL` stdin、隔离 `--base`、环境、超时上限及预定信号；例如 UM-001 的超时上限为 180 秒，UM-L04 为 900 秒且计划在 `upload.started` 后向进程组发 SIGKILL。普通场景及并发、取消、强杀结果均纳入聚合。

本次直接遍历 `evidence/**/result.json`、对应 `process-tree.json` 和 `stdout.bin`/`stderr.bin`，再与十个 `*-execution-index.json`、`evidence-audit.json` 逐项对照。160 个 scenario ID 在索引中唯一，raw 与索引无缺漏；每个场景的 17 类必需证据文件均存在。冻结 observed report 的 SHA-256 为 `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`，observed JSON 为 `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`，evidence manifest 为 `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

## 观察到什么

| 原始结果口径 | 数值 |
| --- | --- |
| exit code | `0`: 66、`1`: 60、`2`: 31、`130`: 2、`-9`: 1 |
| `process_outcome.timed_out` | 160 条均为 false |
| `result.residual_process_count` 与 `process-tree.residual_count` | 160 条均为 0；`residual_processes_after_500ms` 均为空 |
| `evidence_status` / 必需文件 | 160 条为 sufficient；17 类文件缺失数 0 |
| 原始 stdout/stderr 字节流 | 未见 Python 标准 traceback 标记 `Traceback (most recent call last):` |

`-9` 对应 UM-L04 采集器计划的进程组 SIGKILL，不能算 CLI 优雅退出；两个 `130` 是已单独在 UM-O30 裁决的 SIGINT 观测。无残留是采集器在进程结束后 500 毫秒窗口的进程树检查，不是长期、所有外部子进程或任意单进程强杀后的无残留保证。`timed_out=0` 说明这些样本均未触发采集器超时；不能据此证明 CLI 的超时取消、清理或错误投影。普通双流无 Python traceback 也不等于 debug log/内部异常不存在。部分场景的前置条件或标签有缺陷，UM-O36 负责 supersede lineage；160 是**执行和取证数**，不等于 160 个有效 accepted 业务场景。

直接证据：`evidence-audit.json`；`static-execution-index.json`、`actions-execution-index.json`、`formats-execution-index.json`、`supplement-execution-index.json`、`supplement2-execution-index.json` 及其余同级 execution index；`evidence/static/UM-001-help/command.json`、`result.json`、`stdout.bin`、`stderr.bin`、`process-tree.json`；`evidence/lifecycle/UM-L04-docling-sigkill/command.json`、`result.json`、`process-tree.json`；其他 158 个同结构原始目录。

## 语义 owner 与 Accepted 行为

每场景的 exit、超时、信号和进程树观测由 CLI CI 采集器及 raw evidence 拥有；CLI/Fins 的业务成功、取消和错误语义分别由命令及 Fins owner 决定。汇总审计只能投影 raw evidence，不能从 exit 0、`evidence_status=sufficient` 或 residual=0 推出业务正确性或 readiness。UM-O30/O31 已就具体信号切点裁决，UM-O33 的并发失败与本项聚合数字互不替代。

用户接受上述有边界的证据完整性与进程观测：160 条 raw/index 一致、无缺失必需文件、已测运行无采集器超时、500 毫秒残留计数为 0、普通双流无 Python traceback。正式 scenario 若需复用，应逐场景绑定具体信号、观测窗口及终态；不新增“timeout 处理正确”或“任何退出都无残留”的泛化 oracle，也不把本项当 readiness 结论。本项无独立修复项；若今后要承诺超时行为，应另建真实触发超时的隔离场景并记录取证。

当前未修改正式 oracle/scenario、冻结 evidence、registry/readiness 或产品代码。
