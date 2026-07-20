# WU-SEMANTIC-OWNERSHIP-01 / R09 code-review fix Controller validation

## 1. Decision

`PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_CODE_REREVIEW`。

本结论只授权 AgentMiMo / AgentDS 对同一 immutable R09 cumulative tree 做双路完整 code re-review；
不代表实现已接受，不授权 aggregate deepreview、commit、R10、push、PR 或 umbrella closeout。

R09 仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU，不是新 WU、
新 feature/issue 或重新打开的历史 sub-WU。

## 2. Authority and entry locks

- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`；
- accepted plan：`docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`，
  SHA-256 `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`；
- original implementation artifact：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-codex.md`，
  SHA-256 `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81`；
- original Controller validation：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-controller-validation.md`，
  SHA-256 `190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919`；
- code-review adjudication：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-controller-adjudication.md`，
  181 lines，SHA-256 `4fbc1e7bb25c3cbe5af61b40753fdc147e083e28913de39000c6a912382bccbc`；
- AgentCodex final fix artifact：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-fix-codex.md`，
  271 lines，SHA-256 `c9affe9935d2825284c10bcccd61169c3836cb5076d13de90bb517787e8c85d7`；
- staged tree：empty。

## 3. Controller follow-up finding and closure

Controller 在首次 fix handoff 后以真实控制流复核发现，SIGINT 本地取消与 raw close failure 组合路径会：

1. 从 child `CancelledError.__cause__` 取出 `close_error`；
2. 在 active child exception handler 内重抛该对象；
3. outer drain 再返回同一对象并执行等价 `raise e from e`。

直接 Python 证据确认这会形成 `e.__cause__ is e`，并可能通过隐式 `__context__` 形成反向环。
该问题属于已接受的 `R09-CR-F01`，不是新 finding 或 scope expansion。Controller 将同一任务退回
AgentCodex；最终修复满足：

- SIGINT handler 先保存 child cleanup cause，离开 active child exception handler 后才传播；
- drain 对 `cancellation_error.__cause__ is primary_error` 按 object identity 返回 `None`；
- distinct cleanup cause 继续返回，不被同一对象排重规则吞掉；
- 最终 SIGINT close failure 是同一 `close_error`，且 `__cause__ is None`、
  `__context__ is None`，raw close 恰一次；
- completed-child race 同时覆盖 same-primary 去重和 distinct-primary cause 保留。

Controller 完整读取最终 owner code、两条 completed-child race tests 与 SIGINT integration；
实现位于 CLI stream creator/drain owner boundary，没有修改 validator、Service/runtime、设计真源或
增加下游 fallback。

## 4. Finding closure

| Finding | Final status | Controller evidence |
|---|---|---|
| `R09-CR-F01` | closed | CLI creator 对 success/error/cancel/SIGINT 路径确定性 close；primary identity 与 distinct cleanup cause 保留；self-cause/context follow-up 已闭合。 |
| `R09-CR-F02` | closed | `_ControlledRawStream` 与 false `cast(AsyncGenerator, ...)` 均已删除；owner tests 使用真实 async generator。 |
| `R09-CR-F03` | closed | 真实 generator `GeneratorExit/finally` 与 production raw-bridge consumer-abort integration 覆盖 cancellation causal chain 和 late-publication fence。 |
| `R09-CR-F04` | closed | Fins README 三个 plain-def exact signature 均返回 `ValidatedFinsEventStream`；旧 exact signature 扫描为零。 |
| DS former F05 observation | rejected / no current fix | CLI 继续读取 owner public `terminal_result`，没有新增 fallback、compat 或第二语义 owner。 |

当前 accepted finding：`4 closed / 0 open / 0 deferred / 0 blocker`。

## 5. Immutable cumulative target

- sorted 6-path fix-authored product/test/README manifest：
  `0674946265e03a6be6878dde773ec8121cd9cf2bf8675a475e17816ddea02245`；
- sorted 12-path cumulative product/test/README manifest：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`；
- canonical cumulative binary diff：
  `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d`。

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `dayu/fins/README.md` | 789 | `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7` |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |

Controller 独立重算两个 manifest、12 个 content hash、canonical diff、HEAD 与 staged-empty，均匹配。

## 6. Validation

Controller 在最终 follow-up tree 上独立执行：

| Validation | Result |
|---|---|
| R09 affected aggregate | `161 passed, 3 existing warnings` |
| full Fins | `873 passed, 1 existing skip, 3 existing warnings` |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff，9 changed Python files | `All checks passed!` |
| `git diff --check` | pass |
| staged tree | empty |

AgentCodex 在最终 tree 另行完成并记录：accepted adversarial `27 passed`、R06 `242 passed`、
R08 `180 passed`、retained security 参数化结果 `16 passed`、五个 changed production file exact
coverage `88.56%-97.78%`、full pyright/Ruff/scans，以及 fresh SEC download、Docling process、
upload_filing 三条真实 smoke 全部 exit 0。Controller 在 follow-up 前也独立通过 R06 `242`、R08 `180`
和同三条 fresh real smoke；follow-up 最终只改 CLI creator、CLI tests 与 fix artifact，且最终 full Fins / affected
aggregate 已再次独立通过。

Source scans确认：

- Service/CLI old checker/fallback、`_direct_operation_kind`、enum/reason second owner 为零；
- three protocol reason literals 只由 `direct_events.py` enum 与 `direct_stream.py` decision owner 持有；
- false cast/fake seam、`gc.collect`、added-line `hasattr/getattr/compat/fallback` 为零；
- storage/pipelines/processors/Fins tools/Host/Engine/config/root README/dayu README no-touch；
- Issue 142/151/175/177/178、R10-R12、Topic 8/9、统一 authorization、Web/WeChat/render 未实现。

## 7. Security and residuals

保留的安全相关行为包括 direct event 不泄露 path/job id/raw payload、CLI 不绕过 Fins storage、
filesystem containment/symlink/atomic behavior no-touch，以及 consumer abort 的 cooperative cancellation 与
late-publication fence。没有删除 allowed paths、containment、process fencing 或其它既有防御机制，也没有
实现统一 tool authorization framework。

唯一既有 residual 是 Fins thread-backed long operation 的 physical process isolation，owner 仍为 Issue 175；
本 sub-WU 不越界实现 hard kill。full Fins 的一个 existing environment skip 与三条 edgartools deprecation
warning 未由 R09 新增，真实 Docling smokes 已成功，因此不是 waiver 或 blocker。

## 8. Next gate

AgentMiMo / AgentDS 必须分别对上述完整 12-path immutable cumulative target 做 complete code re-review，
重新挑战 terminal protocol、primary/cause/context、external cancellation/SIGINT/completed-child race、
真实 generator lifecycle、runtime raw bridge cancellation、signature propagation、README、security/no-touch 与
deferred scope。reviewer 只能新增各自 re-review artifact；任何 target 内容、manifest、diff 或 fix artifact
变化都会使两路 re-review 失效。

review verdict 不自动授权 commit。所有新 finding 仍由 Controller 裁决；accepted finding 必须由
AgentCodex 修复并再次完整 revalidation / re-review。当前不得进入 aggregate deepreview、commit 或 R10。
