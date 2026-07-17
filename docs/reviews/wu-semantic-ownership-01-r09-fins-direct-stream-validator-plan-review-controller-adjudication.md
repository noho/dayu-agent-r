# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Review Controller Adjudication

## 0. Identity and gate

- Umbrella work unit: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU: `R09 — Fins direct-stream terminal validator`.
- Review target: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`.
- Immutable target SHA-256: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`.
- AgentMiMo artifact: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-mimo.md`, SHA-256 `d220c1dd7637d560c835f059841c7effaafe1027b3deb7fe5b1e0919a80b57ac`.
- AgentDS artifact: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-ds.md`, SHA-256 `0434e4766729d2d85c1ade31c767a88ffd47781e7b49b4b734d86ae8a0a53ad9`.
- Controller decision: `PLAN_FIX_REQUIRED / IMPLEMENTATION_NOT_AUTHORIZED`.

两路 review 都命中同一 immutable plan。reviewer 的 PASS 只表示没有要求重新做产品裁决的 blocker，不会跳过“全部 accepted finding 必须先修复并双路完整 re-review”的 umbrella gate。

## 1. Direct-evidence corrections

### 1.1 API shape

当前 `FinsIngestionRuntime.download/preprocess/upload` 是包含 `yield` 的 async-generator 方法；移除外层 yield wrapper 后，正确接口是 plain `def -> ValidatedFinsEventStream`。当前 Service protocol/public methods 已是 plain `def` 并直接返回 runtime stream，因此它们保持 plain `def`，只收窄返回类型；CLI 不新增 `await`。

### 1.2 Producer protocol-error channel

当前 source scan 只在 consumer-side runtime、Service 和 CLI checker 中发现 `FinsDirectStreamProtocolError` 构造；producer callees 没有该异常 origin。validator 位于 raw queue bridge 的 consumer side，未来也应是 missing/duplicate/event-after 三种协议错误的唯一构造 owner。计划中的 producer typed-error queue variant、catch 和 identity test 是没有当前数据流来源的 speculative dead path，必须删除；不能以“防御性”名义保留。

### 1.3 CLI presentation and README

Topic 6 只要求上层机械消费 typed success/error 并映射 presentation，没有要求把内部 enum literal 作为新的公共错误码格式展示。当前 CLI 已有用户可读 prefix/message 和 exit 1；增加 `[{exc.reason.value}]` 会扩大公共格式但没有产品依据。根 README 当前也没有 Fins direct protocol error-code 格式章节。最小正确修复是保持现有用户可读格式与 exit mapping，只删除上层协议判定；typed reason 继续作为 Fins owner contract 和测试事实，不泄漏为新的 CLI public code。

## 2. AgentMiMo finding dispositions

| Finding | Controller disposition | Reason / required action |
|---|---|---|
| `F-CANDIDATE-01` | `accepted` -> `R09-PR-F01` | 必须列出 runtime `async def` async-generator 到 plain `def` 的精确 cutover，并明确 Service/CLI 保持 plain `def`、无新增 `await`。 |
| `F-CANDIDATE-02` | `accepted` -> `R09-PR-F02` | close failure 与已有 semantic error 的优先级、identity、chaining 和幂等 close 必须成为唯一 contract。 |
| `F-CANDIDATE-03` | `rejected-with-reason` | 首个 RESULT 只有在 clean EOF 后才 yield；yield 后 raw source 已经证明结束，不存在同一 upstream 再产生 error 的路径。无需新增状态或兼容分支。 |
| `F-CANDIDATE-04` | `accepted` -> `R09-PR-F03` | direct source scan 证明 producer channel 没有 origin；删除 speculative queue/catch/test。 |

## 3. AgentDS finding and note dispositions

| Finding / note | Controller disposition | Reason / required action |
|---|---|---|
| `DS-F01` | `accepted` -> `R09-PR-F01` | 接受签名精确度问题；正确修复是 runtime 改 plain `def`，Service/CLI 不改为 coroutine。 |
| `DS-F02` | `accepted` -> `R09-PR-F02` | 接受 precedence/idempotence 缺口；不接受“close error 丢弃 protocol error”的建议。已有 upstream/typed protocol semantic error 必须保持 primary。 |
| `DS-F03` | `rejected-as-proposed`; underlying plan defect accepted -> `R09-PR-F03` | DS 建议精化 producer typed-error channel，但当前不存在 producer-side origin，其 hypothetical call path 与真实线程/调用栈矛盾。正确修复是删除该 channel。 |
| `DS-F04` | `accepted` -> `R09-PR-F04` | `terminal_result` 提前读取必须有确定的 Fins-owned programmer-contract error 与 owner test。 |
| `DS-F05` | `accepted` -> `R09-PR-F05` | 接受计划存在无依据的 CLI public format 变化；正确修复是撤销 raw enum 展示并记录 README no-update scan，不是为无需求的新格式扩写 README。 |
| `DS-N01` | `rejected-with-reason` | 不需要拆出 `CLOSED_CLEAN/CLOSED_ABORTED` 新状态。clean availability 由 terminal-result availability flag/guard 唯一表达；`R09-PR-F04` 会固定提前读取行为。 |
| `DS-N02` | `accepted` -> `R09-PR-F06` | 增加 operation-kind provenance/identity 测试，证明删除 Service checker 后仍以 Fins validator 输入为唯一来源。 |
| `DS-N03` | `accepted-risk-with-current-owner` | 不降低 `>=80%` changed-file coverage。implementation entry 先测 fresh baseline，最终仍须满足完整单文件目标；若真实 baseline 阻塞则 stop 回 Controller，不得以 partial coverage、无关代码或豁免绕过。 |

