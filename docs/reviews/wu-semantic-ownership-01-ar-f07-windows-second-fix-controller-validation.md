# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第二轮 Windows fix Controller validation

## Gate 与结论

- gate：同一 umbrella WU 的 AR-F07 Windows release-blocker fix，本轮不是新 WU 或新 sub-WU。
- baseline：`ac5e755ba7148a5d2f30f3f11222548b3c57cd9e`；draft PR 179。
- Agent artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-codex.md`，SHA-256 `891a020f02c41e8547ea0a60808a4d6f60a3a9be93b227294755fffd058e8e3d`。
- verdict：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / WINDOWS_RERUN_REQUIRED`。
- 本结论只接受本地实现进入双路 code review；不把本地 oracle 当作 Windows pass，不关闭 WIN2-F01/F02/F03 或 AR-F07，也不授权 commit/push/workflow rerun。

## Controller 独立代码核对

Controller 完整读取了 Agent artifact 与七个 tracked path 的完整 diff，并核对第二轮 R11/R12 JUnit/environment evidence：

1. `dayu/cli/main.py` 是 console entrypoint 与 `python -m dayu.cli` 的共同进程边界。它在任何参数解析、usage/help 或命令输出前，只对具体 `io.TextIOWrapper` 重新配置 `utf-8/strict`；没有命令级 fallback、异常吞噬、`hasattr/getattr` 或测试环境 shim。
2. `dayu/cli/upload_script.py` 仍是唯一 Windows renderer。fixed argv 的 percent、caret/metacharacter、CRT quote/backslash 由同一 helper 编码；NUL/CR/LF 在 renderer owner fail-closed；POSIX、publisher、typed Fins plan、JSON-argv 删除结果均未漂移。
3. `.github/workflows/r11-upload-script-windows.yml` 用 `System.Diagnostics.ProcessStartInfo.ArgumentList`、`UseShellExecute=false` 与双流异步 drain 单独运行 `cmd.exe`，严格判定 `ver=0`、help=1；没有全局 native-error ignore、`continue-on-error` 或后续 pytest gate 弱化。
4. R11/R12 workflow 都把公共 owner `dayu/cli/main.py` 纳入 pull-request path trigger。R12 的 registry/setx implementation 与 tests 零修改，符合“setx failure 是 WIN2-F01 传播”的证据。
5. `tests/README.md` 的变更属于测试证据职责；根 README、`dayu/README.md`、设计真源与产品工作流没有需要同步的用户可见 contract 变化。

七个 tracked paths 的 canonical binary diff SHA-256 为
`7058c07324a87b3959420f75c963705125ec50c4b6dad160e2bb466d55381e22`；内容 hash 与 Agent artifact 的七行表逐项一致。当前 staged set 为空。

## Controller 独立验证

所有 Python 命令均在 `source .venv/bin/activate` 后运行：

- focused + exact coverage：`87 passed, 2 skipped`；`dayu/cli/main.py 94%`，`dayu/cli/upload_script.py 92%`，总计 `93%`；
- 完整 `tests/cli`：`519 passed, 7 skipped`；skip 均为既有平台限定节点；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- changed Ruff：PASS；
- R11/R12 YAML parse：PASS；
- `git diff --check`：PASS；
- branch 仍为 `phaseflow/host-issues-control`，HEAD 未变，staged set 为空。

只有既有 `edgar` deprecation warnings；没有本任务 failure。Controller 同时确认 diff 不包含 key/header 值，不修改 Config、Host internal SQLite/EventLog、Tool Trace、audit、public/LLM/log projection，也没有实现统一 authorization 或 Issue 142/151/175/177/178/Web/WeChat/render deferred scope。Gemini 仍为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## 双路 review 必须挑战的边界

- fixed token 的 caret/percent 解码和 CRT 恢复是否在真实 batch phase ordering 下成立，尤其 literal quote 后的 `&|^()<>` 与 `%*`；本地 decoder 不得自证真实 `cmd.exe`。
- raw `%*` 是否在 caller-provided quoted appended argv 下保留边界并阻断 injection；不得用 JSON/base64、第二脚本协议、fallback 或测试 shim 替代。
- `TextIOWrapper.reconfigure` 是否确实位于唯一 CLI process owner，且不会把调用方 capture、日志或错误投影改成隐式 fallback。
- PowerShell helper 是否无 deadlock/output leakage，是否在真实 runner 精确返回单一 integer exit code并让 help probe 后继续执行 pytest。
- Windows artifacts 是否仍 names-only/secret-zero；registry cleanup、path containment、symlink、atomic write 和 deferred/no-code boundaries 是否保持。

## Finding 与 residual 状态

- WIN2-F01：`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- WIN2-F02：`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- WIN2-F03：`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- R12 setx surface failures：`PROPAGATED WIN2-F01 / NO REGISTRY CODE FINDING`。
- 本地新增 material finding：0；design contradiction：0；unclassified residual：0。
- 下一 gate：AgentMiMo 与 AgentDS 对完整 8-path target 并发执行 `$deepreview` 对应的 Claude `/deepreview` code review。两路结果经 Controller 裁决、所有 accepted findings 修复并 re-review 后，才可创建 accepted local commit并触发真实 Windows rerun。
