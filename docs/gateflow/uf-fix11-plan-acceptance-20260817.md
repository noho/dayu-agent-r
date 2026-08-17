# UF-FIX11 plan acceptance

## Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：plan re-review -> implementation
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 状态：`accepted`
- 下一入口：implementation Slice 1

## Controller 裁决

计划已接受，可以进入 implementation。接受依据如下：

1. 两路初审 findings A1-A10 已完成 controller 裁决；A3-A10 已修复，A1/A2 的反例经直接代码证据确认不成立。
2. 第一轮 re-review 中 MiMo 为 `pass`；DS 新提出 DS-RR1/DS-RR2，均有直接 producer/state-machine 证据，controller 接受并要求修订。
3. fix2 已把 SEC/CN failure builder、strict filing parser、显式 `SourceKind` 和真实 workflow roundtrip 放入同一原子 slice，避免 typed failure 退化。
4. fix2 已把 SKIP metadata commit 的 `batch_terminal_started=True` capability 转交顺序写死，并要求 success/commit-failure caller rollback 为 0、commit 前 stage failure rollback 为 1。
5. 最终定向复审中 AgentMiMo 与 AgentDS 均为 `pass`，确认 DS-RR1/DS-RR2 完整关闭，无新 blocker，未引入 material/Host/Engine ownership drift。

## 冻结的实施边界

- Company-name ignored fact 只能由 company-meta commit owner 基于 publication-lock 内 authoritative final state 产生。
- Shared filing publication 是内部 commit outcome 的唯一业务消费者和 public warning 的唯一生产点。
- CLI、direct、durable summary、tool/wait 只能机械投影同一 typed warning，不得重算。
- 合法 alias 在 source skip 时仍通过同一 batch/uniqueness owner 持久化；source assets 保持零 mutation。
- Failed、cancelled、rollback、kill/recovery 未完成态不得产生 ignored warning。
- 不修改 Host、Engine、material、oracle、scenario、registry 或 frozen evidence；不运行真实 CLI calibration；不创建 PR。

## Review 结论

- `docs/reviews/plan-rereview-final-mimo-20260817.md`：`pass`
- `docs/reviews/plan-rereview-final-ds-20260817.md`：`pass`
- Blocking open question：无
- Unclassified residual risk：无

## 下一步

按 accepted plan 的 Slice 1 实现 domain intent、commit outcome、publication-lock storage return contract 与全部 `commit_batch` fake 签名收敛；完成 focused tests、pyright 和 implementation review 后，才进入 Slice 2。
