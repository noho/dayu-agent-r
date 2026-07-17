# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream code-review fix evidence

## 1. Gate、结论与 authority

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`。
- 内部 remediation sub-WU：`R09`；本轮是同一 cumulative implementation 的 code-review fix gate，不是新 WU / issue。
- implementer：AgentCodex。
- 唯一 fix authority：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-controller-adjudication.md`，
  181 lines，SHA-256
  `4fbc1e7bb25c3cbe5af61b40753fdc147e083e28913de39000c6a912382bccbc`。
- entry / exit HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`。
- decision：`COMPLETE / READY_FOR_CONTROLLER_RELOCK_AND_DUAL_COMPLETE_REREVIEW`。
- finding closure：`R09-CR-F01..F04` 全部已修复；rejected observation 未实现；accepted finding 未 deferred 或顺延。
- Controller follow-up：独立复核发现 F01 的 SIGINT + child cleanup failure 仍可能构成
  self-cause/context 环；本 artifact 在同一 fix gate 内继续记录该 root-cause 修复与完整重验，不创建新 WU/issue。
- 未 stage、commit、push、创建 PR、修改 control/design/plan/prior review/adjudication artifact，未进入 aggregate deepreview 或 R10。

## 2. Entry locks 与第一性原理判定

实现前独立复核：

| Lock | Result |
|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b`，match |
| 原 sorted 12-path manifest | `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`，match |
| 原 canonical cumulative binary diff | `531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8`，match |
| implementation artifact | 274 lines；`3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81`，match |
| Controller validation | 104 lines；`190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919`，match |
| staged tree | empty |

问题动机成立。直接代码证据表明 `ValidatedFinsEventStream` 是普通 `AsyncIterator` class；Python
`async for` 不会替调用方关闭其自定义 `aclose()`。CLI 创建 stream 后，render/log 等循环体异常可在两次
`__anext__` 之间退出，此时 validator 不在调用栈，raw async generator 的 `finally`、operation cancellation
request 与 late-publication fence 都不能确定执行。

resource acquisition / lifecycle 的唯一 owner 是创建 stream 的
`dayu.cli.commands.fins::_run_fins_direct_command_async`。validator 继续唯一拥有 raw source 的
close-at-most-once 与 terminal protocol；Service/runtime 不应增加 consumer-specific fallback。外部取消还有一项
必要的同源约束：先 cancel 并 drain CLI event task，避免 raw generator 仍在 `__anext__` 中运行时并发
`aclose()`。这不是新状态机，而是创建者释放资源前必须完成的 child-task ownership。

## 3. Root-cause fix

### 3.1 CLI creator deterministic lifecycle

`dayu/cli/commands/fins.py`：

- `_run_fins_direct_command_async` 在 stream 创建后立即进入 owner boundary；success、typed protocol error、
  generic upstream error、downstream log/render error、外部 task cancellation 和 SIGINT local exit 都显式执行
  `stream.aclose()`。
- 新增 module-level typed helper `_raise_primary_after_fins_stream_close(...) -> NoReturn`。若已有 consumer
  primary，close 成功后重抛同一 object；close 失败时执行 `raise primary_error from close_error`，保持同一
  primary object，并把同一 cleanup error 作为显式 `__cause__`。无 primary 的正常退出路径直接
  `await stream.aclose()`，close error 才允许原样传播。
- 新增 module-level typed helper `_cancel_and_drain_fins_event_task(...)`。外部取消先确定性等待 child
  consumer cancellation/finalization；即使 child 已在检查前完成，也读取同一 task outcome，并以 object identity
  排除已作为 primary 传播的异常，避免丢失取消竞态中的 cleanup cause。随后由 stream creator 做幂等 close，
  不依赖 GC 或调度偶然性。
- SIGINT 抑制正常 child cancellation 后返回本地 130；若 raw generator cleanup 自身失败，不把它吞成
  local success，而是传播同一 close error。
- follow-up 不在 active child `CancelledError` handler 内抛出其 `__cause__`：先保存同一 close error，
  离开 handler 后再传播。`_cancel_and_drain_fins_event_task` 对
  `cancellation_error.__cause__ is primary_error` 也返回 `None`，消除 `raise e from e`；不同 cleanup
  cause 仍原样返回给 creator owner。
