# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Amended Plan Accepted Commit Controller Validation

## Result

`PASS / ACCEPTED_AMENDED_PLAN_COMMIT_VERIFIED / WIN4-RW-S1_IMPLEMENTATION_AUTHORIZED / WIN4-RW-S2_NOT_YET_AUTHORIZED`

## Commit identity

- Accepted amended-plan commit：`cb2785d9b847e852249d05850c0550c5bcea5467`。
- Parent：`b85def887e72dc69e972f42a82a18989523f8634`。
- Tree：`6f2e4384334e97472bf31fdd92e2359729a346c5`。
- Commit subject：`docs: accept AR-F07 WIN4 real-Windows amended plan`。
- Exact changed-path count：`13`。
- Sorted changed-path manifest SHA-256：
  `b4ee35aaa7ff14ca49d655fc52b3620fdfd0a9f2c66844f2e3228cf10541d691`。
- Committed plan SHA-256：
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。

Commit path manifest精确等于fixed-plan re-review Controller adjudication授权的13个plan/control/review/evidence paths。
Product、test、README、workflow与design路径为零。`git diff --check HEAD^ HEAD`通过；commit后working tree与staged tree均空。

## Accepted finding and scope state

- `WIN4-RW-PR-F01..F04`：全部`CLOSED`。
- New accepted/open plan finding：`0`。
- Needs-evidence / design contradiction / local blocker / open question：均为`0`。
- WIN4-RW-F01与WIN4-RW-F02仍是accepted/open code findings，必须分别经S1/S2 implementation、双路code review、fix、
  re-review与accepted commit后，才能进入aggregate与fresh remote closure。

## WIN4-RW-S1 authorization

只授权AgentCodex实施`WIN4-RW-S1`，唯一product/test payload path为：

- `tests/cli/test_upload_filings_from_command.py`

必须执行fixed plan §13.2.1、§13.4、§13.5.1与§13.6中的S1 contract：

1. 删除旧`Fins result` display assertion，不增加任何其它stdout/stderr文案、prefix、substring、regex或parser成功判断。
2. 保留process exit `0`与既有company-name pre-execution oracle。
3. 在runner test进程内、artifact upload前，通过public `FsCompanyMetaRepository`与
   `FsSourceDocumentRepository`读取published company/source facts；source snapshot必须用`with` lifecycle，facts只在块内读。
4. `source_artifact_count`只做physical integrity并保留现有oracle字段，不新增display字段。
5. 更新imports与受影响完整中文docstring；不提取compatibility/test helper，不修改Fins/output/workflow/oracle schema。

Focused tests、POSIX real smoke、full target test file、pyright、scoped/full Ruff baseline、diff-check、README trigger检查与
source scans必须按plan fresh执行。非Windows对real Windows node的skip只记录平台事实。

## Stop and forbidden boundaries

- 若public repositories不能表达company/source facts，或必须读取raw JSON/private core/downloaded artifact重放，立即停止回
  Controller。
- 不得修改`dayu/fins/` production、`dayu/cli/output.py`、workflow、S2路径、README、control/design或其它product/test。
- 不得stage、commit、push、dispatch或操作PR。
- `WIN4-RW-S2`、aggregate、remote R11/R12与PR review仍未授权。
