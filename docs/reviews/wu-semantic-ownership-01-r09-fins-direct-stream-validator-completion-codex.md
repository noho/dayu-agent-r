# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator completion evidence

## 1. Gate、边界与最终结论

- 本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU `R09` 的
  completion evidence gate，不是新 WU、issue 或 feature。
- accepted implementation commit：`8e0f2c5588c395cc8ee459a35f36db1de737b450`，commit message
  `fins: accept R09 direct stream validator remediation`。
- completion verdict：`COMPLETE / ZERO ACCEPTED OR OPEN FINDING / ZERO R09 ACTUAL ACCEPTED RESIDUAL`。
- R09 的唯一语义 owner、implementation、review/fix/re-review、aggregate 与 accepted implementation
  commit 证据链完整；本 artifact 只固化 completion evidence，不修改任何产品、测试、README、design、
  control、plan 或 prior artifact。
- 本 gate 未 stage、commit、push、创建 PR 或进入 R10。R09 `COMPLETE` 不等于 umbrella closeout：
  `WU-SEMANTIC-OWNERSHIP-01` 仍为 active，R10 仍未授权。下一步只允许 Controller validation 与其后
  独立授权的 exact-scope completion commit。

第一性原理判断仍成立：direct stream 是否恰好包含一个且最后一个 `RESULT` 是单一协议事实；只有直接
持有 raw async-generator、operation provenance、terminal event 与 close lifecycle 的 Fins typed stream
边界拥有完整信息。把判断分散在 runtime、Service、CLI 会产生 owner drift、provenance 改写和重复状态机。
最终实现把该事实收敛到 `dayu.fins.direct_stream.ValidatedFinsEventStream`；Service 只透传同一 typed
stream/error identity，CLI 只机械消费、负责自身 consumer close，并沿用既有人类可读 projection。

## 2. 全量 R09 artifact evidence universe

本次读取并交叉核对当前仓库全部 29 个 `wu-semantic-ownership-01-r09-fins-direct-stream-validator-*`
durable artifacts。Controller adjudication 是 finding disposition 真源；MiMo/DS/Codex artifacts 提供代码、
反例、修复和验证直接证据，不覆盖 Controller 裁决。

Accepted-plan stage 的 10 个 artifacts 为：

