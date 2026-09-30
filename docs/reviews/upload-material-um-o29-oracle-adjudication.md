# upload_material 第一轮校准：UM-O29 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户确认 UI print 与诊断 log 分开是正确边界：日志选项不取消用户可见的业务进度与终态。本项保留真实 direct CLI 的日志等级、debug stream、日志文件追加、互斥参数与管道 stdin 的已测事实；未发现独立产品修复项。它不评价故障日志能否解释所有内部根因，UM-O21/O22 的具体失败诊断仍按各自裁决处理。

## 冻结运行与直接证据

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

七个场景均用冻结 `.venv/bin/dayu-cli upload_material`，cwd 为 run 下 `repo`，输入文件是 `inputs/probe.txt`，独立或声明复用的 CI-owned `--base`；除 D07 显式管道文本外，stdin 为 `DEVNULL`。各自 `command.json` 记录 exact argv、cwd、workspace、非敏感环境与 stdin；`result.json` 记录退出、双流摘要、进程与 durable/SQLite 查询。

| 场景 | 关键选项与前置 | 直接观察 |
| --- | --- | --- |
| UM-D01 | fresh workspace，`--quiet` | exit 0、status=ok、requested=stored=1；stdout 仍有三条 Fins progress、succeeded 和 summary，stderr 空；原件、Docling JSON、source meta/manifest 发布。`--quiet` 的公开含义是选择普通诊断日志等级；此例直接证明它不使用户可见业务事件静默。 |
| UM-D02 | fresh workspace，`--debug-stream`，未提供 log-file | exit 0、status=ok、requested=stored=1；stdout 仍为常规 Fins progress/result/summary，stderr 空；正常发布。此例证明没有改变 canonical 终态输出，不证明高频细节一定会显示在普通 stdout。 |
| UM-D03 | log-append workspace 首次，`--debug --log-file <run-owned log>`，带 company-name | exit 0、status=ok、stored=1，正常发布；采集日志 3257 字节，记录本次 command、Docling cleanup 和 success terminal。 |
| UM-D04 | **同一** log-append workspace 和 log 文件第二次，`--debug --log-file`，省略 company-name | exit 0、status=skipped、requested=1/stored=0，原业务文件未新增或修改；采集日志 5648 字节，前 3257 字节与 D03 完全一致，后追加 2391 字节，含第二次 skipped terminal。这是日志追加及幂等跳过的对照，非第二次上传成功。 |
| UM-D05 | fresh workspace，`--quiet --debug-stream` | parser exit 2；stderr 精确说明 `--debug-stream cannot be combined with --quiet`，stdout 空；filesystem diff 为空。 |
| UM-D06 | fresh workspace，`--debug-stream --quiet` | 同样 parser exit 2、同一错误、零 workspace 文件系统变化；冲突规则与参数顺序无关。 |
| UM-D07 | fresh workspace，`--files inputs/probe.txt`，stdin 管道 `ignored stdin bytes\n` | exit 0、status=ok、requested=stored=1；stdout 常规 summary、stderr 空；发布的 original 是 `probe.txt`、Docling JSON 对应同一文件，source fingerprint 与 D01/D02 的相同输入文件一致。只说明本次管道内容未替代 `--files` 或改变终态，不外推到其它命令的 stdin 契约。 |

七次均未超时、无残留进程；D05/D06 的空 diff 还证明本次参数组合在业务 workspace 变更前拒绝。D01/D02/D07 的 source meta 各含 1 original + 1 Docling JSON；D03/D04 的 material document ID、source fingerprint 相同，D04 diff 无新建、修改或删除。诊断日志写在 workspace 外的 run-owned `logs/upload-material-debug.log`；其追加结论由两个 `captured-debug.log` 字节前缀比较支持，不能从业务 workspace 的空 diff 得出。

直接证据路径：

- `evidence/diagnostics/UM-D01-quiet-success/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`
- `evidence/diagnostics/UM-D02-debug-stream-direct/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`
- `evidence/diagnostics/UM-D03-debug-log-first/command.json`、`screen.txt`、`captured-debug.log`、`result.json`
- `evidence/diagnostics/UM-D04-debug-log-second/command.json`、`screen.txt`、`captured-debug.log`、`filesystem-diff.json`
- `evidence/diagnostics/UM-D05-quiet-debug-stream-conflict/command.json`、`screen.txt`、`filesystem-diff.json`
- `evidence/diagnostics/UM-D06-debug-stream-quiet-conflict/command.json`、`screen.txt`、`filesystem-diff.json`
- `evidence/diagnostics/UM-D07-piped-stdin/command.json`、`screen.txt`、`filesystem-diff.json`、`key-json-artifacts.json`

## 语义 owner 与 Accepted 行为

`dayu/cli/arg_parsing.py:_finalize_log_level_selection` 是日志 selector 互斥与 `quiet`/`debug-stream` 冲突的公共参数 owner；`--quiet` 是普通诊断日志等级，`--debug-stream` 是额外 stream 诊断开关。`dayu/cli/main.py:_open_log_file` 以 append 模式打开显式 log-file。Fins direct 事件和 terminal summary 由 direct Service/CLI 输出边界投影，因此诊断日志等级不能被误解为取消 canonical 业务终态。`upload_material` 的输入由显式 `--files` 选择，D07 管道文本不构成另一个材料原件。

接受上述**实测的 direct CLI operator 行为**：UI print 与诊断 log 各有其职责，quiet 与 debug-stream 分别可运行且保留业务进度和 terminal；同一日志路径上的 debug 日志确实追加；quiet/debug-stream 两种顺序的非法组合在业务副作用前 exit 2；本次非空 stdin 不改变由 `--files` 选中的上传。D04 的 status=skipped 应原样保留，不作为 debug 模式重复上传成功 oracle。不将 D02 的无额外普通输出解释成“高频诊断一定生效”或“不生效”，也不承诺 debug log 已涵盖所有内部异常。当前证据不支持新增独立产品修复。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。正式 scenario 应逐场景引用 exact argv、screen/result、文件 diff 和两次日志字节关系；不得只断言 exit 0 或把 quiet 定义成整个命令无 stdout。
