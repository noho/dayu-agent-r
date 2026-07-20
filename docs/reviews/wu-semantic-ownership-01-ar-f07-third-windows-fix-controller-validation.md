# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN3-F01 fix Controller validation

## Scope 与内容锁

- baseline：`4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md`，SHA-256 `1761ea0b41f1dc469ebb44559c098f3a2469ef121f282c115967755070cdbbfd`。
- implementation tracked paths：`tests/README.md`、`tests/cli/test_arg_parsing.py`、`tests/cli/test_init_smoke.py`、`tests/cli/test_upload_filings_from_command.py`。
- 四个 tracked paths 相对 baseline 的 binary diff SHA-256：`9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`。
- Controller 原有 control/evidence paths 的内容 hash 与 AgentCodex 输入锁一致；产品、workflow、根 README、分层 README 与 deferred paths 零 diff。

## 独立 owner 复核

Controller 逐行复核四个 implementation diff 和第三轮 R11/R12 JUnit：直接根因成立。Dayu CLI process boundary 明确产生 UTF-8/strict bytes，而真实 smoke 打开的 text pipe 仍依赖 ambient locale。修复只在七个直接消费 Dayu CLI 或生成脚本转发输出的调用点声明 `encoding="utf-8", errors="strict"`：module help、init run/Popen、POSIX generation/execution、Windows generation/execution。

纯 recorder、prewarm `python -c`、`reg.exe` 与 junction `cmd.exe` 没有被错误纳入 Dayu CLI 输出契约。没有产品 fallback、`PYTHONIOENCODING`、cp1252 回退、ignore/replace、通用 subprocess framework、`shell=True`、兼容 shim 或无关 owner 修改。module help test 直接断言中文文本，形成在 Darwin 可执行的 owner contract；Windows-only节点继续如实 skip。

## Controller fresh validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行：

- 三个 affected test files：`98 passed, 7 skipped, 3 warnings`；skip 均是显式 Windows-only。
- owner coverage：`87 passed, 2 skipped`；`dayu/cli/main.py 94%`，`dayu/cli/upload_script.py 92%`。
- full pyright `dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- changed-file Ruff：PASS。
- `git diff --check`：PASS；staged set empty。
- exact path/hash、README trigger、production/workflow/deferred path 与禁止-pattern scans：PASS。
- warnings 仅为既有 `edgar` deprecation warnings。

## Finding 与 residual 状态

- WIN3-F01：`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- WIN2-F01/F02/F03：`EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。
- 当前 code finding、design contradiction、local blocker、unclassified residual：0。
- Config/Host internal SQLite/EventLog trusted-local 与 Tool Trace/audit/public/LLM/log/output secret-zero 裁决不变；未实施统一 authorization 或 deferred Issues。

## Decision

结论：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / WINDOWS_RERUN_REQUIRED`。

下一 gate 是 AgentMiMo / AgentDS 对完整七路径新树并发 code review，重点挑战 direct-consumer audit 是否漏项、native-command排除是否正确、strict decode 是否导致新的平台不一致、owner contract 是否能防回归，以及安全/deferred 边界。review 前不授权 stage、commit、push 或 workflow dispatch。