1. `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-entry-controller-validation.md`
3. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-mimo.md`
4. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-ds.md`
5. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`
7. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-controller-validation.md`
8. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-mimo.md`
9. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-ds.md`
10. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-controller-adjudication.md`

其余 19 个 implementation/review-stage artifacts 全部位于 accepted implementation commit，见 §3.3 的
逐路径 Git blob 清单。全量 artifact 链给出的时序真值是：`R09-PR-F01..F06` 在 accepted-plan gate 全部
关闭；implementation 后 code review 接受 `R09-CR-F01..F04`，fix/re-review 又接受 `R09-RR-F01`；
这些 finding 最终全部关闭，dual final code re-review 与 dual aggregate deepreview 都为 PASS。

## 3. Accepted implementation commit 直接对象审计

### 3.1 Commit identity 与 exact manifest

对 commit object、tree object 与 parent 直接读取的结果：

| 项目 | 直接证据 | 结论 |
|---|---|---|
| commit | `8e0f2c5588c395cc8ee459a35f36db1de737b450` | match |
| parent | `9d36a115400fb59fd95475189810b43a09fda31b` | match；单一 parent |
| tree | `f2bc9ecee14da46dc95e004922262a3ab521fe24` | match |
| message | `fins: accept R09 direct stream validator remediation` | match |
| changed path count | 32 | exact |
| status distribution | 21 added / 11 modified | 与分组 manifest 一致 |
| commit-range whitespace check | `git diff --check` 零输出 | pass |

`git diff-tree -r` 的 32 路径与授权闭集逐项相等：12 个 product/test/README、19 个 R09 evidence、
1 个同步 control；没有缺项、额外路径、rename、copy、delete、submodule 或 mode-only drift。

### 3.2 12 个 product/test/README path 与 commit blob

下列 OID 均来自 accepted commit tree；并对每个 `git show <commit>:<path>` 独立计算 SHA-256，12 个
内容哈希全部匹配最终 immutable content locks。

| 类别 | Status | Path | Git blob OID |
|---|---|---|---|
| Product | M | `dayu/cli/commands/fins.py` | `3597a1fc139a71c3210f7f13d1037d3af78e2624` |
| README | M | `dayu/fins/README.md` | `083a235b72c82be32731068012f104eadf3c4027` |
| Product | M | `dayu/fins/direct_events.py` | `11f5f01ae41dcb46dd9c122d549589ab25b2ae79` |
| Product | A | `dayu/fins/direct_stream.py` | `7340d0c9f6ce302ab5589993fd9ba44ef5eb9951` |
| Product | M | `dayu/fins/ingestion_runtime.py` | `28680f663490a7940d69b14779bfaa9541cf36c8` |
| README | M | `dayu/service/README.md` | `0d2a5e656b702dea91268c0567aca7b3329fc1bb` |
| Product | M | `dayu/service/fins_direct.py` | `8cdf6f135feb4058a79dc21b36ccd6df4200ee2d` |
| README | M | `tests/README.md` | `d2ae8acdff282b07892b1a1ca0d266cd5a520d58` |
| Test | M | `tests/cli/test_fins_commands.py` | `bc41bf112cfea092a3a6ebadbf07d4e0604bafe3` |
| Test | A | `tests/fins/test_fins_direct_stream.py` | `ac80dd39008e33bd2dec9d5c7a71645c8966e5d9` |
| Test | M | `tests/fins/test_fins_ingestion_runtime.py` | `978872e08e6e9699573a465046229afb382e3a45` |
| Test | M | `tests/service/test_fins_direct.py` | `5191951d694193d904d5d126355c8c2d07bbe379` |

### 3.3 19 个 implementation/review evidence path 与 commit blob

| Gate | Status | Path | Git blob OID |
|---|---|---|---|
| implementation authorization | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-controller-authorization.md` | `c04c90c4e7857174e768ff4541e6f1efadac5f34` |
| implementation | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-codex.md` | `4fdb4f5ebe3490c0ef1dad268bd29fd6cca2479b` |
| implementation validation | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-controller-validation.md` | `e0219ffea903a17cf581c81a3abb707ac6bd4277` |
| code review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-mimo.md` | `df889cc08bc3dcc5d5237f51ce8f12cec92abc22` |
| code review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-ds.md` | `1bd7d84e42b6cfb1be6eebbbcd1417a2657c7d68` |
| code-review adjudication | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-controller-adjudication.md` | `8eb99c4cca8f90efec802e163d78909d7bb580e4` |
| code-review fix | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-fix-codex.md` | `b126d944606493fbb8321d5eb5b5f8727c7630e7` |
| fix validation | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-fix-controller-validation.md` | `d5b81c2ed4879a47960380f4586401b4ed5a8a54` |
| code re-review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-mimo.md` | `5c687ad20730fb4121fc980ecd925a67a914a607` |
| code re-review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-ds.md` | `83604572673f425361e17d38ac925e7598978db2` |
| re-review adjudication | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-controller-adjudication.md` | `e1b0120f716406e8b5c10f7c03e0a5b146039607` |
| re-review finding fix | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-codex.md` | `bb82f4e198b42e91dcaf2268431ed19b1d20b76d` |
| re-review fix validation | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-controller-validation.md` | `af4ba7ff4e3fc8fe8a7f3b9810f5cd6ac952a232` |
| final code re-review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-final-rereview-mimo.md` | `8195b46d143261ab609113d2a4dd6177814f3555` |
| final code re-review | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-final-rereview-ds.md` | `01c99ac553b58a42de62fd924c29baec6af38571` |
| final re-review adjudication | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-final-rereview-controller-adjudication.md` | `a12bcf9e4726f34adb8d0a2ab70de3c04e3a4017` |
| aggregate deepreview | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-mimo.md` | `01ea90887ca5f7ae8711051944a5dd7fc6d55dba` |
| aggregate deepreview | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-ds.md` | `fc044246c64468014556fc279c028b3debc00fd9` |
| aggregate adjudication | A | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-controller-adjudication.md` | `d11a52250f6bfc0613e80613e57b6545aacc9226` |