## 4. Controller accepted plan-fix ledger

### R09-PR-F01 — exact signature and call-site cutover

计划必须为 runtime、Service protocol、Service public methods、CLI opener/consumer 给出 exact old/new signature table：

- runtime `download/preprocess/upload`: `async def ... -> AsyncIterator[FinsEvent]` with yield -> plain `def ... -> ValidatedFinsEventStream`;
- raw queue bridge 保持 async generator，并作为 validator 的 concrete source；
- Service protocol/public methods 保持 plain `def`，返回类型收窄并直接透传；
- CLI helper 接收/返回 concrete stream，调用链不新增 `await`。

### R09-PR-F02 — error/close precedence and idempotence

计划必须固定以下 contract 并加入 owner tests：

- upstream exception/cancellation object identity 或 duplicate/event-after typed protocol error 是 primary semantic error；
- cleanup `aclose()` failure 通过 exception chaining/context 保留，但不得覆盖 primary error 的 type、object、reason、message 或 CLI exit mapping；
- 没有 pre-existing semantic error 的显式 consumer `aclose()` failure 原样传播；
- raw source 至多实际 close 一次，后续 `aclose()` 不再次调用底层 close；
- 覆盖 close success/failure、duplicate/event-after、upstream error/cancel、object identity 和 repeated close。

### R09-PR-F03 — remove speculative producer protocol-error path

从 root-cause、state-machine invariant、production change list、queue union、test nodes、scans 和 residual 中删除 producer protocol-error typed queue variant/catch/test。保留既有 generic producer exception -> bounded business failure RESULT；raw bridge 自身的 native async error/cancel 原样自然传播。validator 继续是三种 direct-stream protocol error 的唯一构造 owner。

### R09-PR-F04 — terminal-result availability contract

提前读取 `terminal_result` 是调用方 programmer-contract violation，不是 missing/duplicate/event-after stream protocol error。使用普通 `RuntimeError` 和 module-owned constant safe message；不新增 speculative public error class。加入 OPEN、RESULT_BUFFERED/abortive close 与 clean exhaustion 后 object-identity tests。

### R09-PR-F05 — retain existing CLI public presentation

删除计划中的 raw `reason.value` 用户展示和对应 CLI assertion。CLI catch 同一个 owner error，只沿用现有用户可读 prefix/message 与 `EXIT_FAILURE=1`，不解析 message、不枚举 reason、不重建 error。计划记录根 README/目标 README 的 fresh scan 和 no-update 理由；若最终代码改变已有 README 职责内 contract，再按触发规则更新。

### R09-PR-F06 — operation-kind provenance propagation

测试必须证明 error 的 `operation_kind`、reason、message/object 均来自 Fins validator 的输入和同一异常对象；Service 不以 command 名重算/替换，CLI 只 presentation，不取得 semantic ownership。至少覆盖 Service `process_filing/material` 名称与 runtime `PREPROCESS` owner 值不同的反例。

## 5. Non-findings, retained scope and security

- `R09-PR-F01..F06` 全部属于 R09 plan fix；任何 severity 的 accepted finding 都不能延期。
- `DS-N03` 不是 coverage waiver；完整目标保持不变。
- 不实施 Issue 175 的 process isolation，不实施 R10-R12，不提前实现 Topic 8/9 或统一 tool authorization framework。
- operation-scoped cancellation、consumer-close cancellation state、queue backpressure、late publication 防线、storage contract 和既有 bounded generic failure mapping均保留。
- 不引入 compatibility wrapper、factory、fallback、loose async iterator typing、`hasattr/getattr` close probing或第二套 validator。

## 6. Next gate

1. AgentCodex 只修改 R09 plan，关闭 `R09-PR-F01..F06`，并写 plan-fix artifact。
2. Controller 完整读取 fixed plan 和 artifact，核对 immutable source locks、scope、tests、README/security/deferred boundaries。
3. AgentMiMo / AgentDS 对新的 immutable plan 并发进行完整 re-review。
4. 只有 Controller 裁决所有 accepted finding 关闭后，才允许 exact-scope accepted-plan local commit；implementation 目前未授权。

Final gate state: `R09 plan fix / IMPLEMENTATION_NOT_AUTHORIZED`.
