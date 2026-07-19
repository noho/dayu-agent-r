# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第三轮 Windows evidence Controller adjudication

## 远端输入

- accepted fix commit：`4814b7dc`（`fix: accept AR-F07 Windows second remediation`）。
- R11：run `29694082161`，job `88211719273`，真实 `windows-latest` / Python 3.11.9，结论 failure，artifact `r11-windows-upload-script-29694082161` 已下载并逐项读取。
- R12：run `29694082143`，job `88211719303`，真实 `windows-latest` / Python 3.11.9，结论 failure，artifact `r12-init-windows-29694082143` 已下载并逐项读取。
- 两个 artifact 的环境记录、JUnit、生成脚本、argv oracle、source hashes 与 environment names 已检查；只有环境变量名，没有 API Key/header/registry value 明文。

## 已获得的正向证据

1. R11 capability probe 完成并记录 `cmd_ver_exit_code=0`、`cmd_help_exit_code=1`，pytest gate 继续执行。原 WIN2-F03 的 workflow native-exit classification 修复得到真实 runner 正向证据。
2. R11 `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` 通过；recorder oracle 精确保存 empty、空格、中文、literal quote、trailing backslash、literal percent、`!&|^()< >`、appended argv，且 injection marker 未生成。R12 的内嵌同一节点也通过。原 WIN2-F02 的 batch/CRT renderer 修复得到真实 runner 正向证据。
3. R12 init 主矩阵 9 个节点中 7 个通过；four-state 的首个真实 CLI 进程实际 `returncode=0`。两个 run 都不再出现产品进程写出阶段的 `UnicodeEncodeError: charmap can't encode`，说明 CLI stream owner 已把输出写成 UTF-8。

上述正向证据保留，但 AR-F07 仍不能关闭，因为两条 workflow 尚未整体通过。

## Accepted finding

### WIN3-F01 — Windows real-smoke consumer 仍按 ambient cp1252 解码 Dayu CLI 的 UTF-8 输出

- status：`ACCEPTED / ROOT CAUSE PROVEN / FIX REQUIRED`。
- direct evidence：
  - R11 real CLI storage 节点的两个 `subprocess` reader thread 在 `encodings/cp1252.py` 抛 `UnicodeDecodeError`，而 test 使用 `capture_output=True, text=True` 且未声明 encoding；`execution.stderr` 因 reader 失败成为 `None`。
  - R12 four-state 的 Dayu CLI 已 `returncode=0`，但 `result.stdout` 为 `None`，随后 `_assert_init_result` 在 `mode=first not in result.stdout` 抛 `TypeError`。
  - R12 setx 节点在同一个 `_run_init` consumer 中超时；reader/pipe 已失去与生产 UTF-8 输出一致的显式解码契约。它不构成 registry 新 finding。
- semantic owner：真实 CLI smoke 的 subprocess consumer。Dayu CLI 已明确拥有 UTF-8/strict 输出；读取该输出的测试必须在直接 consumer 处显式使用同一 `encoding="utf-8", errors="strict"`，不能继续依赖 Windows ambient locale，也不能改回产品的 cp1252、加 loose decode/fallback 或全局环境 shim。
- minimum scope：审计并修复本 WU Windows真实 CLI/init smoke 中直接消费 Dayu CLI 或由生成脚本转发的 Dayu CLI stdout/stderr 的调用；不要改写无关 native `reg.exe`/junction 命令的系统编码，不新增通用 subprocess framework。
- required proof：本地 owner contract tests、focused tests、full pyright、Ruff、diff-check；然后重新执行 R11/R12，并下载 artifacts 证明 R11 4/4、R12 init 9/9 与内嵌 R11 2/2 通过。

## 旧 finding 状态与边界

- WIN2-F01/F02/F03：均已有对应真实正向信号，但在同一 release gate 整体绿色且 artifacts 完整前暂保持 `EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`，避免用局部 pass 提前关闭。
- Config/Host internal SQLite/EventLog trusted-local 裁决不变；Tool Trace/audit/public/LLM/log/output/evidence secret plaintext-zero 不变。
- 不实施统一 authorization，不越界实施 deferred Issues，不用 compatibility shim 或测试驱动产品 fallback。

## Decision 与下一 gate

结论：`FAIL / ACCEPTED_FINDING=WIN3-F01 / SAME AR-F07 FOLLOW-UP`。

这是同一 umbrella WU、同一 AR-F07 remediation continuation 的远端验证 finding，不是新 WU。下一步由 AgentCodex在 test consumer owner 做最小根因修复并提交实现/验证 artifact；Controller验证后进入 AgentMiMo/AgentDS 双路 code review、accepted fix/re-review、accepted local commit、push 与第四轮真实 Windows rerun。