### 3.4 Commit 内 control path 与 blob

| Status | Path | Git blob OID |
|---|---|---|
| M | `docs/host/issues-implementation-control.md` | `516eb80d8da43bb30c36548c21ed5831b64a2ce6` |

当前 worktree 的同一 control 文件是 Controller 在 commit 后有意继续修改的
`d581bf1602872bac931420f534fdce4950bab239` working-tree blob；本 gate 只读取并保持它，不修改、不覆盖、
不 stage，也不把它吸收到 completion artifact。

## 4. Cached product/test/README diff authority lock

Authority lock 的输入不是“12 paths 交给一次 `git diff`”。原算法必须按当时 entry 状态保持三段 patch
byte stream 的连接顺序：

1. 对 parent `9d36a115400fb59fd95475189810b43a09fda31b` 到 accepted commit
   `8e0f2c5588c395cc8ee459a35f36db1de737b450`，先生成 10 个 tracked-at-entry paths 的
   `git diff --binary`：
   - `dayu/cli/commands/fins.py`
   - `dayu/fins/README.md`
   - `dayu/fins/direct_events.py`
   - `dayu/fins/ingestion_runtime.py`
   - `dayu/service/README.md`
   - `dayu/service/fins_direct.py`
   - `tests/README.md`
   - `tests/cli/test_fins_commands.py`
   - `tests/fins/test_fins_ingestion_runtime.py`
   - `tests/service/test_fins_direct.py`
2. 原样追加同一 commit range 仅 `dayu/fins/direct_stream.py` 的 `git diff --binary`。
3. 再原样追加同一 commit range 仅 `tests/fins/test_fins_direct_stream.py` 的 `git diff --binary`。
4. 对三段原样串联的 bytes 计算 SHA-256。

独立复算结果：

`60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`

结论：`PASS / AUTHORITY LOCK MATCH`。

若把全部 12 paths 一次性交给 Git，Git 会按它自己的全局 path 顺序输出另一组 patch bytes，得到
`3b804117088f65b8f8a12a8d21055253ba1668ad5b53c44eda2b4ad43a73abda`。该值只反映不同的串联算法，
不是 authority lock，不是 content drift，不是 finding，也不改变 accepted commit 的任何裁决。

## 5. 语义 owner 与最终 contract

- `dayu.fins.direct_stream.ValidatedFinsEventStream` 是 exactly-one-and-last `RESULT`、
  missing/duplicate/event-after、clean-exhaustion terminal availability 与 raw-source close lifecycle 的
  唯一 decision owner。
- `dayu.fins.direct_events` 只拥有 event/result/typed protocol error data contract；新增唯一 code
  `EVENT_AFTER_RESULT`，没有 alias、兼容 parser 或第二 error schema。
- ingestion runtime 只拥有 producer、queue 与 raw async-generator composition；public direct methods 是
  plain `def -> ValidatedFinsEventStream`，raw bridge 不再构造 protocol error。
- Service 返回同一个 typed stream，不 await、不 iterate、不 wrap、不重建；`process_filing` /
  `process_material` 的 validator provenance 始终来自 runtime `PREPROCESS`，command alias 只用于日志。
- CLI 完整消费 owner stream 后读取 public `terminal_result`，并在 creator boundary 对正常、异常、外部
  cancellation、SIGINT/local-exit 全路径确定性 close；不重判 terminal，不枚举 reason，不解析 message。
- primary semantic error/cancellation 保持 object identity；distinct cleanup failure 只作为显式 cause；底层
  close 成功或失败都至多尝试一次；same-primary cleanup identity 去重，不产生 self-cause/context。
- CLI 沿用既有 `dayu-cli {command}: {message}`、business result 与 exit `0/1/130`，没有把 typed reason
  变成新的用户或 LLM-facing 输出协议。

## 6. Finding 最终 disposition

