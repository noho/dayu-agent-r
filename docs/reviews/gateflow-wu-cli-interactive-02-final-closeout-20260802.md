# wu-cli-interactive-02 final closeout

## Closeout status

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Design truth：`docs/host/design.md`、`docs/engine/design.md`
- Draft PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)
- Branch：`codex/interactive-oracle`
- Base：`main`
- Accepted code/review head：`96a1a89283aef857aafaa49fa4730eaf3eee8128`
- Verdict：`FINAL CLOSEOUT PASS`
- Issue：无；本 work unit 未创建 issue，也不需要 issue closeout comment

## What changed

### S1 — F01–F04

- 从 prompt/interactive help、parser、typed args、implementation、registry 与用户文档彻底
  删除 `--config`；从 interactive 同样彻底删除 `--ticker`，没有 hidden alias、wrapper 或
  legacy branch。
- prompt/interactive label alias 统一由 CLI session identity owner 解析到相同 durable
  Session；prompt 无 label 保持 one-shot，interactive 无 label 每次 fresh Session，不读取旧
  namespace。
- registry 删除依赖 removed option 的错误 invocation/claim，保留 prompt→prompt，并补齐
  prompt↔interactive 双向 continuity 的正确 owner evidence 边界。

### S2 — F05–F09

- composer 按 terminal capability 精确区分 Shift+Enter/Ctrl+J newline、普通 Enter submit，
  完整解析 ESC-prefixed CSI/Alt/bracketed-paste sequence。
- non-TTY 改为首 byte 到真实 EOF 的单一 whole-stdin draft，规范化 CRLF/CR，空白 exit 0，
  literal `0x04` 保留为数据，非法 UTF-8 返回稳定脱敏错误且只执行一轮。
- Escape 与 Ctrl+C 生命周期跨 acceptance barrier 等待 Host canonical terminal；双 Ctrl+C 只
  登记 exit-after-cancel，清理后 exit 130，不取消 canonical waiter。
- active Run 期间 draft/type-ahead 保留；Enter 只提交一个 QUEUE follow-up，terminal 后恰好
  执行一次，不隐式 STEER。

### S3 — F10

- Host attachment recovery owner 在 fresh READ_WRITE immediate reconnect 时安排 bounded
  delayed rescan；positive orphan proof 后按
  `ATTEMPT_LOST -> RUN_RECOVERING -> RUN_STARTED(start_reason=recovery)` 创建新 Attempt 与
  execution id，不让 CLI 重发文本、篡改 SQLite、take over 旧 Attempt 或伪造 cancel。

### S4 — F11–F12

- compaction terminal/CAS owner 保证同一 operation 只有一个 canonical terminal，late/stale
  result 不再二次改写业务状态。
- pre-start governance 建立 per-Session single-flight；promotion/periodic 只是 coalesced
  signals，live in-flight operation 不被误恢复，fresh owner 才恢复 durable operation。

### S5 — F13

- Engine successful final/outcome 保留同源 typed response identity；Host 将安全 effective
  provider/model、始终存在的 client correlation、provider request id present/unavailable
  状态机械绑定到同一 compaction operation、attempt、proposal manifest 与 accepted output。
- ordinary Run、compactor/repair/multi-attempt identity 不串线；endpoint/credential/header/
  secret/raw provider payload 不进入 durable/public evidence。

### S6 and review fixes

- CLI CI handbook/registry/readiness proof 与 parser inventory 对齐；未把未运行 G 项伪装为
  ready，也未为 removed option 建 accepted scenario。
- aggregate review 修复 non-TTY SIGINT、Ctrl+T/exit-intent、SQLite unique-terminal
  deterministic competition proof与 response validator owner message。
- PR review 修复 compaction result required-field owner duplication；不扩大到既有无关 helper。

## Validation closeout

- owner/affected suites：CLI `605`、Service `13`、recovery `116`、compaction
  `367`、Engine identity `173`、CLI/Service integration `1181 passed / 7 skipped`、Host
  affected `775`。
