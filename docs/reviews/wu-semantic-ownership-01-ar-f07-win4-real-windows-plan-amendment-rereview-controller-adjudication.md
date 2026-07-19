# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Fixed Plan Re-Review Controller Adjudication

## Result

`PASS / WIN4-RW-PR-F01..F04_CLOSED / NEW_ACCEPTED_FINDING=0 / BLOCKER=0 / ACCEPTED_AMENDED_PLAN_COMMIT_AUTHORIZED / IMPLEMENTATION_NOT_YET_AUTHORIZED`

## Identity and immutable target

- Timestamp：`2026-07-20 06:01:58 +0800`。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Fixed plan：1060 lines / 73,440 bytes，SHA-256
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。
- AgentMiMo re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-rereview-mimo.md`，305 lines /
  20,040 bytes，SHA-256 `f249846cdb9b6fb6d07fe8a4ee4b8249e42768a80020263d3bd1f482967b4876`。
- AgentDS re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-rereview-ds.md`，542 lines /
  37,073 bytes，SHA-256 `b2225f100f70e342c82e837170a0e325901f9c145d30b30faf3881794441416c`。
- Frozen remote evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。

两路 reviewer 均从零完整读取1060-line fixed plan、初审、Controller adjudication、AgentCodex fix、Controller validation与
direct code/test/storage/workflow evidence；不是只检查finding diff。两路均确认root cause、owner、精确两个slices、allowlist、
顺序、README、validation、remote lineage、security与deferred boundary自洽。

## Finding closure

| Canonical finding | Final disposition | Closure evidence |
| --- | --- | --- |
| `WIN4-RW-PR-F01` | `CLOSED` | Public source snapshot显式使用`with ... as snapshot`，facts只在生命周期内读取；CLI test不重复拥有Fins close-after-use tests。 |
| `WIN4-RW-PR-F02` | `CLOSED` | 既有getpass tests使用test-owned严格typed TTY `sys.stdin` fake并fail closed；redirected tests使用`isatty() == False`的真实`io.StringIO`或等价typed stream；不mock production helper、不依赖ambient TTY。 |
| `WIN4-RW-PR-F03` | `CLOSED` | TTY `EOFError`与redirected empty read显式映射为同一value-free error；`KeyboardInterrupt`保持。 |
| `WIN4-RW-PR-F04` | `CLOSED` | 只有实际移除LF后才条件移除其前CR；bare CR保留并有owner test；禁止`rstrip`过度删除。 |

新accepted finding：`0`。Needs-evidence：`0`。Design contradiction：`0`。Local blocker：`0`。Open question：`0`。

## Reviewer observations with no implementation authorization

1. AgentDS为说明TTY fake可行性给出的示意snippet包含`# type: ignore[override]`。该snippet不是plan contract，也不被
   Controller接受为implementation方式；它没有base override语义且违反本项目零类型抑制方向。实际实现必须使用pyright可验证的
   typed fake，不得增加`type: ignore`、cast逃逸、`Any`/`object`签名或不完整参数类型。
2. Reviewer关于publication guard、Windows lock、universal newline与future CPython的因果说明只作为review reasoning；
   accepted durable contract仅是public context-manager lifecycle与fixed plan中的字符保留规则。
3. 不处理redirected `readline()` 的任意`OSError`没有直接current defect；不接受借此增加generic input-error framework或
   exception projection。

以上均为`NO_ACTION / NOT_A_FINDING`，不得在implementation回流成新scope。

## Security and deferred disposition

- Config与Host internal SQLite/EventLog是trusted-local domain；本plan不新增secret storage、redaction或统一authorization。
- Tool Trace/audit以及public/LLM-facing/operator diagnostics继续禁止API key/header明文。
- Fresh R12 canary仍由Controller在进程内独立派生和扫描，不进入test/production/shared artifact；standalone R11不消费该
  canary。
- Issue 142、151、175、177、178及Web/WeChat/render继续deferred；没有偷带实现。
- Gemini低预算仍是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Accepted amended-plan commit scope

只授权把当前plan/control/evidence链形成一个exact-scope local commit。精确路径为：

1. `docs/host/issues-implementation-control.md`
2. `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
3. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-failure-controller-adjudication.md`
4. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`
5. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-controller-validation.md`
6. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-mimo.md`
7. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-ds.md`
8. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-controller-adjudication.md`
9. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-codex.md`
10. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-fix-controller-validation.md`
11. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-rereview-mimo.md`
12. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-rereview-ds.md`
13. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-rereview-controller-adjudication.md`

Commit前必须确认staged path恰好等于该13-path sorted manifest、`git diff --cached --check`通过、product/test/README/workflow/
design零stage。Commit成功后Controller必须验证parent、tree、path manifest、plan SHA与working/staged tree；只有accepted-commit
validation通过后才可授权`WIN4-RW-S1` implementation。