| Item | Final disposition | Completion evidence |
|---|---|---|
| `R09-PR-F01..F06` | closed | fixed plan dual complete re-review 与 Controller adjudication均确认关闭；accepted-plan commit 后无 plan drift。 |
| `R09-CR-F01` | closed / 已修复 | CLI creator 对 success、consumer/protocol/upstream error、external cancellation、SIGINT 全路径确定性 close；同一 primary identity 与 distinct cleanup cause 均有真实 generator tests。 |
| `R09-CR-F02` | closed / 已修复 | false concrete `AsyncGenerator` cast 与 fake-only `_ControlledRawStream` 删除；Fins/Service/CLI tests 使用 typed real async generators。 |
| `R09-CR-F03` | closed / 已修复 | `GeneratorExit`、`finally`、raw bridge cancellation request、late-publication fence、close-at-most-once、upstream error/cancel 与 cleanup cause 有 owner/integration tests。 |
| `R09-CR-F04` | closed / 已修复 | Fins README 三个 direct exact signatures 均为 plain `def -> ValidatedFinsEventStream`；stale exact signature scan 为零。 |
| F01 self-cause/context follow-up | closed under `R09-CR-F01`；不是新 finding | completed-child/SIGINT same-primary cleanup 按 identity 去重；最终 close error 的 `__cause__`、`__context__` 均无 self-cycle，distinct cause 不被吞。 |
| `R09-RR-F01` | closed / 已修复 | Fins main-component tree 只补入 `direct_events.py` 与 `direct_stream.py` 两个稳定 owner，没有扩成文件流水账。 |
| DS former F05 terminal-result observation | rejected / no current fix | clean exhaustion 后读取 owner public `terminal_result` 是既定 contract；无当前失败反例，不加 fallback 或第二 owner。 |
| Final code re-review new finding | zero | MiMo、DS 与 Controller 均为 PASS / zero material finding。 |
| Aggregate new finding | zero | 双路 aggregate 与 Controller 均为 PASS / zero accepted or material finding。 |

Aggregate candidate 的最终裁决：

- AgentMiMo 初始 `R1-R4` residual candidates：`rejected-with-reason / removed from final artifact`，共 4 个。
  它们没有当前失败反例；不得据此创建 speculative integration WU；dead-thread fallback 已存在；dataclass
  invariant 没有合法绕过路径；异常 object identity 判断本来就必须使用 `is`。因此这些 candidate 不是
  residual、finding 或后续授权。
- AgentDS 的 daemon-thread 与 50ms queue polling 记录：2 个 `non-actionable existing design observations`；
  没有当前 failing behavior，不建立新 owner，也不计入 R09 residual。
- Issue 175 process isolation：`deferred-with-existing-owner` 的既有治理记录；不是 R09 accepted finding，
  未在本树实现，也不计入 R09 actual accepted residual。

Final ledger：accepted/open finding `0`；evidence-invalid rejected candidate `4`；non-actionable observation
`2`；deferred existing-owner record `1`；blocker `0`；**R09 actual accepted residual `0`**。

## 7. 最终验证真值

早期 implementation artifact 的 `155 passed`、full Fins `874 passed` 和早期 coverage 是修复前时点证据；
completion 只采用 code-review fix 后由 Controller 锁定、后续 re-review/aggregate 确认无 drift 的最终真值：

| Validation | Final truth |
|---|---|
| R09 affected aggregate | `161 passed, 3 existing warnings` |
| R06 storage regression | `242 passed, 3 existing warnings` |
| R08 financial/XBRL regression | `180 passed, 3 existing warnings` |
| full Fins | `873 passed, 1 existing skip, 3 existing warnings` |
| accepted adversarial exact nodes | `27 passed, 3 existing warnings` |
| retained security exact parameter cases | `16 passed, 3 existing warnings` |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff，9 个 changed Python files | `All checks passed!` |
| diff checks | cumulative/commit-range checks均 pass，零 whitespace error |
| owner/propagation/stale/compat/deferred/no-touch scans | 全部符合预期；零未分类命中 |

五个 changed production Python files 的最终逐文件 coverage 均使用同一 accepted affected suite data，
分别执行 `--fail-under=80`，没有 omit、waiver、aggregate threshold 或 changed-line 替代：