- SIGINT close-failure integration 精确断言最终异常 `is close_error`、`__cause__ is None`、
  `__context__ is None`、raw close 恰一次。两个真实 completed child race 分别证明 same-primary cause
  去重与 distinct cause 保留；drain 首次读取已完成 task outcome，不依赖 asyncio 对第二次 await
  保留 cancellation cause 的非契约行为。
- 未修改 CLI error prefix/message、business result exit `0/1/130`、typed reason presentation 或 public schema。

### 3.2 True async-generator tests

`tests/fins/test_fins_direct_stream.py`：

- 删除 `_ControlledRawStream`、`cast(AsyncGenerator[...], source)` 与 fake-only `aclose` counter seam。
- source 全部改为真实 `async def ... -> AsyncGenerator[FinsEvent, None]`；独立
  `_RawStreamObservation` dataclass 严格记录 `next_calls`、`GeneratorExit` 和 `finally` 次数。
- 覆盖 clean success / missing / duplicate / event-after / result-then-error / upstream error / upstream
  cancellation、close success/failure、repeated close、abortive/clean terminal availability。
- 真实 generator 的 upstream exception 会在离开 generator 时自行执行 `finally` 并关闭 frame，因此原 fake
  所制造的“upstream 已抛出后同一 generator 仍可在第二次独立 close 失败”不是 concrete
  `AsyncGenerator` 行为。该 false-seam 两个测试未保留；真实可发生的 consumer primary + raw close failure
  已在 CLI owner 的 log/render 两路测试中以同一 primary / cause / finally-once 完整覆盖，protocol primary +
  close failure 仍由 duplicate/event-after owner tests 覆盖。production validator constructor/state machine 未放宽或修改。

### 3.3 Raw bridge cancellation causal chain

`tests/fins/test_fins_ingestion_runtime.py`：

- 新增真实 public `ingestion.download(...) -> ValidatedFinsEventStream -> _run_direct_stream` integration。
- 同步 adapter 通过 `threading.Event` barrier 在首个 production progress 后暂停；consumer 显式 abort 并重复
  `aclose()` 后才允许 adapter 读取 production `request.cancellation_checker()`。
- 观察值精确为 `(True,)`，证明 `consumer abort -> validator aclose -> raw async generator GeneratorExit/finally
  -> cancellation_state.request_cancel -> producer cancellation checker` 因果链。
- adapter 在取消后尝试 late progress 并能返回；已关闭 public stream 继续 `StopAsyncIteration` 且
  `terminal_result` 不可用，证明 consumer 不观察 late publication。测试不调用 GC、不读取 raw bridge private
  state，也不复制 validator 算法。

### 3.4 README contract

- `dayu/fins/README.md` 三个 exact signature 已改为 plain
  `def download/preprocess/upload(...) -> ValidatedFinsEventStream`。
- `tests/README.md` 只按测试职责记录 CLI creator lifecycle、真实 generator observation 和 raw bridge abort
  cancellation integration。
- root `README.md` 与 `dayu/README.md` 的用户工作流、分层和宽泛 iterator 说明未改变，按 accepted plan/no-touch
  decision 不更新。

## 4. Finding closure ledger

| Finding | Final status | Closure evidence |
|---|---|---|
| `R09-CR-F01` | 已修复 | CLI creator 对所有退出路径显式 close；log/render 两路保持同一 primary/cause；external cancellation 与 SIGINT 确定 close。follow-up 进一步证明 SIGINT close failure 是同一无 cause/context 的唯一 primary，completed child same-primary cause 去重且 distinct cause 不吞。 |
| `R09-CR-F02` | 已修复 | false cast 与 `_ControlledRawStream` 删除；全部 owner sources 为真实 `async def AsyncGenerator`，typed observation 通过 full pyright。 |
| `R09-CR-F03` | 已修复 | 真实 generator `GeneratorExit/finally` tests + production raw bridge consumer-abort integration 证明 cancellation request 与 no-visible-late-event 因果链。 |
| `R09-CR-F04` | 已修复 | 三个 exact Fins runtime signatures 更新；Fins/Service/tests README 精确旧签名扫描为零。 |
| rejected DS observation / 原 F05 | 未实现（按裁决） | CLI 继续在 clean exhaustion 后读取 owner public `terminal_result`；未增加 fallback、compat 或第二语义 owner。 |

## 5. Exact fix manifest 与 cumulative locks

