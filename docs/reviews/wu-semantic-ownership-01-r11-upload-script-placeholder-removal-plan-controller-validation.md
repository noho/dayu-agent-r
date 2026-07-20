# WU-SEMANTIC-OWNERSHIP-01 / R11 independent plan Controller validation

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：`R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除`；
  不是新 WU、issue 或 feature。
- validated artifact：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`。
- artifact lock：711 lines / 52,389 bytes；SHA-256
  `c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5`。
- baseline：branch `phaseflow/host-issues-control`；HEAD
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`；staged tree empty。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW`。

本 verdict 只授权 AgentMiMo / AgentDS 对 immutable plan 做并发完整 plan review；不接受 plan，
不授权 implementation、stage/commit、R12、push 或 PR。

## 2. 第一性原理与 owner 核对

动机成立且 production-high 评级准确。CURRENT Fins batch owner 仍未产生完整 OLD-aligned domain
facts，CLI 仍发布无消费者的 JSON argv protocol，current direct runtime `auto` contract 与 CLI grammar
不一致，placeholder scripts/packages/dependencies/README 仍把未实现 capability 作为 public surface。
这些都是 owner/public-contract 偏差，不是测试或文档表面问题。

Plan 把财期、material routing、priority、dedup、caps、skip reason 唯一放在
`dayu.fins.upload_batch`；CLI 只拥有 input normalization、一次可选 FMP resolve、current grammar argv
builder、single platform renderer/publisher 与 human summary；packaging 只发布真实能力。没有在 Service、
renderer、README 或 fixture 重算 Fins facts，owner 正确。

## 3. 三个 slice 与依赖闭环核对

Plan 恰好给出三个 dependency-ordered slices：

1. R11-S1 只修改 Fins batch owner 与 owner tests，产出严格 typed recognized/material/skipped plan，
   固定 annual=5、periodic latest-year/max6、presentation=6、call=filtered filing count、financial
   statements uncapped，以及 same-period priority-before-caps。
2. R11-S2 消费 typed plan，修正三个 action grammar/default、ticker CSV、single FMP resolve、metadata
   projection，并在单一 renderer/publisher 实现 POSIX/Windows output、quoting、containment、symlink、
   atomic replace、summary 与 JSON protocol 删除。
3. R11-S3 删除 placeholder packaging/public surface，更新四个职责匹配的 README，建立唯一最小
   `windows-latest` workflow，并用 wheel metadata/archive/importability 证明发布面闭合。

每个 slice 只有 Controller cumulative checkpoint；三个 slice 后才对完整 diff 执行双 code review、
fix、双 re-review 和单一 accepted implementation commit。这符合 umbrella optimization control，
没有把 implementation slice 伪造成新 WU 或增加旁路 acceptance。

## 4. Contract 与安全核对

- Fins typed request/filing/material/skipped/plan 不含 executable、argv、shell、JSON schema 或 raw bag；
  CLI renderer 不解析 filename/fiscal/material facts。
- action `auto|create|update` 是 batch contract；direct filing/material 保留显式 delete，但默认改为
  `auto`；generated auto command 省略 `--action`，不生成 delete。
- canonical-first ticker CSV、explicit-first alias merge、company precedence、resolver canonical mismatch、
  provider failure 与 zero/once FMP access 均有明确 owner/test；API key 不进入 script/summary/artifact。
- default output 使用 workspace root 与平台后缀；existing directory 与 exact explicit file path 分开；
  output containment、任一级 symlink rejection、same-directory private temp、fsync/replace、failure cleanup
  与 old-target preservation 都由 publisher 单一拥有。
- POSIX 使用 `shlex` 与真实 `/bin/sh` recorder；Windows 以 element-for-element argv outcome 为准，覆盖
  `% ! & | ^ ( )`、quotes、backslashes、Unicode、empty/appended args 和 injection marker，明确禁止
  `list2cmdline`、fallback、双算法与 test shim。
- source/output containment、symlink、atomic write、argv injection 与 secret non-persistence 被保留或加强；
  plan 没有误实现或声称统一 tool authorization framework。

## 5. Windows 与 packaging release gate 核对

Controller 接受 `.github/workflows/r11-upload-script-windows.yml` 进入 closed allowlist，因为直接调查
确认 current tree、default branch 与 repository Actions API 均无 workflow/run。Workflow 被限制为
Python 3.11、`windows-latest`、read-only permission、manual/precise path trigger、real `cmd.exe /d /c`
recorder、real CLI/temp-storage smoke 与 always-uploaded non-secret artifacts；不引入 provider、deployment、
release 或 unrelated matrix。

本地 accepted implementation/completion 可将 Windows 标为 `PENDING_RELEASE_BLOCKER`，但不能写 closed
或 residual。真实 run 必须对应含 workflow/implementation 的 tree；skip/cancel/failure/missing artifact/
oracle mismatch 都阻止 umbrella aggregate acceptance、PR ready 与 final closeout，并回到 R11 owner fix/review。

删除范围精确覆盖三个 placeholder scripts、六个 placeholder package files、`web` extra/requirements
消费、`dayu.render` package-data 和 stale README claims；constraints inert pins 保持 no-touch。Plan 正确保留
`tests/tools/web` 中禁止旧 `dayu.web` import 的两个负向 boundary sentinels，没有用全仓裸 grep 误删真实
Web tools 防御测试。

## 6. Validation 与 scope 核对

Plan 要求 S1 real filesystem、S2 real `/bin/sh` recorder + real CLI/Service/Fins temp-storage、S3 wheel
metadata/archive/isolation，以及 release-blocking real Windows recorder/CLI evidence。Focused/full-related/full
tests、每个 changed production Python file line coverage `>=80%`、full pyright、scoped/full-baseline Ruff、
diffcheck、README trigger、schema/placeholder/danger/secret/deferred scans均给出 exact commands/oracles。

Closed allowlist 包含四个 production Python owner、packaging/requirements、一个最小 workflow、六个删除
文件、五个 tests 与四个 README；Service/Host/Engine/runtime/config/tool/ui/design/constraints/control 都是
no-touch。Issue 142、151、175、177、178、R12、真实 Web/WeChat/render、Topic 8/9 与 unified auth 没有
进入 implementation。

## 7. 双路 review 必须重点挑战

双路 review 仍须独立挑战以下高风险点；这些不是预置 finding：

1. Fins structured auto-recursion、财期/priority/caps/material rules 是否完全同源且不会从 mtime、sibling、
   renderer 或 fixture 猜事实；call cap 是否确实基于过滤后的 recognized filings。
2. current CLI grammar 与 generated argv 的全字段位置/omission 是否精确，`auto`、canonical/aliases、explicit
   vs inferred metadata 与 single FMP resolve 是否会泄漏第二 owner 或 secret。
3. explicit output、workspace containment、symlink、atomic replace 与 interruption cleanup 是否有可实现且不越界
   的单一 publisher contract。
4. arbitrary Windows fixed/appended argv 是否真的可由单一 batch renderer 在真实 `cmd.exe` 下恢复，workflow
   oracle/artifact 是否足以反证 `%`、`!`、metacharacter、quotes/backslashes 与 injection failures。
5. placeholder dependency/package/entrypoint/README 删除是否会误删真实 `dayu.tools.web` 能力，wheel scan 与
   negative sentinels 是否既完整又不过宽。
6. 三 slice checkpoint、aggregate review/commit、Windows pending-release-blocker 与 no-push local gate 是否
   符合 umbrella state machine，是否存在提前 closure 或 deferred scope 偷带。

## 8. Gate state

- current accepted/open plan finding：0（review 尚未执行）。
- blocker：0。
- staged tree：empty。
- next gate：AgentMiMo / AgentDS 并发完整 plan review。
- implementation、commit、R12、push/PR：未授权。
