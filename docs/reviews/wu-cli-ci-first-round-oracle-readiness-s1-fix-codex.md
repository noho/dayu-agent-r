# CLI CI 第一轮 Oracle Readiness S1 Code Review Fix

## Artifact Metadata

- Gate：`code review fix`
- Work unit：CLI CI 第一轮 Oracle readiness handbook contract
- Slice：S1
- Review：`docs/reviews/code-review-20260730-102423.md`
- Status：待 re-review

## Finding Fixes

| Finding | 状态 | 修复 |
|---|---|---|
| CR-01 | 已修复 | 新 oracle 只从 effective run/version 参与 pass/fail；当前 calibration observation 只产生 implementation finding |
| CR-02 | 已修复 | 禁止 SQLite 直接读取/重建/展示 Fins 文档与 provider payload；Fins 内容只经 `dayu.fins.storage` public boundary |
| CR-03 | 已修复 | Campaign 未闭环时保留所有 adjudication/registry/readiness/finding 引用 evidence；删除前要求 retained projection 与 refs 迁移 |
| CR-04 | 已修复 | 顶层定位改为 Codex mandatory reference、Claude Code optional |
| CR-05 | 已修复 | 明确当前 execution run 可结束，但 campaign 保持 incomplete/awaiting，next entry point 不得丢失 |

## Validation

- 修复均位于原 semantic owner 段落，没有在 report/schema 下游增加 fallback。
- 未修改生产代码、tests 或 registry JSON。

## Residual Risks

- Readiness validator 尚待后续 implementation work unit。
- Retained projection 的具体存储格式由 harness plan 定义，但删除前置不变量已在 handbook 中固定。
