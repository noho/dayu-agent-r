# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Fix — AgentCodex

## 0. Gate identity 与结论

- work unit：`WU-SEMANTIC-OWNERSHIP-01 / R09 — Fins direct-stream terminal validator`。
- gate：Controller adjudication 后的 **plan-only fix**；`IMPLEMENTATION_NOT_AUTHORIZED`。
- 修改目标：`docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`。
- 本 artifact：`docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`。
- 结论：`R09-PR-F01..F06` 已全部在 plan owner boundary 关闭；没有发现需要 STOP 的直接设计矛盾。下一入口只能是 AgentMiMo / AgentDS 对新 immutable plan SHA 做双路完整 re-review。

## 1. Immutable source locks

Controller adjudication 是 finding disposition 与 required action 的唯一裁决真源；两路 review 只作直接证据。

| source | verified SHA-256 | role |
|---|---|---|
| original R09 plan | `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210` | immutable fix input，689 行 |
| Controller adjudication | `f615eccf7b2b8db387b5dc1125b95ef5a479c5420cd3c42dff469779a5070643` | sole finding adjudication truth |
| AgentDS review | `0434e4766729d2d85c1ade31c767a88ffd47781e7b49b4b734d86ae8a0a53ad9` | evidence only |
| AgentMiMo review | `d220c1dd7637d560c835f059841c7effaafe1027b3deb7fe5b1e0919a80b57ac` | evidence only |
| current Controller transition | `3d9403bcda79cb195e887141bbf75ffeac5e2ea6ca4d9072f9d2718d04461507` | read-only gate state；本轮未修改 |

plan 内锁定的 production/test/design/umbrella source hashes经 fresh `shasum -a 256` 复核仍匹配；本次只把已经由 Controller 推进的 current control transition hash更新为上表实际值，没有读取 control 作为 finding 真源。

## 2. Old/new plan identity

| metric | original plan | fixed plan |
|---|---|---|
| SHA-256 | `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210` | `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` |
| line count | 689 | 773 |
| gate state | dual review target | plan fix complete / awaiting dual full re-review |

固定后的 plan SHA 是新的 immutable re-review target；任何后续内容变化都会使本 artifact 中的 new SHA 失效，必须重做锁定和 re-review。

## 3. Controller finding closure ledger

| finding | plan fix | exact closure evidence |
|---|---|---|
| `R09-PR-F01` | closed | §3.4 新增 exact old/new signature + call-site table：runtime `download/preprocess/upload` 从含 `yield` 的 `async def -> AsyncIterator[FinsEvent]` 改 plain `def -> ValidatedFinsEventStream`；`_run_direct_stream` 保持 `async def -> AsyncGenerator[FinsEvent, None]` raw bridge；Service protocol/public/private request helper保持 plain `def` 且直接透传同一 stream；CLI opener/helpers保持 plain `def`，wait/consumer 仅收窄 concrete type并删除 fallback 参数，调用链无新增 `await`。表内列出 runtime、raw bridge、三个 Service protocol method、六个 Service public method、`_preprocess` 与全部 CLI helper 的精确参数/返回 shape。 |
| `R09-PR-F02` | closed | §4 将 upstream exception/cancellation identity 与 duplicate/event-after typed error固定为 primary semantic error；cleanup close failure 只能作为显式 `__cause__` 保留，不覆盖 primary type/object/reason/operation_kind/message或 CLI exit。无 primary 的显式 consumer close failure按同一 object传播；close-attempted guard保证底层 close成功或失败都至多一次。§7.1 列出 close success/failure、duplicate/event-after、upstream error/cancel、identity/chaining及 repeated-close exact tests。 |
| `R09-PR-F03` | closed | 从 root-cause defect、状态机变更、production change、queue extension、test node、scan expectation与 residual中删除 speculative producer protocol-error path。plan 只保留真实 contract：`_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` 和 producer generic exception -> bounded business failure `RESULT` 原样不变；raw bridge native async error/cancel自然传播；validator唯一构造 missing/duplicate/event-after。旧 typed-producer identity test已删除。 |
| `R09-PR-F04` | closed | §3.2/§4 把提前读取 `terminal_result` 固定为普通 `RuntimeError`，使用 module-owned `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE` safe constant；不新增 public/private error class或 CLOSED 子状态。§7.1 列出 OPEN、RESULT_BUFFERED、abortive close、clean exhaustion 四个 exact tests；前三者断言类型/常量消息，clean case断言同一 `FinsResultSummary` object。 |
| `R09-PR-F05` | closed | §3.3/§5.4/§7.3 删除 CLI raw `reason.value` public display和对应 code-output assertion；`run_fins_direct_command` 严格保持 `dayu-cli {command}: {exc.message}` 与 `EXIT_FAILURE=1`，不解析/枚举/rebuild。§5.3 fresh scan根/目标 README并记录职责、SHA和 update/no-update rationale。 |
| `R09-PR-F06` | closed | §3.4、§7.2/§7.3/§7.4 增加 Fins `reason/operation_kind/message/object` 同源传播与 stream/error identity tests。Service 与 CLI 都覆盖 `process_filing`、`process_material` 名称和 runtime validator `PREPROCESS` 值不同的反例，禁止 Service alias替换 provenance；CLI public presentation仍不取得 typed reason ownership。 |

