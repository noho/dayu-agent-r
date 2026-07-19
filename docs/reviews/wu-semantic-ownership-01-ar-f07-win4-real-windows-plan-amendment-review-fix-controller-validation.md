# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review Fix Controller Validation

## Result

`PASS / WIN4-RW-PR-F01..F04_FIXED_AND_CONTROLLER_VALIDATED / READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`

## Identity and scope

- Timestamp：`2026-07-20 05:53:04 +0800`。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Plan before：1045 lines，SHA-256
  `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Fixed plan：1060 lines / 73,440 bytes，SHA-256
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。
- AgentCodex fix artifact：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-codex.md`，97 lines /
  5,817 bytes，SHA-256 `be72dbfd708722e799b13b237be2459c68baee8ea29dc03cf130c0c9df90e902`。
- Controller adjudication SHA-256：
  `80c4966b839c968e3fa75cbac1271f8019d9d88c962281a6d9bb33134259ae15`。

Controller完整读取 fixed plan 与 fix artifact，逐项复核 accepted finding、owner、allowlist、tests、remote closure、security
及 deferred boundary。AgentCodex只修改既有 plan并新增指定 fix artifact；没有 product、test、README、workflow、design、
stage、commit、push、dispatch 或 PR变更。

## Finding validation

### WIN4-RW-PR-F01 — fixed

- §13.2.1 现在显式冻结
  `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`。
- identity、source kind、primary filename与 descriptors只能在`with`块内读取。
- §13.5.1明确CLI test不重复拥有Fins close-after-use protocol tests。

### WIN4-RW-PR-F02 — fixed

- §13.4与§13.5.2要求受影响既有tests替换production实际读取的`sys.stdin`，使用test-owned严格typed TTY fake。
- TTY fake的`isatty()`固定为`True`，`readline()`一旦被调用立即assertion失败；redirected tests使用真实
  `io.StringIO`或等价严格typed stream并固定`isatty() == False`。
- Plan明确禁止mock production `_read_secret_input`、修改/依赖`sys.__stdin__`或依赖ambient TTY。

### WIN4-RW-PR-F03 — fixed

- §13.2.2与§13.5.2明确TTY `getpass.getpass()`的`EOFError`和redirected `readline() == ""`是两种不同运行时表现。
- 两路精确收敛到同一value-free `CliInitOperationError("secret input ended before completion")`；prompt、secret、raw
  buffer与raw exception text不进入用户输出，`KeyboardInterrupt`仍不捕获、不改写。

### WIN4-RW-PR-F04 — fixed

- §13.2.2明确只有实际移除一个末尾LF后，才能移除紧邻其前的单个CR；孤立trailing CR原样保留。
- §13.5.2、§13.6.1、§13.6.3与completion-report contract增加bare-CR owner evidence；禁止`rstrip`或等价
  过度删除。

## Preserved boundaries

- Amendment仍精确为`WIN4-RW-S1 -> WIN4-RW-S2`两个slices；§13.3 allowlist未扩大。
- S1仍只改真实Windows smoke test consumer；S2仍只改CLI secret-input owner、owner tests及两份职责匹配README。
- `dayu/cli/output.py`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、Fins production与两个workflow
  继续禁止修改。
- Fresh R11/R12 dispatch identity、accepted head、same-run artifacts/logs与Controller-owned value-free canary scan未改变。
- Config与Host internal SQLite/EventLog仍是trusted-local domain；Tool Trace/audit及public/LLM-facing/operator diagnostics
  继续禁止API key/header明文。
- 没有统一authorization/secret infrastructure；Issue 142、151、175、177、178及Web/WeChat/render继续deferred。
- Gemini低预算仍是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Validation

- Fixed-plan SHA/line/byte identity：PASS。
- AgentCodex fix-artifact SHA/line/byte identity：PASS。
- Four-finding source/propagation scan：PASS。
- Product/test/README/workflow diff相对remote target `b85def887e72dc69e972f42a82a18989523f8634`：零。
- `git diff --check`：PASS，零输出。
- Staged tree：空。
- Trailing-whitespace scan：零命中。
- Plan-only gate未运行implementation tests、coverage或pyright；fixed plan §13.6继续强制后续implementation执行。

## Next gate

只允许AgentMiMo与AgentDS分别从零完整re-review 1060-line fixed plan、两路初审、Controller adjudication、AgentCodex fix
artifact与本validation。不得只检查四处diff。任一新accepted finding必须再次由AgentCodex修plan并完整双路re-review；两路均
PASS且Controller最终裁决accepted/open为零后，才可形成accepted amended-plan local commit。Implementation仍未授权。
