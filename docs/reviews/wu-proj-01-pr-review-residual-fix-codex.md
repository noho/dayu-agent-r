# WU-PROJ-01 PR Review Residual Fix - AgentCodex

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review fix
- Date: 2026-06-11
- Agent: AgentCodex
- Artifact path: `docs/reviews/wu-proj-01-pr-review-residual-fix-codex.md`

## Scope

本轮只处理总控裁决接受的 `PR-F1`：`dayu/host/memory_repair.py`
中 `budget=None` 相关 docstring 与生产 dispatch correctness path 不一致。

Allowed files 实际使用：

- `dayu/host/memory_repair.py`
- `docs/reviews/wu-proj-01-pr-review-residual-fix-codex.md`

## First-principles Judgment

问题成立，但属于 LLM-facing / developer-facing 文档语义缺陷，不是 production
behavior 缺陷。直接证据：

- `docs/reviews/wu-proj-01-pr-review-residual-controller-adjudication.md`
  已裁决接受 `PR-F1`。
- `dayu/host/dispatch.py` 的 required catch-up 与 lag rebuild correctness path
  使用 `budget=None`，并由 `_raise_if_memory_projection_target_not_reached(...)`
  校验 required cursor 覆盖。
- `dayu/host/open_host.py` 与 `dayu/host/dispatch.py` 的 opportunistic path
  使用 `MemoryProjectionCatchupBudget` 表达 bounded catch-up。
- 旧 docstring 写成 ``None`` 仅供 close-only / test-only 调用，和上述生产路径冲突。

因此本轮只修正文档语义，不修改循环行为、batch count、source builder caps 或
production dispatch 参数。

## Changes

- 更新 `ConversationMemoryProjectionCatchupPort` 的 `budget` 参数说明：
  `MemoryProjectionCatchupBudget` 表达 bounded opportunistic / diagnostic
  catch-up；``None`` 表示不设置固定批次数或扫描事件总预算。
- 更新 `catch_up_conversation_memory_projection(...)` 的 `budget` 参数说明：
  ``None`` 表示追到目标 cursor、idle 或 failure。
- 同步最小范围更新 `__init__`、`rebuild_conversation_memory_projection(...)`
  和内部 runner docstring，避免 rebuild correctness path 对 ``budget=None`` 的语义再次产生歧义。

## Non-goals

- 不修改 production behavior。
- 不调整 opportunistic batch count。
- 不修改 source builder caps。
- 不处理 `MemoryProjectionRepairPurpose` 单值 enum cleanup。
- 不处理 reactive compact broad exception cleanup。
- 不进入 re-review、commit、push、PR 或 merge gate。

## Docs Decision

触发了 `dayu/host/README.md` 检查规则，已阅读其 Agent 更新约束。此次变更只修正
内部函数 docstring 的参数语义，不改变 Host 已实现的公共契约、架构边界、主要组件、
状态机或关键执行路径，因此 README 不需要更新。

## Validation

已运行并通过：

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py`
  - 结果：`91 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && git diff --check`
  - 结果：通过，无 whitespace error 输出。

## Finding Status

- `PR-F1`: 已修复。docstring 已从 close-only / test-only 旧语义更新为
  production required-cursor correctness path 的真实语义。

## Residual Risks

- `PR-F2` 单值 `MemoryProjectionRepairPurpose` cleanup: deferred-with-owner，
  owner 为后续 memory repair cleanup / WU-PROJ follow-up。
- `PR-F4` reactive compact broad exception cleanup: deferred-with-owner，
  owner 为后续 reactive recovery hardening。
- 本轮无新增 unclassified residual risk。

## Completion Status

实现与验证已完成。按用户要求，本轮停止于 PR review fix gate，未进入
re-review、commit、push、PR 或 merge gate。