## 4. 修改范围与边界

本 gate 的预期写入闭集只有：

1. 修改 `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`；
2. 新增本 plan-fix artifact。

没有修改 control、entry/review/adjudication、product、tests、README 或其它 artifact；没有 stage、commit、push、PR 或代码实现。工作区原有 `docs/host/issues-implementation-control.md` 修改及既有未跟踪 plan/review artifacts均作为用户/Controller 输入保留，没有吸收到本轮修改。

## 5. README、security、coverage 与 deferred scope check

### 5.1 README fresh scan

| README | verified SHA-256 | decision |
|---|---|---|
| `README.md` | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` | no update：没有 Fins direct raw error-code format章节；R09保持现有 prefix/message、exit和用户工作流 |
| `dayu/README.md` | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | no update：分层、装配和总揽 direct boundary不变 |
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` | implementation 后必须按代码真源更新 concrete validator、唯一 owner与 event-after contract |
| `dayu/service/README.md` | `8d7d7680e82642a769da9a3acc28ea429f8ff32550dff732e6a0478c7aabb2d5` | implementation 后必须删除 Service-owned terminal checker叙述 |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` | implementation 后必须迁移 owner/consumer test叙述 |

本 plan-fix gate 按用户边界不修改任何 README。

### 5.2 Security / coverage

- direct event safe-text/leakage guard、operation-scoped cancellation、consumer-close cancellation state、queue backpressure、late publication、storage containment/symlink、R06 transaction、Host/ToolRuntime authorization 与 process fencing全部保持。
- CLI 不展示 raw enum、不解析 message、不回显 provider payload/path/ticker/document id/raw exception text。
- 完整 changed production file 单文件 coverage `>=80.00%`、full pyright `0 errors`、scoped Ruff、R06/R08/full Fins/no-regression与真实 smoke gate均未降低；`DS-N03` 没有被解释为 waiver。

### 5.3 Deferred scope

- 未实施 Topic 8/9、R10-R12、Issues 142/151/175/177/178、Web/WeChat/render、process isolation、线程强杀、Host wait/schema/tool authorization redesign。
- 未新增 compatibility、factory、wrapper、fallback、loose iterator typing、`hasattr/getattr` close probing、第二 validator或 speculative public error class。

## 6. Validation

- original plan SHA/line lock：PASS。
- Controller/DS/MiMo source locks：PASS。
- fixed plan SHA/line count：PASS（`a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`，773 行）。
- forbidden producer-path / old CLI-code test residual scan：PASS。
- README fresh SHA/content scan：PASS；本轮 README 零修改。
- `git diff --check`：PASS。
- untracked plan/artifact whitespace check（`git diff --no-index --check /dev/null <path>`）：PASS。
- staged tree：empty；未 stage/commit。
- pytest / pyright / coverage / smoke：未运行；本 gate 只修改 plan 文档且 implementation 明确未授权，运行 implementation validation 不会为本次文档修订增加有效证据。

Final gate state：`R09 plan fix complete / IMPLEMENTATION_NOT_AUTHORIZED / AWAITING_DUAL_FULL_PLAN_REREVIEW`。