### 5.1 Fix-authored product/test/README manifest

sorted newline-delimited 6-path manifest SHA-256：
`0674946265e03a6be6878dde773ec8121cd9cf2bf8675a475e17816ddea02245`。

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `dayu/fins/README.md` | 789 | `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |

本 artifact 是唯一额外获准 authored path；为避免自引用 hash 不可能问题，其最终 lines/SHA 由写入完成后的外部
命令计算并在 handoff 报告。

### 5.2 Final cumulative 12-path target

sorted 12-path manifest 未增删路径，SHA-256 仍为：
`ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`。

| Path | Lines | Final SHA-256 |
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

Final cumulative canonical binary diff 使用与原锁相同算法：tracked 10-path
`git diff --binary HEAD` 后顺序拼接两个新增文件各自
`git diff --no-index --binary /dev/null <path>`。SHA-256：
`e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d`。

## 6. Validation ledger

所有 Python 命令均先执行 `source .venv/bin/activate`。

### 6.1 Accepted adversarial 与 regression tests

| Exact scope | Result |
|---|---:|
| `tests/fins/test_fins_direct_stream.py` + raw-bridge abort node + CLI lifecycle/protocol/SIGINT/completed-child/cancel-race exact nodes | `27 passed, 3 existing warnings` |
| R09 affected aggregate：direct stream + ingestion runtime + Service + CLI | `161 passed, 3 existing warnings` |
| R06：`test_fins_storage_atomicity.py test_fins_storage_provider.py` | `242 passed, 3 existing warnings` |
| R08：4 个 financial/read consistency files | `180 passed, 3 existing warnings` |
| full Fins：`pytest -q tests/fins --junitxml=workspace/tmp/r09-full-fins-fix3.xml` | `873 passed, 1 existing skip, 3 existing warnings`，exit 0 |
| retained security exact nodes（9 node selectors，含参数化 cases） | `16 passed, 3 existing warnings` |

full-Fins 首次 console 捕获只到 65%，没有可靠 final summary，未计为证据；最终 JUnit run 独立完整重跑并取得
exit 0。JUnit SHA-256：
`3bc19e729050b567f23c921c8cb638509bffd121938759d2aa3fa1e81dcf0c13`。

coverage acceptance 严格使用 Controller 已验证口径：先 `coverage erase`，再执行不带
`--source/--branch/--timid` 的同一 4-file `coverage run -m pytest`，结果同为 `161 passed`。诊断期间
`--source` 组合曾扰动 asyncio cancellation scheduling；该非 acceptance 命令未用于结论，也未据此修改
production/test 语义。

### 6.2 Five changed production Python file coverage

同一 affected aggregate 生成 `workspace/tmp/coverage-r09-fix3-accepted.json`；五次单文件
`coverage report --fail-under=80` 均 exit 0，无 omit/waiver/aggregate threshold 替代。

| Production path | Exact JSON coverage |
|---|---:|
| `dayu/fins/direct_events.py` | 92.20779220779221% |
| `dayu/fins/direct_stream.py` | 97.77777777777777% |
| `dayu/fins/ingestion_runtime.py` | 90.43942992874109% |
| `dayu/service/fins_direct.py` | 90.16393442622950% |
| `dayu/cli/commands/fins.py` | 88.56382978723404% |

Coverage JSON SHA-256：
`1fdaf6a1266bcf95328c5fbb8c6c5eb9fa2e78d0f6d690098c500a8aa8321819`。

### 6.3 Type、lint、diff

| Command | Result |
|---|---|
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| cumulative 9 changed Python files `python -m ruff check ...` | `All checks passed!` |
| `git diff --check` | pass，零输出 |
| `git diff --cached --quiet` | exit 0，staged empty |

### 6.4 Owner、stale、compat、deferred、no-touch 与 security scans

- Service/CLI 旧 `_ensure_result_event`、old missing fallback、`_direct_operation_kind`：零命中。
- Service/CLI `raise FinsDirectStreamProtocolError`、enum ownership、`reason.value`：零命中。
- runtime/Service protocol error import/construction：零命中。
- `MISSING_RESULT / DUPLICATE_RESULT / EVENT_AFTER_RESULT` production literal：只命中
  `direct_events.py` enum 与 `direct_stream.py` owner decision。
- Fins/Service/tests README old exact `-> AsyncIterator[FinsEvent]` direct signatures：零命中。
- wider scoped `AsyncIterator[FinsEvent]` 只命中 ingestion runtime test 的通用 collect helper 参数；它接受 concrete
  subtype，不是 runtime/Service/CLI return signature，也不承担 terminal 语义，分类为有效非陈旧命中。
- `_ControlledRawStream`、`cast(AsyncGenerator...)`、`gc.collect`：零命中。
- cumulative production added-line / new validator `hasattr|getattr|compat|fallback`：零命中。
- fix added-line Issue 142/151/175/177/178、R10-R12、Topic 8/9、authorization framework、Web/WeChat/render：零命中。
- storage/pipelines/processors/Fins tools/Host/Engine/runtime/config/root README/dayu README cumulative diff：零路径。
- retained security exact tests覆盖 direct event leakage、CLI 不导入 Fins storage、upload event 不泄露 path/job id/raw
  payload，以及 consumer-abort cancellation/late-event fence；9 个 node selectors 的参数化结果为 `16 passed`。
- no-touch content locks精确保持：`direct_events.py`、`direct_stream.py`、`ingestion_runtime.py`、Service README/code、
  Service tests 均与原 Controller lock相同。plan SHA `a46cd445...`、MiMo `ee79e2e...`、DS `0f1a46b...`、
  adjudication `4fbc1e7...`、implementation `3c16b65...`、Controller validation `190a1e6...`、design
  `97033cf...` 均未漂移。

## 7. Real SEC / Docling success smokes

全部使用 fresh、非复用 `workspace/tmp/` 目录，走真实
`python -m dayu.cli -> Service -> DefaultFinsRuntime -> producer -> validator`，无 mock/skip/fake。

| Smoke | Fresh workspace | Result |
|---|---|---|
| SEC AAPL 10-K download（2025） | `workspace/tmp/r09-fix3-real-download-codex` | exit 0；`discovered=1 downloaded=1 written_documents=1`，progress + one success terminal |
| process / Docling | 同一真实 download workspace | exit 0；`selected=1 processed=1 failed=0 not_supported=0`，progress + one success terminal |
| upload_filing / Docling fixture | `workspace/tmp/r09-fix3-real-upload-codex` | exit 0；`uploaded_files=1`，document `fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283`，progress + one success terminal |

环境真源未变化；没有把 full-Fins 的 existing environment skip 当作真实 Docling smoke。

## 8. README decision

- `dayu/fins/README.md`：更新 exact current runtime signatures，属于 Fins public direct contract 职责。
- `tests/README.md`：更新现有测试覆盖事实，属于 tests maintenance 职责。
- root `README.md`：命令、参数、输出通道、exit mapping、用户工作流未变，no update。
- `dayu/README.md`：分层/装配未变，no update；其宽泛 `AsyncIterator` 说明仍由 concrete validated subtype 满足。
- `dayu/service/README.md`：当前已准确描述 validator identity pass-through 与 caller close/cancel，fix 无职责变化，no update。

## 9. Residual owner / destination

- R09 accepted code-review findings：residual `0`；没有未关闭、部分修复或 deferred finding。
- full Fins 的 1 个 existing environment skip 与 3 个 edgartools deprecation warnings 未新增、未升级为 error；真实
  SEC/Docling smokes均成功。
- Fins thread-backed long operation 的 physical process isolation 仍归 Issue 175；本 fix 只保证 cooperative
  cancellation request、deterministic raw close 与 late-publication fence，不越界实现 process kill。
- Issues 142/151/177/178、R10-R12、Topic 8/9、统一 authorization、Web/WeChat/render 仍归既有 owner，未实施。
- rejected terminal-result observation 按 Controller 裁决保持 no-current-fix，不成为 residual finding。

## 10. Exit state 与 next gate

- HEAD 保持 `9d36a115400fb59fd95475189810b43a09fda31b`。
- staged tree empty；未 commit/push/PR。
- 本 artifact 完成后由外部命令报告 final lines/SHA-256。
- next gate：Controller 独立锁定新的 cumulative manifest/diff/content hashes并复核 validation，然后 AgentMiMo / AgentDS
  对完整 S1+S2+fix cumulative tree 做双路 complete re-review。当前不授权 aggregate deepreview、accepted commit、R10
  或 umbrella closeout。
