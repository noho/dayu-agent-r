# WU-CLI-PROMPT-01 Plan Review Fix

## Gate

- Work Unit：`WU-CLI-PROMPT-01`
- gate：`plan review -> fix`
- reviewed artifact：`docs/reviews/plan-review-20260731-181253.md`
- fixed target：`docs/reviews/wu-cli-prompt-01-plan-controller.md`
- decision：`ready-for-plan-re-review`
- next entry point：`re-review`

## Finding Adjudication

### PR-001 — accepted / 已修复

直接最小实验已证明 argparse built-in `append/append_const` 在 root/subparser 共用 dest 时会
覆盖 root occurrence。计划已改为 parser-owned 私有 action：对每次 parse 新建的 typed list
执行原地 append，不扫描 raw argv、不使用全局 collector；并新增 root/command 与
root/command/action 三层 owner tests。

### PR-002 — accepted in part / 已修复

接受“原计划只写 import-phase test，未证明后续 startup phases 的 cleanup/副作用”的部分；
计划已明确同一 bootstrap try 同时包围 lazy import 与完整 `main()` 调用，并新增 parser/log、
runtime prepare、Host open、Session ensure、monitor takeover 前的 phase-controlled tests。

拒绝新增全局 signal registry、Host rollback 或 submission-race 机制：用户明确禁止新增事务回滚
和未经确认的 race requirement。用户原始 contract 是不得遗留“半初始化”业务状态；Host 已拥有
事务原子性。Goal artifact 中把该约束误写为任何 Run 前中断都不得存在 Session，现已校正为原始
语义：不遗留半初始化状态、未 accepted Run 不伪造 Host cancel；冻结信号发生在业务提交前时
SQLite 不新增业务记录。

### PR-003 — accepted / 已修复

计划已明确 debug-stream 开启时 namespace/root logger 与 handler 两道前置 level gate 都降至
`STREAM_DEBUG`；关闭时都保持 ordinary threshold。handler filter 再按 exact stream record 或
非 quiet ordinary threshold过滤，quiet 显式拒绝全部 ordinary records。

### PR-004 — accepted / 已修复

新增 S6 README-only slice，把根 README 与 tests README 纳入明确 allowed files、前置更新约束、
内容边界和验证；不扩写 Host/Engine/config/分层文档。

## Validation

- 已重新读取修订位置，确认四项 finding 均有 code-generation-ready decision、allowed files 与
  owner tests。
- `git diff --check` 将在 re-review 前执行。
- 本 fix 只修改 goal/plan artifacts；未修改生产代码、测试或冻结 registry。

## Residual Risks

- custom argparse action 的签名与 strict typing：由 S5 pyright 与三层 parser tests覆盖。
- startup arbitrary transaction interleaving：不新增 rollback；Host 原子性与 frozen exact timing
  evidence 负责证明无半初始化状态，分类为 covered by S3/final validation。
- editable launcher cache、provider availability：保留为 plan 中已分类的 final validation risk。

不存在未分类 residual risk 或 blocking open question。

## Completion

plan review fix 已完成，进入 `re-review`；re-review pass 前不得进入 implementation。
