# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan re-review Controller adjudication

## Review locks

- final-plan candidate：SHA-256 `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9`。
- AgentMiMo complete re-review：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-mimo.md`，external SHA-256 `9bd74bb26f53ec2b9c91a4a39e2db39408e856b5fe206123a09734b5de23cd41`，结论PASS，material finding 0。
- AgentDS complete re-review：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-ds.md`，external SHA-256 `1c57731127d2fa090ed97c9885e62ce2a92fb621b73b17e13cffce3d1ddb80a0`，结论PASS，2项LOW candidate。
- 两个review artifact内自报SHA因artifact随后写入自报值而与最终外部hash不同；Controller只锁最终文件的external SHA，不把自引用hash当内容真源。

## Common conclusions

两路均确认WIN4-PR-F01..F04主体闭合：S1 pre-execution Windows token oracle、S3 cleanup-timeout单次poll、anonymous `TemporaryFile` handle lifetime以及R12 public-run-id canary双owner方向成立。Standalone R11不声称canary证明，GitHub Secrets/configured production values不作为needles，rejected candidates零回流，未发现架构越界或通用framework扩张。

## Accepted findings

### WIN4-PR-RR-F01 — domain separator必须冻结为无歧义bytes literal

接受DS `REREVIEW-01`。Plan的“ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`”仍允许test实现采用NUL byte，而Controller采用backslash+zero两个字符；两边会产生不同canary，scan零命中反而形成假pass。

AgentCodex必须把唯一真值写成Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`，并明确末字节是single NUL `0x00`、不是`b"\\0"`或`b"\\x00"`的字面字符。Owner tests锁定完整bytes和已知run-id→canary test vector；Controller按同一literal独立重算，不共享production helper或test artifact needle。

### WIN4-PR-RR-F02 — R12 scan必须锁定dispatch返回的run与accepted commit

接受DS `REREVIEW-02`。仅写“新R12 run”不足以防止并发/重复dispatch时误取旧run；若用旧run id派生并扫描旧artifacts，也会虚假零命中。

AgentCodex必须补充Controller procedure：dispatch后锁定该次R12 `run_id`，在下载/扫描前验证workflow identity/path、event、branch与`head_sha == accepted implementation commit`；JUnit/source-hash/artifacts与canary scan必须来自同一run id。任一不匹配、ambiguous或artifact缺失均gate fail并重新取得正确run，不允许从“最近一次成功run”猜测。Review/control只记录公开run id、head SHA与status，不记录canary。

## Rejected open questions

- DS关于S1 `shlex.split`的open question不形成finding：final plan已经明确禁止POSIX loose parser，并要求现有Windows batch/CRT oracle或等价Windows语义解析。
- DS关于Controller/test共享helper的建议被拒绝：它会破坏“Controller独立重算”并引入新依赖；无歧义literal与test vector足够。
- 其它residual notes均为implementation/review需要验证的已计划事实，不另建finding。

## Decision

结论：`FIX_REQUIRED / IMPLEMENTATION_NOT_AUTHORIZED`。

AgentCodex只修改最终plan和plan-fix artifact，关闭WIN4-PR-RR-F01..F02；不得改production/tests/README/workflow/control或既有review，不得stage/commit/push/dispatch。Controller验证后必须由AgentMiMo/AgentDS再做完整re-review；在双路通过前不进入accepted plan commit。
