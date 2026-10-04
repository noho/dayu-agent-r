# upload_material 第一轮校准：UM-O36 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。本项只裁决采集器前置条件与标签纠错；不将补跑自动等同于产品正确、正式 oracle/scenario 已登记或 readiness 已成立。本项没有独立产品修复项。

## 运行了什么

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`，validation commit `fac32ecbff9bfe792b63ee9667c8697826b631f4`。`matrix-inventory.json` 在原执行前冻结 135 项；证据审计发现前置条件混入后，`matrix-supplement.json` 在补跑前冻结 22 项；发现不同 stem 标签错误后，`matrix-supplement-2.json` 在第二次补跑前冻结 3 项。三个矩阵都指向同一 validation commit，原 135 项仍保留在原始 evidence，不被改写。`evidence-audit.json` 记录最终 160 个真实 CLI 结果，17 类必需证据没有缺失。

本次逐项解析两个 supplement 的 `coverage_claims`、`precondition` 和 `argv_template`，核对原场景和补跑的 `command.json`、`result.json`、`screen.txt`、`filesystem-before/after.json`；同时核对三个矩阵和选定原始/补跑文件与 `artifact-sha256.json` 的 SHA-256、大小一致。以下 supersede 仅替代**被混淆变量的解释**，不删除原始运行事实。

| 原场景/问题 | 补跑与直接观察 | 证据解释 |
| --- | --- | --- |
| UM-035、041、043～051：长度、内部 ID、财年/财期、日期等输入与缺文件/缺公司或错误动作混在一起 | S01～S11 在 fresh workspace 加有效文件及公司名，逐个隔离目标输入。例：UM-035 用 `delete` 且无文件，exit 1；S01 用 `auto`、`probe.txt`、公司名，同一长名称 exit 0 并发布。 | 原失败不能证明目标值被拒；S01～S11 替代这些参数行为的归因。 |
| UM-053～055：无文件动作在缺目标的 fresh workspace 中失败 | S12 先成功创建有 manifest 条目的目标；同 workspace 的 S13～S15 分别执行 `auto/create/update` 无文件，均 exit 1。 | S12 是前置基线，不是第 16 个被替代原场景；S13～S15 才替代三个混合前置的归因。 |
| UM-056：`delete --files` 与 fresh workspace 目标不存在混合 | S16 先成功创建有 manifest 条目的目标；S17 在同 workspace 用 `delete --files probe-v2.txt`，exit 0。 | S16 是前置基线；S17 隔离“delete 带 files”行为。该现象的产品修复已在 UM-O16 登记，不在本项重复建单。 |
| UM-F20/F23/F24：场景名误称不同 stem，但实际为 `probe.txt` + `probe.md`，stem 均为 `probe`，三个场景均 exit 1 | S23～S25 改用 `probe.txt` + `tencent-ai-panel.md`，包括正序、逆序与 debug，三个场景均 exit 0。 | 原 F20/F23/F24 仍可作为 same-stem 碰撞证据；S23～S25 取代“真正不同 stem 多文件/顺序”的标签和覆盖声明。碰撞产品修复归 UM-O23。 |

S01～S11、S13～S15、S17 共 **15 条** `supersedes-harness` 映射；S12/S16 是两个共享 workspace 的有效前置基线。S18～S20 是对 empty txt/same-stem 异常的 debug 诊断，S21/S22 是最小 JSON/XML 内容试验，它们不是前述 15 条的一对一替代。S23～S25 是 **3 条** `supersedes-harness-label` 映射。22+3 个补跑并不等于 25 个原场景全部失效。

直接证据：`matrix-inventory.json`、`matrix-supplement.json`、`matrix-supplement-2.json`、`artifact-sha256.json`、`evidence-audit.json`、`supplement-execution-index.json`、`supplement2-execution-index.json`；`evidence/static/UM-035-material-name-overlong/command.json` 与 `screen.txt`、`evidence/supplement/UM-S01-overlong-material-name-isolated/command.json` 与 `screen.txt`；`evidence/static/UM-053-auto-without-files/command.json`、`evidence/supplement/UM-S12-no-files-baseline/filesystem-after.json`、`UM-S13-auto-without-files-existing/filesystem-before.json`；`evidence/formats/UM-F20-multi-distinct-stems/command.json`、`evidence/supplement/UM-S19-multi-distinct-debug/command.json`、`evidence/supplement2/UM-S23-multi-true-distinct-stems-debug/command.json`、S24/S25 的 `command.json` 与 `result.json`。

## 证据纠错与 Accepted 范围

`UM-O36-E01`（证据标签纠错，非产品修复）：S19 的目录名仍写 `multi-distinct-debug`，但原始 argv 实际是 `probe.txt` + `probe.md`，两个 stem 相同。其 `coverage_claims` 仅写 `root-cause-for:UM-F20`，所以原始数据可作为 same-stem 诊断；正式 lineage/场景说明不得从目录名推成“真正不同 stem”。S23 才是相应 debug 对照。冻结文件原字节应保留，仅在裁决和将来的正式 registry 映射中纠正标签。

`UM-O36-E02`（报告范围纠错，非产品修复）：冻结报告的“当前没有仍待补跑项”只能解释为 **O36 已发现的前置混淆与错标签有对应补跑**。它不关闭其他裁决明确留下的后续取证，例如 UM-O33 的并发 `storage_io` 底层异常/debug 补采及获授权修复后的重跑；也不自动覆盖尚未实际触发的 timeout 或 commit 后异常边界。不能用本项宣布整个第一轮 calibration/readiness 闭环。

用户接受上述 **15 条前置归因替代 + 3 条标签/覆盖替代** 的 lineage，并把 S12/S16 保留为基线、S18～S22 保留为诊断/额外格式试验；接受 E01/E02 两处证据说明纠错。原场景的 raw exit、双流、文件差异仍保留，原 F20/F23/F24 继续用于碰撞观察，但不用作不同 stem 失败的断言。本项无需再为已识别的采集器混淆补跑；产品修复与其它裁决要求的后续取证仍按各自 artifact 推进。

当前未修改冻结 evidence、正式 oracle/scenario、registry/readiness 或产品代码。
