# WU-SEMANTIC-OWNERSHIP-01 / R10 dual plan review Controller adjudication

## 1. Immutable review target

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- sub-WU：内部 R10，不是新 WU、issue 或 feature。
- reviewed plan：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`。
- target lock：605 lines；SHA-256
  `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699`。
- baseline HEAD：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`。
- AgentMiMo artifact：166 lines；SHA-256
  `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16`；verdict `PASS`；finding 0。
- AgentDS artifact：338 lines；SHA-256
  `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce`；verdict
  `pass-with-risks`；candidate finding 3。

两路都核对了相同 target/HEAD，并确认 owner、official protocol、finite progress、strict parser、final-only
snapshot、allowlist、单 slice、安全与 deferred 边界总体成立。Reviewer verdict 不独立授权 plan acceptance 或
implementation。

## 2. Finding adjudication

### R10-PR-F01 — ACCEPTED（合并 DS-R10-F01 根因）

**事实**：plan 要求把原始 `Callable[[], bool] | None` 传给 provider，再由 HKEX/CNInfo 各自解释 bool、主动抛出的
typed cancel 和非取消异常。当前唯一一致解释 owner 是 workflow-private `_is_cancel_requested` /
`_raise_if_cancelled`；让 downloader 反向 import workflow helper、复制解释逻辑或自行发明 error policy 都不符合
owner/依赖/去重约束。

**Controller 修正后的 accepted fix**：不接受 DS 建议的 provider-local duplicate helper，也不新增 shared
cancellation framework/module。Plan 必须把 direct seam 改为 workflow-owned、显式
`cancellation_checkpoint: Callable[[], None] | None`：

1. workflow 使用现有 `_raise_if_cancelled` 语义构造一个 no-arg checkpoint，并通过 shared discovery protocol
   原样运输；它统一拥有 bool true、checker 主动抛 `CnDownloadCancelledError`、非取消异常包装及业务可读消息；
2. downloader 只在每个实际 provider I/O 前后调用 checkpoint；返回即继续，抛出即原样传播，不解释原始 bool，
   不复制 workflow helper；
3. HKEX `list_report_candidates` 必须让 `CnDownloadCancelledError` 在 generic RuntimeError wrapper 之前原样通过，
   与 `HkexnewsProviderProtocolError` 的 typed passthrough 并列；
4. tests 必须分别证明 checkpoint 正常返回、bool-true 经 workflow owner 变为 typed cancel、checker 主动抛出的同一
   cancel 对象 identity 保留、非取消异常保留 cause；partial rows/candidates/HEAD 均不发布。

该改法保留“workflow 产生并拥有 operation cancellation 语义、protocol 只运输、provider 在 I/O 边界消费”的
owner map，也避免 callback/factory 泛化：这里的 callback 只用于同步 provider 内部无法直接观察 workflow 状态的
必要 checkpoint。

### R10-PR-F02 — REJECTED-WITH-REASON（DS-R10-F02）

Controller 在当前 baseline 用 plan 的 focused test set实际执行 branch coverage pre-check：

```text
dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%
```

因此“纯 Protocol 可能 N/A、需要 coverage waiver”不成立。逐文件 `>=80%` 是用户与 AGENTS.md 的硬 gate；不得
在 plan 中预设 N/A 例外，也不得添加 padding。保留原命令和零 waiver。

### R10-PR-F03 — ACCEPTED（合并 DS-R10-F03 歧义；修复方向纠正）

**事实**：CNInfo 的一次 `list_report_candidates` 会按 fiscal period 发多个真实 HTTP 请求；plan 的“既有单轮
discovery I/O 前后”表述既可被理解成方法入口/出口，也可被理解成每个 period I/O 前后，无法生成唯一实现。

**Controller 修正后的 accepted fix**：不接受 DS 建议的“仅方法入口+出口两次”。取消是 operation-level 横切真源，
而 direct provider I/O 是实际不可中断边界；只在整个多请求方法入口/出口检查会重现本 seam 要关闭的长窗口。
Plan 必须明确：

- HKEX：每个 cumulative GET 前、响应返回后各调用一次同一 checkpoint；
- CNInfo：每个既有 period POST 前、响应返回后各调用一次同一 checkpoint；
- workflow 原有 discovery 方法前后检查保留；provider 不改变 query、period iteration、pagination、selection、HTTP
  retry 或业务错误语义，只提高既有 cancellation 在真实 I/O 边界的可观察性；
- tests 按请求序列断言 checkpoint 的 ordering/次数，并证明任一响应后取消都不会发下一 provider request。

这不是 CNInfo pagination redesign，而是被 shared direct seam 触达的同一 cancellation transport contract。

## 3. Rejected observations / no-current-fix

- AgentDS §6.2 提及未来可加 `range > 10000` watchdog/warning。当前没有设计真源或 provider evidence 支撑该阈值，
  且用户明确禁止 hard cap/推测性限制；不进入 plan 或 implementation。
- AgentDS 关于 live `>100` query 可能难选的 Q2 已由 plan §9.3/§12 分流：endpoint 不可达记录限制；可达却
  cap/clamp/stall 则 stop；local fixture gate不可豁免。无需新增 fallback。
- AgentDS 把 Controller validation 写为 105 lines，而 locked artifact 当前为 104 lines；其引用内容和 verdict
  正确，该 artifact-only计数误差不影响 review 结论，不要求改 reviewer artifact。

## 4. Required plan-only fix

AgentCodex 只允许修改：

- `docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
- 新增 `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-fix-codex.md`

必须完整修复 `R10-PR-F01`、`R10-PR-F03`，并同步 plan 的 owner map、allowlist说明、protocol signature、state
machine、exception precedence、test matrix、coverage/validation commands、completion report 和 checklist。不得修改
代码、测试、README、design、control、Controller/reviewer artifacts；不得把 rejected F02 waiver 或 speculative
watchdog 带入；不得 stage/commit/push/PR/implementation/R11/R12。

修复后必须报告：fixed plan 行数/SHA、plan-only diff、两个 finding closure matrix、F02 zero-waiver 保留、target
source locks/staged-empty/`git diff --check`。Controller 完整验证后必须进行 AgentMiMo / AgentDS 双路完整 fixed-plan
re-review；不能因 MiMo 初轮 PASS 跳过。

## 5. Gate state

- accepted plan findings：2（`R10-PR-F01`、`R10-PR-F03`）。
- rejected-with-reason：1（`DS-R10-F02`）+ 3 non-finding observations。
- blocker：0。
- current gate：AgentCodex plan-only fix。
- plan acceptance / implementation / commit / R11 / R12：未授权。
