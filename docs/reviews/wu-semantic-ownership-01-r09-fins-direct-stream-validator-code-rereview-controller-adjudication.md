# WU-SEMANTIC-OWNERSHIP-01 / R09 cumulative code re-review Controller adjudication

## 1. Decision

R09 完整 cumulative code re-review 已完成，但尚未接受实现。

- AgentMiMo：`PASS / 1 low-severity finding`；
- AgentDS：`PASS / 0 new material finding`；
- Controller：接受一个收窄后的 README finding `R09-RR-F01`；
- current ledger：`1 accepted / 0 rejected material finding / 0 deferred / 0 blocker`。

下一 gate 仅为 AgentCodex 对 `R09-RR-F01` 做 README-only fix、Controller validation 与双路完整
re-review；不授权 aggregate deepreview、commit、R10、push、PR 或 umbrella closeout。

R09 仍是 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU，不是新 WU、
feature/issue 或重开旧 sub-WU。

## 2. Reviewed target and artifacts

- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`；
- sorted 12-path manifest：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`；
- canonical cumulative binary diff：
  `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d`；
- AgentCodex fix artifact：271 lines，SHA-256
  `c9affe9935d2825284c10bcccd61169c3836cb5076d13de90bb517787e8c85d7`；
- Controller fix validation：141 lines，SHA-256
  `5a6a12c5fc4679de26bc841402fe93d91847fd9015a2c9e54266d04dd8ebfd5b`；
- AgentMiMo re-review：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-mimo.md`，
  194 lines，SHA-256 `4f6e7bc6fac47c3d6c3c864c5cca9e778986361dc0b60e78587ae2d9b9262823`；
- AgentDS re-review：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-ds.md`，
  605 lines，SHA-256 `43dd3a937faa36f7dce9600619615f3efb67897c75ab4df2f9e5a86f6c189b52`；
- staged tree：empty。

两路 artifact 最初各有 self-referential artifact hash/line evidence defect；Controller 在同一 reviewer
task 内要求删除不可能内嵌的 self hash，并纠正 MiMo 的 manifest/diff 计算口径与错误 drift 结论。
上述最终 lines/SHA 是写入完成后由 Controller 外部重算的 immutable review evidence。

## 3. Original finding closure

两路 reviewer 均独立确认：

| Finding | Status |
|---|---|
| `R09-CR-F01` CLI creator deterministic close / primary-cause ownership | closed |
| `R09-CR-F02` false concrete AsyncGenerator cast / fake seam | closed |
| `R09-CR-F03` real generator finally/cancellation causal coverage | closed |
| `R09-CR-F04` stale exact Fins signatures | closed |
| Controller F01 follow-up self-cause/context gap | closed under `R09-CR-F01` |
| DS former F05 observation | remains rejected / no current fix |

两路对 exactly-one-and-last state machine、consumer-body error、external cancellation、SIGINT、
completed-child race、primary/cause/context identity、real AsyncGenerator、runtime raw bridge、
signature/provenance/identity、CLI presentation、security/no-touch/deferred scope 均未提出新的 code defect。

## 4. Accepted finding

### `R09-RR-F01` — LOW — Fins main-component map omits the two R09 stable owner modules

**Source**：AgentMiMo finding 01。

**Direct evidence**：`dayu/fins/README.md` 的“Agent更新约束”允许记录当前已实现的 package stable
boundary 与主要组件；其 `dayu.fins` component tree 目前列出 `ingestion_runtime.py`、
`service_runtime.py` 与 `ticker_normalization.py`，但没有列出 R09 直接建立的两个稳定 owner：

- `direct_events.py`：direct event、typed protocol error 与 result contract owner；
- `direct_stream.py`：`ValidatedFinsEventStream` exactly-one-and-last validator owner。

README 其它章节已经把 direct event contract 与 validator 作为稳定边界承诺，因此 component map 的遗漏
与同一文档的当前架构说明不一致。该 finding 动机成立，但原建议必须收窄，避免把 component tree 扩成
所有顶层文件的流水账。

**Accepted minimal fix**：仅在现有 component tree 的合适位置新增上述两个模块及一句中文 owner 职责；
不得列全 `_log.py`、converter、upload batch 等所有 helper，不得改 direct contract、product code、tests、
其它 README、设计真源或 deferred scope。

**Owner boundary**：`dayu/fins/README.md` 当前 package architecture / main-component projection。

**Validation**：README 约束复核、精确两模块/owner 文本扫描、12-path relock、`git diff --check`、
staged-empty；同时重跑 R09 affected aggregate、full pyright 与 scoped Ruff，证明 README-only fix 未伴随
product/test drift。既有 R06/R08/full Fins/coverage/security/real-smoke 证据继续由不变的 product/test
content hashes承接；若任一 product/test hash 漂移，必须触发完整 validation stop。

## 5. Other reviewer observations

- MiMo 的 bare `assert result is not None` note 不是 finding：`FinsEvent` typed invariant 在 owner constructor
  已验证 RESULT 必有 result；当前没有可执行错误业务结果反例，不授权改 validator。
- DS 关于 child `BaseException`、implicit validator→CLI contract 与 Issue 175 physical isolation 的记录均为
  no-current-fix observation / residual；没有当前 defect 或本 gate 授权。
- Issue 175 继续拥有 physical process isolation；Issues 142/151/177/178、R10-R12、Topic 8/9、统一
  authorization、Web/WeChat/render 均未进入本 fix。

## 6. Fix authorization

AgentCodex 只可修改：

1. `dayu/fins/README.md`；
2. 新增自己的 fix evidence：
   `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-codex.md`。

不得修改 product Python、tests、其它 README、control、plan、design、prior review/adjudication/validation
artifact；不得 stage、commit、push、建 PR。修复后必须报告 README final hash/lines、12-path manifest、
canonical cumulative diff、全部 11 个不变 target content hashes、finding closure、validation 与 staged-empty。

完成后由 Controller relock，再由 AgentMiMo / AgentDS 对完整新 12-path target 做双路 complete re-review。
