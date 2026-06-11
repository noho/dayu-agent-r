# WU-PROJ-01 Residual Risk User Decision

## 元数据

- Work unit: `WU-PROJ-01`
- 日期: 2026-06-11
- Controller: AgentController
- Draft PR: `https://github.com/noho/dayu-agent-r/pull/136`

## 用户裁决

用户裁决：`WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 都必须在当前 PR #136 中实施，不再 deferred 到后续 Host dispatch test hardening。

## 范围

- `WU-PROJ-01-S3-R1`: 补 dispatch before-worker catch-up happy path 独立集成测试，覆盖 required cursor 已被 projection checkpoint 覆盖时不重复追账且继续构造 ordinary RunInput。
- `WU-PROJ-01-S4-R1`: 稳定 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 的 lane timeout flaky，调整 timing fixture 或测试结构，使其不再依赖脆弱超时。

## Gate 影响

- 之前的 final closeout 不再作为可合并状态。
- 当前 WU 回到 implementation gate，下一入口是 `WU-PROJ-01 residual risk implementation gate via AgentCodex`。
- 两项 residual risk 必须在 PR #136 内关闭，并经过 review / re-review / PR body / control doc 更新后才能重新进入 draft-PR-pass。