- full Engine/Host：`2957 passed / 1 skipped / 6 deselected`；六个 clean-base Phase 5
  race 另行分类，不是 regression。
- aggregate fix：`185 passed`，Controller `12 passed`，SQLite competition 连续十次通过。
- PR fix：owner/caller `283 passed`；green Host `2380 passed / 1 skipped / 6 deselected`；
  coverage `86% / 84% / 85%`。
- F10 真实 POSIX owner SIGKILL immediate-reconnect smoke 越过 stale threshold，在同 invocation
  自动恢复并进入明确 terminal。
- F13/行为项 29 完成至少一次真实成功 compactor 调用的脱敏 durable identity smoke；provider
  request id 状态为 present，且与 operation/attempt/manifest/output 同源绑定。这里不记录其值。
- 行为项 30 保留并运行 I0554 的三条 Engine/Host 静态 owner proof：`3 passed`。
- 所有 slice 与最终 fix 的 full pyright 均为
  `0 errors, 0 warnings, 0 informations`；secret、credential、Authorization、provider payload、
  scope 与 diff checks 通过。
- GitHub 当前 reported checks 为 `0`，因此不声称 CI pass。

## Documentation closeout

按职责范围更新：

- architecture truth：`docs/host/design.md`、`docs/engine/design.md`；
- CLI contract/registry：`docs/cli_ci.md`、`docs/cli_ci_scenarios.json`；
- oracle：`docs/cli_ci_oracles.json` 保持 frozen predicate，未机械改写；
- user/developer docs：根 `README.md`、`dayu/README.md`、`dayu/host/README.md`、
  `dayu/engine/README.md`、`tests/README.md`；
- frozen calibration adjudication 仅按其职责同步已裁决状态，没有把 G01–G07 伪装为通过。

## Review and finding closeout

- plan：MiMo/DS 双路独立 planreview 与 re-review 完成。
- S1–S6：每个 slice 均完成 Codex implementation/fix、MiMo/DS 双路 code review、Controller
  adjudication 与所需 re-review。
- aggregate deepreview：`4 fixed / 19 rejected / 0 deferred / 0 unclassified`，双路
  re-review PASS。
- PR review：initial `1 accepted / 3 rejected`；`PR-A01` 已修复；双路 re-review PASS；
  `RE-01` 以 base 直接证据裁决为 pre-existing/out-of-scope。
- 最终没有 accepted pending、deferred、blocking 或 unclassified finding。

## Residual risks and later obligations

- G01–G07 仍未由本 work unit 裁决或关闭；下一阶段必须由后续完整 CLI calibration 在新
  target 上补跑，并由 campaign/report owner 生成正式 scenarios/readiness。
- 行为项 29 **已有可裁决真实证据**；formal renderer target pin 关闭后，后续 calibration
  可将同源 raw evidence 纳入正式裁决，禁止用 workspace config 反推 provider。
- Phase 5 六个 race、五个既有 F401、awaiting entrypoint smoke port drift、calibration harness
  removed-option/target-pin gap 与 RE-01 均已分类为 later/out-of-scope；本 work unit 不创建
  issue、不做无关重构。
- GitHub zero checks 是 external validation gap；local evidence 已完整记录但不替代 CI。
- 当前没有未分类 residual risk。

## User handoff

Draft PR：<https://github.com/noho/dayu-agent-r/pull/190>。

PR 保持 draft，base=`main`，并包含用户指定的原始两个提交 `ae6bb96f`、`cc5c9d57`。
Controller 未 merge、approve、mark ready、request reviewers 或删除 branch。用户审阅并 merge
后，下一入口是启动后续 CLI calibration：更新 renderer target 到 merge 后 commit，完整补跑
G01–G07，裁决/生成正式 scenarios，并复用行为项 29 的真实同源 compactor identity evidence。
