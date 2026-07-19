# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan — AgentCodex artifact

## Gate and scope

- Work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella。
- Continuation：`AR-F07`，不是新 WU/sub-WU。
- Gate：WIN4-F01..03 root-cause diagnosis + minimal remediation plan。
- Baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- Product/test implementation：无。
- Control doc update：无。
- Stage/commit/push/workflow dispatch：无。

## Produced artifact

- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`

## Direct diagnosis

### WIN4-F01

Verdict：`ROOT_CAUSE_ESTABLISHED`。

真实 Windows test 用 fresh storage执行 `action=create`，但其 generation input与 artifact `.cmd` 都缺
`--company-name`。Fins company-meta owner对 fresh create/update明确要求该字段。用 R11真实 source artifact在
baseline Linux public CLI路径复现相同 typed failure，并在现有 pipeline owner结果中取得安全直接原因：缺少
`--company-name`。

R11 artifact与仓库 fixture只差8个 LF→CRLF；normalized bytes相同。两份 bytes分别直调 Docling均成功，因此
CRLF/Docling/storage不是本次 root cause。既有 POSIX real workflow传 company name并通过。

最小计划只修 Windows real-smoke input/oracle；不改 production CLI/Fins、不加默认公司名、不 preseed storage、不启用
FMP、不解析 generic message。若合法输入后的新真实 run仍失败，触发 diagnostic-first stop gate。

### WIN4-F02

Verdict：`ROOT_CAUSE_BOUNDARY_ESTABLISHED / PRIVATE_OS_DETAIL_UNPROVED_AND_UNNEEDED`。

R12 JUnit显示 outer Popen `returncode=1` 后 stdout reader仍存活180秒，直接证明 descendant writer handle越过
outer lifetime。当前唯一显式 native command是 setx；其 `capture_output` bytes零消费者且无 native timeout。

计划由 `dayu.cli.init_environment` 唯一 owner删除 capture pipe，使用 stdin/stdout/stderr DEVNULL、close_fds、
30秒 direct-process timeout；TimeoutExpired收口为 names-only failure且不 retry。不得增加 outer timeout或更换 registry
authority。

### WIN4-F03

Verdict：`ROOT_CAUSE_ESTABLISHED`。

随机 sentinel作为 `subprocess.run(input=...)` 进入 stdlib `_communicate(input, ...)`；pytest/JUnit展开该 frame并回显
input。计划由 test-local Popen lifecycle在启动前把 stdin编码到匿名临时文件，stdout/stderr也写入匿名临时文件；
wait不使用 `communicate(input=...)`，因此既不把 input带入异常 repr，也不再等待 descendant关闭 output pipe。
timeout用 `pytest.fail(..., pytrace=False)`只保留 category/timeout/returncode-at-timeout/cleanup/
cleanup-returncode，仍明确失败，不隐藏 F02。

## Validation performed in this planning gate

- `git branch --show-current`：`phaseflow/host-issues-control`。
- `git rev-parse HEAD`：匹配 baseline。
- entry preflight的 `git status --short`：只存在用户既有 control-doc modification与 fourth-evidence untracked
  artifact；均未修改。
- R11/R12 evidence SHA-256：与 Controller adjudication全部匹配。
- `pytest tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage -q`：
  `1 passed, 3 warnings`。
- R11 CRLF source通过 public CLI在本机复现 typed failure；现有 pipeline owner安全原因是缺 company name。
- LF/CRLF direct Docling对照：两者均 success。
- 本 gate只新增两份 Markdown artifact；未运行 implementation tests、coverage、pyright或Ruff并未声称其通过。

## README decision

本 planning gate无 production/test变更，不更新 README。计划要求后续 implementation只按职责更新
`tests/README.md`；其它 README/design预计 no-update，并设 stop condition。

## Security and deferred boundary

- artifact未复制随机 sentinel、registry value、configured secret或raw source content。
- Config/Host internal SQLite/EventLog trusted-local裁决保持不变；Tool Trace/audit/public/LLM-facing/operator log仍禁止
  API key/header明文。
- Issue 142/151/175/177/178、Web/WeChat/render、unified authorization与 secret infrastructure均未实现。
- Gemini低预算保持 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Completion status

`PLAN_ARTIFACT_COMPLETE / READY_FOR_CONTROLLER_READ_AND_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED`
