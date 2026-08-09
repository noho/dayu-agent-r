# wu-cli-interactive-02 aggregate deepreview final adjudication

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：aggregate deepreview final adjudication
- Branch：`codex/interactive-oracle`
- Base：`main`
- Reviewed committed HEAD：`cf041c2c564bbc1ad9edca579dfc74f8fcab0f3a`
- Initial reviews：
  - `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-mimo-20260802.md`
  - `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-ds-20260802.md`
- Controller adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-deepreview-adjudication-20260802.md`
- AgentCodex fix：
  `docs/reviews/gateflow-wu-cli-interactive-02-aggregate-fix-codex-20260802.md`
- Independent re-reviews：
  - `docs/reviews/aggregate-deepreview-rereview-wu-cli-interactive-02-mimo-20260802.md`
  - `docs/reviews/aggregate-deepreview-rereview-wu-cli-interactive-02-ds-20260802.md`
- Final finding status：`4 fixed / 19 rejected / 0 deferred / 0 unclassified`
- Gate decision：`PASS`
- Next gate：accepted aggregate deepreview commit → ready-to-open-draft-PR

## Controller final decision

Controller 完整读取两路 initial aggregate review、全部 finding、直接代码证据、
fix diff、fix validation 与两路 clean re-review。两名 reviewer 的 PASS 没有被
直接当作 gate 结论；Controller 另行走读 non-TTY signal loop、TTY event state、
runner identity validator 和双连接 transaction harness，并独立复跑聚焦矩阵与
competition stress。

最终接受以下 closure：

1. **AGG-A01 / F08**：non-TTY whole-batch 现在显式消费 invocation
   `CliSigintMonitor`。第一次 signal 复用 `_InteractiveAcceptedRunState` 和
   acceptance barrier 登记 single graceful cancel；第二次只登记 terminal 后
   `130`；第三次 no-op。submit/cancel canonical waiter 在正常 signal 路径保留到
   Host terminal，外层随后关闭 display、monitor 与 attachment。
2. **AGG-A02 / F08**：`TOGGLE_ACTIVITY` 只调用 display owner，不再修改
   `exit_intent` 或 `idle_interrupt_revision`。因此第二次 Ctrl+C 已登记的
   `EXIT_AFTER_CANCEL` 不会在 CANCELLING phase 被 Ctrl+T 撤销。
3. **AGG-A03 / F11 validation**：新增两个 thread-owned 真实 SQLite connection
   对同一 operation 的确定性竞争证明。winner 取得 production permit并持有 write
   transaction；trace 证明 loser 已尝试 `BEGIN IMMEDIATE` 且未完成；winner 提交
   后 loser 只得到 closed disposition，fresh EventLog inventory 恰好一个 terminal。
   production CAS、锁与 writer owner 没有变化。
4. **AGG-A04 / F13**：共享非空 validator 接收显式 owner 名；request/response
   分别产生正确错误归属。dataclass、client correlation、provider identity schema
   与 JSON wire shape 均未改变。

## Re-review decision

AgentMiMo 与 AgentDS 均在重新 discovery、`/clear` 后独立执行 re-review：

- 两路都直接追踪 pre-accept、single/double/third SIGINT、simultaneous count、
  cancel waiter failure 与 cleanup 分支；未发现 orphan、重复 cancel、waiter 被第二
  signal 取消或提前关闭 Host。
- 两路都确认 Ctrl+T 分支已成为 display-only，并从 active CANCELLING state
  追踪到 terminal 后 `EXIT_KEYBOARD_INTERRUPT`。
- 两路都检查 SQLite test 的 connection ownership、write-lock linearization、
  barrier、trace、timeout、fresh read 与 single-terminal assertion；未发现 mock
  proof、sleep timing、deadlock或假竞争。
- 两路都确认 validator 只改变 error owner，wire/schema 不变。
- 两路重新复核 initial rejected findings，没有一项因 fix diff 变为真实问题。
- 本次 re-review 没有 stash、checkout、reset、rebase、commit、push 或工作树
  切换；唯一既有 stash 保持未触碰。

两路结论均为 `PASS`，无新 finding。Controller 接受该 re-review closure。

## Finding closure

| Finding | Final status | Closure |
|---|---|---|
| `AGG-A01` non-TTY SIGINT lifecycle | `fixed` | production active-turn wait loop + pre-accept/single/double/third/cleanup tests |
| `AGG-A02` Ctrl+T erases exit intent | `fixed` | display-only event branch + idle/active lifecycle regression |
| `AGG-A03` unique-terminal deterministic competition proof | `fixed` | two real connections, production transactions, loser blocking trace, one terminal |
| `AGG-A04` response validator owner message | `fixed` | explicit request/response owners + exact contract tests |
| Initial rejected findings | `19 rejected` | factual errors、pre-existing code、explicit non-goals、frozen owner contract或 G01–G07 later boundary；均未被新 diff 改变 |

没有 partial、deferred 或未分类 finding。

## Validation decision

AgentCodex post-correction validation：

- focused closure：`12 passed`；
- affected regression + coverage：`185 passed`；
- `session_execution.py` 86%、`runner_identity.py` 95%、
  `compaction_terminal.py` 84%，aggregate 87%；
- affected ruff check：通过；
- full repository pyright：`0 errors, 0 warnings, 0 informations`；
- compileall、`git diff --check`、scope 与 secret pattern scan：通过。

Controller 独立 validation：

- 同一 focused closure matrix：`12 passed`；
- SQLite two-writer competition test 连续 10 次：`10 x 1 passed`，每次约
  0.34–0.35 秒；
- `git diff --check`：通过；
- normal 与 whitespace-insensitive diff 只相差一行新增 wrapping，controller
  correction 要求恢复的 formatter churn 已关闭。

warnings 仅为既有 `edgar` deprecated imports，不属于本 work unit。

## Scope and docs decision

最终 code/test diff 精确为：

- `dayu/cli/session_execution.py`
- `dayu/engine/contracts/runner_identity.py`
- `tests/cli/test_interactive_command.py`
- `tests/engine/contracts/test_runner_identity.py`
- `tests/host/test_compaction_terminal.py`

没有修改 Host production CAS、schema、design、oracle、scenario 或 README。
现有 README/design 已承诺 canonical cancel/terminal 与 successful response identity
contract；本 fix 只让实现满足既有 contract，并修正开发者错误消息，故不再机械
同步文档。

## Residual risks

所有 residual risk 已分类：

- G01–G07、formal interactive scenarios 与完整后续 CLI calibration 仍属于下一个
  calibration 阶段，不在本 work unit 伪造通过。
- 行为项 29 已在 S6 获得真实成功 compactor durable identity evidence；该 raw
  evidence 尚未注册为 formal scenario，因为 renderer target pin 与 G01–G07
  adjudication 尚未完成。这是已分类 validation boundary，不是 F13 implementation
  finding。
- SQLite competition 依赖 production 同样使用的 SQLite write serialization；
  controller 10 次稳定复跑和双路结构审查将当前 test-flake risk 分类为低且受控。
- 当前没有 deferred、blocking 或未分类 residual risk。

## Gate decision

- 两路 initial aggregate deepreview：完成。
- Controller findings adjudication：完成。
- AgentCodex accepted finding fix：完成。
- 两路 independent re-review：完成并通过。
- Tests、coverage、pyright、scope、secret 与 docs decision：完成。
- Commit scope：五个 owner/test 文件与本 gate 七份 durable artifacts。

结论：`aggregate deepreview pass — ready for accepted aggregate commit`。
