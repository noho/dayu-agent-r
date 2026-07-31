# AAPL 下载与 canonical ticker 目录计划审查修复

## Gate

- gate：plan review fix
- work unit：AAPL SEC 下载与 canonical ticker 目录
- reviewed artifact：`docs/reviews/plan-review-20260731-142835.md`
- fixed target：`docs/reviews/aapl-download-canonical-ticker-layout-plan.md`
- completion status：待 re-review

## Findings

### PR-01

- decision：accepted
- status：已修复
- fix：SEC primary document 规则改为逐段严格校验；absolute、backslash、空 segment、
  dot/dotdot、double separator 与 trailing separator 全部 fail closed，不再使用“最后一个
  非空组件”语义。
- validation：计划已列出目标 transform path、普通单文件名与全部非法 segment 测试。

### PR-02

- decision：accepted
- status：已修复
- fix：company lookup 的 direct locator 只接收 `try_normalize_ticker(...)` 成功后的
  canonical ticker；公司名/普通 alias 跳过 direct locator，继续走现有 alias index。
- validation：计划已要求 `AAPL`、`aapl.us`、`apple` 与 unknown alias contract 测试，
  并要求九个 read tools 在 canonical ticker 目录上完成。

## Residual risks

- 旧 `portfolio/id-*` ticker workspace 不兼容：assigned to fresh workspace operation。
- 真实嵌套 SEC archive 文件：assigned to later work unit when direct evidence exists。

## Completion status

两个 accepted findings 均已修复；没有 unclassified residual risk，进入 plan re-review。