| Production path | Exact JSON coverage | Completion display |
|---|---:|---:|
| `dayu/fins/direct_events.py` | 92.20779220779221% | 92.21% |
| `dayu/fins/direct_stream.py` | 97.77777777777777% | 97.78% |
| `dayu/fins/ingestion_runtime.py` | 90.43942992874109% | 90.44% |
| `dayu/service/fins_direct.py` | 90.16393442622950% | 90.16% |
| `dayu/cli/commands/fins.py` | 88.56382978723404% | 88.56% |

三条 fresh real success smoke 均先激活 `.venv`，通过真实
`python -m dayu.cli -> Service -> DefaultFinsRuntime -> producer -> validator`，没有 mock、fake、skip 或
pytest injection 替代：

1. SEC AAPL 2025 10-K download：exit 0；`discovered=1`、`downloaded=1`、
   `written_documents=1`，progress 后恰一个 success terminal。
2. process / Docling：exit 0；`selected=1`、`processed=1`、`failed=0`、`not_supported=0`，
   progress 后恰一个 success terminal。
3. upload_filing / Docling fixture：exit 0；`uploaded_files=1`，progress 后恰一个 success terminal。

full Fins 的一个 existing environment skip 与三个既有 edgartools deprecation warnings 均非 R09 新增；
真实 Docling smokes 成功，因此 skip/warnings 不是 waiver、finding、residual 或 blocker。

## 8. 安全保留与 no-sneak scope audit

以下安全语义均保留，没有删除、放宽、替换 owner 或以 Topic 9 no-code decision 为由撤销防御：

- direct event safe-text/leakage guard；path、job id、raw payload/body/provider text 不进入 direct event；
- operation-scoped cooperative cancellation、consumer-close cancellation state、queue backpressure 与
  late-publication fence；
- CLI 不导入或绕过 Fins storage，不自行访问财报文档存储；
- filesystem containment、symlink 防线、atomic publication、R06 transaction authority；
- 既有 authorization、resource/process fencing 与 generic bounded failure mapping；
- typed protocol code 只来自 Fins enum/validator，CLI 不解析或展示 raw `reason.value`。

retained security 的 16 个 exact parameter cases 全部通过。R09 加强 consumer abort cleanup，但没有实现统一
tool authorization framework，也没有把 physical hard-kill/process-isolation 伪装成已解决。

Accepted commit 的 exact path manifest、product diff scan、owner/propagation/deferred/no-touch scans 与双路
review 共同确认：

- Issue 142、151、177、178 没有实现；
- Issue 175 没有实现，只保留既有 deferred owner 记录；其 owner 仍是 Fins Docling process isolation / Issue 175；
- Web、WeChat、`dayu/render` tracker 没有实现；宽泛 `render` 命中只属于既有 CLI presentation helper，
  不是 deferred render scope；
- Topic 8 的 Engine 240-character redacted/truncated exception policy 未修改；
- Topic 9 与统一 tool authorization framework 未实现；
- R10-R12、Host/Engine/UI、storage/pipelines/processors/read contracts、root/dayu README、design truth 均未偷带。

因此 Issue 175 是唯一既有 deferred owner 记录，但 **R09 actual accepted residual = 0**。

## 9. Completion state、workspace ownership 与 handoff

- R09 status：`COMPLETE`。
- umbrella status：`WU-SEMANTIC-OWNERSHIP-01 ACTIVE`。
- R10 status：`NOT AUTHORIZED`。
- 本 gate 唯一 authored path：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-completion-codex.md`。
- Controller-owned `docs/host/issues-implementation-control.md` 的 current worktree 修改保持原样；本 gate 没有
  修改、stage、commit 或覆盖它。
- staged tree 必须并保持 empty；本 gate 不执行 stage、commit、push、PR 或任何 R10 动作。
- 下一入口只允许 Controller 独立验证本 completion evidence；任何 completion commit 必须另行获得 exact-scope
  授权，不能由本 artifact 自动产生。

为避免不可能的递归自引用，本 artifact 不在正文嵌入自身最终行数或 SHA-256。写入完成后由外部只读命令
计算并在 handoff 中报告 path、lines 与 SHA-256。
