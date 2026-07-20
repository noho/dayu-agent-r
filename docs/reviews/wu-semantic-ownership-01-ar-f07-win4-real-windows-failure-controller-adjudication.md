# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real Windows Failure Controller Adjudication

## Result

`FAIL / TWO_ACCEPTED_REMOTE_FINDINGS / DIAGNOSTIC_FIRST_PLAN_AMENDMENT_REQUIRED`

本 gate仍属于既有`WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation的AR-F07 WIN4，不是新WU、
不是新feature/issue，也不重新打开历史独立sub-WU。

## Locked runs and identity

Accepted remote target为`b85def887e72dc69e972f42a82a18989523f8634`。两次dispatch都由本次调用response直接返回
唯一run id，并在读取evidence前验证metadata：

| Gate | Run | Workflow / path | Event | Branch | Head SHA | Result |
|---|---:|---|---|---|---|---|
| R11 | `29703932798` | `R11 upload script Windows gate` / `.github/workflows/r11-upload-script-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `b85def887e72dc69e972f42a82a18989523f8634` | failure |
| R12 | `29703933666` | `R12 init Windows gate` / `.github/workflows/r12-init-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `b85def887e72dc69e972f42a82a18989523f8634` | failure |

Push自动触发的`pull_request` runs不属于本次验收，未被混入。

## Accepted finding WIN4-RW-F01 — stale display string is not the upload success owner

R11 four nodes为`3 passed, 1 failed`；R12 embedded R11为`1 passed, 1 failed`。两者唯一失败节点相同：
`test_windows_generated_script_runs_real_cli_into_temp_storage`在真实命令已经exit `0`后仍断言旧字面量
`Fins result`。直接evidence同时证明：

- 当前CLI output owner `dayu/cli/output.py`的terminal summary prefix是`Fins summary`；
- 真实运行已经输出typed success summary；
- standalone R11 artifact中的portfolio已发布company meta、filing manifest、source、Docling结果与source meta；
- test在写`cli-grammar-oracle.json`之前被旧display断言中断。

根因是test consumer把可变展示词误当业务成功真源，不是company-name、Windows quoting、CLI→Service→Fins、Docling或
storage失败。正确修复owner是`tests/cli/test_upload_filings_from_command.py`：删除旧展示字符串断言，以已存在的
process exit `0`和Fins storage发布事实形成业务闭环；不得改production renderer、不得换成另一条硬编码展示词、不得
解析generic message或增加兼容alias。

## Accepted finding WIN4-RW-F02 — Windows redirected secret input has no owner path

R12 init nodes为`8 passed, 1 failed`。唯一失败节点
`test_windows_real_setx_round_trip_is_name_safe_and_cleaned`在outer `180s`到期时仍未退出；safe projection为
`returncode_at_timeout=not_exited / cleanup=completed / cleanup_returncode=1`。Canary没有进入失败文本。

直接代码与运行时证据把root cause锁定在CLI secret-input owner，而不是setx：

- test已把完整交互输入写入redirected stdin anonymous handle；
- `dayu.cli.commands.init`对required/optional secret直接调用`getpass.getpass()`；
- CPython 3.11 Windows `win_getpass`在`sys.stdin is sys.__stdin__`时直接使用console `msvcrt.getwch()`，Windows上的
  `stream`参数也被忽略；child的stdin虽然被OS重定向，Python对象仍是`sys.__stdin__`，因此预置stdin bytes无人消费；
- timeout发生在第一个required secret读取之前，真实setx尚未获得执行机会，不能把failure归到S2 native timeout。

正确修复owner是`dayu/cli/commands/init.py`的secret-input boundary：真实交互TTY继续使用hidden getpass；redirected
stdin走明确的line-oriented input路径且不得回显value。必须补owner tests证明Windows redirected input不调用console
getpass、TTY仍保持hidden input、EOF/interrupt与required/optional/confirmation顺序不漂移、secret不进入stdout/stderr。
不得在test harness注入兼容shim、不得增加Windows console/PTY/job-object框架、不得把test canary写进artifact。

## Security evidence

R12 run在读取failure log前先完成value-free exact scan：downloaded artifact files `5`、完整workflow log files `12`、
`match_category=test_canary` matches `0`、status `PASS`。扫描只根据dispatch-returned public run id与冻结文字公式在进程内
独立派生needle；命令、输出、本artifact和control doc均未回显该值。Standalone R11没有消费R12 canary，不以该scan
声称non-disclosure。

Config与Host internal SQLite/EventLog仍属用户裁决的trusted-local domain；只有Tool Trace/audit禁止API key明文。
本finding不授权secret infrastructure或统一tool authorization，也不删除任何既有安全机制。

## Ledger and plan boundary

- Accepted remote findings：`2`（WIN4-RW-F01、WIN4-RW-F02）。
- Rejected speculative root causes：company-name、quoting、Docling/storage、setx native timeout、Gemini quota。
- Design contradiction：`0`。
- Remote evidence ambiguity：`0`。
- Real Windows blocker：active。

下一gate仅允许AgentCodex对既有WIN4 remediation plan做bounded amendment并写plan artifact。Amendment必须按两个语义owner
切分implementation slices，锁定allowed paths、negative tests、README判断、fresh验证与重新dispatch矩阵。plan完成后必须
AgentMiMo/AgentDS并发完整plan review、fix和re-review；在accepted amended-plan commit前不得implementation、push、rerun或
PR review。
