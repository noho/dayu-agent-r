# WU-SEMANTIC-OWNERSHIP-01 / R10 plan-review fix Controller validation

## 1. Verdict 与 locks

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：R10；不是新 WU、issue 或 feature。
- fixed plan：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`，698 lines，
  SHA-256 `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a`。
- AgentCodex fix artifact：
  `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-fix-codex.md`，120 lines，
  SHA-256 `02db30f1d365efd76917b3326893c2e7c58e27c99cb0a63ae8b695f6edb0ffe8`。
- baseline HEAD：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`；staged tree empty。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REREVIEW`。

本 verdict 只确认两个 accepted plan finding 已在计划中闭合；不接受 plan、不授权 implementation/commit/R11/R12。

## 2. Scope 与 source-drift validation

Controller 完整读取 fixed plan 与 fix artifact，并重算所有 implementation input locks。以下 production/test/README
SHA 与 pre-fix plan 完全一致：

| Source group | Result |
|---|---|
| HKEX owner + owner tests | exact / no drift |
| shared protocol/workflow + workflow tests | exact / no drift |
| CNInfo implementation + tests | exact / no drift |
| pipeline/runtime test doubles | exact / no drift |
| `dayu/fins/README.md` + `tests/README.md` | exact / no drift |

本 gate 的 Agent 修改仅是 fixed plan 与 fix artifact。Controller-owned control transition、既有 entry/validation/review/
adjudication artifacts 均保持其 owner；`git diff --cached --name-only` 为空，`git diff --check` 通过。

## 3. `R10-PR-F01` closure

状态：`FIXED / CONTROLLER-VALIDATED`。

Fixed plan 已把 cancellation 事实拆成唯一 owner 与纯运输：

1. raw `Callable[[], bool] | None` 只由 workflow 既有 `_raise_if_cancelled` 解释；
2. workflow 用 `functools.partial(_raise_if_cancelled, module=..., ticker=..., document_id="",
   cancel_checker=...)` 构造一个 no-arg `Callable[[], None]`；不新增 helper、framework 或 ambient state；
3. shared protocol 只运输 `cancellation_checkpoint: Callable[[], None] | None`；provider 只调用，不能读取返回值、
   解释 bool、复制 workflow helper 或按异常消息分支；
4. HKEX 每个 cumulative GET 前和成功响应后调用 checkpoint；response 后 checkpoint 位于 strict parse 前；
5. HKEX `list_report_candidates` 先让 `CnDownloadCancelledError` 与
   `HkexnewsProviderProtocolError` 原样通过，再处理 generic RuntimeError；caller cancel object identity 与 provider
   protocol type/cause 不被抹平；
6. raw checker 非取消 failure 由 workflow 包装并保留 direct cause；如再经 HKEX provider-context wrapper，测试断言
   exact 两层 cause chain，不增兼容 exception 或字符串识别。

这解决了原 plan 让 downloader 自行解释 raw bool/cancel/failure 的多 owner 缺口，同时保持 sync provider 内每轮
取消可观察。`cn_download_models.py` 不需要改动，exact allowlist 没有扩张。

## 4. `R10-PR-F03` closure

状态：`FIXED / CONTROLLER-VALIDATED`。

Fixed plan 已把请求粒度唯一化：

- HKEX 一轮 complete exact trace：`CP1, GET(100), CP2`；多轮在每个 GET 两侧延续同一 checkpoint identity；
- CNInfo 两个 supported periods exact trace：
  `CP1, POST(period_1), CP2, CP3, POST(period_2), CP4`；不是仅方法入口/出口；
- checkpoint 抛出后不得 strict-parse/save partial rows、发下一 request、进入下一 language/category、selection 或 HEAD；
- CNInfo checkpoint 位于现有 period transport wrapper 之外，或 typed cancel 在 generic wrapper 前 passthrough；
- workflow 原有 discovery 方法前/后检查保留；query、period iteration、pagination、selection、retry 和业务错误语义
  不变。

Owner test matrix新增/收紧了正常 checkpoint、workflow bool mapping、caller typed cancel identity、四个 HKEX cancel
时点、non-cancel cause chain、HKEX exception precedence、CNInfo normal/response-cancel/before-next 序列、test-double
identity/propagation 与 partial zero-publication。

## 5. Rejected F02 与 forbidden scope

Fixed plan 保留四个 changed production files 各自 branch coverage `>=80%`，并记录 Controller baseline pre-check：

```text
dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%
```

没有 N/A waiver、omit、pragma、padding 或 coverage compatibility。Plan 同时明确禁止 speculative range
watchdog/warning/threshold、hard cap、date recursion、append/dedup、generic pagination/cancellation framework、旧
exception compatibility、Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9 与统一 authorization。

## 6. Plan completeness validation

Controller 复核以下 sections 已同步且相互一致：gate/authority/source locks、goal/success/non-goals、owner map、exact
allowlist、strict provider model/parser、typed error precedence、cumulative state machine、cancellation seam、single-slice
steps、owner tests、fixture/live smoke、focused/full/coverage/type/lint/diff/scans、README/security、stop conditions、handoff、
completion report 与 checklist。

没有发现新的 plan finding。尤其：

- requested range 的客户端增长不算 provider progress；连续 continuation 只接受严格 loaded/rows 增长；
- 最新自洽 terminal snapshot 先于历史 progress 比较；不要求跨轮 prefix identity；
- final-only rows replacement、query invariance、recordCnt growth、per-language isolation 和 exact official types 保持；
- direct checkpoint callback 有同步 provider 内无法直接观察 workflow state 的充分理由，且没有扩成 callback/factory
  abstraction。

## 7. Gate state

- `R10-PR-F01`：fixed-and-controller-validated。
- `R10-PR-F03`：fixed-and-controller-validated。
- `DS-R10-F02`：rejected-with-reason，zero waiver 保留。
- current accepted/open plan finding：0（等待双路完整 fixed-plan re-review 发现新问题的可能）。
- blocker：0。
- next gate：AgentMiMo / AgentDS 并发完整 fixed-plan re-review。
- plan acceptance / implementation / commit / R11 / R12：未授权。
