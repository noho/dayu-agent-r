# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第四轮 Windows evidence Controller adjudication

## Remote inputs

- accepted head：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- R11：run `29695780994`，job `88216176362`，真实 `windows-latest` / Python 3.11 / locked test environment；结论 `failure`，artifact `r11-windows-upload-script-29695780994` 已下载到 Controller 临时 evidence 目录。
- R12：run `29695780992`，job `88216176310`，真实 `windows-latest` / Python 3.11 / locked test environment；结论 `failure`，artifact `r12-init-windows-29695780992` 已下载到 Controller 临时 evidence 目录。
- R11 JUnit SHA-256：`ad93c02307272bf9a1fcd3da10863ffc3621978f435b73ab8951d8c0d09076b7`；R11 stdout SHA-256：`bb4250e89da3f66815fca1485a9ded5a312391e9f7132bc11fc0ad51214d8fad`。
- R12 init JUnit SHA-256：`8a66c5f29785d371ca3e8ae2e02133fb5a9019e2536a63db046644f97f708004`；R12 embedded-R11 JUnit SHA-256：`495cda81c6b7a3f2337157cf6831cd0681ab7e28e7944a0ad026b32747e79812`；source-hash evidence SHA-256：`1dfc56fd75f36573aa4c3847ce35ccedf985b4e4d7b06d2d78ed7147b98a64c3`。

Controller 未把临时 API-key sentinel 值复制进本 artifact；下述证据只记录变量名、exit/status、typed failure 与测试计数。

## Positive closure evidence

1. R11 capability probe 完成，真实 `cmd.exe` 可执行与 help-exit 分类继续通过。
2. R11 `4` 个节点中 `3` 个通过；真实 adversarial batch/CRT argv round-trip 再次通过，recorder oracle 逐元素保持空串、空格、中文、quote、尾反斜杠、percent、bang 与 shell metacharacters，且 injection marker 不存在。
3. R12 init `9` 个节点中 `8` 个通过：four-state/config reload、junction fail-closed、symlink privilege/fail-closed、workspace identity drift、platform capability、non-POSIX run-keys、publication rollback、Windows scan/delete race 都通过。
4. R12 embedded R11 `2` 个节点中 adversarial argv 节点通过。
5. 两条 run 都不再出现产品 charmap encode error、test consumer `UnicodeDecodeError`、stdout/stderr `None` 或 PowerShell 对 help exit 的提前终止。

据此关闭：WIN2-F01（产品 redirected CLI strict UTF-8）、WIN2-F02（batch/CRT renderer）、WIN2-F03（exact native exit probe）与 WIN3-F01（test direct-consumer strict UTF-8）。它们已由真实 Windows 正向证据关闭，不再是 residual。

## New accepted findings

### WIN4-F01 — R11 real CLI→Service→Fins upload 在 Windows 返回 typed failure

- 状态：`ACCEPTED / ROOT-CAUSE DIAGNOSIS AND FIX PLAN REQUIRED`。
- 两个彼此独立的真实执行位置（R11 主 job 与 R12 embedded R11）都在生成脚本、argv 与 UTF-8 消费成功之后执行 `upload_filing`，实际返回 exit `1`。
- 可读 stderr 明确为 `operation=upload_filing`、`source_kind=filing`、`status=failed`、`uploaded_files=1`；因此失败不是脚本生成、cmd grammar、测试 consumer decode 或 capability probe 的传播。
- 当前 pipeline 把捕获到的内部异常收敛为 `status=failed`，随后 typed runtime projection只保留通用 failure；现有 artifact 不足以在 storage、Docling conversion、pipeline publication 中选择唯一 root cause。不得在 CLI/test 下游把 generic failure 当原因，也不得先写 fallback。
- AgentCodex 必须从 upload pipeline/storage owner 代码和可复现 evidence 建立唯一 root cause；若现有安全投影不能提供定位证据，计划只能增加有界、name/path/secret-safe 的 owner diagnostic seam，不能把 raw exception、源文件内容、路径或 configured secret 投影到 Tool Trace/audit/public/LLM-facing 输出。

### WIN4-F02 — R12 real `setx` persistence 独立超时

- 状态：`ACCEPTED / ROOT-CAUSE DIAGNOSIS AND FIX PLAN REQUIRED`。
- strict UTF-8 consumer 修复后，`test_windows_real_setx_round_trip_is_name_safe_and_cleaned` 仍在 `_run_init(..., timeout=180)` 超时；其余八个 init 节点通过。
- traceback 显示等待 Windows subprocess stdout reader thread结束时 timeout；该证据推翻“setx timeout 只是 cp1252 decode reader 崩溃传播”的上一轮未决假设。
- owner 候选是 `dayu.cli.init_environment` 的 Windows native-command process/stdio contract，以及测试 harness 对 outer process/descendant pipe 生命周期的验证。AgentCodex 必须判断 `setx` stdout/stderr 是否有产品消费者、pipe 是否必要、进程终止/继承边界如何 bounded；不得仅提高 180 秒 timeout、跳过节点、改 registry 真源或把 API key 写进 diagnostic。

### WIN4-F03 — timeout failure evidence 会回显 test secret input

- 状态：`ACCEPTED / TEST-EVIDENCE HYGIENE FIX REQUIRED`。
- R12 traceback 的 `TimeoutExpired` representation 包含完整 stdin。该 stdin 的值是随机 test sentinel，不是用户 configured secret，但测试自身承诺 failure diagnostic 只暴露环境变量名；当前失败路径违反该 harness contract。
- 修复 owner 是 test subprocess failure projection：必须继续保留 command category、timeout、return code 与 name-safe evidence，同时不能把 stdin 值复制进 assertion、JUnit、workflow log 或 review artifact。不得通过 loose error swallowing 隐藏 WIN4-F02。

## Scope / security / deferred boundary

- Config/Host internal SQLite/EventLog 继续属于用户裁决的本机 trusted-local domain；本轮没有引入 secret storage、统一 authorization 或额外泄露面分析。
- Tool Trace 与 audit 继续禁止 API key/header 明文；public/LLM-facing diagnostics 也不得新增 raw secret。Windows native-command内部处理可使用已确认值，但 review/workflow evidence 只记录名称和 typed status。
- 不删除 allowed paths、containment、symlink、DNS/peer、resource budget、atomic swap/rollback、process fencing 等现有安全机制。
- 不实施 Issue 142、151、175、177、178 或 Web/WeChat/render tracker 能力；尤其不得借 WIN4-F01 越界实现 Issue 175 Docling process isolation。

## Decision 与下一 gate

结论：`FAIL_WITH_ACCEPTED_FINDINGS / WIN4-F01..03 OPEN / AR-F07 REMAINS_RELEASE_BLOCKER`。

下一 gate 是同一 AR-F07 的 AgentCodex root-cause diagnosis + minimal remediation plan，不是新 WU 或新 sub-WU。计划必须锁定 owner、反例、最小修改、跨平台验证和下一次真实 R11/R12 closure criteria；在双路 plan review 与 accepted plan fix/re-review 完成前，不授权 implementation、stage、commit、push 或 workflow dispatch。
